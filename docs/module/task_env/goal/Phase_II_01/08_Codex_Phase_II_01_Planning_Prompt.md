# Codex — Phase II-01 检查点恢复与实施交接入口

更新于 2026-10-28。维护者本轮要求更新规划，后续考虑从 R03c attempt002 检查点恢复。
**本文提供后续工作包的准备与接收规则，不是现在启动实现或 native 的指令。**
旧 2026-10-23 审阅 Prompt 的“P00/R01–R07 尚未启动”已不适用于当前进度；原文可从 c30 及其历史恢复。
具体状态以 [07](07_Execution_Order_and_Acceptance.md)、[manifest](planning_manifest.json) 和各 slice 真实 Evidence 为准。

## 后续会话先读什么

读取 AGENTS 与 geochora、文档/架构/API/测试相关 Skill；核实际 branch、HEAD、dirty paths、gitlinks，
遵循单写入、保护 ignored Evidence。CodeGraph 有索引时先用它追踪 owner/caller，不重建索引。

依次读取 [README](README.md)、[00](00_Phase_II_01_Blueprint.md)、
[07 恢复合同](07_Execution_Order_and_Acceptance.md#r03c-checkpoint-recovery)、
[R03](03_R03_Physical_Attachment.md)、[10 补丁计划](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md)、
manifest 与当前包涉及的 R01–R07 文档。原 [validation receipt](validation_receipt.json) 是历史签署快照，
不因其 NOT_STARTED 字段否认后续明确授权，也不把原检查结果当本轮重跑。

## 已确认的输入

- 功能审阅检查点：`c30d97efa6ad169c205ea25d7917bc7b9a06e93c`。恢复时使用实际后继 HEAD，
  复核差异并冻结新输入；不 reset、不覆盖 attempt001/002 的 source/ledger/raw。
- R03c 静态修正接收、当前模块20项 S1；S2 不完整、S3 未运行。默认下一包为 R03c attempt003，
  同源四配置/四 H5 的原出口不变；旧启动额度已耗尽，新的执行窗口只来自后续明确合同/授权。
- 一个 Core Runtime、多 provider adapter；扩展现有 Core 构造入口，ReferenceTaskBinding 保持内部。
- 上游资产按已验证 USD 输入，不等待资产团队分支，不重做上游验证；实际运行固定 delivery/hash/报告。
- 首个 Isaac 场景为官方 Panda+刚体，后扩当前 Panda 导入；pip、独立 Python 环境、小显存单场景。
- 原 7/22、R04/R05/R06 blockers、R07 五任务与 P99 保留；F00–F07 独立记账，不能自动充当原 gate 的替代证据。

## Sol 生成一个完整工作包

1. 选择一个前置明确、已授权的原 slice 或 F 计划行。默认按 07 顺序；提前选独立安装/GeoPhys/集成行时
   明确理由与未变的 gates，不自行扩大全阶段范围，不按每个 Prompt 创建分支。
2. 列输入 HEAD、source/closure/build/profile/seed、保护路径、允许修改与本地提交范围、输出目录、owner/方法、
   真实调用链与 API/shape/unit/frame/顺序；复用 [10 补丁表](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#3-按层级定位补丁)，
   不另造 Runtime/Recorder/Controller/工厂或 provider-private bypass。
3. 将 implementation、受影响 S1、普通接线修正、必要文档/Skill同步与本地提交组织成同一个有界包；
   只有影响实现选择的实际未知才分准备包。未变的 c30 20 项或更强邻接证据复用，改变的输入才失效重跑。
4. 分开定义 source/hash/账本 preflight 与真实生产调用链 S1。调真实 admission/reset/runner snapshot/step/
   publication/record/reader/close，只替 native IO；补 Reference/Definition、requirements、乱序、Ack、fault/close 等负例。
5. 有 native 时，先冻结准确 case/oracle/tolerance、start/materialization/reset/physics/outer 预算、timeout/资源/关闭、
   失败保存与允许修复/重试范围，再引用后续维护者的真实执行授权。未明确授权不启动，不填虚构许可。
6. Luna 在同一窗口完成包后报告 commit、实际命令/Evidence、PASS/FAIL/BLOCKED/NOT_RUN、计数与限制；
   Sol 只读复核 diff/raw 后再接写入窗口、记录决定和必要摘要提交。不依据 Luna 自报 PASS 自动接收。

## 新补丁线的关键停止条件

- F00：固定 Harness 的 lifecycle false-positive 必须有实际负例修复；交接方真实 seed/H5 缺失时如实标记，
  不能把 mock/compiler 可调用当真实资产/Isaac 接收。
- F02/F03：USD entry/variant/闭包、free-body reset、typed frame/unit、native drive/receipt 不明时先解决 owner 合同；
  不能填假 MuJoCo slot、删除 guard 或绕过上游资产来源。
- F04/F05：native baseline 与 Core public Env/记录/读回分别给证据；同一 USD 三 provider 的要求不能用旧 MJCF cell 充数。
  GeoPhys single-Panda USD、split Attachment、R05 500Hz 是不同交集。
- F06：按真实 provenance 处理 synthetic/backend/provider；四报告、≥20 seeds、Oracle 与 pending Judge 包各有门。
  task/Expert/lifecycle/storage/qualification 分开；On/In/region 不替换为 lift。
- 所有行：独立无法确定项明确交维护者或 provider owner/网页 GPT，见 [10 第7节](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#7-分支接收人与待核实项)。
  不因难点擅自改预算/范围，不把 diagnostic 升格，不推送/合并/main/tag/Release 或自动授 Qualification。

## 本次文档修订的交接

本轮只做 docs 规划、交叉引用、manifest/hash 与静态文档检查，复用已有源码审阅。
保持实现、native、安装和 integration 未开始；后续恢复先取得一个明确工作包。
本次文档提交后的实际 HEAD 是下包的 Git 输入，c30 继续作为历史功能检查点。
