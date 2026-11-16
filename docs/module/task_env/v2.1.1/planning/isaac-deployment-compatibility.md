# Isaac部署兼容：v2.1.1与后续版本范围

2026-11-06当前：3b attempt003经[Sol独立复审](../maintenance/reviews/20261106_3b_attempt003_sol_review.md)在冻结范围有界接收，包括6.2真实F06短程和同次读回；原N08 FAIL保留。6.1／6.2共同部署与版本consumer有离线证据。主目标完成后的6.1独立App实际自报6.1.0-rc.26+release.49347.2d230af4.gl，模块origin与指定安装一致，但SimulationApp.close在300秒内未返回，状态VERSION_VERIFIED_CLOSE_TIMEOUT；只确认启动／版本／来源，完整Env闭环与正常关闭未通过。[3c](../maintenance/reviews/20261106_3c_attempt001_sol_review.md)已在显式profile及指定6.2切换边有界接收，不因此扩展6.1状态。

本页保留2026-11-05按维护者反馈及版本化官方资料形成的范围与差异依据，并按实际返包更新实现／运行状态；当前能力边界查[能力矩阵](../capabilities/README.md)。共同接口已接线不等于每个版本都已完成真实闭环。外部反馈调整单保留完整维护者需求和逐项验收，此页是仓库内执行入口。

| 版本 | 本次安排 | 真实运行证据 |
| --- | --- | --- |
| 6.2.0／发行包6.2.0.0 | v2.1.1保留既有PhysX state-only路径并修部署可移植性 | 3b短程执行及3c显式profile的MuJoCo↔Isaac6.2切换已有界接收；App／USD清理和受控worker退出0有同次凭据，不声称Kit自然析构已修复 |
| 6.1.0／发行包6.1.0.0 | v2.1.1实现与6.2共用adapter、部署选择、真实版本回执及同USD／closure消费 | 独立App实际版本6.1.0-rc.26+release.49347.2d230af4.gl，启动／来源已核对；close超时，完整Env闭环未测，不能声明完整6.1兼容通过 |
| 5.1.0 | 后续版本适配，未指定具体发布号 | 当前不安装、不提前宣称兼容；需初始化／推进／生命周期公共API映射及真实验证 |
| 其他／未知 | 不自动扩权 | 明确unadmitted或unknown及原因，不猜测版本 |

## 版本差异依据

已对当前路线选取40个公开接口条目逐项比较。6.1和6.2对应条目均存在；规范类型别名、空白与尾逗号后，参数／默认值／返回类型表达一致，支持复用现adapter的可行性判断，不是SDK全接口／ABI等价证明。参见[6.1 prims](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/py/source/extensions/isaacsim.core.experimental.prims/docs/index.html)、[6.2 prims](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/py/source/extensions/isaacsim.core.experimental.prims/docs/index.html)、[6.1 manager](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/py/source/extensions/isaacsim.core.simulation_manager/docs/index.html)和[6.2 manager](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/py/source/extensions/isaacsim.core.simulation_manager/docs/index.html)。

[6.2发布说明](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/overview/release_notes.html)记录Kit 110.3→110.4、DOF getter独立数组、update_app重入限制及质量getter不再补写缺失属性。当前有序同步worker、即时owned value投影和required物性声明／readback是有界复用方向；不据此分叉Env／Controller或复制所有资产。Newton／传感器／Cortex等非当前调用变化不自动扩大PhysX state-only实施范围。[6.1资产结构](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/robot_setup/asset_structure.html)已有UsdPhysics／PhysX及mimic示例，同资产复用有依据。

5.1的[manager参考](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/py/source/extensions/isaacsim.core.simulation_manager/docs/index.html)使用step(render=False)，6.1／6.2则使用steps／callback／update_fabric；5.1公开参考未列出当前setup_simulation等入口，需查明公共替代。[5.1 utils](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/py/source/extensions/isaacsim.core.experimental.utils/docs/index.html)也未列出当前play／stop／update_app组合。不能说5.1所有控制接口都不存在；延期依据是当前调用链确有不同的初始化与推进边界。

## v2.1.1的有界实现

- 路径／launcher：Core常规入口默认当前sys.executable；Isaac显式选择pip Python或SDK官方python.sh，统一CLI／环境／部署配置的优先级与冲突检查。复用现有launcher／3a transport；不直接运行Kit内部python，不把整个stdout当JSON，正确传递空格路径及argv，回执报告实际worker解释器。
- SDK识别：在原provenance／App owner集中核验pip metadata或绑定所选SDK根的VERSION／公开版本信息。缺pip distribution不等于缺App SDK；不能按目录名猜版本。分别报告环境缺失、版本未准入、required接口／schema缺失和native未运行。
- 共同接口与回执：在既有admission／native IO owner集中表达6.1／6.2共同要求，协调真实版本的生产者和校验消费者，包括App owner、native metadata和驱动回执；不能只删除==6.2.0.0守卫。沿用既有值和codec，旧6.2历史身份与旧F04/F05候选不自动扩权。
- 资产：优先消费完全相同的USD文件和依赖closure，不按minor版复制／重导出。内容hash描述资产，实际SDK／runtime身份另记；仅当具体API／schema或载入结果证明不兼容时再安排最小转换。旧证据不重标版本。
- 文档：实现完成后同步当前README、安装／已有安装指南、TaskEnv开发指引、API语义、矩阵、恢复页和相关Skill；不能先把拟议参数写成可运行接口。

## 实施顺序与验收边界

当前3a–3c均已按各自冻结范围独立接收。消费级依赖按实际host／engine／solver与worker角色判断；Core host安装清单不直接等于Isaac worker必需清单。真正required缺项继续拒绝，不能用未选GeoPhys/Taichi路线依赖误报SDK缺失。维护者已澄清GeoPhys原生solver不消费其MuJoCo求解路线依赖；原preflight owner已修正，不混装环境。本次3b GeoPhys pin更新服务于公共有效模型读回，与其MuJoCo求解路线依赖无关。以下早期协调顺序保留历史。

3a attempt001按原包复审，新增反馈不倒加门。attempt002先修普通reset闭包与原能力／worker缺口。3a独立接收后，3b完整包先纳入上述路径、SDK识别、6.1／6.2共同接口与准确身份接线，再在单独授权的native预算内验证三路线。不得以本规划开启3b、安装或native。

离线门覆盖两种部署、带空格路径、参数转发、pip缺失但SDK有效、SDK与版本不符、未知版本、required API／schema缺失、真实版本贯通及旧codec／资产hash兼容。正例通过既有生产consumer，以外部fixture替代SDK，不以目录名或伪版本自证。6.2已完成本包有界门；6.1共同实现与离线检查保留，辅助App关闭超时及未测完整Env闭环单列，不用6.2结果代填。旧F06启动18步只代表所属历史基线，不硬套所有SDK。

后续5.1复用同一配置、Env、Controller、Session、Recorder和资产owner，先定位实际公共替代API，再用同资产运行单个完整代表闭环；只有具体不兼容证据才改资产。暂不引入第二套provider骨架、全量render/batch矩阵、额外转换链或泛化版本框架。

调研原始材料在主工作区 `feedback/20261105-isaac61-62-interface-research.md`、40项comparison JSON及sources收据；完整维护者需求为 `feedback/20261105-isaac-deployment-portability.md`。它们的绝对路径和摘要随下个正式实施包冻结，不复制为第二份资产或运行证据。
