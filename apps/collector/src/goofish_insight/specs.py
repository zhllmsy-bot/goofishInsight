from __future__ import annotations

import sys

from . import specs_runtime as _specs_runtime


sys.modules[__name__] = _specs_runtime
