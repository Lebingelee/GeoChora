# TaskEnv 文档入口

TaskEnv 文档按使用场景分为三组：

| 读者 | 文档 | 适合解决的问题 |
| --- | --- | --- |
| 使用者 | [README Quickstart](../README.md) | 安装、创建环境、并行运行、渲染和启动 PPO |
| 训练/采集使用者 | [训练与采集](新手使用训练与采集.md) | RL、SB3、RSL-RL、轨迹和 H5 数据 |
| 任务开发者 | [自定义任务构建指南](自定义任务构建指南.md) | 创建 task family、reset、observation、reward 和 parallel capability |
| 资产开发者 | [资产导入与二次开发指南](资产导入与二次开发指南.md) | 注册 world、robot、object 并接入 assembly |
| API 使用者 | [API Reference](api/index.md) | 查找稳定的公开接口和数据契约 |

## 推荐阅读顺序

1. 先运行 [README Quickstart](../README.md)，确认环境和依赖可用。
2. 需要训练或录制数据时阅读 [训练与采集](新手使用训练与采集.md)。
3. 需要创建新任务时阅读 [自定义任务构建指南](自定义任务构建指南.md)。
4. 需要导入新资产时阅读 [资产导入与二次开发指南](资产导入与二次开发指南.md)。
5. 需要确认函数签名、返回值或生命周期时查阅 [API Reference](api/index.md)。

## 公开入口

~~~
task_env.make_env(...)          # 单环境
task_env.make_parallel_env(...) # 同构并行环境
task_env.ENV_REGISTRY           # 单环境注册表
task_env.PARALLEL_ENV_REGISTRY  # 并行能力注册表
~~~

TaskEnv 使用者只通过 reset、step、action_space、observation_space、info 和记录器访问环境。solver、Taichi field、runtime private state 和 stage/diagnostic 文件不属于 Quickstart 使用面。
