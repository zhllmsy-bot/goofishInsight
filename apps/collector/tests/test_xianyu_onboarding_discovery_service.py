from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from goofish_insight.application.services.xianyu_onboarding_discovery import (
    XianyuOnboardingDiscoveryError,
    run_xianyu_onboarding_discovery,
)


class XianyuOnboardingDiscoveryServiceTests(unittest.TestCase):
    def test_run_xianyu_onboarding_discovery_prefers_attached_browser_when_cdp_available(self) -> None:
        task = SimpleNamespace(
            id=12,
            task_key="apple-monitor",
            business_domain="apple_m_series",
            display_name="Apple Monitor",
        )
        cli_helpers = SimpleNamespace(
            SearchPlanEntry=lambda **kwargs: SimpleNamespace(**kwargs),
            get_settings=MagicMock(return_value=SimpleNamespace(browser_profile_dir=Path("/tmp/goofish-profiles"))),
            get_task_or_raise=MagicMock(),
            load_profile_settings=MagicMock(
                return_value={"channel": "msedge", "headless": False, "cdp_url": "auto"}
            ),
            resolve_cdp_url=MagicMock(return_value="http://127.0.0.1:9222"),
            run_live_search_capture=MagicMock(),
            run_search_plan_in_attached_tab=MagicMock(
                return_value={"run_id": "run-attached-1", "pages_succeeded": 2, "pages_attempted": 2}
            ),
        )

        with patch(
            "goofish_insight.application.services.xianyu_onboarding_discovery._load_cli_helpers",
            return_value=cli_helpers,
        ), patch(
            "goofish_insight.application.services.xianyu_onboarding_discovery._resolve_discovery_task",
            return_value=task,
        ):
            result = run_xianyu_onboarding_discovery(
                source_keyword="macbookpro14",
                task_key="apple-monitor",
                pages=2,
            )

        self.assertEqual(result["executionMode"], "attached_cdp")
        self.assertEqual(result["run"]["runId"], "run-attached-1")
        cli_helpers.run_search_plan_in_attached_tab.assert_called_once()
        attached_call = cli_helpers.run_search_plan_in_attached_tab.call_args.kwargs
        self.assertEqual(attached_call["resolved_cdp_url"], "http://127.0.0.1:9222")
        self.assertEqual(attached_call["plan"].query, "macbookpro14")
        self.assertEqual(attached_call["plan"].pages, 2)
        cli_helpers.run_live_search_capture.assert_not_called()

    def test_run_xianyu_onboarding_discovery_falls_back_to_persistent_context_when_cdp_unavailable(self) -> None:
        task = SimpleNamespace(
            id=18,
            task_key="apple-monitor",
            business_domain="apple_m_series",
            display_name="Apple Monitor",
        )
        cli_helpers = SimpleNamespace(
            SearchPlanEntry=lambda **kwargs: SimpleNamespace(**kwargs),
            get_settings=MagicMock(return_value=SimpleNamespace(browser_profile_dir=Path("/tmp/goofish-profiles"))),
            get_task_or_raise=MagicMock(),
            load_profile_settings=MagicMock(
                return_value={"channel": "msedge", "headless": False, "cdp_url": "auto"}
            ),
            resolve_cdp_url=MagicMock(side_effect=RuntimeError("No attachable Chrome instance found.")),
            run_live_search_capture=MagicMock(
                return_value={"run_id": "run-local-1", "pages_succeeded": 1, "pages_attempted": 1}
            ),
            run_search_plan_in_attached_tab=MagicMock(),
        )

        with patch(
            "goofish_insight.application.services.xianyu_onboarding_discovery._load_cli_helpers",
            return_value=cli_helpers,
        ), patch(
            "goofish_insight.application.services.xianyu_onboarding_discovery._resolve_discovery_task",
            return_value=task,
        ):
            result = run_xianyu_onboarding_discovery(
                source_keyword="macbookpro14",
                business_domain="apple_m_series",
                pages=1,
                profile_key="default",
            )

        self.assertEqual(result["executionMode"], "persistent_context")
        self.assertEqual(result["profile"]["cdpFallbackReason"], "No attachable Chrome instance found.")
        self.assertEqual(result["run"]["pagesSucceeded"], 1)
        cli_helpers.run_live_search_capture.assert_called_once()
        cli_helpers.run_search_plan_in_attached_tab.assert_not_called()

    def test_run_xianyu_onboarding_discovery_requires_source_keyword(self) -> None:
        with self.assertRaises(XianyuOnboardingDiscoveryError):
            run_xianyu_onboarding_discovery(source_keyword="   ")


if __name__ == "__main__":
    unittest.main()
