# 终态审核测试

参见[模块入口](../README.md)。测试使用独立合成输入和编写的模型响应，不启动物理或在线模型。

| 文件 | 保护的行为 |
| --- | --- |
| `test_task_inputs.py` | 固定任务schema、版本拒绝、字段定位、资源ID／位置和模型调用前的校验 |
| `test_terminal.py`、`test_sampled_geometry.py` | 通用几何、有限采样、缺失观测与边界 |
| `test_terminal_numeric.py`、`test_numeric_requests.py` | 16种测量、完整碰撞scope、接触／载荷、源参考点、参数准入与网格 |
| `test_terminal_source_reviews.py` | 原要求、对象／量词、三值候选与独立确认 |
| `test_physpi_terminal.py`、`test_recorded_terminal.py`、`test_terminal_contact_records.py` | 公开记录、位姿、接触、来源身份与实际终点 |
| `test_terminal_dispatch.py`、`test_terminal_costs.py` | 图片字节、文件／回调传输、预算、错误及不可重复支付 |
| `test_terminal_adaptive.py`、`test_terminal_assets.py` | 初末／补证选择、终点时钟舍入、独立资产基线、缓存和参数反例 |

跨文件显式构造函数在fixtures中的source_reviews、runtime、geometry和evidence内；测试不相互导入。
旧规格／四路组合及专项benchmark用例随完整冻结源码移到workspace实验归档，通过legacy.py显式运行。
混合用例中的数值、来源、时钟、图片和恢复保护已经迁移到当前接口；归档不代表这些保护退出。

```powershell
python -B -m pytest validation/tests -q
# TaskEnv consumer integration, in an existing TaskEnv environment:
python -B -m pytest task_env/diagnostics/tasks/test_franka_scene.py -q
```

按文件可选择更小的回归。合成协议和解析计算测试不构成真实物理准确率或provider Qualification。

`test_independence.py`在阻止TaskEnv与仿真运行时导入的子进程中，实际执行记录数值计算和初审／独立复核。历史producer回归保留两种旧来源身份，并继续拒绝证据内容篡改。
