# v2.1.1 指南交付要求

当前阶段尚无本版可运行 quickstart；安装和现有命令参照 [v2.1.0 installation](../../v2.1.0/guides/installation.md)及[quickstart](../../v2.1.0/guides/quickstart.md)，不从本目录推断 selected RGB 已接通。仓库当前无 root packaging metadata，不使用 `pip install -e .`。

## 实现后必须提供的操作路线

1. 查询某任务／资产的能力和拒绝原因，选择三个首批 physics 路线之一，查看解析配置。
2. state-only 构建、reset、step、记录和 close，独立读回同次运行；不要求安装 renderer 才能使用 state-only。
3. 配置窗口观察相机并 render；另配任务相机，采集离屏 RGB，并证明无需额外 render 即从 reset／step 获取同步图像。
4. reset 切换已支持 backend／renderer，按任务初始化新 episode，观察旧数据失效和失败后的恢复操作。
5. reset 切换 Controller，读取新的 action spec／space；展示关节／末端参考及 direct effort 输入的语义差别。
6. 在已验证的两个以上后端建立小 batch；展示部分 reset、终止帧、固定动作规格及整批切换。
7. 用 NutAssembly 复用上述公共配置，明确实际支持的子集。

每条指南附实际版本、task/source、设备、所需依赖、已运行入口和限制。相机标定、数组布局、返回设备、buffer 有效期与关闭行为链接权威协议，不复制第二份定义。

## 故障说明应覆盖

能力未实现、依赖不可用、资产不可表达、数值／reset 检查失败、缺少 Controller feedback、原生构建失败、图像过期／采样失败、固定 obs 不兼容、worker 故障及资源回收。给出失败阶段和下一行动；不能建议读取私有状态或关闭必要检查。

示例和指南随阶段 3–6 的真实实现添加，7a/7c 检查调用者可用性。本次只有交付要求，没有运行示例、训练或仿真结果。
