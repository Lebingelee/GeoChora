# 独立任务验证合同

当前实现归属仓库根目录 `validation/`。本合同从TaskEnv记录合同提取，用于已有实验数据的离线终态检查；TaskEnv继续拥有运行、记录与生命周期判定。

通用输入处理和审核不导入TaskEnv、不启动仿真；原生查询仅由显式选择的适配入口执行。Validation输出满足／不满足／未知，执行错误单列；Qualification仍指项目正式能力资格。

[模块入口](../../../validation/README.md) · [测试](../../../validation/tests/README.md)

<a id="task-input-contract"></a>

## 对外任务输入

`validation.inputs.validate_task/load_task`支持`low-detail-task/1.1.0`和`low-detail-task/1.2.0`，
使用从SimDataKit保留的[原始schema与来源摘要](../../../validation/schemas/README.md)。任务ID、原文、验收、
资源引用和版本原样保留；未知版本、缺字段、非法类型及非有限JSON在模型调用前报出文件／字段位置。
这是一条任务输入合同，不授予数据集发布资格，也不证明语义解释或物理任务完成。

`load_task_source`以显式`resource_root`（默认任务文件所在目录）解析资源，拒绝越界、缺失和重复ID，
仅把`task_contract`与`initial_state`的JSON载入`dependencies`。原始资产由调用者保留来源和字节身份，
不执行、不重新生成。[外部用户样例](../../../examples/validation/README.md)
复用同一校验。底层`prepare_source_review`仍保留自由source协议，不能据此宣称任务schema已验证。

任务格式不合规为输入错误；格式合规而必要观测缺失时，继续沿用证据／审核的未知与错误区分。

<a id="offline-semantic-diagnostic"></a>

## 离线终态审核与数值测量

当前诊断主流程直接读取原任务和同次原生证据：初审、必要时最多一次补证、独立复核布尔候选。
发布满足／不满足／未知，执行错误另列；终态不等于完整过程、Expert完成或provider Qualification。
通用几何与数值计算由validation维护，作为带来源的逐项事实；旧规格生成与多路线组合改为实验归档。

`validation.sampling` 保留有限采样、显式几何、三值结果及严格先后见证原语；
调用者提供身份、采样时钟、缺失标记和几何，不从有限记录推断连续时间证明。
Scene50专用验证器仍为此前已退役的历史代码，不恢复为逐题判据。

<a id="terminal-geometric-diagnostic"></a>

## 终态几何诊断

通用关系 owner 为 `validation.terminal.TerminalScene`，输入一个末帧的物体位置、
WXYZ 姿态与显式资产绑定；`TerminalPolicy` 保存三值测量区间。
`geometry.py` 是内部闭合凸碰撞块工具，复用现有旋转工具。
调用者显式使用该几何接口；旧文件／关系benchmark入口已随实验归档。
末帧须有有效实际终点依据；否则快照几何事实不能认证终态。

关系包括完整球体在矩形内腔、球体与桌面几何接触、夹爪包络分离、抽屉沿轨道开关、
刚体碰撞面与桌面／另一刚体的支撑相容、三个长物体平行且分离成行。
支撑使用凸碰撞块的面接触候选及穿透检查，不以外包围盒重叠否定叠放。
几何中心不是真实质心或接触力；侧面摩擦、点／线接触和边界情况可未判定。
碰撞块须闭合、凸且非退化，不把任意凹网格静默转成凸包。
夹爪包络分离是充分几何证据，包络相交只返回未判定。

默认距离区间为 1 mm／3 mm，平行角为 2°／10°，成行残差按最窄物体宽度归一化为 0.25／0.75。
这些是开发诊断策略，不是原任务新增门槛。不要求等间距、特定行方向、固定编号或保持时长。
球体桌面检查要求接触点位于桌面内部，支撑允许几何中心仍处于接触区域内的悬挑。
平行成行使用世界 XY 碰撞块分离，竖直分层不能代替横向分离；投影中心重合且无明确反例时保持未知。
输入快照由 `TerminalScene` 复制持有，外部映射变化不修改其几何缓存或位姿。

