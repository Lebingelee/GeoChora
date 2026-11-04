# 阶段3前维护续作检查点：Marker构造

日期：2026-11-05。输入 `develop@fdea7fbb`，根据维护者目标继续阶段3前维护；本检查点待Sol审阅，整体维护仍为 PARTIAL，阶段3未开始。此前两个保护 untracked 不属于改动范围。

既有 `ReferenceTaskDeclarationV1.compile` 的可选Controller编译通过 `compile_panda_box_task` 暴露；构造身份与来源字节快照交由assembly compiler准备。示例仍保留任务声明、reset、评价和正常注册，使用公共 `make_env`；构造摘要按本次真实源码计算，不复用历史SHA。`CompiledReferenceTaskV1` 记录场景构建owner，以保留 `PickCubeSceneComposer` 来源。源文件名冲突和缺失Controller拒绝构造。

Marker仍须在示例中配置并创建 `ReferenceTaskBinding` 和resolved配置；本检查点只收回部分通用接线，并不宣布R2完成。F06任务值与runtime准入职责分离、环境类减责、必要真实物理回归及独立reader尚待实施或验证。

无引擎guard与禁用外部pytest插件条件下，选定的配置／消费者／维护边界三组 **118 passed**；覆盖Marker公共factory、合成reset/step、实际来源文件SHA及recipe摘要。首次测试启动缺少 `PYTHONPATH` 导致收集失败；第二次因pytest basetemp父目录不存在导致38个setup error（80通过）；修复环境与目录后全组重跑通过。合成测试不证明物理成功。未启动Isaac、GPU或其他真实物理引擎，未申请共享native锁。
