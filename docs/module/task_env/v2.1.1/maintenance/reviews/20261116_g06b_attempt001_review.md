# G06b attempt001：接触异常与渲染停滞专项主审

日期：2026-11-16。结论：**PARTIAL_NOT_ACCEPTED**。六格真实入口与设备链已有实现和有界证据，应复用；GeoPhys PickCube 数值稳定性、B=16混合渲染停滞及正确规格性能矩阵仍阻断6b。本轮是专项代码／证据审查，不声明全部六格逐项重新认证。

## 输入与本次复核

Core `1ad14dd82812ef69587e5ca6aabdb1a4e6cdc818`；GeoPhys gitlink/HEAD `9ef7768b4bd6c2b105c16f3d5fd75d2136b3ab2a`；Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。两仓tracked clean；保护日志SHA仍为`3b08b858f62dcbaa6521802455c76126f9876a3d6727c7586db90c94296ed6a8`。本轮未改生产代码／pin、未启动native/GPU/窗口。

本次新执行：`g06/test_device_semantics.py` **46 passed**；三个provider的`*-pickcube-camera-record-001`独立reader均通过，每份4个H5、14个边界、base/hand及4对终止/reset图像。首轮reader缺PYTHONPATH未启动读回，修正后重跑成功，两次记录保留。见[复核输出](../../../../../../workspace/maintenance/v211_g06b_attempt001_review/readbacks.json)。这证明所存边界的记录一致，不证明全部接触物理或性能通过。

[原报告](../../../../../../workspace/maintenance/v211_g06b_attempt001/report.md)、[修正性能表](../../../../../../workspace/maintenance/v211_g06b_attempt001/performance-b16-corrected.json)保留原时点。不得清理ignored证据目录；git commit不包含其中轨迹。

## 1. GeoPhys穿透必须作为待修问题

维护者提供的同seed同动作四路径比较：GeoPhys batch零臂力矩最大重叠10.327mm、弱保持4.998mm，scalar GeoPhys约0.803/0.903mm；受控动作约0.535/0.790mm。即便内部配置仍未全部对齐，这足以要求定位batch路线的构造／配置／求解问题，不能仅以“离散模式有局限”或改用一条成功动作豁免。

须区分：零臂部力矩不等于场景无载荷，机械臂仍受重力且可能通过其他mesh传力；指尖不碰cube不能证明其他部件未碰。下一轮应读出所有与cube/table相关的实际pair和力／冲量，不预设原因。

四路径对照逐步轨迹和隔离副本已删除，因此表中数字是维护者提供的定位线索，不能作为本轮可重新读回的最终证据。原attempt中另有保留的高穿透与受控轨迹，仍可使用，但不得混称同一四路径试验。下一包必须保全重现脚本、动作、全部初始状态、逐子步见证及独立reader。

### 已确认的接线问题

`task_env/runtime/providers/geophys/device_batch.py:GeoPhysDeviceBatchSession.__init__`接受`runtime_config`，却没有将求解迭代配置放入worker request；`GeoPhysNativeBatch`重新构造配置时将`body_contact_solver_iterations=None`。底层`rigid_batch.py`具备读取该配置的逻辑，但上层链断开。应修复通用配置透传和actual resolved facts；不能在任务里指定隐含64轮或只改诊断副本。

原保留的64轮探索读回最大桌面重叠约0.755mm，说明收敛预算是有价值的诊断轴；它不是对已删除四路径试验的配对证明，也不是“64轮即唯一修复”的证据。必须在同初态、同动作、同配置下做对照，解释残差／冲量如何变化，并复测成本。

### 必须验证、尚未证实的求解假设

