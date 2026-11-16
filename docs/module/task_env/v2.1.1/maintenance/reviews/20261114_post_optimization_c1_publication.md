# C1：Env 发布与 reset 边界

输入 `7f9d1091`，当前阶段分支；本记录对应其后 C1 本地改动，不改变 E00～E16 已接收结论。无第二生命周期、推进、source 或相机 owner。

- Env 构造和 reset 退休共用 `_clear_position_publication`；reset、physical step、position step 和 physical sequence 的位置边界共用 `_publish_position_boundary`。实际生产读取为 state（故障前状态、停止及专家边界）、typed state（绑定／generation／render）、evaluation（停止事实）。之前的 obs/info 快照没有生产读取者，已删除；info 的返回／记录流程不依赖它们。
- reset 在当前 binding 准备阶段确定任务事实。正式配置直接提供 task UID 和成功定义，不查询 recipe；typed 输入保留原来的 source／recipe／Artifact 回退及缺失拒绝。Nut 配置成功定义与 Artifact 内部语义名不同，不能把 Artifact 当作所有正式任务的唯一替代。
- reset 事务仍依次 preflight、退休旧边界、关闭／重建、reset、读取、观察、提交；sampled 路线在外层追加的 seed、reset 参数和 episode 元数据具有不同所有者／时点，未机械合并。预检保留 RNG，重建失败保留旧 runtime owner 清理；新旧 source lease 和重复关闭仍走已有 owner。
- 延迟 RGB 仅在 reset 物理提交后创建新的 observation/info 映射；它不再维护无人读取的第二份快照。捕获失败通过原 `on_failure` 标识提交后阶段，不重新执行 reset。图像身份／generation 的原验证未删除。

## 验证及边界

- 正式 pure guard `geochora/bin/python -B task_env/diagnostics/tasks/v2.1.1/run_pure_checks.py`：**245 passed**。新增测试实际调用 sequence 的发布 hook，并用 fake 验证采集失败不会重新 reset；sequence 的准入及 native 推进并未由该 fake 证明。原 reset owner 测试的 SimpleNamespace 增加当前方法，reset-switch 定向测试修正退休的 controller 配置，RGB 顺序 fixture 补当前 binding。
- 受 guard 的 sequence／RGB 顺序定向检查 **7 passed**；真实 source、禁止 native SDK 导入的 reset preflight／materialization／partial reset 失败检查 **3 passed**。首次系统 Python 3.14 因缺 NumPy 收集失败；更换既有 `geochora` 环境。首次定向混合检查有 5 个旧配置失败；所需的三个 reset 节点已修 fixture 重测，另外两个旧 caller 未作为通过证据。
- [最终 CPU 计划与结果](../../../../../../workspace/maintenance/v211_c1_publication_20261114_003/plan.json)：共享锁内 MuJoCo 3.8.1，Pendulum、TwoWheel、PickCube R3、Nut 各自 reset→一次非零 step→reset→重复 close，四条 PASS；显式子步依次 25、25、5、5。观察空间、schema 及配置任务 UID／成功定义检查通过。锁、输入源码哈希、内存／子步和超时记录在计划，非全 Solution。
- [四条独立短程记录及 reader 结果](../../../../../../workspace/maintenance/v211_c1_publication_20261114_004/readback.json)：各一条转换、两个边界；Pendulum／TwoWheel 为 physical v3，PickCube／Nut 分别用 canonical trajectory／execution reader。核对任务名或 Artifact／seed 一致性。`external_stop`、任务成功、Solution completion 与 close 是不同事实，不把记录完成当作 Solution 完成。首次 readback 脚本误将 execution reader 的 dict 当成对象，修正后四条均通过。
- 两次 native sequence 候选分别在 Pendulum 的 direct-feedback 和 Panda joint Controller 类型准入拒绝，均 **0 子步**；不得报告 native sequence 通过。sequence 的 bound-position publication 分支仅有上述 fake 证据。未重跑 GeoPhys／Isaac、完整 Solution 或渲染窗口；适用旧路线证据保留原源码身份和边界，C5 按最终共同链影响复验。

## 度量与账本回看

生产三个受影响文件合计 `+47/-49/net -2`；其中任务身份约 19 行从 Env 移至既有 binding，属迁移而非删除。`reference_env.py` 4,277→4,254 行，reset 函数 592→570 行；physical、position 和 reference step 分别 301→298、184→180、322→322 行。完整边界写入由四处收敛至一个 Env 方法，清空由两处收敛至一个方法；调用仍需一次方法跳转，未新增状态镜像。受影响的诊断／probe 为既有文件 `+11/-3`，新增测试 73 行；文档为本记录。最终文件和全部类别总数以提交 diff 为准，不能把移动误报为整体删减。

回看原总账 ENV-01／02／04／05、OBS-01 和 REC-02：本次仅收敛已存在的发布／reset 身份位置，并未改 observation 声明、source、Recorder 或 provenance owner；其历史有界接收不重开。当前四保护输入字节和两个 submodule pins 与 E14 基线一致。冻结 archive、既有接收例外和历史记录保留；未清理目录／refs、merge、push、tag、发布或启动 G06。C2～C5 仍未完成。
