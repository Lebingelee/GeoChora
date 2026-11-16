# GeoChora shell environment. Source it; do not execute it.
#
#   source scripts/setup/geochora-env.sh [CORE_DIR]
#
# CORE_DIR defaults to the checkout that contains this script. Interpreters are
# taken from the environment so no machine path is written into the repository:
#
#   GEOCHORA_CORE_PYTHON     Core/MuJoCo interpreter (default: python3 on PATH)
#   GEOCHORA_GEOPHYS_PYTHON  GeoPhys isolated worker (default: GEOCHORA_CORE_PYTHON)
#   GEOCHORA_ISAAC_PYTHON    Isaac Sim 6.2 interpreter (default:
#                            CORE_DIR/workspace/environments/isaacsim-6.2.0/bin/python if present)
#
# Put machine-specific values in a file outside the repository, for example
# ~/.config/geochora/env.sh, and source it before this script.

if [ -n "${BASH_SOURCE:-}" ]; then _gc_self="${BASH_SOURCE[0]}"; else _gc_self="${(%):-%x}"; fi
_gc_core="${1:-$(cd "$(dirname "$_gc_self")/../.." && pwd)}"
if [ ! -d "$_gc_core/task_env" ]; then
    echo "geochora-env: $_gc_core is not a GeoChora checkout" >&2
    unset _gc_self _gc_core
    return 1 2>/dev/null || exit 1
fi
_gc_core="$(cd "$_gc_core" && pwd)"

export GEOCHORA_PROJECT="$_gc_core"
export GEOCHORA_CORE_PYTHON="${GEOCHORA_CORE_PYTHON:-$(command -v python3)}"
export GEOCHORA_GEOPHYS_PYTHON="${GEOCHORA_GEOPHYS_PYTHON:-$GEOCHORA_CORE_PYTHON}"
if [ -z "${GEOCHORA_ISAAC_PYTHON:-}" ] && [ -x "$_gc_core/workspace/environments/isaacsim-6.2.0/bin/python" ]; then
    export GEOCHORA_ISAAC_PYTHON="$_gc_core/workspace/environments/isaacsim-6.2.0/bin/python"
fi
[ -n "${GEOCHORA_ISAAC_PYTHON:-}" ] && export ISAAC_SIM_PYTHON="$GEOCHORA_ISAAC_PYTHON"
export GEOCHORA_GEOPHYS_SRC="$_gc_core/GeoPhys/src"
export PYTHONPATH="$_gc_core/GeoPhys/src:$_gc_core"
export PYTHONDONTWRITEBYTECODE=1
# Isaac Sim routes also need OMNI_KIT_ACCEPT_EULA=YES. Export it yourself after
# reading the NVIDIA Isaac Sim EULA; this script does not accept it for you.
case ":$PATH:" in
    *":$(dirname "$GEOCHORA_CORE_PYTHON"):"*) ;;
    *) export PATH="$(dirname "$GEOCHORA_CORE_PYTHON"):$PATH" ;;
esac
unset _gc_self _gc_core
