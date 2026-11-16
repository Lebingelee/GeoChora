# 清理后 Harness 短程运行与进程回收事故

本记录保留失败和执行偏差，不将其作为项目接收。原始计划与各次输出位于 `workspace/maintenance/v211_e11_e16_final_worker_20261114_001/`，没有改写 U4/U5 的冻结证据。

- `mujoco/seed_31`：HEAD `5ff99eaf`，构造、reset、3 个控制步、close、H5 同进程检查与独立冷读通过；短程矩阵 disposition 为 `PARTIAL`，不是 Solution 完成或资格结论。
- `geophys/seed_31` 首次因未设置 GeoPhys 解释器变量在 reset 前失败，构造成功、关闭完成、无 H5；`geophys-retry/seed_31` 补齐原冻结解释器后完成 3 个控制步、close 与 H5 独立读回，短程矩阵仍为 `PARTIAL`。两条记录均保留。
- `isaac/seed_31` 缺 Gymnasium，在 App 启动前失败；`isaac-v2/seed_31` 的 worker 输出目录检查拒绝监督器生成的依赖目录，同样在 App 启动前失败。各自无有效 H5。
- `isaac-v3/seed_31` 先编译导致 `pxr` 在 App 前加载，App 启动期间发生 USD 动态库符号错误并原生退出；没有 `run.json`，App 是否完成启动及正常关闭均为 **UNKNOWN**。锁收据只证明当时 Harness worker 进程组退出后锁被释放，不能证明 App 正常关闭或所有独立进程已退出。
- `isaac-v4/seed_31` 改为 App 先启动；实际看到 Harness worker PID `1595293` 及其另建进程组的 runtime PID `1596435`，后者启动过程可能打开第二个 App，违背本次计划中单 App 上限，确切 App 启动次数及隐式物理推进均为 **UNKNOWN**。观察到后向监督器 `1595176` 发送 SIGTERM；监督器和 Harness worker 退出后，runtime 仍存活并被重新收养，而共享锁已释放。实施者随后向 runtime 进程组单独发送 SIGTERM；事后 `/proc` 查询这三个 PID 均已消失，GPU 计算进程和共享锁持有者列表无命中。没有最终 worker/App close 收据、H5 或成功结果；不能推断正常关闭。四个保护输入 SHA 随后匹配运行前值。

此次事故暴露：Harness 原监督器仅等待自身 worker 进程组，而 runtime transport 独立建 session；父进程显式 `LOCK_UN` 可以在独立 runtime 存活时释放锁。后续修复与纯合成验证必须覆盖真实 transport 的锁 fd 继承、父进程死亡及不同进程组；在修复验证前不再启动 native。旧的仅证明 Harness worker 组退出的收据不能升级为全部 runtime 已退出的证明。
