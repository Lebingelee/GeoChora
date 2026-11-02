# v2.1.0 公共任务 API 收敛

日期：2026-11-02。状态：实施已授权，尚未执行/验收。

## 基线与目标

Sol 已有界接收集成基线 Core 35e0b89a40e47aa17f01915ad25831c53474598f，统一 GeoPhys 为 67da1165149486d3ae3e779c13ce31af49e17d50。复用 codex/v2.1-integration；不改 provider pin、不扩大后端能力、不执行发布操作。

本轮先完成公共构造和配置，再迁移任务。用户编写任务差异，Core 承接 Artifact/Scene/source/引用/控制绑定/身份与运行接入；继续一个生产 Runtime/Recorder。当前实现仍存在 selected/通用配置分叉，本文件描述目标，不声称已完成。

## 已确认范围

- PickCube、NutAssembly 完整迁移；LIBERO 复用 Core 公共构造并保留 benchmark 目录。
- 其他轻量任务兼容过渡；不要求本轮迁完 BaseTaskEnv/batch/learner 调用者。
- make_env 保持主入口；配置优先级为 Core → 任务类 → 任务 YAML → 显式覆盖，解析一次，结果可查询、记录。
- 任务开放的语义参数可覆盖，重新生成受影响身份并校验；不把旧接受转移到新配置。
- PickCube 默认改为 R3 continuous，R1 仅显式选择或历史恢复；公共 R3 配置不依赖 NutAssembly YAML。
- 任务业务文件收敛为 task.py、specialization.py、solution.py、config.yaml，加必要 package/资产文件。
- task.py 本轮基线为 PickCube 663、NutAssembly 686 物理行，至少瘦身 60%（≤265/≤274），同时报告迁出与新增代码，不能只搬运重复实现。历史 F/R 清理 60% 已取消，不恢复该全局门。
- 保留已接受 GeoPhys/USD、官方 Panda/Isaac、F06/NutAssembly/R 路线；physics/render 只开放既有可用组合。
- 活跃 canonical/Generic H5 保留；ReferenceTaskBinding 保持内部。
- Solution 效果、F07、全源等价、Qualification 延后；F06 的 0/9 任务成功不是本轮阻点。

## 施工顺序和最小验收

1. 单页迁移表后立即统一配置和公共编译，不另开长期诊断。
2. 迁移两个任务及 LIBERO/Harness caller；环境可独立于 Solution 构造。
3. 一个使用不同任务/实体语义身份的小任务，通过公共声明和一个已有 CPU 后端真实执行。
4. 改动合同、PickCube 三后端短运行、NutAssembly 受影响路线、LIBERO 代表性短运行；不重跑九例 Expert、全部 A123 和 GP01–GP08。
5. 更新 API/examples/Skill，提交并交 Sol 复核。

当前关键 owner：registry.make_env；environment.configuration；environment.task_definition/task_source；assembly.compiler；tasks.reference_env；controllers.canonical。不新增平行 factory/生命周期。

## 执行编排

- Goal：V210_PUBLIC_TASK_API_REFACTOR_20261102_001，attempt001。
- 预期主动工作 4–6 小时，上限 8 小时含提交交接。
- 冻结包标识：sol_v210_task_api_refactor_20261102_001；完整本地路径与 prompt SHA 由维护者交接，原始执行包保持 ignored。
- 执行输入 HEAD 以包内 input_snapshot.json 为准；本文件的规划提交不改变生产实现。
- 一个 writer/native worker；维护者手动转交，未自动创建 Goal/派发消息。
- 同根因重复失败且无新修复假设时询问；不以无限诊断延长窗口。
- 当前输出/验收：未执行。后续由 Luna 更新实施结果，Sol 独立复核。
- 文件级许可/署名仍未解决；集成接受不改变发布前置或旧证据边界。
