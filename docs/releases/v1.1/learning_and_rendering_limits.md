# Learning and Rendering Limits

**RELEASE_CANDIDATE — NOT_PUBLISHED**

## Learning

- Generic SB3 and RSL-RL adapters are **IMPLEMENTED**.
- The bounded Pendulum SB3 example ran one CPU update with two
  `merged_scene` environments and four timesteps. This is wiring evidence, not
  convergence, training, or general RL qualification.
- RSL-RL provider-free import and explicit task-UID admission checks passed.
  No native RSL-RL training run was performed. Retired Go2 task/profile IDs do
  not have replacements.
- PickCube and NutAssembly are not declared default PPO targets. No
  manipulation checkpoint inference or general manipulation PPO claim is
  made.

## Rendering

- Renderer Registry, Flora, Camera, and rasterizer contracts are
  **IMPLEMENTED** within their documented capability boundaries.
- The bounded executable RGB intersections are Pendulum × GeoPhys CPU ×
  scalar TaskEnv × rasterizer, and Pendulum × GeoPhys CPU × `merged_scene`
  batch × rasterizer. Each smoke used a small RGB frame and one step.
- Flora registry tests used fake endpoints. No Native Flora qualification was
  added. No selected manipulation task × Flora route is established.
- No Physics × Renderer interoperability claim is made. The Camera API remains
  available, while retired historical camera and rendering entry points fail
  explicitly.

See the candidate [capability matrix](capability_matrix.md) and
[`examples/README.md`](../../../examples/README.md) for exact commands and
limits.
