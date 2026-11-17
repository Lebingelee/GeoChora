# Claude Code instructions

The repository rules live in [AGENTS.md](AGENTS.md); follow them as if they
were written here. They cover ownership, capability and evidence language,
repository hygiene, and the phase-branch workflow.

Skills are in [.agents/skills/](.agents/skills/). Read the matching `SKILL.md`
before working in its area:

| Work | Skill |
| --- | --- |
| Repository governance | [geochora](.agents/skills/geochora/SKILL.md) |
| TaskEnv APIs, examples, providers | [geochora-task-env](.agents/skills/geochora-task-env/SKILL.md) |
| Task candidate construction (catalog → spec → checks → Oracle → Judge package) | [geochora-task-harness](.agents/skills/geochora-task-harness/SKILL.md) |
| Asset generation and materials | [asset-creation](.agents/skills/asset-creation/SKILL.md), [asset-material-creation](.agents/skills/asset-material-creation/SKILL.md) |
| Scene composition | [scene-orchestration](.agents/skills/scene-orchestration/SKILL.md) |
| Module Skill review | [geochora-module-skill-maintainer](.agents/skills/geochora-module-skill-maintainer/SKILL.md) |

Machine setup, the environment script and the read-only `doctor.py` check are
described in [docs/global/agent-setup.md](docs/global/agent-setup.md). Source
`scripts/setup/geochora-env.sh` before running GeoChora commands. Generated run
data goes under the ignored `workspace/` directory.
