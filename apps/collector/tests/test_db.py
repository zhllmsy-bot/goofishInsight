from __future__ import annotations

import unittest
from unittest.mock import patch

from goofish_insight import db


class DbLifecycleTests(unittest.TestCase):
    def test_dispose_engine_closes_global_engine(self) -> None:
        with patch.object(db.engine, "dispose") as dispose_mock:
            db.dispose_engine()

        dispose_mock.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
