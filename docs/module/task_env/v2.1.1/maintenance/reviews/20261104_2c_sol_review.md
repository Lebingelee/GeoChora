# G02阶段2：2c独立主审与有界收尾

日期：2026-11-04。主审：Sol。执行包：`V211_G02_2c_attempt001`。接收决定：**`ACCEPTED_BOUNDED_2C_REFERENCE_FREEZE`**；结合既有2a归因与2b代表实现，阶段2按 **`ACCEPTED_BOUNDED_STAGE2_REFERENCE`** 收尾，停在阶段2。

## 接收范围

- 2a已有界接收失败机制和人工控制变量诊断；运行有效不等于任务成功，不证明近奇异是全局唯一根因。
- 2b按原G02出口接收MuJoCo CPU PickCube seed31成功实现及受影响NutAssembly回归。实现为 `8fba7f8ff0d47f7de8e5ced53f2ecdeb21869238`，seed31在960 transitions完成，原task lift门限0.10m保留。
- 2c接收[已有成功参考冻结](20261104_2c_reference_freeze.md)、版本／配置／同run证据关联、复现入口和未决清单。此次只是文档封存，没有新运行、pytest、reader或provider import。

原2b attempt002按扩展工作包的G2 FAIL、G3 PARTIAL、G5 INCOMPLETE_USER_PAUSED及中止历史均保留，见[中止记录](20261104_2b_closeout.md)。代表性成功和后端差异定位是原G02出口；固定1000步下seed32也必须成功是Sol后加的门槛。此次恢复原出口，不倒改旧失败、不声称原包全部通过，不另开2b修复轮。

## 独立核验

输入实现commit为8fba7f8f；Luna文档提交为 `60929971d5789b3bc2a7708ca0d64668e8e9dc4e`、`fc8954edc5ef8e30415cf6a0db88d20f231cd20e`、`8abbd52fcb343cf71b87f04deb5a5483add8f6be`，主审输入HEAD为最后一项。三次提交相对实现commit只改包内九份文档／Skill，生产、测试、配置、子模块及阶段3–7均未变。执行窗口约25分52秒，未超30分钟。

已逐项核验封包成员、snapshot关联、参考manifest及sidecar、38项引用原件的size／SHA-256、保护文件、pin和允许路径。主参考H5为 `4a28d177ccf30cb0efa86a268496166616a00adf79e647e006770d3d412f4283`，reader／trace／worker／supervisor来自同run，来源commit为8fba7f8f，与旧人工dirty成功H5分开。71项窄测试及四份MuJoCo记录沿用前次独立主审，不重复执行。

Luna报告doc validator运行两次，但validation.txt仅保留第二次输出；本次只能独立确认最终一次为0 current errors、0 stale paths、96项历史问题，首轮PASS不作独立背书。不补造或重跑历史检查。Sol自身当前状态文档修改后另作一次文档检查，结果存入主工作区主审收据。

## 参考使用澄清

主参考worker_result中的 `resolved_public_config` 是公开环境配置；完整Controller／Planner／Solution策略还须结合冻结的8fba7f8f源码，阶段实际值见同run trace，不能只凭该字段还原全部策略。run按task_success／Solution完成结束，记录中的Env `terminated=false`、`truncated=false`；不把runner成功结束误写成Env终止标志为true。

Luna原参考页、原manifest和validation.txt按其交付时点保留。manifest SHA-256为 `7c4c515286e87b5f6495a2e44ff289839e56a986bb129abfcfd77adc59e73504`。其中tracked编排页的hash属于executor输出ref `8abbd52fcb343cf71b87f04deb5a5483add8f6be`；Sol更新当前状态后，应从该ref解析原字节，不改写旧manifest或当前hash冒充历史。参考页和raw本身未改。

## 保留未决与停止点

1. PickCube seed32固定horizon1000时lift0.08261901333725602m，任务失败；更长horizon未测。由PickCube路径时间owner及4c／7b复核。
2. GeoPhys在control_step3时间guard失败，无实际／期望时间值和完整H5；新增native接线未被接收为有效GeoPhys修复。由PickCube时间消费与GeoPhys session owner在3–4阶段处理。
3. Isaac delivery校验不代表native成功；本轮没有App／native运行，环境与route问题归3a。

不授予三后端等价、D0、Qualification或Release；后续控制迁移在4c重新验证，最终九格仍属7b。当前执行窗口已释放，不恢复paused goal，不派发或启动阶段3。

外部主审记录与commit收据：主工作区 `/home/lly/Documents/ChatGPT/GeoChora v2.1.1/handoffs/V211_G02_2c_sol_review_20261104/`。
