# TaskEnv Daily — 2026-08-10

## 范围

完成 canonical source 路径迁移，复核 f32 contact candidate、Go2 render input、并行渲染 contract 和 Stage 任务边界。

## 核心发现

- 唯一源码位于根目录 `task_env/`；`test/task_env` 不再承载第二份实现。editable/wheel、package-data、import shadowing 和 bootstrap 已按此边界验证。
- f32 contact intermediate 经过数值、Graph/reset、B=1/2/17/32 和大 batch qualification；最终 production 采用固定 topology、active-slot 且通过门禁的路径。
- 并行渲染的窗口、输入、相机布局和 F/Esc 生命周期与 physics/learner 分离；render 不参与仿真频率结论。
- task YAML、RSL action profile 和 device provenance 是公开配置与审计来源。

## 结论与边界

旧兼容 symlink、旧 runtime CLI 和旧 `go2_rsl_ppo.py` 仅保留为历史背景；当前入口以 `rsl_ppo.py` 和 `script/rl/go2/` 为准。headed renderer 只完成接口和生命周期验证，未替代 headless physics benchmark。
