# G04/4b attempt002：Sol 独立主审

## 决定

`ACCEPTED_BOUNDED_4B_PHYSICAL_CONTROL`：按原 4b 的明确 source、provider、Controller 和代表外力交集有界接收；普通 attempt count=2。001 的代码及分层真实结果，加上 002 的实际路径变化分析、限幅负例和文档修正，足以关闭 001 主审指出的证据关联问题。没有根据文件整体 hash 变化要求重新运行全部物理实验。

接收的是真实三后端 Panda 7＋2 direct effort 的限定配置、共同 typed 命令、joint/R3 reference 及 MuJoCo 自由体／Robot hand 外力代表，具体为 001 的真实运行及 002 逐路径有界关联；不外推所有 source、所有 drive 状态、逐关节独立实测力、真实三后端 BodyWrench、任务成功或正式 Qualification。4c 的同一 Env Controller／动作规格切换与迁移后 PickCube 成功仍未运行；physical active Recorder 在现有代码中未准入，须在 4c 实际记录路径解决或有符合原门的方案。

## 独立核对

- Core 分支 `codex/v211-stage4`，002 输入 `4d60ac8edee84ada4c250e87137fb07e32d74ab3`、输出 `168db6410a1c2721aeefa8160d9c32c7664b8cf5`；从 001 的 `a7181de4` 到 002 没有生产代码改动。GeoPhys pin `dc2685e28c6c916fb6403a2342c04e0d2520aef7` 和 Menagerie pin `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` 保持，三项保护输入 SHA 不变，002 writer／双锁和 native 已释放。
- 002 清单自身 SHA 与记录一致，**18/18** 文件／symlink 与摘要匹配；独立检查 `edit-history.jsonl` 所引用的主要编辑条目 ID 与实施会话真实记录对应，并抽查 `560/598` 自由体绑定、`1394/1396` GeoPhys drive 分支、`1427/1712` direct 默认分支以及 `1472/1519` Isaac 接触观测变化。001 的 **5409/5409** 清单和 Sol 的 **55 项 guarded pure** 结果复用；002 补充 limit 的独立受 guard 纯测试 5 参数通过，不能冒称实测饱和。本主审未启动 source、provider、native 或 GPU。
- MuJoCo hand 运行时 port 与 `c1115694` 文件字节一致，随后变化新增对另一 no-drive Artifact 的 drive 分支；profile 与场景绑定变化由编辑记录和最终 source fixture 检查关联。自由体另按自己的 fixture/source、floating joint 绑定改变、最终 source30 构造与旧真实 impulse 对照综合判断；不声称最终字节版本重新跑过该 impulse。MuJoCo／GeoPhys 原逐输入结果对应 coexist 路线，后续无 drive 和 reference 的条件分支不进入该原条件；最终 reference 运行只补充它实际覆盖的路径。
- Isaac `isaac13/15` 是已隔离 drive 的 8 输入正负方向对照；后续 cube 接触 reporter 变更**确实进入**相同 Artifact 路径。它新增观测及检查，并非对旧 run 不可见；结合未改的 direct writer、`isaac18` 接触阳性检查及最终相同 source/no-drive effort owner 的 `isaac24/25` 真实运行，对原逐输入结果作有界关联。最终源码的每个基向量并未被声称重跑；coexist drive 的 `isaac09/11` 方向失败仍保留。若未来修改接触路径或扩展声明，按实际影响重新验证。
- 002 的 API 和现有 TaskEnv Skill 改动准确区分 4a 历史和 4b 候选；两个文件均为文档或 Skill，无物理实现变化。文档 current 校验无当前错误，96 项既有历史链接问题保留；Skill 静态检查通过。002 账本 source/native/物理子步/GPU 均为 0。

## 延续限制

参考 Controller 的 source-bound 固定质量模型、初态邻域、特定 cadence 和已隔离 drive 不构成全姿态动力学模型。原始 Isaac 失败、接触无效、`get_stage_state` 关闭异常、001 私有字段搜索越界记录保留；有 owner 关闭回执和退出码 0 不代表无异常。GeoPhys `hold_reapply` 独立声明仍拒绝；BodyWrench 的真实代表仅 MuJoCo，ACK 不是独立测力。3b 原 N08 失败、6.1 关闭超时、通用装配补偿未实现等既有边界不变。装配 Panda 为版本附加用例，不代替或扩大 4c 原出口。
