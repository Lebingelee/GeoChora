#!/usr/bin/env bash
# One-command GeoChora setup on Linux (Codex + Task Harness + asset services).
#
#   bash scripts/setup/setup.sh [--skip-assets] [--skip-mcp] [--yes]
#
# Steps, each skipped when its result is already present:
#   1. core     Core interpreter imports task_env; submodules are checked out.
#   2. assets   Asset-service runtimes, pinned sources, CUDA extensions, models
#               and Blender under workspace/asset-services (about 46 GB; needs
#               an NVIDIA GPU, conda and a Hugging Face token).
#   3. mcp      Registers trellis2, ultrashape, trellis-texturing and
#               experiment-batch in $CODEX_HOME/config.toml (a timestamped
#               backup is written first).
#   4. lock     Creates workspace/locks/shared_native_execution.lock.
# Finish with: python scripts/setup/doctor.py
#
# Inputs (environment): GEOCHORA_CORE_PYTHON, GEOCHORA_ISAAC_PYTHON (see
# geochora-env.sh), HF_TOKEN or a prior `hf auth login`, CONDA (default: conda
# on PATH), CODEX_HOME (default ~/.codex), BLENDER_PATH (optional).
set -euo pipefail

SKIP_ASSETS=0; SKIP_MCP=0; ASSUME_YES=0
for argument in "$@"; do
    case "$argument" in
        --skip-assets) SKIP_ASSETS=1 ;;
        --skip-mcp) SKIP_MCP=1 ;;
        --yes) ASSUME_YES=1 ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "unknown option: $argument" >&2; exit 2 ;;
    esac
done

CORE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$CORE"
# shellcheck source=geochora-env.sh
source "$CORE/scripts/setup/geochora-env.sh" "$CORE"
step() { echo; echo "== $*"; }
stop() { echo "SETUP STOPPED: $*" >&2; exit "${2:-1}"; }

# ---------------------------------------------------------------- 1. core
step "core: interpreter and submodules"
[ -x "$GEOCHORA_CORE_PYTHON" ] || stop "GEOCHORA_CORE_PYTHON is not an executable interpreter: $GEOCHORA_CORE_PYTHON"
if git submodule status | grep -q '^-'; then
    echo "initialising submodules"
    git submodule update --init --recursive
fi
"$GEOCHORA_CORE_PYTHON" -c "import task_env, mujoco, numpy; print('task_env OK, mujoco', mujoco.__version__)" \
    || stop "Core interpreter cannot import task_env. Install task_env/requirements.txt into it; see docs/module/task_env/v2.1.1/guides/installation-and-start.md"

# -------------------------------------------------------------- 2. assets
W="$CORE/workspace/asset-services"
PY="$W/runtime/trellis2/bin/python"
UPY="$W/runtime/ultrashape/bin/python"
MODEL_COUNT=6

models_ready() {
    [ -f "$W/model-receipt.json" ] && "$GEOCHORA_CORE_PYTHON" - "$W/model-receipt.json" "$MODEL_COUNT" <<'PY'
import json, sys
receipt = json.load(open(sys.argv[1]))
sys.exit(0 if len(receipt.get('models', {})) >= int(sys.argv[2]) else 1)
PY
}

hf_token_present() {
    [ -n "${HF_TOKEN:-}" ] && return 0
    local home="${HF_HOME:-$HOME/.cache/huggingface}"
    [ -s "$home/token" ]
}

if [ "$SKIP_ASSETS" = 1 ]; then
    step "assets: skipped (--skip-assets)"
else
    step "assets: asset-service runtimes and models under $W"
    if ! models_ready && ! hf_token_present; then
        cat >&2 <<'MSG'
SETUP STOPPED: a Hugging Face token is required to download the asset models.

  1. Create a read token at https://huggingface.co/settings/tokens
  2. With the same account, request access to the two gated models and wait
     for approval:
       https://huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m
       https://huggingface.co/briaai/RMBG-2.0
     (microsoft/TRELLIS.2-4B, microsoft/TRELLIS-image-large, infinith/UltraShape
     and facebook/dinov2-large are downloaded from the same pinned revisions.)
  3. export HF_TOKEN=hf_...   (or run `hf auth login`), then rerun this script.

