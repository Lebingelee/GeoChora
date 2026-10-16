"""Retired legacy NutAssembly Phase I recovery command.

The former implementation materialized a retired TaskEnv through private
GeoPhys state and diagnostics. Recover it from its immutable source commit or
``v1.0.0`` in a separate historical checkout. The active task route is
``nut-assembly-outcome-reference-v1`` and does not provide legacy replay.
"""

import sys


def main(argv=None) -> int:
    del argv
    print(
        "The Phase I NutAssembly recovery command is retired from active develop; "
        "restore its immutable historical source in a separate checkout. "
        "No legacy TaskEnv or provider-private access is substituted.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
