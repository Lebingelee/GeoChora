# P1.8 Recorder stability.history 无损去重 v2

**状态：ISOLATED_RECORDER_ACCEPTANCE_PASS。** 本次提交只优化记录表示及诊断入口，不修改 controller、planner、资产、solver、force cap、Timebase 或任务/验收判定。它不是新 FULL 成功或正式 D0/D1/D2 qualification。

## 实现及兼容边界

`ExecutionRecorder` 的内部扩展接口新增可选 `owner_content_fields`，使用 `(owner, field)` 精确匹配。旧 `content_fields` 与 `_actions` 默认行为保留。非法 selector、不存在的 owner/field fail closed。blob 持有独立数据，调用方后续修改不会改变记录；展开后的 snapshot 值和 integrity hash 不变。schema 和既有 reader 不变，未扩展 Core facade。

诊断 `LiveRecording` 支持显式 `stability-history-refs-v2`，只为 `stability.history` 增加 content-ref；旧默认 `owner-fields-v1` 保留。recipe 写入 `recording_storage_variant`、`owner_scoped_blob_fields` 和 recorder source SHA，结果也显式标记版本。不要把新容器冒充旧源 identity。

FULL diagnostic runner 新增 `--recording-storage-variant`。所有控制律、stage gates、终止与 lifecycle 语义保持原样。新增 `recording_storage_smoke` 是独立 subprocess 的有界验收工具，固定 MuJoCo 500 Hz、2,500 transitions，不能将其当作 FULL 测试。

## 隔离验收

68 项 recorder/guard/lifecycle/native-math 测试 PASS。覆盖 scope 精确匹配、同名其他 owner 不被捕获、未知 selector/variant 拒绝、caller mutation isolation、旧 reader、lossless snapshot 和坏 blob 拒绝。已有 v1/v2 reader 和 clock 负例保留。

相同 ResetSample、原控制候选，分别执行 baseline/candidate 两条真实 500 Hz native-ramp 前缀：各 2,500 transitions / 2,501 boundaries / 5.0 s，覆盖 approach_nut、descend_to_handle、close_gripper、verify_lift。两条录制的全部 state、feedback、readiness、Requested/CanonicalActions、native targets/acknowledgments 和 owner 内容精确一致；只存储表示和显式 recipe 存储版本不同。

两条均通过 H5 byte roundtrip、完整语义校验、original full-mapping reader、六个实际边界的 owner restore，以及 2,500 步 canonical reconstruction。MuJoCo PickCube seed 31 和 73 的既有 R1 回归均 PASS。GeoPhys 新存储 candidate 未运行。

| 5 秒真实录制前缀 | baseline | candidate |
|---|---:|---:|
| 逻辑 JSON | 105.191 MB | 64.238 MB |
| H5 文件 | 18.207 MB | 7.174 MB |
| freeze 校验 | 4.167 s | 3.493 s |
| save 前完整校验 | 4.189 s | 3.506 s |
| 编码/压缩/写入 | 2.509 s | 1.274 s |
| read/compare/hash | 1.764 s | 0.930 s |

这是一对前缀测量，不是完整 rollout 性能保证；总验收进程包含物理模拟、旧 reader、restore 和 reconstruction，不能只用 I/O 数字声称端到端 2.45 倍加速。

## 完整源文件离线对照

另外，对同一既有 primary-only continuation FULL H5 做过只改 history 表示的 counterfactual。所有 12,160 boundaries / 12,159 transitions 独立逐记录比较和完整语义检查通过。

逻辑 JSON 899.457→294.012 MB；压缩 H5 189.516→31.170 MB。审计 wall 两次分别为 baseline 71.54/71.48 s，candidate 29.19/29.10 s，约 2.45 倍。这是离线审计，不是新 live FULL 录制。

summary 审计 RSS 为 baseline 159–164 MiB、candidate 197–199 MiB：新增唯一 blob 常驻约增加 40 MiB，必须保留这一取舍。old full-mapping reader candidate 仍约 1.43 GiB，不建立低内存 replay 能力。原 primary authorization 失败仍保持失败，不会因存储优化变成 FULL PASS。

## 使用

从仓库根目录，在独立 subprocess 中执行有界 recorder 验收（输出路径必须尚不存在）：

```sh
python -m task_env.diagnostics.phase1.integration.recording_storage_smoke \
  --variant stability-history-refs-v2 --output <fresh-evidence-directory>
```

执行已有 FULL diagnostic 时，可显式添加：

```text
--recording-storage-variant stability-history-refs-v2
```

本次未新执行 FULL、完整 D0/D1/D2 或正式跨 provider qualification。原始验收用 local smoke.py，提交中的 module 是该 harness 的独立入口封装，CLI/bootstrap 已检查。

首次新增测试因相对 import 失败、首次隔离 smoke 因相对 profile 路径缺失而在物理前失败。两项设置问题均已修正并保留 Evidence；没有删除断言或扩大容差。原 MUJOCO_LOG.TXT hash 未改变，未清理历史 Evidence。

源码、测试命令、结果和 SHA256 见 [results.json](results.json)。原始 H5、native/contact sidecars 保留 local workspace，不提交 Git。该报告是 recorder 开发验收记录，不替代此前 FULL/replay 状态报告。
