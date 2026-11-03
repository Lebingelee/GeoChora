# G07：任务复用、最终验收与文档收口

规划标识：`V211_G07_INTEGRATION`。3 个子阶段；只收口已冻结范围，不恢复旧 P99／F05 研究门。最终能力仍是精确交集的有界工程结果，不自动授予 Qualification。

<a id="7a"></a>
## 7a：NutAssembly 复用与调用者兼容

- **输入／依赖：**4c、5c、6c，阶段 1 的任务／配置兼容决定。
- **工作：**在 NutAssembly 已支持后端复用公共构造、配置、施控、reset、render、obs 和记录；核对受影响 TaskDefinition／旧 BaseTaskEnv alias／examples／LIBERO 代表 caller 及 learner／vector wrapper 边界。
- **检查：**无 PickCube 名称／Panda维度硬编码泄漏；具名通道与Robot组件binding复用，任务差异留 task；fixed-space consumer 对 action 变更有明确处理，未迁 caller 有保留路径。选最小相关检查，不要求完整训练和全部 A123 重跑。
- **交付／出口：**代表性真实复用、受影响兼容结果和明确未迁列表；不宣布所有任务已统一，也不移除 2.x 承诺保留的 import 名称。

<a id="7b"></a>
## 7b：稳定输入下的最终矩阵

- **输入／依赖：**7a，冻结的最终 Core／provider／source／Controller／Solution／renderer／device／seed／horizon／预算和 oracle。
- **工作：**执行 PickCube 三后端×三 seed（初始 31/32/33），目标 9/9 task-success；收口阶段 3–6 已冻结的同一Env切换、Controller／7＋2／BodyWrench与贡献组合、图像与并行代表性交集。
- **检查：**runtime validity、原任务 predicates、生命周期有效成功、Solution completion、图像同步、独立同运行 H5 读回及 close／进程清理分别报告。对受影响输入才重跑；可以复用仍精确匹配的更强证据。
- **交付／出口：**九格成功与其他独立门都有可审核证据；失败／NOT_RUN／未测项如实保留，不能用 runtime-valid 或不同 run 的部分结果拼接成通过。

最终九格不等于每个 backend×renderer×Controller×batch 都跑三 seed；组合覆盖在阶段 1 冻结，各维度有最小真实代表例。不同 solver 不要求轨迹或像素逐点相同。若九格有失败则本门未完成；范围改变须维护者决定，保留原门和失败历史。

<a id="7c"></a>
## 7c：版本文档与能力记录

- **输入／依赖：**7b 结果、各阶段实际 commits／报告／原始 Evidence；失败也需收据，但不能以文档完毕代替版本全部验收。
- **工作：**保持已确认设计与已实现／已验证能力分列，更新本版协议状态、公共 API／配置／迁移和示例、单一矩阵、当前导航、恢复页及相关 Skills。复核文档校验器覆盖；检查旧候选状态／基线文字的时点，不重写历史接受决定。
- **检查：**文档结构／链接／JSON、公开例子与真实 caller、能力语言和证据身份、dirty／gitlink／refs；Skills 按源码和调用者刷新，不只做文字同步。记录检查运行与未运行项。
- **交付／出口：**版本文档准确描述实现与未支持组合，7 个 Goal 的摘要和编排索引可恢复，原始日志／图片／H5 不入库。必要本地提交与审阅意见完整。

## 发布边界

当前文档与阶段接收不授权 push／merge／tag／GitHub Release，也不自动选许可证。第三方资产来源／分发未决项保持原状态，不因技术接通被改为获准分发。若维护者后续要求发布，单独冻结发布范围、许可和版本材料。