终态几何不能证明同组对象实际经历过抓放；真实支撑、操作因果和过程义务需要相应证据。
同一球存取等任务所需角色由调用方显式绑定，不能根据已知标签或终态表现选择对象。
`task_success` 保持 null，几何检查不授予 Formal Qualification 或跨资产准确率结论。
通用回归入口为 `validation/tests/test_terminal.py`。

<a id="terminal-numeric-measurements"></a>

### 显式来源绑定的数值测量

`validation/terminal/numeric.py` 的 `measure_source_requests` 接收原始source、
caller已核验的 `source_ref`／dependencies、同次record、evidence_refs及显式requests。
每条request包含 `request_id/method/arguments/params/source_basis`；没有AST、逻辑树或量词展开。
返回 `terminal-numeric-measurements/0.1` 的逐项 `value=true/false/null`、实际数值、缺失原因、
参考点、采样覆盖、请求／来源／producer摘要。它不返回整体terminal或task_success。
原任务初审和独立复核仍须核对测量方法、参数与原要求是否相符；源指针存在不证明解释正确。

保留16种固定方法：中心先后、初末位移、采样姿态稳定、绝对／初态朝向、世界坐标界、
轴角／平行、碰撞投影落区v1/v2、无机器人接触、两对象无接触、松爪、支撑v1/v2及非支撑。
旧方法ID保持原义，参数白名单、必填项、有限数、枚举、角度、正窗口及单位四元数在计算前校验。
未知方法、错误身份、非法参数和引用冲突是输入错误；缺观测、缺参考点、缺完整采样或无效终点
保持null。物体原点不默认为源中心；同一body的不同request可以绑定不同源参考点。

`numeric_request_digest(requests)` 绑定完整显式请求。可选几何／载荷包使用
`terminal-numeric-evidence/0.2`，以 `requests_sha256` 替代旧spec摘要；reference_bindings同样
绑定请求摘要和源摘要，entries按 `(request_id, entity_id)` 保存，携带原始source指针与native basis。
旧spec绑定的0.1数值包只由冻结实验路线读取，不做隐式升级。

几何包保留完整collision scope、原生body映射及坐标／单位；接触保留phase、geometry／availability
时钟、容量溢出、缺失／部分状态、force scope和支撑路径完整性。距离近不证明承托，空接触不代表
无接触；松爪的几何推断仍需要明确的contact-only retention前提。
窗口来自原始结构化来源的明确指针和采样周期；不编译自然语言窗口，不插值或静默稀疏化。
无法核验原始要求或完整网格时保持未知，原任务及已记录数据仍可交给主流程独立判断。

调用者可将该JSON及其来源、producer文件摘要作为 `measurement` evidence交给
`reviews.prepare_source_review`。参考标签、旧整体判定和其他模型结论不能混入测量包。
它是调用方显式准备的辅助证据，不是source_run内置的自动任务解析或另一套成功判定器。

<a id="terminal-offline-contacts"></a>

### 原生记录、接触和原任务输入打包

`physpi.collect_evidence` 读取已有完成batch或sealed resident运行的公开查询，固定来源身份、
初末边界、源文件及显式请求的窗口。`collect_native_evidence` 保留完整已有原生样本、body/import
映射及可用控制通道；`collect_native_pose_measurements` 按名称整理原点位姿与变化量。
它们不运行历史脚本，不生成缺失几何、接触或力，不把原点自动当作源中心。
CLI使用 `--run-directory`；旧manifest/snapshot命令属于归档实验入口。

显式 `include_native_measurements=True` 读取已有白名单测量并保存接触sidecar。
`contacts.decode_contact_records` 保留公开body身份、原始冲量N·s、接触点、阶段、时钟和容量。
available／partial／unavailable表示数据可用性；空、未知、缺字段及溢出不同，不能补零或自动换算承重。
几何时钟与记录可用时钟分开，上一求解状态不自动成为当前终点接触。
证据目录按既有`1e-8`秒时钟比较容差处理终点浮点舍入；原始观测时间保持不变，真实晚于终点的区间仍拒绝。

