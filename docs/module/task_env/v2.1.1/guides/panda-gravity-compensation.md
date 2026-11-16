# Panda 本体重力补偿（有界实现与验收）

2026-11-06 [003 Sol复审](../maintenance/reviews/20261106_3b_attempt003_sol_review.md)已接收最终限定Panda MuJoCo CPU实现：Nut19的350控制步／3.5 s保持、Nut19与PickCube31各10步正向动作，三份同次H5及1850条子步贡献已独立读回。保持时最大TCP高度偏差约1.42037e-8 m，采样中无目标或力限幅。此项补齐002的最终记录／稳态缺口，不外推任意姿态、载荷、夹爪或后端；较早实验仍保留原身份。

此选项为 selected PickCube 与 NutAssembly 的 MuJoCo CPU、进程内位置伺服路径增加 Panda 本体重力贡献。默认关闭；关闭时沿用原控制语义及动作空间。当前 GeoPhys、Isaac、隔离 worker、混合执行器和固定附件路线不支持开启，显式请求不支持的组合会拒绝，不会静默降级。本实现不表示阶段 4 控制协议已接收。

```python
from task_env import make_env

env = make_env("nut-assembly-outcome-reference-v1", config={
    "execution": {"physics_provider": "mujoco", "physics_backend": "cpu"},
    "controller": {"gravity_compensation": True},
})
```

显式 `False` 与省略开关等价。开启值进入 selected 请求身份及记录配置。计算以来源绑定的 Panda 七连杆、hand 与双指的质量、局部质心、关节与固定变换为输入；独立的桌面、物体、夹持物和接触力不计入。仅固定基座及固定祖先受支持；来源／编译模型物性、拓扑、轴或姿态不匹配，已有 provider 本体重力补偿，以及未声明的施加外力均被拒绝。模型数据不由控制器读取私有 solver 状态。

控制边界使用当前关节位置和手指开度，按实际基座的世界旋转把世界重力变换到基座坐标，再计算各具名臂关节的重力支撑力矩。MuJoCo adapter 仅对经过检查的固定增益、仿射 bias、单关节 transmission、具有位置和力限幅的执行器，将该贡献换算为位置目标偏移。当前夹爪使用一条对称 tendon 和相等位移约束；代码同时计算两个手指的本体重力，如果沿耦合自由度存在无法表示的净重力负载则明确拒绝，不绕过夹爪力限制。此换算依赖具体驱动模型，并非通用的 JointEffort 接口。未修改原外部动作、Solution 或夹爪力限制；没有额外物理步或隐藏 settle。

每次开启时，`info["gravity_compensation_v1"]` 列出已计算力矩、来源与 materialization、reset 和控制边界、世界重力、基座旋转、原／请求／实际位置目标、位置目标限幅，以及每个原生子步的执行器力和限幅标记。执行器力是 provider 内部驱动输出，不是外部力传感器读数，也不等同于单独测得的重力贡献。单独的控制目标和 applied 回执继续保留；持久化轨迹含上述贡献。达到目标或力限幅时不能将该动作视为稳定通过。

对非单位基座旋转的计算包含显式坐标变换与解析／势能数值检查；有限旋转和短闭环测试只证明所测状态。无法保证在关节极限、饱和、接触、负载、模型错误或数值病态下保持目标。实时移动基座、外物载荷补偿、其他 provider 和安全认证不在当前支持范围。原 3b 默认关闭的 N08 历史失败及其门限不因新增选项改变。

维护者提出按运动实体装配树显式选择连通子段，以支持纯机械臂和不同末端装配。该通用选择与跨实体补偿**尚未实现**；其来源、自由度和验证边界见[设计提案](../planning/gravity-compensation-assembly-tree.md)。当前开关不能指定子树，也不能启用其他夹爪或灵巧手。

后续[装配Panda版本用例](../planning/stage4-assembled-panda.md)将消费阶段4公共控制／补偿成果，建议4b稳定后早检查、7a完整集成，排期已由维护者采纳。它用新装配自身模型验证空载TCP跟踪及夹爪／Solution复用，不要求原／新物性相等，也不替代G04 effort／BodyWrench／Controller reset门。当前支持范围不变，新Robot类及其配置仍未实现。
