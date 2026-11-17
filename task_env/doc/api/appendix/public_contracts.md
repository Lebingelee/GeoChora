# Public contracts

**Import path**：`task_env.environment`  
**任务域**：Appendix  
**稳定性**：按各数据类型的消费者使用；导出本身不保证适用于所有环境
**职责**：定义 action、observation、metadata 与 snapshot 的跨层数据 contract。  
**调用者/消费者**：env、adapter、task definition、recorder。  
**源码**：`environment/types.py`、`metadata.py`

`ExternalActionContract.for_mode(mode)` 返回三种源码支持 mode 的 action contract；不支持 mode 抛 `ValueError`。`ControlCommand`/`AppliedControl` 表示控制请求与实际应用结果；其中 external/universal action 是公开层，actuator ctrl 仅为 runtime 细节。

`ObservationFieldSpec`、`ObservationSchema` 描述 observation field；`freeze_observation` 冻结 observation tree。`TaskEnvMetadata`、`CameraMetadata` 和 `RenderObservation` 承载 metadata/render contract。`RuntimeSnapshot` 的数组在构造后复制为 readonly；需要什么字段由 `SnapshotRequest` 的布尔字段明确请求，源码未声明的 shape/dtype 不应补写。

上述 `RuntimeSnapshot` 和 `ControlCommand` 是当前 classic 环境与 RuntimeBoundary 的契约；selected 路线使用其 Artifact、RuntimeSession 和相应的 canonical/structured control 契约，不能以一个类型或 Panda action shape 推断所有任务。实际入口和两条生命周期的状态见[环境接口](../semantics/task_environment.md)。

## Selected 数据在各层的位置

`TaskArtifact` 描述任务语义、实体、初始化和 timebase；Robot recipe 描述具名主体、frame、joint 和 writer；source composition 将二者绑定到实际来源。`RequestedAction` 是 Controller 解释过的动作请求，`CanonicalControlTarget` 是目标，`AppliedCanonicalControl` 是 provider 对目标的应用回执；三者不是同一份 native 数组。任务状态按语义名称访问，snapshot 的 boundary 和 sample clock 绑定 episode、source 和推进时刻；旧边界不能用于新 reset。类型和实现位于 [artifacts](../../../artifacts)、[canonical Controller contracts](../../../controllers/canonical/contracts.py) 和 [environment](../../../environment)。

例如 Nut/PickCube 的 reference pose 是长度 8、有限的 `float64` 输入：world xyz 使用米，旋转使用 wxyz 四元数，末项是夹爪标量。零范数四元数、错误 shape 和 NaN 被拒绝；其他任务和 physical Controller 可采用不同 schema、dtype 或 device。观测树的 shape、dtype 和复制寿命应从实际空间与[观测契约](observation_and_rendering.md)读取，不能从某个 Robot 推断全部任务。

下面通过公开入口读取实际 schema，再提交当前 pose；不需要直接构造内部 contract：

```python
import numpy as np
from task_env import make_env

env = make_env('nut-assembly-outcome-reference-v1', config={
    'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu', 'deployment': 'in_process'},
    'episode': {'horizon': 10},
})
try:
    obs, info = env.reset(seed=19)
    print(env.metadata['action_schema'], env.action_space)
    pose = env.state.pose_world['panda-v1/ee']
    action = np.asarray([*pose.position, *pose.quaternion_wxyz, 1.], dtype=np.float64)
    obs, reward, terminated, truncated, info = env.step(action)
finally:
    env.close()
```

7c002 已验证同类 MuJoCo 普通 pose 的实际推进和关闭；此代码块本身尚未单独运行。返回的五元组区分任务评估与生命周期；普通动作不意味着 Solution 完成。支持范围和字段的唯一当前规范见[版本 API](../../../../docs/module/task_env/v2.1.1/api/README.md)与[能力矩阵](../../../../docs/module/task_env/v2.1.1/capabilities/capability-matrix.json)。
