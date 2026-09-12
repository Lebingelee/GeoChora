# Public contracts

**Import path**：`task_env.environment`  
**任务域**：Appendix  
**稳定性**：Public API  
**职责**：定义 action、observation、metadata 与 snapshot 的跨层数据 contract。  
**调用者/消费者**：env、adapter、task definition、recorder。  
**源码**：`environment/types.py`、`metadata.py`

`ExternalActionContract.for_mode(mode)` 返回三种源码支持 mode 的 action contract；不支持 mode 抛 `ValueError`。`ControlCommand`/`AppliedControl` 表示控制请求与实际应用结果；其中 external/universal action 是公开层，actuator ctrl 仅为 runtime 细节。

`ObservationFieldSpec`、`ObservationSchema` 描述 observation field；`freeze_observation` 冻结 observation tree。`TaskEnvMetadata`、`CameraMetadata` 和 `RenderObservation` 承载 metadata/render contract。`RuntimeSnapshot` 的数组在构造后复制为 readonly；需要什么字段由 `SnapshotRequest` 的布尔字段明确请求，源码未声明的 shape/dtype 不应补写。
