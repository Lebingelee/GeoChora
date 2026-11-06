# 5b observer implementation notes — pending independent review

The selected PickCube MuJoCo CPU path now accepts an explicit observer camera and `human` or `rgb_array` render mode through the existing Env and render owner. The RGB mode returns an owned HWC float32 array in [0, 1]; the native framebuffer color encoding is not yet established. A separate observer update invalidates the previous receipt. The earlier binding-only camera profile remains capture-disabled. These changes do not supply automatically synchronized task observations.

The Isaac F06 path has a camera-enabled App profile and an observer capture/presentation path under the existing App/session owner. It compares renderer-facing public transforms against the published physics state before returning a frame and fails closed on mismatch. On the tested Isaac Sim 6.2 installation that check fails: native rendering cannot yet be claimed to depict the current published state. GeoPhys renderer integration is not established by these changes.

This note describes implementation and known limits, not acceptance of the 5b gates. Route-specific configuration, raw data, failures, resource and release records are in `workspace/maintenance/v211_g05_5b_attempt001/`; independent review remains pending. Renderer switching, synchronized task observation and cross-provider combinations remain subsequent work.