`physpi.prepare_source_evidence` 核验引用并打包可读JSON/XML、原生状态／接触、资产参数和实际图片，
返回给 `prepare_source_review` 的endpoint/evidence。`model_view="boundary"` 复用同一个
evidence_views实现；原文件及摘要保持权威。宿主与登录由外部调用方配置，validation不内置模型SDK。
调用环境使用`validation/requirements.txt`中的依赖，并将仓库根目录作为导入路径。
`runtime_python`另行选择PhysPi公开查询环境，仅显式执行原生查询时需要。

`recorded.validate_terminal_evidence` 统一准入0.1公开PhysPi、0.2原生MuJoCo和0.3标准化位姿记录。
MuJoCo原生入口要求 `mujoco.public_state_and_contact`、native run及绑定producer的独立身份。
3.10.0仅标识当时独立采集环境，离线验证消费其来源绑定的记录。2026-11-15构造正反例与Scene-50
近似移植的实际范围见[实测摘要](../task_env/v2.1.0/maintenance/reviews/terminal-validation-20261115.md)，不是一般Qualification。
标准化位姿用 `recorded.read_recorded_poses/adapt_recorded_poses`，明确world/m/s/wxyz和独立completion。
没有确认最后记录为实际终点时保留无效标记；缺初态、对象和通道不补零、不猜时间网格。
旧生产者身份可按原记录保存，调用者仍核对原字节；这不恢复旧规格或四路判定接口。

<a id="terminal-source-review"></a>

### 原任务直接判断与独立复核（当前诊断主流程）

`validation/terminal/reviews.py`新增原任务路线，复用现有证据描述符和
`validation/terminal/dispatch.py`传输。它直接保留完整原任务，
不要求先生成固定谓词、对象类型表或可执行 AST；原规格路线及冻结实验保持原合同。
这次是实现与协议验证，不是新的准确率、正例覆盖率或泛化评测。

1. `prepare_source_review(source, endpoint, required_source_pointers=..., model_profile=..., evidence=...)`
   固定原任务、必需覆盖的源指针、运行/实际终点和证据。可同时提供起始/终态原生图片、
   原始数值与可选测量，模式为`multimodal`。资源依赖应作为已核验的可读源证据交付；
   原任务已有结构化验收时原样保留其对象、数值与单位。
2. 模型返回带源指针的自然语言要求清单。每个`terminal`条目是一个必要条件；
   条件内部保留选择分支、量词与共同对象。`initial/process/delivery/context`条目保留原义，
   值为null。顶层终态按必要条件的三值合取核对，没有终态条目时为未知。
   新模板逐条报告`judgment_basis`（`structured/visual_inference/mixed/unresolved`；非终态为null）
   及`missing_structured_evidence`（实际缺失信息的非空描述列表，无缺口时为`[]`）。
   两字段共同提供；兼容两字段均省略的旧响应。缺失项用于披露，不自动将判断降为未知。
   2026-11-11模板另报告`category`：终态为`goal/asset_integrity/other`，非终态为null。
   独立目标与资产要求分别列行，共同对象、选择分支和量词仍保留。旧响应省略该字段时
   归入`unclassified`，不按条目名称猜测分类。类别只解释结果，不改变必要条件的合取。
3. `admit_source_review`核对请求、引用、源指针覆盖和合取一致性。源字段可由本身或可解析的
   子指针定位，相似名称的同级字段不算覆盖；这只检查结构定位，语义完整性仍交独立复核。返回`candidate_terminal`；
   `terminal`仍为null，原因为`independent_review_required`。
   同时返回`requirement_summary`：每类候选值、条目ID、未知/失败ID及各类延后义务。
   `source_run`将清单与摘要保存在`run-result.json`。摘要标记
   `candidate_checklist_not_independent_verification`；总体复核通过也不把每个子项单独认证，
   争议后的候选目标结果不能冒充已确认结论。
4. `prepare_source_verification(judgment_request, judgment_response, judgment_dispatch=..., model_profile=...)`
   将原任务、相同证据和首答交给新的上下文。复核原义、遗漏、对象身份、证据充分性、
   时间覆盖和逻辑；`admit_source_verification`只在`confirmed`时释放候选结果，
   `disputed/unresolved`均保留未知。它不会改答或以投票替代复核。
   对判假的候选，独立核实一条原任务必要条件的失败反例即可确认结果；无关条目的遗漏或
   未知写入复核理由，不据此否决已有反例。若遗漏改变了反例的原义、选择分支、量词、
   对象或适用性，仍须争议或未知。判真与未知候选的确认仍要求完整源覆盖。

