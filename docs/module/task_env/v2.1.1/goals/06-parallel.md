# G06：并行执行、部分 reset 与整批切换

规划标识：`V211_G06_PARALLEL`。3 个子阶段；复用既有 batch runtime、vector 调用、parallel render 和 Recorder。由[数据协议](../contracts/lifecycle-and-data.md)规定身份与时序，不为 batch 新建第二套任务生命周期。

2026-11-15维护者补充：后续并行实施采用CUDA，不把CPU physics或CPU多进程方案作为本轮并行交付路线。三家仿真器、GeoPhys static沿革、下游实现参考及共同Task／Robot构建建议见[并行环境调研](../planning/20261115_g06_parallel_research.md)。该调研不代表native batch验收；确切provider／task／source／Controller／固定renderer名单仍在6a冻结。

维护者后续提出版本冻结、代码落位审批、canonical action 先行、same-step autoreset 保留完整终止图像、固定 renderer 网格场景及 Pendulum／PickCube 验收要求，详见[G06a～c 实施方案审批稿](../planning/stage6-parallel-execution-plan.md)。该方案包含待审批的 D1～D6，不自动改变本 Goal 的已批准出口或代表实施已经开始。

## 当前边界与阶段3前维护的衔接

维护者已明确：统一环境路线的并行适配尚未完成，阶段3前重构先完成Pendulum等旧任务的单环境迁移。现存并行注册、factory、脚本及历史证据保留，但不能证明统一路线已适配；`num_env=1`也不构成多环境验证。未适配的并行调用须明确声明或拒绝，不静默降级。

G06承接Pendulum及其他受影响旧vector caller的适配和真实多环境验证。上述延期不改变下列6a–6c依赖、至少两个后端及至少一条native batch的目标，也不表示G06已启动。参见[阶段3前维护方案](../planning/pre-stage3-environment-refactor.md)。

<a id="6a"></a>
## 6a：批量契约接通

- **输入／依赖：**3c、4c、5c；1a 冻结的两个以上后端／模式，及 1d 的同步／终止边界。
- **工作：**接入 env ID、batch 轴、device、reset mask、每环境 episode／clock／Core sampler流和provider派生seed、固定 action／obs schema 与图像布局。选择并公开支持的一种 auto-reset 语义，正确保存终止 obs 与新 episode 首帧。
- **检查：**布局／排序／mask 正反例、错环境写入、借用 buffer 生命周期、嵌套主体／joint effort／BodyWrench贡献的row identity、无效 Controller 规格和未知并行能力拒绝；Recorder 可区分同批不同 episode。
- **交付／出口：**标量语义可映射到 batch，设备数据路径明确；不强迫所有状态 CPU copy，不静默改变旧 vector caller 语义。

<a id="6b"></a>
## 6b：多个后端真实并行

- **输入／依赖：**6a；冻结的实现范围、少量环境数、相机规格及 RAM／VRAM 预算。
- **工作：**至少两个物理后端实际构建／reset／step／render／obs，至少一条 native batch；优先核实 GeoPhys 和 Isaac 的既有路线，有缺口则在本范围扩展既有 owner。
- **检查：**环境间隔离、动作对应、状态／图像的 env ID 与时间、终止／部分 reset 相关行为；记录原生批量或进程并行，实际工作进程和设备数据传输。
- **交付／出口：**两后端完整小批量证据，不用 N 个串行调用冒充 native batch；吞吐量可描述，不新增大规模性能或多 GPU 门。

<a id="6c"></a>
## 6c：部分 reset 与配置切换整批重建

- **输入／依赖：**6b、3c、5c。
- **工作：**不改配置时支持所声明路线的部分 reset；同一 public vector Env 在已准入且与创建时固定 renderer 兼容的 backend 之间切换时内部关闭并重建整个原生 batch，初始化新 episode，清理旧 Controller／pending force contributions／相机／GPU 绑定。2026-11-07 修订：renderer 切换未排期，不作为 6c 默认前置或自动转入 6c；不兼容的 backend／固定 renderer 组合须明确拒绝，6c 的代表切换边在工作包中按实际能力确认。
- **检查：**相对已完成step后的pre-reset边界，mask reset不改变未选环境的状态、时间、Controller／RNG历史和图像身份；共享borrowed buffer失效另行标记；整批重建后的旧 view／command／frame 失效；失败、重复 close、worker／共享资源回收及锁释放。
- **交付／出口：**显式声明 reset 粒度，不偷偷重置其他 slot；不能在单个 native batch 中替某个 slot 换后端。整批 A→B→A 的固定 obs 和动作规格正确。

## 范围和阻塞

本版不要求异构资产任意混批、每 slot 不同维度 Controller 或所有 autoreset 模式。并行方式必须显式，数量／能力下调须维护者决定；1a 的实际核实不能自动把“至少两个”改为单后端。图像若只支持选定 env 或拼图，需区分窗口展示与每 env 的 Agent observation，不能互相替代。
