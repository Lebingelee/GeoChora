# TableCraft

TableCraft 收录 SimDataKit 冻结版本 `franka-scene-50@2.0.0` 的全部 50 道中文任务，保留原题顺序、`fsc2-*` ID、题面、私有验收条件和相对资源路径。机器人为固定底座的 Franka Panda，场景包含三层抽屉和 24 个可操作物体。

| 分组 | 内容 | 难度 | 题数 |
| --- | --- | --- | ---: |
| A | 原子技能 | L1 | 11 |
| B | 指代与属性 | L2 | 9 |
| C | 空间布局 | L2 | 10 |
| D | 长程组合 | L3 | 12 |
| E | 灵巧姿态 | L3 | 8 |

## 浏览与准备资源

从 GeoChora 根目录运行，先安装 [validation 依赖](../../validation/requirements.txt)。

```powershell
python -m bench_deploy.tablecraft list
python -m bench_deploy.tablecraft show fsc2-stack-small-on-mid
python -m bench_deploy.tablecraft show fsc2-stack-small-on-mid --include-truth
python -m bench_deploy.tablecraft prepare-assets --source-release ../SimDataKit/datasets/releases/franka-scene-50/2.0.0 --output-directory workspace/assets/tablecraft/2.0.0
python -m bench_deploy.tablecraft show fsc2-stack-small-on-mid --asset-directory workspace/assets/tablecraft/2.0.0
```

`list` 按发布顺序列题。`show` 和 `model_prompt()` 默认返回公开输入，审核方通过 `--include-truth` 或 `get_task()` 读取完整的 `low-detail-task/1.2.0` 记录。原始数据见 [tasks.jsonl](tasks.jsonl)，冻结版本、文件摘要和演示索引见 [source.json](source.json)。

`prepare-assets` 从指定版本核对文件摘要，将共用 USD、Panda 模型和逐题依赖准备到一个新目录。`scene_resources()` 解析该题的资源和抽屉初态。实际运行还需仿真环境接入；当前包提供数据与资源准备入口。场景和模型的使用条件见 [LICENSE.txt](LICENSE.txt)。

## 查看参考运行

```powershell
python -m bench_deploy.tablecraft reference fsc2-ball-into-middle --simdatakit-root ../SimDataKit
```

SimDataKit 为 v2 的 6 道题另外保存了 GeoPhys + Flora 脚本预览。命令从指定的 SimDataKit 目录核对并定位参考文件。部分轨迹和视频只保存在本地运行归档中，使用此命令需同时保留对应的运行文件。冻结发布时，50 题的正式评分状态均为 `not_run`。发布记录中另列的 19 次校准使用 v1 历史演示。

## 准备终态审核

每题的 `truth.goal` 给出权威终态判据。可选的 `truth.bind` 限定对象选择，`truth.process` 描述执行过程要求。对象清单、谓词词表和逐题初态均来自同一发布版。调用方提供同一次运行的终点及证据；涉及动作顺序的判断还需相应的轨迹记录。

```powershell
python -m bench_deploy.tablecraft prepare-review fsc2-stack-small-on-mid --evidence-bundle workspace/run/source-evidence.json --artifact-root workspace/run --judge-profile workspace/judge-profile.json --verifier-profile workspace/verifier-profile.json --output-directory workspace/tablecraft/review-001
```

[审核适配器](evaluation.py) 复用 GeoChora 的[通用终态验证](../../validation/README.md)。该命令离线生成审核材料，模型执行由后续审核流程负责。

定向回归可运行 `python -m pytest task_env/diagnostics/tasks/test_franka_scene.py -q`。
