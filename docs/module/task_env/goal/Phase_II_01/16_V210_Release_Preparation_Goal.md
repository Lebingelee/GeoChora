# v2.1.0 本地发布候选准备

日期：2026-11-02。Goal：V210_LOCAL_RELEASE_PREPARATION_20261102_001，attempt001。状态：实施已授权，待维护者转交；未执行、未验收。

## 输入与目标

基线：codex/v2.1-integration@73b276f28cb80a1b7017bf6de61e77f34528989f；统一GeoPhys 67da1165149486d3ae3e779c13ce31af49e17d50不变。输入HEAD以完整冻结包snapshot为准，本规划提交不改变生产实现。

1. 修复任务class/YAML执行默认、renderer选择接线与optional Controller identity。
2. 根据已确认的逐文件映射将TaskEnv文档按v1.1.0/v2.0.0/v2.1.0和guides/api/contracts/capabilities/goals/planning/maintenance/history分类。
3. 补全全局文档、v2.0.0/v2.1.0发布资料、三个Harness说明入口和治理Skill/validator。
4. 正常合并develop遗漏历史；最终仅保留历史分支及develop/main/v2.1.0三个同候选本地分支。
5. 保留旧F/R工作树原HEAD、ignored资产和证据，仅detach并删除指定旧分支引用。

## 许可与范围

GeoChora/GeoPhys自有来源按维护者声明记录，license UNDECLARED；不代选许可证。第三方未决资产EXCLUDED，不分发/复制本机资产，不删除历史Evidence。
不改provider/Menagerie pin、不push/删远端、不新建/改tag、不发布Release、不启动native/solver/App/physics，不向其他线程发消息。Solution/F07/Qualification不在本轮。

## 验证和执行包

只做A/B必要离线合同、文档映射/链接/JSON/Skill与本地refs检查；不重跑历史矩阵。预期4–6小时，最大8小时含提交交接。同根因两次失败无新假设先问维护者。
完整包标识：sol_v210_release_preparation_20261102_001。包含luna_goal_prompt、逐文件document_migration_map及plan、branch_plan、budget、input_snapshot、manifest。
Luna完成后由维护者转Sol复核；本地候选收口不等于正式发布接受。

## 迁移位置

本文件在文档重组中移到docs/module/task_env/v2.1.0/goals/release-preparation.md；原Phase_II_01混合记录归版本history，不继续作为现行canonical。

