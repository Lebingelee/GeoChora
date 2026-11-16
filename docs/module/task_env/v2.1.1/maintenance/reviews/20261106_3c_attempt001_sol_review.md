# G03/3c attempt001：Sol独立复审

2026-11-06。决定 **ACCEPTED_BOUNDED_3C_RESET_REBUILD**，ordinary attempt_count=1；不需要实施返工或attempt002。已完成本包冻结的显式PickCube state-only profile、四条跨provider边和same-route reset、Core随机流、旧绑定失效、故障处置及逐episode记录出口。3a、3b及本3c分别获独立接收，G03按上述限定范围收尾；不启动阶段4，不授予最终矩阵或Qualification。

输入 `305b1fa5f99e3430b8e71ee6d0ed61586f6556af`，实现提交 `4f22b28d`、`bd678582`、`91c99d8c`及最终运行代码 `af6638684c071749c6ecb19f990b13afdb742cee`，执行交付HEAD `29855741e4e0075336854a9f7708c67d78a8a0aa`。复审基线 `237052c41f497ef60244114def81b4b7a7e147b5`仅在后者上增加3b主审文档；GeoPhys pin仍为 `dc2685e28c6c916fb6403a2342c04e0d2520aef7`。原[执行摘要](20261106_3c_attempt001_execution.md)、ignored报告／results／manifest不改写。

## 完成情况与证据

| 原包required项 | 已核实结果 | 决定 |
| --- | --- | --- |
| C1-01同一Env重建 | 实链MuJoCo→GeoPhys→MuJoCo→Isaac6.2→MuJoCo，五段各5步，Env对象身份由同run断言和日志核对，5个不同materialization及request | 接收四条声明边，未借close/make_env替代 |
| C1-02固定观测 | 构造时创建固定observation_space；30个边界符合shape／dtype／contains，9个实测速度与H5状态一致；hand_pose明确为ee别名 | 接收opt-in profile，原缺省观测不改 |
| C1-03随机流 | 独立PCG64重算task seeds为31、1177726415、1939546695、1059401220、145337961；再次显式31重现完整首样本；预检拒绝不提交候选流 | 接收显式seed重置／None延续；provider seed按已声明恒等映射，不另抽样 |
| C1-04旧数据／输入 | 实链拒绝旧ExpertAction，旧owned observation保持；生产Position消费者fixture拒绝旧publication／target，旧owned typed副本可读 | 接收当前owned交集；此profile未发布provider_alias，借用view失效未实测 |
| C1-05预检失败 | CPU live episode插入非法目标，session／source／状态／流保持，随后正常step；三目标真实source至selected preflight的合成终端拒绝记录 | 接收原门，后者不当作native故障 |
| C1-06破坏性失败 | 生产reset的materialize／部分reset write及部分advance局部注入；fault阻止step，无正常新transition，write未知保留；清理和close沿原owner | 接收契约证据；Sol另用合成session独立验证失败后显式reset重建并step恢复 |
| C1-07逐episode记录 | 公共reader独立加载五份同次H5，均T=5／T+1=6；对照sample／source／request／materialization／generation与30个状态边界；旧默认F06代表复核已记录 | 接收逐episode记录，未把不同codec强并成一个H5 |
| C1-08关闭与资源 | 最终Isaac worker PID1156024退出0；App close一次完成，无failure，native IO及USD snapshot lease均关闭；CPU返回、重复close及双锁释放均有同次日志 | 接收受控worker退出边界，不宣称自然Kit析构修复 |
| C1-09交付与停点 | 220输出／12,001,615 bytes逐项manifest匹配；实际绑定3b输入、结果摘要及提交祖先核对；writer/native已释放，未进阶段4 | 接收本包交付；原偏差和未知计量保留 |

## 实现与独立验证

