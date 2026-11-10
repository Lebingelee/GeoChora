# 作用：修复固定Windows后端在大邻接表卸载特征后丢失惰性通道维度的问题。
# 接口：patch_sparse_shape() 在生成和独立贴图进程中应用同一最小兼容补丁。
import inspect
import os
import textwrap


def patch_trellis_windows_runtime():
    """为 Windows 的 flex_gemm 选择可用实现并补齐缺失的加权求和。"""
    if os.name != 'nt':
        return
    import torch
    import flex_gemm.ops.spconv as spconv
    from flex_gemm.ops.spconv import Algorithm
    spconv.ALGORITHM = Algorithm.EXPLICIT_GEMM
    import flex_gemm.kernels as kernels
    if hasattr(kernels, 'triton'):
        return

    class TritonFallback:
        """以常规 Torch 张量运算替代缺失的 Triton 内核。"""
        @staticmethod
        def indice_weighed_sum_fwd(feats, indices, weights):
            """计算稀疏邻域的加权特征和。"""
            index = indices.long().clamp(min=0, max=feats.shape[0] - 1)
            result = torch.zeros((len(index), feats.shape[-1]), dtype=feats.dtype, device=feats.device)
            for column in range(index.shape[1]):
                result += feats[index[:, column]] * weights[:, column].unsqueeze(-1)
            return result

        @staticmethod
        def indice_weighed_sum_bwd_input(grad_output, indices, weights, count):
            """计算上述加权和对输入特征的梯度。"""
            index = indices.long().clamp(min=0, max=count - 1)
            channels = grad_output.shape[-1]
            weighted = grad_output.unsqueeze(1) * weights.unsqueeze(-1)
            result = torch.zeros(count, channels, device=grad_output.device, dtype=grad_output.dtype)
            result.scatter_add_(0, index.reshape(-1, 1).expand(-1, channels), weighted.reshape(-1, channels))
            return result

    kernels.triton = TritonFallback()


def patch_sparse_shape():
    """在清空特征前固定五维卷积形状，保持原邻接及数值计算不变。"""
    from trellis2.modules.sparse.conv import conv_flex_gemm
    original = conv_flex_gemm.sparse_conv3d_forward
    if getattr(original, '_asset_shape_fixed', False):
        return
    source = textwrap.dedent(inspect.getsource(original))
    marker = '    N = x.feats.shape[0]'
    shape = 'torch.Size([*x.shape, *x.spatial_shape])'
    # 固定官方源码未卸载输入特征，无需原开发版本的形状修复。
    if marker not in source and source.count(shape) == 1:
        return
    if os.name != 'nt':
        from flex_gemm.ops.spconv.submanifold_conv3d import SubMConv3dFunction
        if 'needs_grad' in inspect.signature(SubMConv3dFunction._compute_neighbor_cache).parameters:
            argument = '                self.dilation\n'
            if source.count(argument) != 2:
                raise RuntimeError('固定后端邻接缓存调用已改变，请重新核对 Linux 接口适配')
            source = source.replace(argument, '                self.dilation,\n                needs_grad=False\n')
    if marker not in source or source.count(shape) != 2:
        raise RuntimeError('固定后端卷积实现已改变，请重新核对形状补丁')
    source = source.replace(shape, 'input_shape').replace(marker, marker + '\n    input_shape = torch.Size([*x.shape, *x.spatial_shape])', 1)
    namespace = dict(vars(conv_flex_gemm))
    exec(compile(source, '<asset_sparse_shape_compatibility>', 'exec'), namespace)
    replacement = namespace['sparse_conv3d_forward']
    replacement._asset_shape_fixed = True
    conv_flex_gemm.sparse_conv3d_forward = replacement
