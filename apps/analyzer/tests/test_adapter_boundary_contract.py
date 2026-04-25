from __future__ import annotations

import ast
import unittest
from pathlib import Path


class AnalyzerAdapterBoundaryContractTests(unittest.TestCase):
    def test_analyzer_adapter_goofish_insight_imports_are_allowlisted(self) -> None:
        source_path = (
            Path(__file__)
            .resolve()
            .parents[1]
            / "src"
            / "goofish_analyzer"
            / "adapters"
            / "__init__.py"
        )
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and isinstance(node.module, str)
            and node.module.startswith("goofish_insight")
        }

        self.assertSetEqual(
            imported_modules,
            {
                "goofish_insight.domain.pricing.contracts",
                "goofish_insight.application.services.pricing_templates",
                "goofish_insight.application.services.template_feature_flags",
                "goofish_insight.application.services.collector_runtime",
                "goofish_insight.application.services.quality_metrics",
                "goofish_insight.application.services.notification_delivery",
                "goofish_insight.pricing",
            },
        )


if __name__ == "__main__":
    unittest.main()
