# Asset Harness

**Status:** asset intake and validation are implemented by existing TaskEnv artifact/source owners and bounded tools; this page documents the direction, not a new standalone product or a universal asset importer.

Asset preparation records source identity, bytes/closure, mappings, validation, and representation separately. Current owners include `task_env.artifacts`, `task_env.assembly`, and source-specific preparation under `asset/benchmarks/`. A valid manifest or import does not establish licensing, simulator compatibility, provider admission, or a runnable task.

Use the current [Task Artifact contract](../task_env/v2.1.0/contracts/task-artifact.md), [runtime/provider contract](../task_env/v2.1.0/contracts/runtime-and-providers.md), and [asset distribution record](../../releases/v2.1.0/third-party-assets.md). Unknown or unresolved third-party assets are excluded from distribution. Local source bundles and raw evidence remain outside tracked docs.

Add future asset workflow documentation under a TaskEnv version directory or the owning benchmark's existing source tree; do not copy provider-private state into Core.
