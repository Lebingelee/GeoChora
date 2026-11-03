# G01：统一任务表示与三方协议

规划标识：`V211_G01_PROTOCOLS`，不是已启动 Goal。4 个子阶段，默认顺序 1a→1b→1c→1d；依赖及接收统一见[执行表](../planning/execution-and-acceptance.md)。本阶段以现有 owner 的契约收敛为主，具体 API 与协议经讨论后冻结。

## Owner 与当前基础

公共构造、配置、Artifact／Scene／source、RuntimeSession、render／camera、Controller、batch 和 Recorder 都有现有入口，见[源码映射](../planning/source-map-and-references.md)。selected 与通用 TaskEnv 尚有兼容路径；当前 protocol／profile 不能直接外推所有后端。本阶段不新建平行抽象，不把源码注册等同运行能力。

<a id="1a"></a>
## 1a：核实 owner、当前范围和可实施组合

- **输入／依赖：**已确认路线、当前 HEAD、v2.1.0 有界矩阵与既有失败；先检查 worktree、dirty paths、gitlink 和依赖版本。
- **工作：**沿 make_env、配置、reset、step、render、记录和 close 追 caller；列出现有协议与缺口。冻结首批三个物理路线的资产、设备、renderer、窗口／RGB 能力；核实 GeoPhys×MuJoCo 跨组合及两个以上并行后端的公开入口。
- **资产范围：**列出质量／惯性／单位／关节／传动／约束／reset／稳定性检查和未测项；区分原生构建转换与未来 asset harness 适配。
- **交付／出口：**更新源码映射、能力矩阵的目标组合和 D01/D05/D06；有依据地区分支持、实现缺口、依赖缺失及未验证，不减少已确认的必达数量。
- **检查／证据：**源码／生产 caller／已有证据核对；只有决策确实依赖且获得后续包授权时才做最小原生探针。审计不默认运行整矩阵，不无限展开全项目盘点。

<a id="1b"></a>
## 1b：统一任务表示

- **输入／依赖：**1a。Owner 为既有 declaration、TaskDefinition、Artifact／Scene、assembly compiler 和 execution config。
- **工作：**讨论并冻结[统一表示](../contracts/unified-task-representation.md)，把任务语义、物理模型、资产表示、执行配置映射到既有 schema；明确 semantic ID、表示映射、扩展类型和兼容解码。
- **交付／出口：**形成字段与 owner 对照、复用／扩展理由、版本与不支持规则。刚体、关节和相机可实际落地；非刚体保留有意义的接口位置，不设计完整未来语言。
- **检查／证据：**结构化正例及未知字段、身份／映射冲突、缺失必需物理表示的拒绝案例；可先使用静态说明，实际检查代码由冻结包授权，不以文档示例代替实现。

<a id="1c"></a>
## 1c：Core 与 physics provider 双向协议

- **输入／依赖：**1b。Owner 为 RuntimeSession、admission、ControlBinding、provider adapter 及公开 provider API。
- **工作：**冻结[physics 协议](../contracts/physics-provider.md)及[控制语义](../contracts/control-and-feedback.md)；定义 query／build／reset／command／advance／publish／close 的值与失败责任。独立 Newton、Isaac 宿主内引擎、多 solver 与 coupler 可区分。
- **关键决定：**最小必需状态、数值准入、夹爪 effort／传动、公共模型服务、反馈时序、命令与实测区别，及 reset preflight 拒绝后的状态。
- **交付／出口：**三条首批路线逐项对照协议；能力不匹配和原生构建限制有结构化拒绝；明确错误／部分执行、异步完成、公开数据有效期。不承诺所有后端提供所有量。
- **检查／证据：**量纲／轴向／排序、数据身份、缺失反馈、solver 耦合不支持、资产不可表达和 stale command 等反例；已有事实与新目标分别记录。

<a id="1d"></a>
## 1d：Core 与 render 协议及共同生命周期

- **输入／依赖：**1b、1c。Owner 为既有 render／camera、RuntimeSession、环境生命周期和数据契约。
- **工作：**冻结[render 协议](../contracts/render-provider.md)和[生命周期／数据](../contracts/lifecycle-and-data.md)。汇总原生构建需求，明确共享 scene、app、device、context 和 worker 的唯一 owner；确定 renderer 输入、输出及动态几何扩展。
- **关键决定：**reset 首帧与 step 同步、窗口／任务相机分离、窗口关闭语义、数据设备／借用期限、相机失败；公布 batch 终止语义的设计约束。
- **交付／出口：**五份协议草案统一审阅；确认字段／签名映射、首批 render／cross 组合和每项资源 owner。具体不可确定项须有明确后继 owner 与冻结时点，不能留下影响 3a 开工的强制未知。
- **检查／证据：**原生共享场景和独立 renderer 两类时序图／案例；reset 后旧图、借用过期、重复 close、需求冲突等拒绝行为；明确后续最小 contract 检查。

## 阶段接收

四项是协议与可实施性出口，不是三后端 native 或渲染 PASS。讨论决定写回对应权威协议，Goal 只保存决定与检查索引。参考来源及采用／拒绝理由更新[研究入口](../planning/source-map-and-references.md)。派包遵守[统一工作包要求](../planning/execution-and-acceptance.md)，不把本页直接当作可执行 prompt。
