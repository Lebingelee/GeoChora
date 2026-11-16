# G06b attempt002 补充交接：B1对照、清理清单与最终验收可行性

状态：**PREPARED_NOT_DISPATCHED**。本文件供维护者完整转发给原attempt002执行者。维护者转发本包后，允许在以下边界恢复补充工作；不是恢复原包全部研发，也不是启动attempt003。保留attempt002已耗时、所有运行记录及暂停历史，普通attempt计数仍为2。本包只补充决定下一包所需的事实，不借“补充”继续一轮求解器开发。

## 1. 目标与输入

交付一份可供Sol直接制定attempt003的补充报告，回答四个问题：

1. 最终GeoPhys discrete／32配置下，B1与多行batch、B1与scalar分别对齐到什么程度？
2. 三后端×两任务的原始出口，哪些已有有效证据、哪些具体缺项？
3. 哪些无效探索代码需要移除，哪些有效修复必须保留？
4. 本机Isaac B16渲染能否执行；如果不能，下一包前需要什么明确决定？

冻结输入：

- Core checkout `/home/lly/Program_Files/Geochora`，分支`codex/v211-stage6-parallel`，输入`b2ea985c63534cb8c0f49dfdcfddb0d8c9efd438`及本补充包／索引的纯文档后继。生产代码基线仍为`f8c43d61163e6774b3869875842337b427781fe4`。
- GeoPhys阶段分支`codex/v211-stage6-render-device`，HEAD与Core pin须为`dd393187983798abac0e8d99c2426d64d4a8aa5e`；Menagerie保持`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。
- 保护untracked `MUJOCO_LOG.TXT`，SHA256=`3b08b858f62dcbaa6521802455c76126f9876a3d6727c7586db90c94296ed6a8`。核对实际HEAD、dirty及writer，不reset或清理原证据。
- 既有材料位于`workspace/maintenance/v211_g06b_attempt001/`、`workspace/maintenance/v211_g06b_attempt002/`；本包新输出只写`workspace/maintenance/v211_g06b_attempt002/supplement001/`，已有文件不覆盖。
- 使用既有`/home/lly/miniconda3/envs/geochora/bin/python`；MJWarp、Isaac依赖环境保持原版。本包不升级依赖、驱动或改环境。
- 先读[最新主审及第7节](../reviews/20261116_g06b_attempt002_scope_reassessment.md)、[原6b出口](../../goals/06-parallel.md#6b)、[attempt001原包](20261115_g06b_attempt001_goal.md)、[优化账本](../../planning/post-5c-code-project-optimization-diagnostic-ledger.md)。attempt002的`brief-for-sol.md`是当前证据索引，旧report和技术笔记按各自时点读取。

记录本包文件和实际收到的转发文本各自SHA，避免把Markdown转义后的字节摘要当成仓内文件摘要。核对输入之后开始，不因已明确授权的普通只读核查再次请示。

## 2. 本包权限与纠偏

允许：源码／diff／caller审查，已有数据离线独立读回，当前资源只读采样，补充报告和少量必要离线脚本；仅在缺少对应证据时，允许第3节限定的GeoPhys B1真实运行。使用既有supervisor和锁。

不修改Core／GeoPhys生产或测试源码，不改pins／全局默认／资产，不执行探索代码回退；本包给出具体移除清单，实际清理并入经审核的attempt003。不要为获取诊断数据临时monkeypatch solver或扩充3530行runner。若既有入口不足，定位缺失字段与最小修改位置后报告，不新造框架。

本包明确覆盖并取代原attempt002的继续研发要求：

- 不追求跨引擎接触点数、每点力、瞬时力乘dt或长期轨迹相等；不研究新的soft EFC／Schur／mixed交替求解方案。
- scalar mixed已知缺陷不自动阻断batch；但B1与scalar不能未经核实就标成一致。
- 保留GeoPhys指定三组输入的2mm几何回归和已测1.715mm结果，不把它扩大成跨后端普遍门，也不接受此前默认配置10mm级异常。
- 短程真实双指接触足够满足原包该项，不追加稳定抓取、R3、6c整批切换。已有102个双指接触子步等证据应作正面归位，不能用“不是完整抓取”将其抹除。
- AOT、GeoPhys主分支合并和既定治理暂缓；窗口外观继续由维护者人工验收。

## 3. B1与scalar：先读回，最多补缺失的目标运行

建立三列比较：**同native batch的B1与多行**、**同provider的B1与scalar**、**其他引擎参考**。不要混写为一个“对齐”结论。

### 已有证据优先

Sol已离线核对默认预算与64次预算的若干B1/B3轨迹，qpos/qvel差为0；这些不能替代最终32配置。当前32次B3轨迹在`contact-b3-trace-current-pin-32-full-001/`，500子步记录在`contact-trace-b3-current-pin-32-full-001/`。它们与之前相应读回输入一致。

已有scalar seed31对照在`contact-scalar-seed31-discrete-32-full-002/`，初态一致但接触后分叉；先使用这些数据，不重新跑scalar mixed研究。记录真实scalar与batch的contact／joint／coupled预算及其不相同之处，requested32不是全部策略相同的证明。

### 如确无对应B1/32数据，执行以下有界补齐

复用`g06/contact_comparison.py::replay`和runner的`contact-replay`，普通主解释器作为worker，不使用trace-worker或测试求解补丁。冻结动作文件为attempt002的`frozen-actions.npz`，SHA256=`9547370dfabcb16c008c1a3bfb2155675b86a7850d894c39001bddb44d13a30e`。

以B1分别选择源row1（seed31，衔接scalar）和row0（seed3706，覆盖实际双指接触），每次只运行原三组20／20／60 control steps，每步5个native子步；discrete、32次预算。已有同配置数据足够时直接复用，不再启动。两种输入是目标覆盖，不是无理由的重试次数限制；常规启动错误可在预算内修正调用，但不得修改产品实现。

参考命令，执行前核对当前CLI并替换输出为未使用目录：

```bash
PYTHONPATH=/home/lly/Program_Files/Geochora /home/lly/miniconda3/envs/geochora/bin/python \
  /home/lly/Program_Files/Geochora/task_env/diagnostics/tasks/v2.1.1/g06/runner.py \
  --run --case contact-replay \
  --worker-python /home/lly/miniconda3/envs/geochora/bin/python \
  --action-file /home/lly/Program_Files/Geochora/workspace/maintenance/v211_g06b_attempt002/frozen-actions.npz \
  --batch-size 1 --source-row 1 --iterations 32 \
  --output /home/lly/Program_Files/Geochora/workspace/maintenance/v211_g06b_attempt002/supplement001/b1-row1-32-001