To set up only the Task Harness without asset generation, rerun with --skip-assets.
MSG
        exit 3
    fi
    command -v nvidia-smi >/dev/null || stop "asset services need an NVIDIA GPU driver (nvidia-smi not found)"
    CONDA="${CONDA:-$(command -v conda || command -v mamba || true)}"
    [ -n "$CONDA" ] || stop "conda or mamba is required to create the asset-service runtimes (set CONDA=...)"
    if [ "$ASSUME_YES" != 1 ] && ! models_ready; then
        read -r -p "This downloads about 46 GB into $W. Continue? [y/N] " answer
        [ "$answer" = y ] || [ "$answer" = Y ] || stop "cancelled by user" 1
    fi
    export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONNOUSERSITE=1
    CF=(--override-channels -c conda-forge)
    (
        unset PYTHONPATH
        mkdir -p "$W/runtime"
        if ! "$PY" -c "import torch, mcp" 2>/dev/null; then
            [ -x "$PY" ] || "$CONDA" create --prefix "$W/runtime/trellis2" "${CF[@]}" python=3.11 pip -y
            "$PY" -m pip --isolated install torch==2.8.0 torchvision==0.23.0 xformers==0.0.32.post2 \
                --index-url https://download.pytorch.org/whl/cu128
            "$PY" -m pip --isolated install -r scripts/asset_services/deployment/requirements-trellis.txt
        fi
        "$PY" scripts/asset_services/deployment/prepare_sources.py
        models_ready || "$PY" scripts/asset_services/deployment/prepare_models.py

        # torch cu128 extensions need nvcc 12.8; use a local toolkit when the system one differs.
        if nvcc --version 2>/dev/null | grep -q 'release 12.8'; then
            :
        else
            C="$W/runtime/cuda128"
            [ -x "$C/bin/nvcc" ] || "$CONDA" create -y --prefix "$C" "${CF[@]}" cuda-version=12.8 \
                cuda-nvcc-tools cuda-nvcc-impl cuda-cudart-dev cuda-cccl cuda-libraries-dev cuda-nvtx-dev cuda-profiler-api
            [ -e "$C/lib64" ] || ln -s targets/x86_64-linux/lib "$C/lib64"
            export CUDA_HOME="$C" PATH="$C/bin:$PATH"
            export CPATH="$C/targets/x86_64-linux/include${CPATH:+:$CPATH}"
            export LIBRARY_PATH="$C/targets/x86_64-linux/lib:$C/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
        fi
        "$PY" scripts/asset_services/deployment/install_extensions.py

        if ! "$UPY" -c "import diffusers, cumesh" 2>/dev/null; then
            [ -x "$UPY" ] || "$CONDA" create --prefix "$W/runtime/ultrashape" "${CF[@]}" python=3.11 pip -y
            "$UPY" -m pip --isolated install torch==2.8.0 torchvision==0.23.0 numpy==1.26.4 \
                --index-url https://download.pytorch.org/whl/cu128
            "$UPY" -m pip --isolated install -r scripts/asset_services/deployment/requirements-ultrashape.txt
            "$UPY" -m pip --isolated install --no-deps "$W"/wheels/cumesh-*.whl
        fi

        if [ -z "${BLENDER_PATH:-}" ] && ! command -v blender >/dev/null; then
            B="$W/runtime/blender-4.2.3-linux-x64"
            [ -x "$B/blender" ] || curl -fsSL https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz \
                | tar -xJ -C "$W/runtime"
            "$B/blender" --version | head -1
        fi
    ) || stop "asset setup failed; see the output above and build logs under $W/evidence"
fi

# ----------------------------------------------------------------- 3. mcp
if [ "$SKIP_MCP" = 1 ] || [ "$SKIP_ASSETS" = 1 ]; then
    step "mcp: skipped"
else
    step "mcp: register asset services and experiment-batch for Codex"
    ( unset PYTHONPATH; "$PY" scripts/asset_services/deployment/register_mcp.py )
    ( export PYTHONPATH="$CORE/scripts"; "$PY" -m orchestrator.server --register )
fi

# ---------------------------------------------------------------- 4. lock
step "lock: shared native execution lock"
mkdir -p "$CORE/workspace/locks"
touch "$CORE/workspace/locks/shared_native_execution.lock"
echo "$CORE/workspace/locks/shared_native_execution.lock"

step "done; checking the result"
"$GEOCHORA_CORE_PYTHON" "$CORE/scripts/setup/doctor.py"
