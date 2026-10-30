# Codex — Phase II-01 当前规划与后继派包入口

更新于2026-10-30。**本轮仅调整文档；F05 successor尚未派包、实施或启动native。** 当前F线owner为`develop-full`；`develop`同步规划与已合入checkpoint，camera分支继续其独立R线。文档副本不代表分支具有相同实现。

## 先读当前入口

读取AGENTS.md及适用的GeoChora/TaskEnv、文档/API/测试Skill，核branch、HEAD、dirty、gitlinks和writer。CodeGraph存在时先定位真实owner，不重建索引。

依次读取[README](README.md)、[07执行表](07_Execution_Order_and_Acceptance.md)、[10历史补丁与结果](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md)、[11后继路线](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md)、[12执行指南](12_F05_F07_Execution_Playbook.md)和`planning_manifest.json`。原R线事项另读其slice文档，F线本次改向不改变R07三任务当前合同或P99；F06/Harness的20-seed门不能回写成R07新前置。

## 本轮确定的规划方向

- 同一物理来源、可追溯的多种表示：固定Menagerie Panda共同基线，MuJoCo/MJCF、Isaac/USD、GeoPhys/USD；不要求每个Provider原生解析相同后缀或产生相同数值轨迹。
- 一个Core Runtime/RuntimeSession、多provider adapter；复用Source/Asset/Scene/Joint/Frame、Controller、Recorder等既有owner，不新增平行Scene IR。
- r009与原MJCF的equality/tendon/驱动语义尚须盘点，旧native物理门不证明共同source-family全特性等价。关键loss/unknown阻止依赖它的后继native。
- 原F05同USD三Provider门在后继规划延期，旧F05仍PARTIAL、原门未通过；官方Panda→GeoPhys兼容单列，Isaac资产/USD一等输入策略不取消。split Attachment移交F07候选时保留旧门未通过记录。
- 旧F00–F05的Evidence/接收/失败和普通attempt001–003保持原样；没有默认F05 attempt004，首个successor窗口仍需新的精确Scope Decision与完整包。

## 生成实际工作包之前

1. 明确选定stage/cell、required/deferred表、共享源和实际representation/build/solver/device/profile。优先处理S0语义门；只因影响实现选择的未知拆准备包，已知owner的实现/验证/收口可合在一个窗口。
2. 核对source closure/license/revision、recipe/checker/report、原始与派生bytes可恢复性、真实provider候选和gitlink。旧ignored fixture/cold-checkout限制如实保留；缺输入报SOURCE_UNAVAILABLE，不猜路径。
3. 追踪真实Core public factory→admission→reset/control/step→typed state→Recorder/independent reader→close，列owner/方法及缺口。`ReferenceTaskBinding`保持内部，不用provider-private状态或伪造pose/零速度补洞。
4. 固定实体/Joint/Frame对应、轴向/单位/COM/四元数/控制模式。不同representation和Artifact的精确hash分别保留；通过对应与语义证据建立逻辑一致性，不强行同hash。
5. 冻结环境合理性、空载控制器hold/追踪、gripper/free-body、Task各门和oracle/阈值；FK一致、Ack、正常horizon、Task success、Expert completion、storage、Qualification分别判定。
6. 在一个完整包内给出implementation、受影响S1、必要修复重跑、文档/Skill与本地提交范围。native需新授权且先冻结代码/输入/plan、资源/timebox/累计steps/RAM/VRAM/disk/锁与cleanup；不默认一次launch，也不继承旧额度。
7. Luna一次一个未完成包，报告/释放writer后Sol独立复核。F06只按新Scope Decision选择的ready intersection推进，保留真实任务四报告、至少20 seeds、Oracle与pending Judge；F07/Newton另定实际交集。当前不发上述任何包。

## 文档同步与历史

本轮只改规划、入口、manifest/hash与Skill的计划说明，未运行软件测试/native、未安装依赖、未更改source/gitlinks或原始Evidence。历史2026-10-28的R03c/c30恢复说明可从Git历史恢复，不能继续作为默认“下一包attempt003”。当前执行事实见各分支本地slice记录和F线owner记录。

本轮范围：`develop-full`/`develop`各自文档提交；camera仅准备补丁，待其writer释放后重新核HEAD/冲突并同步。主仓不为切换分支打断camera；`develop`使用一个仅文档临时checkout，提交后清理，零新branch。main、发布分支与历史worktree保持。
