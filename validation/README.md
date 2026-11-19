# 任务与轨迹验证

`validation/` 接收任务原文和已有实验数据，输出来源可追溯的数值测量与终态判断。
当前支持离线终态验证；完整轨迹验证是后续扩展方向。
Validation检查要求是否满足；项目的正式能力资格认定仍称Qualification。

## 使用

从仓库根目录使用Python及`validation/requirements.txt`中的NumPy和JSON Schema校验依赖。
通用验证入口不导入TaskEnv，也不构造环境、运行仿真或内置模型SDK。

```powershell
python -m pip install -r validation/requirements.txt
python -m validation.terminal.source_run --help
python -m validation.adapters.physpi --help
```

```python
from validation.adapters.recorded import adapt_recorded_poses, read_recorded_poses
from validation.inputs import validate_task, load_task, load_task_source
from validation.terminal.numeric import measure_source_requests
from validation.terminal.reviews import prepare_source_review
from validation.terminal.source_run import prepare_source_run, execute_source_run
```

实验数据先经来源适配，保留任务要求、文件字节引用、对象身份、世界坐标、SI单位、WXYZ姿态、
实际时钟及独立完成记录，再进入数值计算或审核。支持的是[合同](../docs/module/validation/contracts.md)
列出的记录和证据格式；其他原始格式需显式转换。来源、时钟或观测不足时保留缺失状态。

任务输入优先通过`validation.inputs`。当前支持`low-detail-task/1.1.0`和`low-detail-task/1.2.0`，使用
[原始schema及来源](schemas/README.md)校验后保留原文，不隐式升级其他版本。
`load_task_source`核对资源位置和ID，并加载明确引用的任务／初态JSON合同。
TableCraft和[外部任务样例](../examples/validation/README.md)共用这个入口校验。
底层`reviews.prepare_source_review`仍是独立的source协议；任意非空JSON不等于已通过任务schema。

`numeric.measure_source_requests`保留16项逐项测量方法，输入显式来源绑定的请求，返回数值、单位、
bool／null和诊断，不生成整体任务结论。来源指针证明出处，原任务审核负责检查选用方法与条件的含义。

审核流程是原任务及同次证据 → 初审 → 必要时最多一次补证 → 独立复核布尔候选 → 发布终态。
有效未知默认不复核，执行错误单列；终态结果不自动更新TaskEnv的task_success。
`prepare_source_run`默认`full`，按需补证需显式选择`evidence_mode="adaptive"`。
执行通过调用者提供的文件宿主完成；离线测试使用编写的响应，不代表真实模型效果。

## 实现归属

| 位置 | 职责 |
| --- | --- |
| `terminal/reviews.py`、`source_run.py`、`dispatch.py` | 原任务审核、独立复核、一次补证与交付 |
| `terminal/numeric.py`、`terminal/__init__.py` | 数值测量与快照几何关系 |
| `terminal/evidence_views.py` | 初末及按需窗口、独立资产基线比较 |
| `adapters/recorded.py` | 标准世界位姿记录、身份、时钟和完成性准入 |
| `adapters/physpi.py`、`contacts.py`、`assets.py` | 公开原生记录、接触与资产参数读取 |
| `sampling.py`、`geometry.py`、`results.py` | 有限采样、凸几何、纯数学和独立三值结果 |
| `protocol.py`、`artifact_io.py`、`json_codec.py` | 请求校验、字节引用与输入表示 |

TaskEnv继续维护任务定义、环境生命周期、Recorder、轨迹存储／回放和自身的运行判定。
[TableCraft任务集合](../bench_deploy/tablecraft/README.md)通过显式调用使用本模块，任务来源由其部署包维护。
PhysPi原生查询需调用者显式提供运行时Python；仅导入适配器或处理已有标准记录不需要该运行时。

## 证据和迁移

当前回归见[测试说明](tests/README.md)，详细格式和限制见[验证合同](../docs/module/validation/contracts.md)。
新生成的证据使用新文件路径及实际源码哈希；已保存证据中的旧producer身份和原文件字节保留。
准备好的执行计划绑定当时源码；跨版本恢复需使用匹配的源码，或在新目录重新准备。

旧规格生成／编译、词表、多路线组合和专项benchmark仍保存在本地忽略的
`workspace/tasks/terminal-experimental-routes-20261116/`冻结实验归档中，其`legacy.py`仅用于历史复现。
当前模块不依赖该归档；本次迁移不改写历史物理实验、模型调用或资格结论。