首答与复核只依据原任务及其已交付依赖提出验收要求。资产检查回执是观测清单，
其中的`missing_properties`和`asset_integrity=null`本身不增加任务条件；需要具体源义务
才能据此阻塞结果。源确实要求的资产保持和过程不变量的必要终点后果仍须核对。
对“任一合适对象”的任务，一个对象失败不能证明所有允许选择都失败；共同对象已被
源过程明确绑定时按该对象核对，缺乏成功证据不能直接判假。

两次请求分别使用`terminal-source-review-request/0.1`和
`terminal-source-verification-request/0.1`，通过已有prepare/write/complete或callback流程执行。
所有列入证据的图片都是必交付集合；若需要选图，应先固定证据集合，再准备请求。
PhysPi的现有`terminal-model.mjs`宿主支持这两个角色，仍使用新会话和实际图片字节。

数值测量是可选辅助，不要求每种自然语言关系都有数值算法；确定判断仍须引用原生状态、
接触或与实际终点对齐的原生图片。只有测量摘要或初态/历史图片不能准入确定结果。
相关结构化信息缺失或不足时，清晰、对象明确且尺度/分辨率足够的实际终点图片可以独立
支持位置、朝向、摆放关系和普通桌面支撑等可见静态终态判断；理由须注明“基于视觉判断”
及推断前提。视觉依据须引用对齐的实际终点图片；`mixed`还须引用结构化观测，
`structured`须引用原生状态或接触。首答和复核使用同一视觉准则。
核实对象、单位、坐标与时刻后的结构化反例仍判假；未解决的矛盾、遮挡、关键证据缺口、
超出图片分辨率的精确阈值以及仅凭静态图判断时间窗口仍为未知。程序不维护逐谓词的
视觉许可表。两种证据可共同使用，不声称数值与视觉判断统计独立。
真实身份不明、语义歧义或证据缺失仍可返回未知，`task_success`始终为null。

源指针覆盖、协议准入与独立上下文均不证明要求清单完整、模型注意力或物理判断正确。
调用者负责来源/字节核验，并检查展开的原任务和证据中没有参考标签、旧模型判断或整题分数。
清单在看到证据后生成的解释可能有偏差，独立复核须直接对照原任务；其有效性仍需冻结评测。
输出仍保留首答和失败回执，使用新目录；未知、输入错误和复核争议分别报告。

文件宿主的两次调用示例（输入中的源指针与模型配置须来自真实冻结输入）：

```python
from validation.terminal.reviews import prepare_source_review, prepare_source_verification
from validation.terminal.dispatch import (
    prepare_terminal_job, write_terminal_job, complete_terminal_job,
)

request = prepare_source_review(source, endpoint, required_source_pointers=source_pointers,
    model_profile=judgment_model, evidence=evidence)
job = prepare_terminal_job(request, job_id="source-judge", transport="external_file",
    context_id="fresh-judge-context", artifact_root=artifact_root)
write_terminal_job(job, judge_directory)  # 新目录；调用宿主后取得实际 host_result。
first = complete_terminal_job(judge_directory, host_result)

# judgment_response 为该次冻结的 response.json，不能使用修改后的候选。
review = prepare_source_verification(request, judgment_response,
    judgment_dispatch=first["dispatch"], model_profile=verification_model)
review_job = prepare_terminal_job(review, job_id="source-verify", transport="external_file",
    context_id="fresh-verifier-context", artifact_root=artifact_root)
write_terminal_job(review_job, verifier_directory)
final = complete_terminal_job(verifier_directory, verifier_host_result)
terminal = final["admission"]["terminal"]
```

`test_terminal_source_reviews.py`通过真实文件/回调传输与合成模型响应检查两个角色、
逐图交付、独立上下文、源覆盖、三值结果和首答保留；它不测量模型或真实物理准确率。

<a id="terminal-source-cost-controls"></a>

#### 输入体积与调用成本控制（2026-11-08）

