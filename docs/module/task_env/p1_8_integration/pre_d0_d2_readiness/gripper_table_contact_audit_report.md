# GeoPhys gripper/table contact audit

## Scope
GeoPhys TB100, existing 10 N equal-rate diagnostic trace with absolute height gate disabled. No production controller, planner, physics, geometry or force thresholds changed. No new physics execution; recorded state replay and authored collision geometry reconstruction only.

## Findings
- Close starts at approximately 3.13 s. The inner-servo first force-mode record is 3.160 s, measured opening 79.942 mm and incoming closing-force feedback 1.485 N. The activation threshold is 1 N, so readiness is not needed to enter force mode.
- The contact geometry stored with that sample is post-substep (3.162 s); its incoming feedback is pre-substep. These must not be treated as perfectly simultaneous measurements.
- Table top is 462.000 mm. At the first force-mode sample, reconstructed right-finger collision mesh bottom is 461.169 mm: geometric overlap 0.831 mm. Right principal pad-box bottom is 461.970 mm: overlap 0.030 mm. Left mesh overlap is 0.018 mm; left principal box clearance is 0.635 mm.
- Across close, minimum reconstructed clearance is -0.832 mm (right finger mesh, 3.388 s). Palm/hand proxies remain at least 35.5 mm above the table at activation.
- Thus finger/table interference is geometrically plausible and is a supported suspect. It is not yet a demonstrated decomposition of the reported actuator force into table normal/friction loads.
- GeoPhys existing native diagnostics expose task-body aggregate impulses, not pair-level finger/table contacts. Nut aggregate impulses include Nut/table support and cannot establish a finger/Nut grasp. Exact realized GeoPhys mesh collision proxies may differ from the authored renderer mesh.
- Close ends with opening approximately 76.741 mm, force 9.086 N, controller close_ready true but canonical grasped_nut false. Authorization fails closed at its deadline; no lift is commanded. The controller force-mode activation uses actuator-force magnitude as a contact proxy and can therefore respond to non-Nut resistance.

## Media
Recorded GeoPhys poses and individual finger coordinates rendered in an authored-scene MuJoCo camera, without MuJoCo physics stepping. Video is auxiliary evidence, not a GeoPhys native contact oracle.
- hand_camera.mp4: wrist camera, 640x480, 30 fps.
- close_0p25x.mp4: wrist close-stage quarter-speed excerpt.
- table_side_0p25x.mp4: additional near-table side camera, quarter speed, to inspect finger/table clearance.
See media_manifest.json for hashes. No media embedded.

## Conclusion / next check
The user's table-contact hypothesis is supported by authored-geometry reconstruction, especially the right finger mesh; friction contribution remains unresolved. Next use read-only GeoPhys per-finger native contact/realized collision bounds and a separate diagnostic table-collision isolation fixture to determine whether removing this external load prevents premature force-mode entry. Do not promote a height/force/controller adjustment on this evidence alone.
