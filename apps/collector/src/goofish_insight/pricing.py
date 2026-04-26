from __future__ import annotations

import sys

from . import pricing_runtime as _pricing_runtime


sys.modules[__name__] = _pricing_runtime