普通本地运行使用诊断组合入口`validation/terminal/source_run.py`，
复用原有请求、文件传输与准入，不包含模型 SDK 或物理执行。
`prepare_source_run(request, artifact_root, output_directory, verification_model_profile=...)`
只离线准备首答；`execute_source_run(output_directory, invoke)`中的
`invoke(input_path, output_path)`负责调用文件宿主并保存结果。两种模型配置均显式提供，
没有默认降级推理强度。

- 默认`review_unknown=False`：首答先完整准入；候选为null时返回
  `status=judgment_unknown, review_status=unknown_not_reviewed, review_performed=false`，
  不创建复核作业，不标为完成两阶段复核。布尔候选仍须新的上下文独立确认才能释放。
  诊断时显式设置`review_unknown=True`。底层`prepare_source_verification`兼容旧调用，
  默认仍准备未知复核；传`review_unknown=False`时只对有效null返回None，错误仍抛出。
- 默认`evidence_encoding="lossless-json/0.1"`：原文件/哈希保留，JSON正文采用可逆列式和
  常量表示，附解码说明，并逐文件核验类型、数值和顺序的往返一致性。`validation/json_codec.py`
  保留所有时点、速度、缺失值和接触信息；不可压缩或非JSON文件保留原文。
  仅在字节哈希和除ID/路径外全部语义绑定相同时共享正文，每个原描述符保留为可引用别名；
  图片仍逐图交付。底层`prepare_terminal_job`默认不编码，旧作业维持原表示；新编码绑定进作业哈希。
- `write_terminal_job(..., max_text_characters=..., max_images=...)`在写作业和调用前检查
  预算，超限报错，不静默截断。`input-summary.json`记录准确字符、UTF-8字节、图片数量/字节，
  这些不是 token 计数或账户费用。
- 重复执行已保存结果只读返回，已有完成阶段可复用；输入/实现漂移拒绝执行。
  失败响应和中断的宿主调用不自动重试。突然中断留下`execution.claim`时先核查原进程与文件，
  确认停止后再处理该锁；已有宿主尝试保留，不自动重付。
- PhysPi 文件宿主将用量存于`<output>.usage.json`，与模型输入和严格结果协议分开。
  只记录SDK的`input/output/reasoning/cacheRead/cacheWrite/totalTokens`及身份、时间、停止状态；
  未报告或SDK初始化的全零计数保留未知。`input`是未缓存输入，缓存读取/写入单列；
  `reasoning`属于`output`的子集，不重复相加。SDK计数不等于ChatGPT额度或实际账单；失败也可能消耗。

在已安装`validation/requirements.txt`依赖、`PYTHONPATH`包含仓库的调用环境中，先离线准备：

```bash
python -m validation.terminal.source_run prepare --request fresh-request.json --root /path/to/evidence-root --output /path/to/new-run --verification-profile verifier-profile.json --max-text-characters 500000 --max-images 8
```

`fresh-request.json`由当前`prepare_source_review`准备；`verifier-profile.json`含准确的
`name`和`reasoning_effort`。使用PhysPi文件宿主时，两份配置的名称都必须为
`provider/model-id`，如`openai-codex/<可访问的精确模型ID>`；先在PhysPi中完成`/login`。
宿主使用`PI_CODING_AGENT_DIR`或`~/.physpi`，不同配置目录通过run的`--agent-dir`显式选择。
该宿主不支持未投影的二进制证据；使用可读JSON/XML和原生图片。
预算数值为调用者示例策略，并非内置阈值。检查
`judge/input-summary.json`后，在本地显式启动有模型调用的执行：

```bash
python -m validation.terminal.source_run run --output /path/to/new-run --host-script /path/to/PhysPi/scripts/terminal-model.mjs
```

prepare阶段的`--review-unknown`和`--raw-evidence`固定诊断策略，可用新目录对比原文/压缩和
复核强度。离线往返和字符缩减不证明模型正确理解新表示；真实质量与token收益仍需小样本冻结评测。
`test_terminal_costs.py`覆盖调用次数、错误隔离、独立放行、预算和可逆表示。

<a id="terminal-adaptive-evidence"></a>

#### 初末证据与一次补证（2026-11-09）