变更沿configuration→`prepare_switch_reset`→既有SelectedReferenceEnv reset→原session／worker owner接线；新模块只准备候选配置和脱离当前流的RNG值，没有第二Env、Runtime或物理推进owner。目标从自身provider默认值解析，避免继承旧route／USD manifest。预检在旧session关闭前完成；进入替换才提交流和configuration代次、关闭旧资源并重建。首effect后异常记录failure phase、close和reset write状态，faulted时不发布正常新观测。成功发布后由既有episode owner清除fault。

Sol按当前源差异核对上述生产调用者，并通过公共canonical／structured reader独立比较观测、关节位置／速度、TCP／cube位姿、sample／request与代次；Isaac的typed boundary摘要与公开uint8身份吻合。五段源分别绑定，不要求MJCF与USD完整样本hash相等。记录中owned值与对象身份不是同一种证据：原Env／space身份和跨reset副本保持依靠同次执行断言及已审阅测试，静态H5不能单独证明Python对象身份。

独立guard组24项通过，6项三目标来源用例未选；另一个旧Position来源fixture试图导入`scene`，被Sol禁止provider／SDK导入的守卫阻止，记录为审阅环境受限，不计PASS，也不解除守卫。原包该用例日志为1 passed，相关生产source／consumer代码已审阅。另增维护者工作区的聚焦恢复检查1项通过，验证破坏性构建失败→阻止step→显式reset重建→公开step恢复；使用FakeSession终端，不能冒充物理运行。因此本轮独立共25项通过、1项受守卫阻止，和Terra报告的58、3、13、12项按各自命令分列，不叠加成native覆盖。

Sol的native／SDK launcher／physics／GPU／render均0；独立材料位于维护者工作区 `workspace/reviews/V211_G03_3c_attempt001_sol_review/`。CodeGraph对新owner索引滞后，本次读当前源码及提交差异，不重建索引。三份保护untracked及provider／Menagerie pin保留。模块Skill仅按已验证的当前路由和接收状态更新；不将未运行的新agent冷启动记为通过。

## 退出码−11与适用边界

早期−11失败保留。最终策略是在专用Isaac worker完成session、App、source、socket清理和close ACK后受控退出；服务端清理失败返回错误／非零，客户端继续核对真实退出码并保留首错。它符合本包资源关闭出口，不能描述成CPython／Kit自然析构已经修复。没有为此再启动9组历史native或扩大关闭矩阵。

本次只接收PickCube、R3、state-only、单环境、gravity_compensation关闭及声明的MuJoCo↔GeoPhys CPU／MuJoCo↔Isaac6.2 CUDA边；不外推GeoPhys↔Isaac、Nut、Controller／renderer通用切换、batch、RGB或新effort接口。固定hand_pose是ee兼容别名，不是手掌原点；无provider_alias的结果不能证明通用借用view支持。

3b原N08 FAIL与[3b有界接收](20261106_3b_attempt003_sol_review.md)保持；3c短程保持动作不验证任务成功或消除默认关闭时下沉。6.1独立App是主Goal之后的辅助检查：版本／启动核验成立、close超时，完整Env闭环未测；它不属于本包冻结的6.2必达边，不因本次3c接收而通过。5.1仍延期。

3c窗口08:49:09–09:55:27，约66.3分钟，在240分钟上限内。已记录native/source计时1578.066 s；已知owner发起1501子步，失败bootstrap／内部启动有未知，不能当全量上界。树RSS峰值7,546,245,120 bytes；全卡峰值3,043,033,088 bytes不是独占VRAM。早期一次无双锁source解析及丢失测试观察句柄均保留，后续对应重跑不抹除原偏差；原缺结果不计通过。这些披露项和当前有界限制均不构成重开3c实施的理由。

G03收尾：3a routing/admission接收、3b冻结三路线执行与有界Panda补偿接收、3c本profile重建接收。下一步等待维护者后续安排；不自动派attempt002、进入阶段4、push／merge／tag或提升Qualification。