```

核对构建记录的source、初始qpos/qvel、动作切片、dt/substeps及resolved32/32，再比较对应B3行。报告每组、每字段的最大误差和首次差异边界；quaternion按相同表示或符号等价比较，不能把混合单位qpos最大值当作统一物理量。若不同，先检查输入／相位／映射，不自动增大容差或修改求解器。

B1→scalar直接比较须给出：初始条件是否一致、接触前误差、接触后误差、首次分叉边界及已知算法差异。已有scalar数据不足时准确列缺项，不新增整段scalar实验。最终只能给“已对齐的部分／已知不一致／尚缺证据”三类结论，不能把同批量实现的B1当作scalar。

给attempt003提出按字段、单位、比较阶段划分的容差及依据，优先沿用已有合理测试容差；本补充不自行新增跨后端统一阈值。接触后数值不一致必须指向具体行为影响或已知路径差异，不能把所有力值差异都列为待研发阻断。

对Isaac、MJWarp只整理现有B1／scalar证据与真实版本；特别标清MuJoCo3.8.1与MJWarp4.0.1的身份。不为本补充启动这两个SDK。

## 4. 原出口与普通用户配置对账

在报告中用一张紧凑表列三后端×两任务，逐格归位：真实batch／动作与状态、Task计算、物理及接触、隔离与reset、相机／窗口、H5／关闭、性能。每项给证据路径、配置/pin、能否复用及具体缺口。

无需复制所有历史日志或重新跑六格；区别“缺证据”“已失败”“有证据但未更新索引”。若判失败，写明原门、具体反例和实际owner，不只写“物理尚未完全证明”。

检查普通示例中`geophys_contact_iterations=None`的实际行为，提供一个**无需诊断包**的完整discrete／32调用配置及预计落位。核对公共配置是否已支持，不在本包改默认或实施；明确未配置时的旧结果不包含在32次配置接收范围内。其他后端不注入GeoPhys参数。

## 5. 清理清单必须具体到代码

审查Core和GeoPhys自attempt001交付以来的diff和实际caller，给出简表：文件／符号、生产或诊断归属、有效成果、保留／删除／最小重构、受影响caller、所需最小验证。

至少覆盖：

- `GeoPhys/test/development/rigid/g06b_mixed_contact_minimal.py`的`G06B_DIAGNOSTIC_INTERLEAVE_ROUNDS`与monkeypatch候选、专用输出字段；保留原始缺陷最小复现的具体方式。
- Core g06 runner中`geophys-mixed-contact-minimal`／`geophys-mixed-contact-regression`研究入口如何退出本轮六格收尾路径，以及是否仍有其他使用者。
- world-Schur等原型究竟只存在于ignored证据，还是仍有tracked残留；不能凭笔记提到原型就要求回退生产代码。
- 迭代预算透传、DLPack生命周期、依赖预检、Graph兼容、FREE armature修复的实际有效成果与保留理由。

禁止批量回退提交链、删除失败证据或用关键词清扫既有算法。没有有效成果且增加结构负担的探索必须列入attempt003清理，不允许仅从验收表中隐去；有价值的缺陷复现可保留在正确上游测试owner。不新增框架、公共探针、每步hash、任务UID／Panda分支或复制runner。

## 6. 性能与Isaac资源：报告实际可执行范围

纠正索引与日志的对应关系。GeoPhys32次预算已有B16约10.894Hz、B256约6.697Hz；B4096按纯状态>10Hz规则为CONDITION_NOT_MET，无需重跑或尝试分配。MJWarp传感器／窗口低于10Hz不构成失败，10Hz仅用于纯状态扩容。

18项B16表分别标记可复用、受修改影响待补测、真实失败或RESOURCE_LIMIT；每项只给必要理由及下一次最短命令。renderer改变不自动使所有旧状态／H5证据作废，旧pin也不能自动当作当前性能。

Isaac只做只读资源评估：记录采样时间、MemAvailable、GPU余量、现有进程占用和已测B3/B16固定开销，区分进程RSS加总的保守性与真实可用内存；不读取无关进程内容、不结束他人进程、不修改swap。估计在8GiB显存／16GiB RAM下三项B16渲染是否可启动，给出依据和不确定性。资源状态是时点事实，不承诺稍后相同。

如果仍不可行，报告应明确提出一个可供维护者决定的资源例外，例如保留B3完整正确性、B16该组合RESOURCE_LIMIT；这只是提案，不能自行把未运行改成PASS或视作已获批准。不得把这一必需决定拖到attempt003末尾。

## 7. 时间、资源和停止条件

预计45～90分钟，补充窗口上限90分钟，包含报告整理；新增native累计最多20分钟，单run最多10分钟，原attempt002已耗时另列不清零。既有6GiB整卡工作上限、至少512MiB GPU余量、至少1GiB主机可用余量以及supervisor更严格限制继续适用；单进程组RSS最多10GiB。先取得现有native锁，串行运行，只关闭自己创建的资源。

超过最后正常阶段90秒无进展按既有supervisor保留栈并退出；编译期单列。新增证据控制在256MiB内，不保存整张渲染矩阵。不得改限制以容纳额外研究。

遇到具体源码缺陷，记录最小复现、owner和建议修复，不在本包实施；继续完成不依赖它的事实核查。无需追求本包把6b验收为PASS，补充报告的成功标准是交接问题得到可核实回答，而不是所有研发事项消失。不得以此启动新的诊断阶段、attempt003或其他agent。

## 8. 交付格式

在新输出目录交付一个`report.md`和一个`index.json`；离线reader、必要比较JSON和新运行目录放同目录，不另增多套账本。报告建议控制在150行以内，链接已有证据，避免再次写长篇逐实验历史。

报告依次包含：

1. 实际输入／prompt身份、代码是否未变、运行与新增耗时；
2. B1／多行／scalar的比较结果及差异解释边界；
3. 原六格剩余项、可复用证据和discrete／32普通配置；
4. 精确清理／保留清单；
5. 性能修正和Isaac资源结论；
6. attempt003建议：仅列具体修改文件、最小验证、预计耗时、必须先解决的维护者决定。若没有可信闭合路线，指出具体原因，不能用“继续研究接触”代替。

本包不提交产品或测试代码、不改变pins；ignored报告作为原attempt002补充证据返Sol，之后由Sol统一提交跟踪摘要。最终回复明确“补充交接完成／哪些问题仍缺事实”、报告绝对路径、保护输入检查，以及writer／native锁已释放。原6b维持未接收状态，返包后停止，等待Sol独立审核后再制定attempt003。