`prepare_source_run(..., evidence_mode="adaptive")`先交付所有对象的初始/实际终点观测、
完整原任务、来源几何/图片，以及单位、坐标参考点、身份、solver布局和限制。
`terminal/evidence_views.py`只选择已记录的数据，不生成判定或新采样值。
完整原文件及哈希保留；原录制完整性放在`original_record_metadata`中，不能充当当前模型
已看到的窗口。窗口位姿统计不随初末视图交付。采集打包入口
`physpi.prepare_source_evidence(..., model_view="boundary")`复用同一实现，
返回的`evidence_view`保留原始证据、可请求目录与资产检查引用；默认None保持原打包行为。

**统一记录输入（2026-11-11）。** 已有文件先通过格式适配提供明确单位、坐标、对象身份、
观测时钟及独立运行完结依据，再进入同一个视图接口。`recorded.read_recorded_poses`
读取标准化JSON位姿和独立completion文件；纯数据入口为`adapt_recorded_poses`。
当前标准化位姿是world/m/s/wxyz；其他单位或四元数顺序须由源格式适配器明确转换，
本入口拒绝不符声明，不猜单位。逐帧允许缺对象/缺通道，保留缺失，不能补零或插值。

`terminal-evidence/0.3`的`provenance.frames`与现有`terminal_window.samples`由同一
state样本选择路径读取。目录包含实际已有时刻；初末视图移除完整历史，只保留初末快照，
将录制完成声明移入归档元信息；扩展将所选历史放在`requested_window_samples`。
保留原始行值、单位和来源；没有明确源网格时只能请求`recorded`，不能把帧序号猜成源step。
最早一帧没有被独立确认为任务初态、或最后一帧没有被确认为实际终点时，原有效性标记不变。
录制结束、历史存在和窗口连续覆盖是三个不同事实。新来源复用该契约，不增加题号分支。

新协议`terminal-source-review-request/0.2`保留0.1全部判定语义，另加`evidence_catalogue`、
`evidence_round`；响应0.2须含`evidence_requests`。仅首轮null可请求最多8组数据：准确的
`evidence_id`、目录中的`entities`、原任务`source_pointers`、`channels`、闭区间
`time_range_s`、`sampling`和`reason`。通道为`pose/velocity/contact/controls/asset_properties`，
采样为`source_grid`或`recorded`；优先原任务已有网格，禁止插值、虚构降采样或静默裁剪。
所有`source_pointers`只以`request.source`为根；附件自己的`/payload/...`等路径不能
冒充该根下的地址，附件内容通过`evidence_ids`引用。
目录给出真实记录时刻；最早/最晚时刻不代表中间覆盖完整。视图保留实际交付时刻与缺失边界，
补证按已知字段选择请求的命名对象和通道，保留所有所选时点及原始数值。联动solver数组
保留原有索引/映射上下文，不重编号；单位、参考点、接触相位及限制仍完整保留。
部分通道仍缺失时单列报告。不存在的记录返回availability结果；文件、协议、哈希或预算错误
在执行阶段记为`execution_failed`；准备或入口冻结校验失败直接抛异常/非零退出，调用方须
同时处理这两种错误出口。第二轮的新上下文只看到原任务及初末/补充证据，不注入首答结论。

最多一次补证；补证后的响应不得再请求数据。首答、可选重判、独立复核最多3次模型调用。
有效未知默认不复核；任何布尔结果仍须独立确认。必要终态反例可直接进入复核，正例仍须满足
原任务全部必要条件。`evidence_mode="catalogued_full"`是同协议、同资产检查的全量A/B基线；
默认`"full"`和旧0.1调用保持兼容。CLI prepare使用`--evidence-mode adaptive`启用。
adaptive未显式设置字符上限时使用250000；超限报错，调用方可在新作业中明确调整。

