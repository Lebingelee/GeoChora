# v2.0.0 migration notes

This page describes how to inspect the frozen v2.0.0 source snapshot; it does not define an upgrade from a published v1.1.0 distribution.

1. Check out the exact `refs/tags/v2.0.0` source and read the [v2.0.0 TaskEnv index](../../module/task_env/v2.0.0/README.md).
2. Keep configuration, runtime contracts, and historical evidence bound to that tag. Do not use v2.1.0 pages or API fixes as if they existed in v2.0.0.
3. Treat later TaskEnv UIDs, resolver rules, and provider evidence as version-specific. The [v2.1.0 migration guide](../../module/task_env/v2.1.0/api/migration.md) applies only to the local v2.1 candidate.

No data-file rewrite or historical H5 schema upgrade is asserted here. Preserve source IDs and hashes when comparing runs across versions.
