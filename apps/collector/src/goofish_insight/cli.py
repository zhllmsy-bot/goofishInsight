from __future__ import annotations

import sys

from . import cli_runtime as _cli_runtime


if __name__ == "__main__":
    _cli_runtime.app()
else:
    sys.modules[__name__] = _cli_runtime
