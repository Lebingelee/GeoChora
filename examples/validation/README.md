# 从外部实验数据准备终态验证

## 统一入口

从 GeoChora 根目录安装依赖后，运行 `python -m validation.validate_run --help`。任务可以是 UTF-8 的 `.txt`、`.md`，或 `low-detail-task/1.1.0`、`1.2.0` JSON。用户自有任务无需登记 ID。下面的自包含例子读取合成仪表的末帧颜色。纯文本题缺少可执行的 goal，因此离线结果为 `unknown / no_authored_goal`。

```powershell
python -m validation.validate_run --task examples/validation/external-fixture/task.txt --evidence-bundle examples/validation/external-fixture/bundle.json --output workspace/indicator-offline
```

有 PhysPi 封存记录时，直接指定运行目录和含已安装 runtime 的 PhysPi 根目录。使用 resident 时间线时显式选择分支；manifest 记录省略 `--branch`。如果 PhysPi 使用其他解释器，可用 `--runtime-python` 指定。批量运行目录旁存在 `input.json` 时会核对原题。其他布局由调用者确定任务与运行的对应关系。

```powershell
python -m validation.validate_run --task <case/input.json> --resource-root <case/inputs> --physpi-run <case/runs/run-id> --branch main --physpi-root ../PhysPi --output workspace/validation/case-01
```

**其他平台的证据格式。** [最小证据包](external-fixture/bundle.json)给出同一次运行的 `endpoint` 和 `evidence` 列表。每个条目绑定 episode、终点、类型、相对路径和原始字节 SHA-256。默认从证据包所在目录解析文件，另设根目录时传 `--artifact-root`。已有物理测量、图像和来源凭据的规范见[证据合同](../../docs/module/validation/contracts.md)。直接采集 PhysPi 时，根目录默认取输入、资源、运行和输出的公共目录。输出必须使用新目录。

**确定性求值。** 当前内置场景词表从任务声明的 `object_manifest` 和 `predicate_vocabulary` 资源加载。PhysPi 输入会使用真实跟踪名、世界坐标和 WXYZ 姿态；固定的 scene-predicates/1.0.0 会触发末尾 0.5 秒窗口采集。也可通过 `--window` 传入既有适配器支持的、绑定来源的窗口声明。仅采样末段时，完整的过程义务仍需另取过程证据。

外部平台可在包中提供 `id=goal_state`、`kind=raw_state` 的 JSON 条目，让求值器使用该平台的规范化状态。文件含 `schema_version="goal-states/1"`、与包一致的 `endpoint`，以及 `initial` 和 `terminal` 两个 [SceneState](../../validation/goals/state.py) 字段字典。坐标为世界系、米、Z 向上，姿态为 WXYZ，终点的 `time` 须等于 `endpoint.time_s`。平台有独立稳定性依据时才提供 `settled` 布尔值；缺失观测保留为空。PhysPi 生成的标准包可直接复用。

**启用模型审核。** 在任一命令末尾追加以下参数。仅当离线结论未知且终点有效时调用宿主。两个 profile 分别声明 `name` 和 `reasoning_effort`，模型名须由该 PhysPi 账号和模型目录实际支持。已有实验专用宿主时，用 `--host-script <file.mjs>` 指定。

```powershell
--review-on-unknown --physpi-root ../PhysPi --agent-dir <PhysPi-profile> --judge-profile <judge.json> --verifier-profile <verifier.json>
```

默认提交完整证据；大输入可显式使用 `--evidence-mode adaptive --max-text-characters <预算>`，保留按需补证和独立复核流程。结果统一写入 `result.json`，包含 `status`、`terminal`、路线、证据引用和缺口。确定性结果指已声明的**终态 goal**；过程项和整体 `success` 单独保存在 `goal-result.json`。模型逐项判断和复核回执位于 `review/`。有效未知的退出码为 0，执行错误返回非零。

## 分步准备审核

从GeoChora仓库根目录安装依赖，设置`PYTHONPATH=.`。本例不依赖TableCraft任务ID注册，
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
