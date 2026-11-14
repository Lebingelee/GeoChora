# C4：Isaac task RGB 完成证明与诊断输出

输入 `f80fbb02`。本单元仅调整 Isaac task RGB 常规采集中的详细输出；原 E00～E16 有界接收、旧日志和历史 H5 不重开或改写。App、physical session、task sensor、observer、CameraGeometry 和 source owner 未变。

## 字段／消费者核对

| 事实 | 当前消费者与处置 |
| --- | --- |
| dispatcher 前后 compute count、reference time | task capture completion 的新鲜性／当前 physics time 门；保留计数、参考时间和原门限。 |
| Fabric 前后 external time、stage ID | completion 要求两次 Fabric time 匹配 provider clock，stage ID 与时间保留在 completion evidence；读取失败不补值，原门继续拒绝。 |
| sensor payload、frame ID／freshness、paused timeline、零 delta、playSimulations 恢复 | 同步 completion、现有 observation metadata 和故障判断消费；原字段及检查保留。重复 render 仍先后检查同一物理 clock。 |
| provider／episode clock mapping 与 epoch | 原 episode 内一致性检查和 completion evidence 消费；保留，移除重复的独立打印。 |
| viewport handle、render product 路径／分辨率／camera rel、Replicator status／待写时间、完整 stage 与 settings 快照 | 旧代码只拼接并打印 `G05_TASK_RGB_RENDER_DIAG`，无正式完成门或当前生产 reader 消费；退出常规采集。历史日志与 decoder 不改。 |
| `G05_TASK_RGB_SYNC_CAPTURE` | 只重复打印仍保留在 completion evidence 的同步捕获事实；移除独立打印，既有 receipt 结构和字段不删。 |

renderer 正式完成仍通过同一个 session 和 App；task sensor 与 observer 资源仍分开，camera binding 仍校验实际 transform／optics、旧 generation 和 source。两条实际 caller 共用的采集函数与 session 私有资源交叉紧密，拆为相机模块会增加私有状态穿透，因此保留原位置。MuJoCo visual-only 与 GeoPhys raster 的接口未改，按原源码身份复用既有受测证据，不将其声称为本次新跑。

## 验证

- 正式 pure/fake guard **261 passed**；原 camera/renderer 纯检查保留。没有用 fake 像素或源码扫描冒充原生采图。
- [短程 Isaac 计划](../../../../../../workspace/maintenance/v211_c4_task_rgb_20261114_002/plan.json)冻结当前源码 SHA、USD manifest SHA `6cb07d216689d1e0b6f31ef127d9a511906be90c2acbecb9a30667cdebf113e2`、共享锁、App 上限、显式子步／墙钟和资源 scope。用户已授权 CUDA 与 EULA。PickCube R3、seed31、腕部 256×192 task RGB：reset 首帧 → 一次非零 action／5 显式子步 → 同一物理边界两次额外 task-camera capture → 再次 reset → close，**PASS**。两次额外采图物理 step 增量均为 0；第二 reset 的 episode 和 renderer generation 与首轮不同。SDK 隐式 startup/reset 推进仍为 unknown。
- reset／step／reset 的最终 dispatcher count 增量为 10／5／11；reference、Fabric 与 physics time 分别一致于 0.036／0.046／0.036 s。task sensor 的真实图像及绑定通过现有 native gate。该有限运行不代表任意相机、完整 Solution 或新资格。
- [关闭后独立 H5 读回](../../../../../../workspace/maintenance/v211_c4_task_rgb_20261114_002/isaac-rgb-short-r2/readback.json)使用 `load_structured_control_records_h5` 和 h5py：1 transition／2 observations；两帧均为 finite float32 RGB，字节 SHA 与同次返回帧一致。H5 SHA `f2ecef2b9620e9b27954294c078151e203d25212d489e32ba93a5fecf5dd8ff9`。external_stop、terminated=false、truncated=true、task success=false、Solution completion=null；未运行 Solution。`load_physical_recording_h5` 不适用于该历史 F06 witness，未将其误写为通过。
- 首次[窗口](../../../../../../workspace/maintenance/v211_c4_task_rgb_20261114_001/plan.json)在 Env 构造时缺 Gymnasium，0 显式物理步；App 关闭期间进程以 -11 退出，无完整 close receipt，scope 已空、锁已释放。保留失败而不称正常关闭。诊断按既有 Isaac 路线预加载现成 Gymnasium／h5py 后重新冻结；[重测 supervisor](../../../../../../workspace/maintenance/v211_c4_task_rgb_20261114_002/isaac-rgb-short-r2/supervisor.json)退出码 0、scope 空、锁释放，最终 native IO／source lease／App close completed。首次 reset 的 session 关闭而共享 App 尚未关闭，最终 close 才关闭 App，不将前者误报为 App close。

## 度量与原账回看

生产 `isaac_native_io.py` **+11/-91/net -80**：文件 3,513→3,433 行，采集函数 412→332 行。详细 SDK 状态装配和三类重复日志退出常规路径；保留一个窄 Fabric witness 读取，formal completion gate 及 completion receipt 字段未删。诊断新增 134 行用于本次真实短程验证，另增本记录，不计作生产删减。

回看 REN-02～07、RUN-04、TEST-01／03：task/observer 及固定 camera identity、单一 App／physics owner、clock 和关闭事实保持原边界；未修改其他 renderer factory、native 读回或 source admission。四保护输入与两个 pins 同 E14 基线，冻结 archive 与已有例外保留。无额外目录/ref 清理、merge、push、tag、发布或 G06；C5 的两条完整 Solution、最终 reader 与独立复核仍未完成。