资产检查缓存按终点与输入文件哈希绑定，每次补证及复核复用同一记录。可读证据可包含
`terminal-asset-properties/0.1`：相同`endpoint`、经核验的`source_refs`和`comparisons`，
每项含`entity/property/expected/observed/native_binding_verified`。支持
`collision_geometry/mass/material/joint_limits`，只比较确实提供且已绑定的值。
文件哈希一致、值相符和资产物理完整性是不同事实；缺少属性保持未验证，不能从位姿或图片
编造质量、材料或碰撞模型。该缓存不自动给出终态或整体资产完整性结论。
只有源要求的属性才构成验收义务。一个实体的某属性相符不代表其他实体或未比较属性相符；
`missing_properties`只统计该包中未出现匹配比较的属性种类，不是完整资产覆盖证明。
`test_terminal_adaptive.py`覆盖选择、请求准入、一次补证、独立放行、缓存与错误分类。

2026-11-13资产读回接入：PhysPi通过可选`AssetObservationV1`在build后和实际结束时保存
`asset-properties.json`，绑定运行、源代码、分支和实际step/time。当前实现为GeoPhys刚体原生
字段，读取有效质量/惯量、碰撞形状及过滤、接触材料和关节范围；不从源声明或图片补造实测。
三角网格/SDF的完整拓扑及pyramid/swing-cone限位尚未导出，对应属性保持缺失。
其他引擎没有此facet时明确报告不支持。

`physpi.collect_evidence`将存在的资产记录加入源哈希冻结；`prepare_source_evidence`自动封装
可读参数证据。可传`asset_baseline_ref`，它指向原资产独立参考运行的已采集state evidence；
取该参考运行真正episode initial的实际字段，与候选final核对。调用方负责选择代表原始资产的
权威参考运行，不能把任意候选初态当作原资产标准；同一运行自证被拒绝。默认按原生solver/body
名称对应，`asset_entity_map`可显式给出完整一对一映射。只在相同引擎、版本、backend及原生表示
及GeoPhys源提交/局部补丁身份下比较规范值；等效导入适配需要经过审核的参考表示，
不能由简单相等比较自动授予等效性。
CLI对应`--asset-baseline-ref`和可选`--asset-entity-map`，均使用JSON文件，且要求
`--source-evidence-output`。缺少原资产基线时保留实际观测、报告未比较；旧运行缺少实际记录时
报告`runtime_asset_record_not_available`，不重放历史脚本。

参数证据进入目录的`asset_properties`通道，可按原生对象补证。资产receipt的
`comparison_summary`分别统计记录值相符、不同和未核实，source-run结果保留同一receipt及统计。
目标/资产条件仍由`requirement_summary.terminal_categories`分别展示，且保持初审权限；
参数匹配不代表全场景覆盖，不自动放行原任务，也不证明整个过程始终未修改资产。
`test_terminal_assets.py`覆盖完整封装/补证、四类变更反例、缺证和运行/时钟/哈希绑定。
较大的规范属性值在模型视图及receipt中以`canonical-json-digest/0.1`表示，包含完整值的
SHA-256和UTF-8字节数；比较使用完整原值，原始文件及哈希保留。此方式适用于大量网格顶点，
不会抽样或截断几何来制造匹配。缓存按检查器修订区分，旧receipt保留原样。
2026-11-14准入连接修正：包含已绑定实际原生对象属性的`asset_properties`证据标为
`raw_state`，允许直接支持资产条件的终态反例；缺失清单及派生`asset_record_checks`
仍为`measurement`，不能单凭它们满足原生观察准入。布尔结果仍须独立复核。

<a id="terminal-relation-runtime-diagnostic"></a>
<a id="terminal-specification-diagnostic"></a>
<a id="terminal-model-pipeline"></a>

### 已归档的历史实验路线（2026-11-16）

旧规格生成／编译、schema与版本化词表、structured/visual独立意见和四路组合，以及关系benchmark、
历史core_snapshot和旧manifest/snapshot采集，已从当前Core支持范围迁出。
迁移前完整候选源码及SHA-256清单位于本地忽略目录
`workspace/tasks/terminal-experimental-routes-20261116/`，实验入口为其中的 `legacy.py`。
归档保留旧接口、依赖和测试，只供显式实验／历史复现，不是持续维护的第二份Core。
TaskEnv和validation均不导入workspace；原始数据、标签、历史结果及冻结摘要不改写。
PhysPi文件宿主仍可消费当前source两类job；它对旧job的兼容留给冻结producer，未修改其它仓库。