- `batch/step_binding.py`采用速度kick→检测→contact/limit/equality/tendon耦合迭代→split修正→位置积分；`batch/constraints.py`每轮contact在前、非接触约束在后。需测最后一轮是否又破坏接触法向约束，而非直接改顺序猜测。
- `batch/contact.py`位置偏差使用固定0.2 relaxation和slop/max_bias，contact warmstart还要求接触点位移平方≤1e-12。检查实际warmstart命中、法向／切向残差、split位移是否符合预期，不能凭阈值本身断言错误。
- 核对cube freejoint属于广义坐标还是direct-body路线、质量矩阵和惯量坐标、接触Jacobian/有效质量、pose刷新时刻；排除漏施力、重复施力、漏积分快照与源几何变换错误。
- scalar与batch的接触算法/材料软硬、solref/solimp、integrator和CCD不完全相同；对齐可对齐的参数，逐一解释不可对齐部分，不以这个事实终止排查。

离散模式批准只解决运行配置选择，不是接收10mm级重叠的授权。连续模式该组合、AOT、既有治理继续未接收／按原决定暂缓，不新增本轮阻断门。

## 2. 渲染停滞是正确性／可完成性问题

保留stack在`scene_visualizer.write_frame_rgb8`的`render_frame`之后、`_fb.write_rgb8_to_device`之前的Taichi sync。因此可确定“此前GPU工作或依赖未完成”，不能仅凭Python栈命名为同步API缺陷、IPC死锁或RGB8量化错误。已修的高度缓存错误不能宣称解决此停滞。

优先以固定B=16快照独立renderer重现：无物理推进／无IPC、sensor-only、observer-only、sensor→observer尺寸交替、observer渲染而不present，再恢复完整链。在诊断作用域分段同步定位首个不能完成的kernel/依赖；检查活动分辨率、viewport、tile/task计数及容量、清零范围、camera切换、资源寿命和CUDA事件先后。保留故障点与操作序列，禁止无限重试、吞错返回旧帧或到处添加全局sync。

同scene渲染全部world保留；不通过只显示world0、降采样、换renderer或视觉外观调整绕过。修复后先小B sensor/window切换、B16失败组合和关闭后继续采图，再按影响恢复性能矩阵。

## 3. SHA范围纠正

新scalar/device观测已移除动态boundary SHA，device热路径已报告无每步SHA；133次/step来自旧scalar控制回执／提交链，不能据此把batch物理判为失败。删除观测叶子与更改公开控制回执是不同范围。

建议attempt002不混入版本化scalar receipt全面迁移：保留默认scalar现有公开合同，记录133次作为独立性能／架构欠账；禁止增加新逐步hash。将[迁移提案](../../../../../../workspace/maintenance/v211_g06b_attempt001/scalar-control-no-sha-proposal.md)单列，待维护者明确要求变更公开回执后实施。若后续批准，必须一起迁移producer/consumer、不可变值、重放／写入所有权、失败提交、旧H5读回，不能用常量或旧摘要顶替。本建议不撤销此前观测合同调整。

## 4. 下一包与不应重复的工作

[attempt002](../work-packages/20261116_g06b_attempt002_goal.md)聚焦接触修复、renderer停滞及必要矩阵补测；scalar GeoPhys依赖预检若确实阻碍正式对照，必须在生产owner落地最小修复和测试，不再只改即将删除的副本。

B16性能表当前11项通过/可复用、1失败、6未运行，其中2项在framebuffer修复前。按影响重新确认，不重跑完整历史矩阵。GeoPhys B4096逻辑载荷约37.6GiB及Isaac B256 RAM估算应审查输入/计算；真实资源不足是RESOURCE_LIMIT，不要求本机强跑。物理/renderer修复改变成本时，旧速度和扩容资格也必须重新评估。

新代码应保持声明驱动的共同builder、一个session/episode owner、公开device状态和固定Rasterizer；无PickCube/Panda特化、第二套worker／Recorder／身份框架。诊断runner已超过3300行，后续将本次新增接触对照和渲染复现按职责归入既有g06包的少数模块，保留统一CLI；不在产品增设测试开关，不把所有旧诊断重构当成本包前置。

文档检查：`git diff --check`通过；current validator仅报既知受保护`MUJOCO_LOG.TXT`基准差异，实际摘要与本包要求一致，历史链接问题79项未扩入本次修改。校验输出保留于review workspace。本次只提交主审、下一包及状态索引，未修改生产代码、pins或保护日志。
