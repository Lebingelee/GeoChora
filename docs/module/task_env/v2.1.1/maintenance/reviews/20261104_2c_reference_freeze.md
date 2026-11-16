# V211_G02_2c_attempt001：PickCube MuJoCo 成功参考冻结

日期：2026-11-04。状态：`REPORTED_PENDING_REVIEW`。范围：冻结既有成功记录并整理阶段2文档；无新代码、native运行、pytest、provider import、reader或GPU探测。Sol复审前不进入阶段3。

## 实现与运行身份

- Core：`develop@8fba7f8ff0d47f7de8e5ced53f2ecdeb21869238`；GeoPhys pin `67da1165149486d3ae3e779c13ce31af49e17d50`；Menagerie pin `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。
- 主参考：attempt002 ignored raw中的`runs/mujoco_pickcube_seed31/`，MuJoCo CPU，task `pick-cube-p16-reference-v1`，seed31，horizon1000，R3 profile `r3_continuous_v1`。公开construction/TaskArtifact为`pick-cube-v1/p1_6_experimental_100hz`；完整 resolved config 保存在同run `worker_result.json`。
- task artifact SHA-256 `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`；Controller `ReferenceExecutionController` identity `e07d5f97af71556081cccee2035945bf561a6d2d9882e732d9406b08d1acd96a`；Solution `PickCubeReadinessSolution` identity `dbd5bc4e812d3d1b2db28fe08e35d8527f7b7a1d68bfc18100c883cbadba1c71`。
- 本次执行为100 Hz外层控制与500 Hz gripper servo cadence；物理步长0.002 s、每个外层控制间隔5步、control_dt0.01 s、horizon1000。真实 reset sample id：`reset-ee9644c1af42c7897f79a0cece21e5fc4bd5323ae40eba7b7259d34d681a5fb6`。run使用真实桌面、方块和机械臂碰撞，未使用未批准override。

## 成功策略与判定

复现配置记录高位clear与approach目标分别高于cube top 90 mm和80 mm；measured-TCP clearance gate 65 mm、XY门限10 mm；close/settle/post-close hold为34/50/10 ticks。原 task lift predicate仍为0.10 m，Solution收集余量0.105 m。完整solution配置与逐阶段实际值以同run `worker_result.json` 为准；resolved configuration不在本页重复展开。成功对应已记录的整组方案，不证明单独改变某个高度即可成功，也不改变物性、reset分布或碰撞语义。

## 唯一主参考记录

- 结果：960 transitions、961 boundaries；task success、Solution done、Expert complete均true；cube_lift=`0.10518958081676949 m`。termination由task_success结束。
- HDF5：`runs/mujoco_pickcube_seed31/episode.h5`，5,493,544 bytes，SHA-256 `4a28d177ccf30cb0efa86a268496166616a00adf79e647e006770d3d412f4283`。
- 独立reader：`runs/mujoco_pickcube_seed31/reader_retry02/readback.json`，status PASS，H5 SHA与上行一致；T+1、control_dt、target/ack identity均通过。
- 边界轨迹：同目录`reader_retry02/step_trace.json`，SHA-256 `9acc68263151af86c1e8005e4be935692cfc94b3b21b381220d9f48e4163df4c`。
- `worker_result.json`与`supervisor.json`保存来源commit、task/Controller/Solution identity、resolved config、实际命令/cwd、close结果、worker PGID退出、双锁取得/释放顺序及资源样本。实际wrapper argv由该supervisor记录。
- 人工接管时期HDF5 `4b9e2e78cb69d08c3b6f023112859e2f9f273eba4ff3905fd21a31a610f3b9e6` 是另一份历史运行，只作辅助引用，不能与本页主参考混为同一HDF5或source identity。

## 复现入口和限制

现有public使用入口为：

```text
python examples/tasks/pick_cube.py --provider mujoco --execution direct --seed 31 --horizon 1000 --controller-profile r3_continuous_v1
```

该入口仅作后续维护者复现参考，本窗口没有执行它。实际采集run使用原始`supervisor.json`中记录的argv和run directory cwd；原薄helper `workspace/maintenance/v211_g02_2b_attempt002/run_public_reference.py` SHA-256 `8c4a5bbcd7d15170734f0ddc27d051646b8e418765a24aa18e98d27f9e74c86f`。全部原始运行与失败文件保持在既有ignored raw根，没有复制或重读HDF5。

## 回归、失败和未决边界

- Sol已复核六个窄回归模块共71项通过；本窗口未重跑。NutAssembly seed19有两次独立2377-transition成功。PickCube seed32在固定horizon1000以lift `0.08261901333725602 m`失败；不增大horizon、不修改task oracle、不抹去失败。
- 原2b attempt002仍保留G2 FAIL、G3 PARTIAL、G5 INCOMPLETE_USER_PAUSED。Sol接受的是MuJoCo代表性实现与受影响Nut回归的有界证据，不是完整2b或阶段2接收。详见[2b中止记录](20261104_2b_closeout.md)及[执行表](../../planning/execution-and-acceptance.md)。
- GeoPhys PickCube在control_step=3附近因Solution stale execution time guard失败；实际/期望simulation time未记录、无完整HDF5。最小后续owner是PickCube时间消费与GeoPhys session，属于3–4阶段边界，非本包修复项。
- Isaac冻结delivery 77项hash/size匹配，但无稳定GPU准入后的native结果。环境和route核验归3a；资产校验不是route成功证据。
- 原人工跨环境轨迹回放差异为TCP约`3.44e-15 m`和四元数约`2.12e-15`，属浮点舍入尺度内一致；不称bitwise相同。其余人工尝试和误差过程见主工作区 `/home/lly/Documents/ChatGPT/GeoChora v2.1.1/execution-output/V211_manual_analysis_stage2_summary_001/report.md`。

本页只冻结一条已有的MuJoCo CPU PickCube seed31成功参考。状态待Sol复审，不授予全后端等价、Qualification或阶段3授权。
