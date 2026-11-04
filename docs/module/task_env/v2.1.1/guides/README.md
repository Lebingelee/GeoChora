# v2.1.1 指南交付要求

[安装与启动指南](installation-and-start.md)提供已有安装路径、轻量入口与新克隆的依赖边界；本维护版本的 native 启动和完整新安装组合尚未验证，不从本目录推断 selected RGB 已接通。仓库当前无 root packaging metadata，不使用 `pip install -e .`。

## 阶段3前必须补齐的新手路线

本节属于[阶段3前维护要求](../planning/pre-stage3-environment-refactor.md)，随环境重构交付，不等到阶段7。以下为验收清单；部分入口已实现，尚未运行的组合见安装指南。

| 路线 | 必须说明与交付 |
| --- | --- |
| 新克隆后安装 | 从仓库／submodule准备开始，列出所选路线的Python环境、simulator、renderer及资产需求、安装来源与兼容版本；给出最小单环境启动步骤 |
| 复用已有安装 | 明确解释器、SDK根、renderer根、资产／manifest及Core／GeoPhys源码路径如何传入；支持checkout外安装，不依赖复制ignored目录 |
| 启动脚本 | 转调既有examples／公开factory，显式选择provider／backend及可选renderer；复用现有bootstrap和路径配置，错误指出缺哪项，不自动安装或换路线 |
| 基于example开发 | 从已存在的声明式任务example出发，解释UID、资产组合、reset、观测／评价与Solution的修改位置，按规范Env完成reset／step／close与结果检查 |
| 诊断与边界 | 诊断脚本和说明放专用目录，通过正式接口引用模块；说明当前不支持的组合和Pendulum单环境范围，不教用户向Core添加专用探针 |

安装／路径表分别覆盖MuJoCo、GeoPhys、Isaac及rasterizer／Flora；区分所选路线必需项与可选渲染项。其他provider仅标明现有状态与来源，不扩大为本次必须安装的范围。ISAAC解释器不得固定为某一worktree内部路径；Flora复用已有`FLORA_ROOT`／`runtime_root`。Core与GeoPhys的MuJoCo声明区间冲突必须明确说明，不能给出未经核实的混装指令。具体当前缺口见维护方案。

交付导航同时落在根README、`task_env/README.md`及`task_env/doc/index.md`，更新新手与自定义任务指南中的旧构造示例。安装细节以本版指南为权威，其他入口链接它。验收同时检查新安装与外部安装路径的说明、脚本参数、错误提示和真实调用入口；未运行的步骤明确标注，不将文档检查算作native成功。当前不宣称统一Env并行已适配，Pendulum首先提供单环境流程。

## 阶段3–6实现后必须提供的操作路线

1. 查询某任务／资产的能力和拒绝原因，选择三个首批 physics 路线之一，查看解析配置。
2. state-only 构建、reset、step、记录和 close，独立读回同次运行；不要求安装 renderer 才能使用 state-only。
3. 配置窗口观察相机并 render；另配任务相机，采集离屏 RGB，并证明无需额外 render 即从 reset／step 获取同步图像。
4. 同一个public Env通过reset切换已支持 backend／renderer，按任务初始化新 episode，观察旧数据失效和失败后的恢复操作。
5. reset 切换 Controller，读取新的 action spec／space；展示Robot／组件binding、关节／末端参考、direct joint effort及有界BodyWrench组合的语义差别。
6. 在已验证的两个以上后端建立小 batch；展示部分 reset、终止帧、固定动作规格及整批切换。
7. 用 NutAssembly 复用上述公共配置，明确实际支持的子集。

每条指南附实际版本、task/source、设备、所需依赖、已运行入口和限制。相机标定、数组布局、返回设备、buffer 有效期与关闭行为链接权威协议，不复制第二份定义。

## 故障说明应覆盖

能力未实现、依赖不可用、资产不可表达、数值／reset 检查失败、缺少 Controller feedback、原生构建失败、图像过期／采样失败、固定 obs 不兼容、worker 故障及资源回收。给出失败阶段和下一行动；不能建议读取私有状态或关闭必要检查。

新增后端／切换／控制／render／batch示例随阶段3–6的真实实现添加，7a/7c检查调用者可用性；不据此延期前述新手基础交付。本页当前只有交付要求，没有新增运行示例、训练或仿真结果。
