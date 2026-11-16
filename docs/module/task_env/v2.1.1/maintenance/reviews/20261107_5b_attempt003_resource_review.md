# G05 5b attempt003：资源边界中间主审及维护者续作

结论：原 5b **BLOCKED / PARTIAL，尚未接收**，普通 attempt count=3。第三次原包先因资源边界无 native 返包；维护者随后授权同 attempt 的 CPU 续作，现又要求解除 6 GiB 阻碍并允许 Terra 后续开发。按该明确指示准备针对实际资源约束的同 attempt 续作，不记作普通 004；现有两个 release 和所有失败/偏差保留。该记录不是最终验收；完成剩余路线后仍需 Sol 对最终提交和证据主审。5c 尚未启动。

## 独立核对

- Core `codex/v211-stage5@b76f718e44e92126d2618692ba915ca5a123f99c` 为原输入 `a34262af95bf9ef65438ece5b2620ff2df553be5` 直接子提交；GeoPhys `codex/v211-g05-render-clipping@a6bf45b3422e31dfc632a58948e57fa4b686f1b0`，Core gitlink 指向该提交；Menagerie pin 和三保护输入无变化，两仓 `git diff --check` 通过。两个报告均有 release；时点检查无相关锁持有者，不能以时点扫描代替 release 收据。
- 分别重算原包 output manifest **8/8**、CPU followup **2974/2974** 文件大小和 SHA，均匹配。后者共 1084559434 bytes，manifest SHA `322e296a3b4ca6635f679212743e332e7271a64e1f6ae9827ae0ce951793f8a0`。Sol 在禁止 SDK/source 导入的 guard 下独立复跑 **37 passed**；未运行 source 解析、SDK、native、GPU 或 GUI。执行者额外报告的 COM 2 passed 按原日志保留。
- MuJoCo 与 GeoPhys rasterizer 的窗口各有独立同 run X11 drawable 和 RGB 两视角逐像素一致、图像 reader 五种负例；准确范围是实际 drawable，非桌面合成或主观观看。GeoPhys 正式 source-bound 光源实验与独立 MuJoCo 跟踪灯对照最大误差 `1.8287093395130682e-8 m`；现有测试不证明所有 representation。两路线 RGB/窗口仍是有界事实，已有图像 oracle 探索偏差和颜色约定限制不能消除。
- 真实输出存在既已披露的过程偏差：10 个零步 CPU 诊断未作事前零步预约；多数 CPU worker 仅 RSS 离散采样，不能证明进程树瞬时硬峰值。保留事实，不倒填预约或宣称硬限制曾被满足。provider docs check 的既有损坏链接和 frontmatter 报错亦保留。
- Isaac 在本次 followup 未启动；002 的真实窗口、帧、publication 只按其对应代码/配置保留。6 GiB 硬上限不能通过本机已证实机制同时约束 GPU 图形及计算；对已验证零 bootstrap 物理步或完整上界的要求也未完成。6 GiB 提升本身不能解决第二个问题。

## 维护者要求的资源修订

为完成原 5b，维护者要求允许后续开发；针对本次 003 续作，将原 GPU 6 GiB 可证明硬上限改为允许使用该卡实际可用容量（包括 CUDA 与图形），连续采样并如实报告设备总量、基线、全卡与可读进程值及采样盲区，不能把采样当硬峰值。实际 OOM 或严重压力时安全停止自己的资源、记录原因；有实质修复可在预算内重试，不逐次请求 CUDA 授权，不干扰其他进程。

同时允许 Isaac 的正常 SDK/App bootstrap，即使启动前无法严格证明所有隐式物理步的上界；启动后尽可能尽早监测并记录时间、物理计数、显式 step、warmup 和未知区间，对显式 steps 按原 10000 预算及已有 192 预约继续保守管理。无法证明 bootstrap 隐式步骤时准确写 `unknown`，不可宣称全窗总步数≤10000或补造预约。原重复 render 不推进已发布 physics 的**产品合同未改变**，须在可测正式边界检验。该决定改变资源证明要求，不将不可测数据当零。

仍维持原 003 总墙钟、source/native、单 worker、CPU、RSS、输出、两锁和保护等其他授权限制；按前序用量衔接，不重置历史账本，不扩大到其他阶段、下载、安装、其他 provider 或训练。续作在单一 writer 下由维护者手动转发，不创建或联系其他会话；完整报告由维护者转 Sol，最终若仍未接收则停止普通派包并按工作流开展维护者主导诊断。
