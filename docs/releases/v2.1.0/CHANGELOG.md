# v2.1.0 candidate change notes

This is a local draft summary. It is not a published changelog and does not assign a formal release date.

- Preserves the normal F/R Core merge history and the unified GeoPhys provider commit P.
- Resolves selected execution defaults in the order Core → task class → task YAML → caller; carries a typed state-only `RendererSelectionV1` into resolved configuration and recording metadata; unsupported render pairings fail closed.
- Makes an optional Controller's absence explicit in compiled task identity as `controller_identity: null`, while retaining a bound Controller's real identity.
- Adds versioned current contracts, migration guidance, capability evidence, release notes, and explicit asset/licensing exclusions.
- Restores scalar selected construction of the public `render` section. The section is resolved with the other scalar fields and retained in the resolved configuration, allowing the existing single-environment `env.render()` route to consume its camera declaration.

The API changes had a focused offline regression run (10 passed) on implementation commit `0bf4a8e21cc0c19c087e6ca683c1d97eb990e50`. Earlier bounded integration/native evidence remains attached to its own Core/provider heads in the matrix; this candidate preparation did not rerun it.
