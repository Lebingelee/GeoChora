# 从外部实验数据准备终态验证

从GeoChora仓库根目录安装依赖，设置`PYTHONPATH=.`。
也不要求安装SimDataKit或TaskEnv。支持`low-detail-task/1.1.0`和`low-detail-task/1.2.0`原始任务。

```powershell
python -m pip install -r validation/requirements.txt
$env:PYTHONPATH='.'
```

每次运行提供原始`task.json`、它引用的资源目录、原生运行记录和来源绑定的证据包。
资源保持原样；任务中的`resources[].path`相对`--resource-root`解析。

已有PhysPi/GeoPhys运行可先用公开适配器采集：

```powershell
python -m validation.adapters.physpi --run-directory <PhysPi-run> --runtime-python <PhysPi-python> --root <artifact-root> --output <new-state.json> --source-evidence-output <new-evidence-directory>
```

已封存的resident运行需加`--branch <分支名>`，例如`--branch main`。
该命令只读已有运行，原生公开查询需要相应PhysPi环境。已有标准世界位姿文件也可用
`validation.adapters.recorded.read_recorded_poses`核对源字节后接入。
实际终点、图片捕获身份、接触、采样和资源基线以[验证合同](../../docs/module/validation/contracts.md)为准；
未记录的数据不能通过填写字段补造。

`judge.json`和`verifier.json`各包含`name`（例如`openai-codex/<model-id>`）和`reasoning_effort`。
用真实可用模型配置准备一次初审与独立复核：

```powershell
python examples/validation/prepare_review.py --task <task.json> --resource-root <resources-root> --evidence-bundle <source-evidence.json> --artifact-root <artifact-root> --judge-profile <judge.json> --verifier-profile <verifier.json> --output <new-review-directory>
```

该脚本先校验任务和资源，再复用现有审核入口；这里只准备文件，不调用模型。
默认`full`保留完整证据，`--evidence-mode adaptive`允许按需补证一次。
可用`--max-text-characters <整数>`显式设置输入文本预算；超出预算会在调用模型前报错，不截断证据。
随后通过调用方已有的文件宿主执行：

```powershell
python -m validation.terminal.source_run run --output <new-review-directory> --host-script <terminal-model.mjs> --agent-dir <PhysPi-profile>
```

宿主由调用方提供；当前PhysPi仓库的`scripts/terminal-model.mjs`可复用其已有登录配置。
宿主支持的模型名称须与冻结profile一致，每个审核角色使用独立上下文。
结果在`run-result.json`中区分`terminal=true/false/null`与执行错误；原始来源、实际图片和失败回执留存。
终态通过与完整过程通过、TaskEnv的task_success和正式Qualification分别表达。

真实多题样例与报告按实验索引提供，原始数据、视频及轨迹放在忽略的workspace中。
