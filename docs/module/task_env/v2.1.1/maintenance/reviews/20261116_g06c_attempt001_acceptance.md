# G06c attempt001 独立主审与有界接收

日期：2026-11-16。结论：**SOL_ACCEPTED_BOUNDED_6C**。执行交付 Core `a824b7df3ddbcafc9f886a4f476959cdbe6b60a7`，主审清理小修 `a4d9eb26de0a32b1cb515433f42a4304272d939c`；GeoPhys保持`198d30ac64ce873a1467f55d2adfc471db18fbc5`，Menagerie保持`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。G06abc canonical目标均已有界独立主审接收，维护者最终接收未代为宣称。无需6c attempt002，R3/G07另包。

## 1. 输入、方法与接收范围

对照[冻结工作包](../work-packages/20261116_g06c_attempt001_goal.md)、[执行报告](../../../../../workspace/maintenance/v211_g06c_attempt001/report.md)、gates与原始收据核对C1–C5；工作包SHA为`a8a283dfdac876db7e50cefa7893fc598bcf86c98bc971347332f9aa8fc533e0`，实际执行输入为文档后继`697102cc75b68dbc8f69e5ba26a007b241ca2d8f`。主审只读代码与数据复核后完成一处故障清理小修，没有启动native、GPU、窗口或新attempt。

采用CodeGraph定位，核对当前源码及diff；两个只读子审分别检查生产生命周期和原始H5/相机证据。三后端×两任务B3部分reset、错开截断和终止图像保留成立；跨provider限Isaac↔MJWarp，两个任务各自Isaac→MJWarp→Isaac，在同一public Env、固定共享Rasterizer配置下整批重建。GeoPhys跨provider切换未准入；不宣称任意资产/后端组合或跨行视觉隔离。

## 2. 原门与独立证据

| 门 | 独立核对 | 判定 |
| --- | --- | --- |
| C1 部分reset | 三后端六格最终mask检查、未选行状态/动作响应、六组后续三次RNG采样；Pendulum任务驻留计数纯测试 | PASS，复用不受重建分支影响的最终运行 |
| C2 错开结束 | 重读三后端21份H5、81个状态边界、162帧相机图像；与公共返回witness的state/action/reward/done/context逐值一致，各后端69项检查 | PASS，短程truncated，不新增完整抓取要求 |
| C3 整批切换 | 重读两个任务18份H5及NPZ；A1/B/A2 provider为Isaac/MJWarp/Isaac，generation为1/2/3、materialization各自独立；全部obs叶子、动作、reward/done一致；PickCube含72帧双相机图像 | PASS，最后配置修复后的两个普通示例也有三段实测 |
| C4 失效/清理 | 旧state/view/selection/typed command/renderer被拒绝；真实target建立后首次reset失败，两个target PID退出、IPC owner解绑且buffer/event清空、GPU进程清单不再含target；faulted阻止reset/step/render/state、重复close成立 | PASS；主审另补下述构造与清理复合故障重试 |
| C5 caller/回归 | 公共示例不导入诊断包；原最终回归87通过，较广回归105通过/8跳过、scalar定向2通过，分别按各自范围保留，不相加 | PASS；主审新增3例，相关纯测试文件23通过 |

三后端部分reset的共享场景base相机有6–8个远景像素变化，hand不变。主审核对同一runtime只渲染未选行时base/hand逐像素不变，完整场景同状态重复渲染稳定，另有只改变一行的负对照。证据支持其他行几何进入共享视野，不是已证明的framebuffer残差，也未按像素数量阈值放行。未选行物理/相机绑定身份不变与图像内容包含别行几何可以同时成立；这符合原包要求解释变化来源。视觉隔离需求须由相机/场景布局另行约束，不在本包补上新门。

独立H5比较证明记录对应公共边界；物理与pose到图像映射沿用6b既有资格，不把读回重复解释为独立物理求解。owned历史快照可读，但不能用作新generation输入；普通数值action无来源身份，不虚称可拒绝它来自旧episode。

## 3. 主审发现与已完成小修

原交付构造helper会尝试各资源close并将异常加note，但构造中途失败且清理也失败时，factory抛出后Env没有目标owner可重试。相比旧batch关闭失败、目标首次reset失败的已有保留逻辑，这是实际控制路径缺口，未宣称已观测到native泄漏。

`a4d9eb26`沿用现有owner完成小修：helper仅返回失败的bound close操作，重建Env保留这些操作；close成功项删除、失败项保留，所有资源完成后才标记close complete。adapter的source/binding仅在清理成功后清空。没有新资源管理类、故障后门或公共API，没有更改求解和正常推进路径。

新增三例纯检查覆盖runtime/adapter构造阶段的清理失败重试，以及source失败后的引用保留；完整`test_reconfiguration.py`为**23 passed in 1.73s**。命令在`/tmp`、隐藏CUDA、关闭bytecode与pytest cache/autoload执行，未启动GPU：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 CUDA_VISIBLE_DEVICES='' \
PYTHONPATH=/home/lly/Program_Files/Geochora:/home/lly/Program_Files/Geochora/GeoPhys/src \
/home/lly/miniconda3/envs/geochora/bin/python -m pytest -q -p no:cacheprovider \
/home/lly/Program_Files/Geochora/task_env/diagnostics/tasks/v2.1.1/g06/test_reconfiguration.py
```

首次同命令未禁自动插件，pytest-rerunfailures在收集前因sandbox禁止创建socket而退出3；禁用无关自动插件后通过，未提升权限执行测试。没有删除失败历史或把它记成产品测试失败。小修经第二位只读代码审查；原native证据按正常路径与未改物理/渲染代码复用，不因这一故障收尾改动重跑矩阵。

## 4. 流程偏差的处置

两项不能补造的历史事实保留：未找到执行前写入该attempt目录的实际调用链/最小改动表；API说明在最初实现之后补写。输入工作包已有owner/落位规划，只能证明规划存在，不能证明规定的事前落盘步骤完成。执行报告和HANDOFF均不改写为合规。

最终公共接口、真实caller、生产调用链与独立结果已经核对；这两项流程偏差不产生待完成的产品功能或额外native验收门，因此本次技术主审不据此继续阻断。不能通过再跑attempt、补写旧时间戳或另开研究来修复历史时序。执行Goal可依据技术结案完成收尾，平台标记仍由持有该Goal的执行会话操作；本主审不操作其他会话Goal。

## 5. 资源与结案

独立重算63份监督收据，共`6899.375 s = 114.989584 min`，无violation，最长500.81s小于单次900s。保留早期探针错误、严格像素负对照和close重试失败及其后续修复，不将非零退出全部解释成已通过。新增主审测试为CPU纯检查，不计新增native；不突破120分钟native预算。

两仓tracked在主审前干净，保护日志SHA与冻结值一致。主审只提交上述必要小修及当前文档/编排状态；原report、HANDOFF、gates、运行数据与pins不改。文档校验的既知保护日志基准差异单列，实际日志未改。GeoPhys显式discrete/32及6b物理边界、AOT/main合并暂缓、窗口外观人工验收继续保留。

当前C1–C5无未闭合技术阻断；无需第二次执行包。R3及G07/版本收口另行规划，本结论不授权merge、push、tag或发布。
