# G05 5b attempt003：Sol 可移交前置工作

2026-11-07，维护者已同意[第三次前重评](stage5-5b-attempt003-reassessment.md)中的 GeoPhys provider/public API、主题分支、本地提交、Core gitlink 和预算提议。此项授权只在完整工作包经维护者手动转发给指定实施者后执行；准备不消耗 attempt。Sol 无 source 解析、SDK、native、GPU、GUI，也不实现待审的生产路径。

## 提前定位的实现边界

1. **GeoPhys Core 接线不仅是 camera setter。** `task_env/render/camera/api.py::admit_dynamic_camera` 当前动态 profile 只接 MuJoCo renderer；`create_dynamic_camera_session` 直接实例化 MuJoCo session。`reference_env.py::_configure_selected_observer` 非 Isaac 分支的 backend 标签目前是 `mujoco-native-opengl`；`_capture_selected_observer` 走 `bind_visual_state`。旧 `task_env/render/camera/geophys.py::GeoPhysCameraSession` 使用独立静态 mesh、简化光照，不是已满足 PickCube 真实完整场景的 selected 生产入口。应在现有 Env/provider/session owner 中接 admitted GeoPhys 真实 source、状态、camera 和输出；不能仅为 clip setter 写测试或把旧静态路线当作完成。
2. **Raster 远裁剪有共享实现风险。** GeoPhys `raster_camera.py::world_to_clip` 是 infinite-far 投影；`geometry.py` 的确定性 owner 假定每源三角形最多两个近平面子图元，`native_visibility.py` 的 draw/打包亦硬编码两个，`punctual_shadow.py` 还调用部分相同 helper。一个三角形同时跨 near/far 可能裁成五边形、需要三角扇的三个三角形；简单扩展同一 helper 或只调整 camera 投影，不能自动保证 owner、原生 visibility、alpha 与阴影正确。可研究在最终每片元参与 owner/depth/alpha 前按 optical-Z 排除 far 外片元，以保留近平面拆分；但必须核实 compute 和所选 native visibility、透明、admitted representation、深度遮挡与所有调用路径的一致性。不能仅在最终 RGB 上遮图。若实际路线不可行，明确停用不支持组合或转用 raytracer，不假定两者成本。
3. **Ray 备选也需真实最小范围裁剪。** `raytracer/mesh_pipeline.py` 已有 `trace_after` 和接收 `t_min` 的交点路径，`engine.py` 同时存在 trace_pixels、native-ray 和普通 trace 等入口；它们不是现成的完整 near/far 公开能力。光轴 near/far 与斜射线的距离要按方向转换；必须在最近可见交点与透明/遮挡前应用，并核对 ground、所准入表示及采样路径。不依据名字宣称无缝修复。
4. **复用现成回归入口。** `GeoPhys/test/verification/rendering/raster_r1_correctness_smoke.py` 已有 near、遮挡与透视校正相关 oracle；`render_material_r5_oracle.py` 具有材质/alpha 层参考。它们的真实执行与新增 far 代表 case 属执行者预算内，Sol 未运行。仅选择受修改路径影响的 case，遵循 GeoPhys test catalog，不重跑全部历史矩阵。

## 已准备的离线辅助件

`/home/lly/Documents/ChatGPT/GeoChora v2.1.1/handoffs/V211_G05_5b_sol_prework_001/` 提供：

- `slab_oracle.py`：纯 Python camera-local +Z、米单位、双裁剪面多边形参考及独立射线求交；`test_slab_oracle.py` 验证两面交叉得到五边形/三个子图元、光轴深度与射线距离区别、网格上光线与多边形独立一致、非法范围拒绝。只有合成几何，没有源资产或 native 调用；使用时需按最终真实配置将坐标转换到同一 convention，处理边界像素容差，并和实际 renderer 原始数据关联，不单独宣称产品通过。
- `substep_budget.py`：纯 Python、跨运行累计的保守预约台账；在可产生 physics 的 worker 启动前记入经过证明的 warmup/step 最大值，中断不退款，超过上限拒绝。`test_substep_budget.py` 检查累计超额、失败预算不回收、重复 ID 和无效输入。该工具**不截获 physics 调用，也不能证明实际 worker 遵守预约**；实施者必须对初始化、App update、控制步骤及子进程设硬上界并留可审计证据，不可证明上界时不能运行。其文件锁只保护自己的本地 ledger，与两把原有 native 锁无关，不替代它们。
- `PYTHONDONTWRITEBYTECODE=1 python -B -m unittest -v test_slab_oracle test_substep_budget`：Sol 在上述目录执行，**7 passed**；这只是工具的合成自检，不是 provider 测试或能力验收。

002 的 `run_locked.py` 有可参考的锁序、进程组、CPU affinity、RSS/GPU 采样，但只记录运行时段，并未解决累计 physics 计数；它的 GPU 指标是全卡变化，不证明特定进程 VRAM 峰值。实施者可借鉴而不得照搬为已满足全部预算；必须按新包补全可执行上界和采样局限，超限安全结束自己的进程和资源。

## 待实施者完成

核验调用链并选定一条 provider 路线，落地真实能力；对原三条路线的窗口和离屏分别完成有独立证据的原 5b 出口；针对颜色和 Isaac 发布影响做必要定向核验，保留 002 中未改变范围的证据。当前前置材料没有证明任何 native 或生产路径通过，也不改变 002 结论。不得自动 5c、阶段6、push/merge/tag/发布。
