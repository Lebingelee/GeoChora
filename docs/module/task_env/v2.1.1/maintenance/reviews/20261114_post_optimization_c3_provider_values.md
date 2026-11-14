# C3：provider 共同值与原生边界

输入 `77ef9ad1`。本单元只合并 mixed RuntimeSession 进度收据中已有的共同值；不改 provider 能力、Scene、Controller、相机或物理推进。原 E00～E16 有界接收与例外不重开。

| 计划项 | 实际核对及处置 |
| --- | --- |
| C3.1 | MuJoCo／GeoPhys 都通过 `_SessionValues` 拥有 materialization、episode、reset、control step、revision、source 和 plan 身份。将两份相同投影收敛到该 owner 的 `_mixed_runtime_progress_values`。调用仍先拒绝未准入 mixed 路线；GeoPhys 仍调用自身 snapshot 读取时间；MuJoCo 仍从自身 data／reset origin 读取时间，并单独提供 preprocess、forward 和 monitor。没有统一取整、补零或第二组计数。worker transport 暴露该 property；已有 LIBERO 历史 consumer 按字段读取，不以此宣称其退役 Env 入口可用。 |
| C3.2 | MuJoCo mixed 初始化的 native joint/actuator 类型、gear、gain、bias、range、source 和 timebase 检查各对应不同读回；fingerprint 的对象名、维度和 numeric array hash 也是按当前 model 独立读取与缓存。未发现可以删除而不损失 witness 的重复，保留原实现。 |
| C3.3 | 三个 physical adapter 中短小的 binding/receipt 外观相近，但写入、buffer、gear、drive、held-load 支持及 native 映射不同。强制公共基类或仅搬运短方法会增加跳转并扩大 native 验证范围，故保留；没有新增计数器或能力猜测。 |
| C3.4 | Isaac `_open_public_runtime` 为 754 行同一 App/stage/context/view 资源事务；CUDA/PhysX、verified snapshot 和异常清理属于真实准入／所有权。没有找到可同时减少实际重复和私有状态穿透的抽取，原样保留；未启动 Isaac App。 |

## 验证

- 正式 pure/fake guard **261 passed**。新 provider-free 测试检查两 provider 的完整共同键、各自时间来源、MuJoCo 独有字段及 monitor 返回副本、计数变化和未准入时在 snapshot 前拒绝。首次测试把 property 误当函数导致 1 failed／260 passed；修正测试后重跑全绿。
- [最终 native 计划](../../../../../../workspace/maintenance/v211_c3_mixed_progress_20261114_003/plan.json)在当前共享锁内分别用 MuJoCo CPU、GeoPhys CPU 实例化 source-bound mixed RuntimeSession，绑定 Controller、reset、提交一次 named mixed command、推进 2 显式子步、读取前后进度并 close。两条均 **PASS**，boundary 0→1、native steps 0→2、native time 0→0.004 s，source 和锁均关闭／释放；原始 [MuJoCo](../../../../../../workspace/maintenance/v211_c3_mixed_progress_20261114_003/mujoco/result.json) 与 [GeoPhys](../../../../../../workspace/maintenance/v211_c3_mixed_progress_20261114_003/geophys/result.json) 分开保存。此为合成 source 的最短 RuntimeSession 验证，不是正式任务、完整 Solution 或资格。GeoPhys 用独立 no-contact Artifact，MuJoCo 保留其 contact 声明。
- 诊断仅复用旧 fixture 构造 source/sample；通过局部测试注入取得声明后，实际 materialize、Controller binding、reset、提交、推进、progress 和 close 均走当前 RuntimeSession owner，不恢复退役 Env factory。旧 fixture 同轴关节会造成原生奇异，最终运行使用不同轴的**新** source receipt；不改原 fixture 或旧结果。
- [首轮](../../../../../../workspace/maintenance/v211_c3_mixed_progress_20261114_001/plan.json)：MuJoCo 因诊断未绑定 Controller 拒绝 target，GeoPhys 因请求未支持的 geom-pair contact 在物化前拒绝。 [第二轮](../../../../../../workspace/maintenance/v211_c3_mixed_progress_20261114_002/plan.json)：MuJoCo 合成模型出现数值不稳定，被原 physical monitor 拒绝；GeoPhys 旧 fixture 的字符串对象在物化阶段被拒绝。失败及关闭收据均保留；第三轮使用不同轴和有效 scene 组件，不放宽 admission 或 monitor。

## 度量与账本回看

生产三个文件 `+25/-31/net -6`：common 945→961 行，MuJoCo 2,498→2,488 行，GeoPhys 1,600→1,588 行。共同身份／计数字段原两处各维护一组，现一处；每次读取增加一次 `_SessionValues` 方法跳转，provider 时钟和额外字段仍各在一处。共同字段是迁移，不能将 16 行新增归为删除。版本 diagnostics 新增测试 58 行、probe 138 行及 launcher 1 行，记录为验证开销，不计入生产精简。

回看 RUN-01～04、SRC-04、TEST-03：本次只更改 mixed progress 值封装，独立 native 时钟、source identity、native readback 和拒绝语义保留；其他 provider/source 的已有证据按其原身份复用。四保护输入及两项 pins 与 E14 基线一致；冻结 archive 与已接收例外保留。未清理目录／refs、merge、push、tag、发布或启动 G06。C4、C5 和最终完整 Solution／独立复核尚未完成。
