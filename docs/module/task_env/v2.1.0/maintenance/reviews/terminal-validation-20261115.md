# 终态验证方案收尾记录（2026-11-15）

本次交付通用终态审核实现、证据接入与传输、回归测试，以及Scene-50任务集合的薄接入。
实现与本次MuJoCo实测支持进入代码提交收尾；该决定不新增完整任务、过程或provider Qualification。
输入分支为`feat/trajectory-qualification-pilot`，输入HEAD为`fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`。
提交后的代码身份由包含本记录的Git提交确定；实验使用的源文件摘要保留在各批冻结配置中。

## 交付行为

原任务与同次运行证据进入初末视图和证据目录；初审可请求一次补证，再判断。
布尔候选必须经独立上下文复核确认，才能发布`terminal=true/false`；有效未知保留为null，
协议、预算或调用错误另记`execution_failed`。`task_success`和过程义务保持独立。
源绑定、对象选择、原始阈值、单位、接触时钟、图像实际交付、参数差异及缓存身份均受检查。

- 通用语义与审核协议：`validation/terminal/`；有限采样原语：`validation/sampling.py`。
- 证据适配、目录、资产比较、执行与传输：`validation/adapters/`和`validation/terminal/`。
- Scene-50：20条原始任务及公共条件、外部资源准备和19份既有演示引用；复用通用审核，未注册为`make_env`环境。
- 外部模型宿主和登录由调用方配置，Core不内置模型SDK。旧规格实验所用jsonschema依赖现仅留在实验归档。

接口、错误边界和诊断性质以[现行合同](../../contracts/recording-and-learning.md#terminal-source-review)为准；
可运行检查见[测试说明](../../../../../../validation/tests/README.md)。

## 2026-11-16交付范围收敛

按用户决定，旧规格／词表、多路线审核与组合、关系benchmark和旧snapshot采集迁入忽略的
`workspace/tasks/terminal-experimental-routes-20261116/`。归档保留迁移前完整源码、文件摘要和显式实验入口。
Core保留原任务直接审核、独立确认及16种来源绑定数值方法；数值入口改为显式逐项测量，
不生成整体终态、不再依赖旧规格或词表。Scene-50任务集合的薄接入保持原样。
下列物理实验与856项回归是2026-11-15原版本的历史证据，本次没有重跑在线模型或物理实验。
迁移后的回归、35份原始审核请求的协议一致性与归档测试另存于该本地目录，按实际收据解释。

## MuJoCo实测

两批独立数据均由MuJoCo 3.10.0真实运行产生，没有PhysPi仿真重跑。
审核复用原`source_run`，初审`gpt-6.1-sol` medium、独立复核max，adaptive最多一次补证，
无自动模型重试；每次最多1,500,000文本字符、8图。该版本仅指本次独立producer，未改变Core生产依赖范围。

| 批次 | 独立参考组成 | 与参考一致 | 未知／审核错误 | 调用 | 已知token |
|---|---|---:|---:|---:|---:|
| 3条接入预检 | 2正、1反 | 3/3 | 0／0 | 7 | 440,013 |
| 10条正式构造验证 | 5正、5反；投影、姿态、相对位置、支撑、短时稳定各一对 | 10/10 | 0／0 | 22 | 1,223,701 |
| 3条Scene-50追加探索 | 叠放、侧立、关中屉；3正 | 3/3 | 0／0 | 6 | 1,878,932 |

正式构造集明确判断覆盖率100%，无误放行或误拒绝；参考为同次原生记录的独立几何／物理计算。
Scene-50参考由父Agent依据独立重算的原始力、姿态、位置及原生图片做定性判读，非人工金标准。
两批标签均在被测模型调用前冻结并与输入隔离；预测单独冻结后再对照参考。
token只计被测审核调用，缺失用量为0；reasoning已包含在total中，不重复累加。

构造集有7,500次物理步、7,513个状态／接触边界及52张图。
Scene-50首次执行三题共30,646步，保留30,649个完整qpos/qvel/ctrl边界、
1,260个0.05秒加相位边界的公开状态／接触样本和48张图；没有按成败换样。
立积木过程中一颗球被碰落，原始记录完整保留；原题没有额外要求所有其他物体终态留在桌面。

## 结论边界

本轮支持该终态方案从GeoPhys证据扩展到独立MuJoCo原生证据，并在五类构造条件及三类完整场景操作上工作。
Scene-50保留原几何、质量、初态和真实Panda接触操作，材料采用用户授权的近似映射，
不声称跨引擎物理等价。三个追加样本只有正例，不提供新增失败识别率或一般任务成功率估计。
终态通过不等于全部操作过程已由此审核认证；没有声称覆盖任意MuJoCo任务、数值边界或连续时间条件。
旧172条数据与B50重跑结果保持独立，不把跨运行标签一致率当作原终态准确率。

## 提交检查与证据位置

2026-11-15提交准备回归：`task_env/diagnostics/qualification/tests`与
`task_env/diagnostics/tasks/test_franka_scene.py`共**856 passed**（48.25秒）。
这是合成输入、编写的模型响应和离线协议检查，不包含在线模型或新物理运行；物理证据见上表。
运行环境为Python 3.12、已有TaskEnv依赖加临时pytest 9.2.0和jsonschema 4.26.0，
设置仓库及GeoPhys公共源码的`PYTHONPATH`，未安装editable项目或变更运行环境原生库。
本轮未跑与改动无关的全仓库provider/训练回归。

全量文档检查尚未通过：历史冻结文件出现字节差异，Windows换行转换只是待核实原因；
迁移manifest要求的两份本地输入仍缺失。暂存快照检查也未完成，没有`staged-docs.json`成功收据。
检查脚本、未完成快照及回归收据保存在`workspace/tasks/terminal-validation-closeout-20261115/`；
不改写历史冻结文件或原摘要来消除检查错误。

[机器可读证据索引](terminal-validation-20261115.evidence.json)保存两批结果摘要与SHA-256。
原始数据及日志继续保持Git忽略，路径均相对仓库根目录：

- `workspace/datasets/terminal-validation-mujoco/v1/`
- `workspace/datasets/terminal-validation-mujoco-scene50/v1/`
- `workspace/tasks/terminal-validation-mujoco-fast-20261115/REPORT.md`
- `workspace/tasks/terminal-validation-mujoco-scene50-20261115/REPORT.md`

这些是本地证据位置，并非远程仓库自带的数据集。用户场景二进制资源没有公开再分发许可，
本提交仅包含任务文本、资源身份和接入代码。局部采集脚本不是新增通用Runtime或Recorder。


2026-11-17归属更新：当前验证实现已独立到仓库根目录[validation](../../../../../../validation/README.md)。本文日期标记的实验、命令、源码身份和证据JSON仍描述当时执行，不因迁移重写或升级能力结论。
