# Agent setup: Codex and Claude Code

This guide takes a fresh Linux machine from `git clone` to a Codex (or Claude
Code) session that can run the GeoChora Task Harness and, optionally, the asset
generation services. Every step can be rerun; finished steps are skipped.

Scope: this sets up tools and interpreters. It does not establish a task,
provider or Qualification capability; use the versioned
[capability matrix](../module/task_env/v2.1.1/capabilities/capability-matrix.json)
for that.

## 1. Clone and check out submodules

```bash
git clone <GeoChora remote> GeoChora
cd GeoChora
git submodule update --init --recursive
```

## 2. Choose interpreters

The repository has no root packaging metadata; do not `pip install -e .`.
Prepare a Core interpreter with `task_env/requirements.txt` as described in the
[installation guide](../module/task_env/v2.1.1/guides/installation-and-start.md),
then point the environment script at it. Keep machine paths outside the
repository, for example in `~/.config/geochora/env.sh`:

```bash
export GEOCHORA_CORE_PYTHON=/path/to/core/env/bin/python
# optional
export GEOCHORA_GEOPHYS_PYTHON=/path/to/geophys/env/bin/python
export GEOCHORA_ISAAC_PYTHON=/path/to/isaacsim-6.2/bin/python
```

Then, in every shell that runs GeoChora commands:

```bash
source ~/.config/geochora/env.sh        # your machine values
source scripts/setup/geochora-env.sh     # PYTHONPATH, PATH, GEOCHORA_PROJECT
```

Isaac routes also need `OMNI_KIT_ACCEPT_EULA=YES`. Export it yourself after
reading the NVIDIA Isaac Sim EULA; the scripts never accept it for you.

## 3. Hugging Face token (asset services only)

The asset services download six pinned models. Two are gated:

1. Create a read token at <https://huggingface.co/settings/tokens>.
2. With the same account, request access and wait for approval:
   - <https://huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m>
   - <https://huggingface.co/briaai/RMBG-2.0>
3. `export HF_TOKEN=hf_...` or run `hf auth login`.

Skip this section if you only need the Task Harness.

## 4. Run the one-command setup

```bash
bash scripts/setup/setup.sh                 # Harness + asset services + MCP
bash scripts/setup/setup.sh --skip-assets   # Harness only; no download, no MCP
bash scripts/setup/setup.sh --skip-mcp      # do not touch ~/.codex/config.toml
```

What it does:

| Step | Result | Needs |
| --- | --- | --- |
| core | Submodules present, Core interpreter imports `task_env` and `mujoco` | `GEOCHORA_CORE_PYTHON` |
| assets | `workspace/asset-services/` runtimes (TRELLIS.2, UltraShape), pinned sources, CUDA extensions, models, Blender 4.2.3 | NVIDIA GPU, conda, HF token, about 46 GB disk |
| mcp | Registers `trellis2`, `ultrashape`, `trellis-texturing` and `experiment-batch` in `$CODEX_HOME/config.toml` | a finished asset step |
| lock | Creates `workspace/locks/shared_native_execution.lock` | — |

Without a token and without downloaded models, the asset step stops with exit
code 3 and prints the token and gated-model links above. The download asks for
confirmation first; pass `--yes` for unattended runs.

The MCP step writes a timestamped backup of `config.toml` before editing it,
and points every entry at **this** checkout. If another checkout on the same
machine is already registered and in use, run with `--skip-mcp` instead.

The deployment scripts behind the asset step are in
[scripts/asset_services/deployment](../../scripts/asset_services/deployment)
(pinned sources, model revisions, CUDA extensions, MCP registration); the
experiment-batch server is [scripts/orchestrator/server.py](../../scripts/orchestrator/server.py).
See also the [Asset Harness overview](../module/asset_harness/README.md).

## 5. Check the result

```bash
python scripts/setup/doctor.py
```

It prints one JSON report (`geochora-doctor-v1`): git state, submodules,
interpreters, native lock, asset models and Codex MCP registration, each with
`ok`, `warn` or `fail` and a `next_steps` list. It is read-only. `fail` means
the Harness cannot run; `warn` covers optional parts (Isaac, assets, MCP) and a
dirty checkout, which the Harness refuses because catalog provenance records
`core_commit` and `core_dirty`.

## 6. Start Codex

Start Codex from the checkout root so it reads [AGENTS.md](../../AGENTS.md) and
discovers the skills in `.agents/skills/`:

```bash
cd GeoChora
source scripts/setup/geochora-env.sh
codex
```

In Codex, `/mcp` should list the four servers from step 4. Then ask for a task
with the skill name as ordinary prompt text, for example:

```text
$geochora-task-harness
Build a pick-lift candidate from examples/harness/mock_upstream/task.json,
run the checks and the 20-seed feasibility probe on mujoco, record the Oracle
and prepare the Stage-1 Judge package under workspace/harness/<run>.
```

The skill's [workflow](../../.agents/skills/geochora-task-harness/references/workflow.md)
and the [Harness CLI README](../../task_env/script/agent/README.md) list the
commands it runs. Asset generation uses `$asset-creation`,
`$asset-material-creation` and `$scene-orchestration`.

Claude Code reads [CLAUDE.md](../../CLAUDE.md), which points to the same
`AGENTS.md` and skills.

## 7. Offline consistency check

`examples/harness/mock_upstream/` is a synthetic upstream delivery. The test
below runs catalog → spec → asset/semantic checks → compile against it without
stepping physics, so a Core change that breaks candidate construction fails in
seconds rather than in a 20-seed run:

```bash
"$GEOCHORA_CORE_PYTHON" task_env/script/agent/test_mock_upstream_consistency.py
```
