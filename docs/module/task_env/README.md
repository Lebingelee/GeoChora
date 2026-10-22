# TaskEnv

`task_env/` 是 GeoChora Core 唯一实现，负责 task/environment lifecycle、provider admission、
controller/observation、录制与学习/渲染接入边界。当前发布基线是
[v1.1.0](../../releases/v1.1/README.md)，其 bounded acceptance 不等于新的正式 qualification。

| 阅读任务 | 当前文档 |
| --- | --- |
| 构造任务、public imports、配置分支与失败行为 | [public-api](public-api.md) |
| 冻结任务、Experiment、randomization、Evidence/Judge | [task-artifact](task-artifact.md) |
| runtime/state/timebase、controller、Expert lifecycle、providers | [runtime-and-providers](runtime-and-providers.md) |
| recorder/H5/replay、learning、rendering | [recording-and-learning](recording-and-learning.md) |
| 唯一能力矩阵、测试/验收 gate 与历史审批 | [qualification](qualification.md) |
| 首个失败边界、重试/恢复与升级 | [troubleshooting](troubleshooting.md) |

## 快速开始

从仓库根目录执行。已发布环境记录为 Ubuntu 24.04.4/x86_64/Python 3.12.14；
没有根 packaging metadata，不使用 `pip install .` 或 editable installation。

```bash
git submodule update --init GeoPhys asset/external/mujoco_menagerie
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r task_env/requirements.txt
export PYTHONPATH=GeoPhys/src:.
python - <<'PYTHON'
from task_env import make_env
env = make_env("pendulum-v1", config={"runtime": {"backend": "cpu"}})
try:
    observation, info = env.reset(seed=73)
    observation, reward, terminated, truncated, info = env.step(env.action_space.sample())
finally:
    env.close()
PYTHON
```

注意：v1.1.0 的 `single_inline` Pendulum 一步路线已复现 `env.binding` AttributeError；
上面的 public API 路线不经过该 CLI helper，详见[troubleshooting](troubleshooting.md#已复现的-cli-缺陷)。

只在学习流程需要时安装 `task_env/requirements-rl.txt`。本轮不重新安装依赖；requirements
不是已验证的 lockfile。冻结发布可用 `git checkout --detach refs/tags/v1.1.0`；开发应基于当前 develop。
v1.1.0 的 GeoPhys Gitlink 为 `c665ce5028a12bb4d2afe49f05e015fa9b684a39`；2026-10-20 的
`54f40fbfffd945967525aa85801087e7da0b491e` 同步记录是历史开发基线，见
[依赖同步记录](runtime-and-providers.md#geophys-开发基线同步2026-10-20)。2026-10-22 的 Phase II 实现与验收记录已保全到 `a5ba537`，整理后由 develop 承载；维护者于 2026-10-23 已接受 Phase II 的有界工程范围并冻结，见 [正式范围决定](../../maintenance/phase_ii_scope_freeze_20261023/maintainer_scope_decision.yaml)。发布和 Formal Qualification 仍独立。
GeoPhys Gitlink 与检出固定为
`a53a8cfed7c9d6464274b5c96fca601271dc4ee4`。指定 legacy PickCube external Solution 在 GeoPhys CPU 与 MuJoCo 3.8.1 CPU
的 S2/S3 通过有独立收据；C02b 的声明交集工程出口已满足，其他任务/Provider、Qualification 与发布接受范围仍单列。
Phase II 九份文档的统一状态见[当前审阅与 Goal 处置表](goal/Phase_II/05_Architecture_Review_and_Execution_Order.md)。详见[当前开发基线与有界证据](runtime-and-providers.md#当前开发基线与有界证据2026-10-22)与
[C05b S2/S3 acceptance](goal/Phase_II/C_Development_Record.md#c05b)。
Menagerie 仍为 `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`；复现时使用所属 Core 提交的
Gitlink 与对应 Evidence，不以浮动 HEAD 替代。

```python
from task_env import make_env

env = make_env("pick-cube-p16-reference-v1", config={"provider": "mujoco", "backend": "cpu"})
try:
    obs, info = env.reset(seed=31)
finally:
    env.close()
```

## 执行、录制与离线验证

```bash
PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider mujoco --seed 31 --horizon 6000
PYTHONPATH=GeoPhys/src:. python examples/tasks/nut_assembly.py --provider geophys --seed 19 --horizon 6000
PYTHONPATH=GeoPhys/src:. python examples/recording/record_expert.py   --env-id pick-cube-p16-reference-v1 --provider mujoco --seed 31   --horizon 600 --output workspace/new-run/pickcube.h5
PYTHONPATH=GeoPhys/src:. python examples/recording/inspect_h5.py --input workspace/new-run/pickcube.h5
```

使用新的输出路径。NutAssembly 保留 guarded `step_expert()`；task-owned external Solution 的 full Expert
与 execution H5 S2/S3 在 MuJoCo 3.8.1 CPU bounded 通过。GeoPhys `a53a8cf` CPU/CUDA × gripper 100/500 Hz
四格也完成真实 diagnostic S2/S3；实验逐 native substep 调用公开 `read_cpu_snapshot()`，因此不扩展该 Reader
的通常低频使用合同、通用 capability 或 device-resident control。禁止 raw external actions；提前截断不构成成功，task outcome、
Expert completion 和 termination/truncation 分开报告。具体数值、设备、成本和 H5 hashes 见
[C05c cadence report](goal/Phase_II/C_Development_Record.md#c05c)。
离线 H5 integrity 不证明 replay/D0。完整选项与有界资源语义见
[examples](../../../examples/README.md)。Linux `RLIMIT_AS` 是每进程虚拟地址空间限额，
不是 RSS 或整个进程树内存上限。

[模块 Skill](../../../.agents/skills/geochora-task-env/SKILL.md)提供 Agent 操作路由；
[API reference](../../../task_env/doc/api/index.md)提供符号级细节，后者不是第二份能力矩阵。
