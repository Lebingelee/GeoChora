# G03双包顺序授权：3b003 → 3c001

2026-11-06。维护者明确要求构建3b attempt003以及完成后的3c attempt001 Goal包，一次手动交Terra实施。外部目录 `handoffs/V211_G03_3b003_3c001_bundle/` 完整包含两个prompt、case、数值／接口／provider合同、预算、依据与输入verifier。当前仅PREPARED_NOT_DISPATCHED；count保持3b2／3c0，active_packages=[]。不创建对话、subagent或自动消息。

通常下一子阶段等待Sol独立接收；**本次按维护者新安排，改为先顺序完成技术实施，再一起交Sol分别复审**。这只修改该两包的执行调度，不授予Terra主审权或改变历史接收。3b技术全通过后保持REPORTED_PENDING_SOL_REVIEW；3c是在此技术依赖上的条件实施，不记3b已ACCEPTED。

1. [3b最后窗口](stage3-3b-attempt003-reassessment.md)由count2开始记3。原始物性目标与显式N08-v2、最终补偿case全部通过，无required unresolved；提交provider及Core、完整report/results/manifest和释放window。
2. bind-3c-input.py核对冻结case全PASS、原N08 FAIL保留、结果为本包新版本技术PASS、actual final HEAD等于报告、pin绑定、tracked clean、旧writer/native释放、3c未开始；仅向ignored 3c目录写准确输入绑定。准备时不捏造3c未来SHA。任何不符停止，不能手写绕过。
3. [3c首包](stage3-3c-attempt001.md)在绑定后只读核对并记count1，使用自身新预算实施真实切换／状态随机流／故障恢复。两包仍一个writer，不能并行或把前包未完工作转移给后包。
4. 最后返两个完整包与combined report；Sol分别看实际diff／证据和3c对3b的影响，作独立决定。两个技术PASS也不自动进入4a、push、merge、tag或Qualification。

若3b第三次未过，3c NOT_STARTED／count0，按既定上限转维护者主导人工诊断，不普通004／改名续作。若3c001未过，只返其首包，不自动002。此例外不延续到其它Goal，也不允许executor自行降低门。未被新安排改变的Goal orchestration、所有权及诊断规范继续适用。

每包主动预计120–180分钟、墙时上限240分钟；连续主动约4–6小时、总硬墙时8小时，各自包含实现、必要修复、测试、报告、提交和释放，不互借。native/source和资源限额见包内budget；Sol准备阶段无native／SDK launcher／GPU probe。维护者手动转交就是本次具体范围的实施入口。
