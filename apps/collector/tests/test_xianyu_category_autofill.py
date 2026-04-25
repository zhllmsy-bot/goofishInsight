from __future__ import annotations

import unittest
from types import SimpleNamespace

from goofish_insight.application.services.xianyu_category_autofill import (
    _build_scope_proposal,
    _looks_like_apple_computer_title,
    _looks_like_camera_body_title,
    _looks_like_lens_title,
)


class XianyuCategoryAutofillTests(unittest.TestCase):
    def test_looks_like_camera_body_title_accepts_known_camera_models(self) -> None:
        self.assertTrue(_looks_like_camera_body_title("索尼 a7r4 微单机身"))
        self.assertTrue(_looks_like_camera_body_title("canon r6 单机"))
        self.assertFalse(_looks_like_camera_body_title("尼康 Z 24-70mm f/2.8 S 镜头"))

    def test_looks_like_apple_computer_title_rejects_apple_watch(self) -> None:
        self.assertFalse(_looks_like_apple_computer_title("Apple Watch Ultra 2 49mm"))

    def test_looks_like_lens_title_rejects_camera_body(self) -> None:
        self.assertFalse(_looks_like_lens_title("索尼 A7C2 全画幅机身"))

    def test_looks_like_camera_body_title_rejects_handheld_gps_copy(self) -> None:
        self.assertFalse(_looks_like_camera_body_title("Garmin Oregon 550 GPS手持机，灰色机身，3寸显示屏"))

    def test_build_scope_proposal_promotes_scope_when_observed_domain_is_stable(self) -> None:
        candidate = SimpleNamespace(
            match_scope="CAT_TB",
            match_key="CAT_TB:50025387:110308",
            item_count=416,
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="110308",
            xianyu_c_cat_id=None,
        )
        sample_items = [
            SimpleNamespace(title="Mac mini M4 16G 256G 国行"),
            SimpleNamespace(title="苹果 Mac mini M4 几乎全新"),
            SimpleNamespace(title="Mac mini M4 16+256"),
            SimpleNamespace(title="Mac mini 主机 M4 16G"),
            SimpleNamespace(title="Apple Mac mini M4 自用"),
            SimpleNamespace(title="Mac mini 2024 M4"),
            SimpleNamespace(title="Mac mini M4 带盒子"),
            SimpleNamespace(title="苹果电脑 mini 主机 mac mini m4"),
            SimpleNamespace(title="Mac mini M4 到 2027 保"),
            SimpleNamespace(title="Mac mini M4 送拓展坞"),
            SimpleNamespace(title="Mac mini M4 硬盘扩容剩余小板"),
            SimpleNamespace(title="Mac mini M4 服务器项目闲置"),
        ]
        targets = {
            "apple_computer": SimpleNamespace(
                category_id="33333333-3333-3333-3333-333333333101",
                template_id="33333333-3333-3333-3333-333333333401",
            )
        }

        result = _build_scope_proposal(
            candidate=candidate,
            sample_items=sample_items,
            observed_domain_counts={"apple_computer": 415, "camera_body": 1},
            targets=targets,
        )

        self.assertEqual(result["action"], "FORCE_TEMPLATE")
        self.assertEqual(result["dominantCategoryCode"], "apple_computer")
        self.assertEqual(result["payload"]["policyMode"], "FORCE_TEMPLATE")
        self.assertEqual(result["observedBusinessDomains"]["apple_computer"], 415)

    def test_build_scope_proposal_blocks_offscope_accessory_cluster(self) -> None:
        candidate = SimpleNamespace(
            match_scope="CAT_TB",
            match_key="CAT_TB:50025426:124174008",
            item_count=69,
            xianyu_cat_id="50025426",
            xianyu_tb_cat_id="124174008",
            xianyu_c_cat_id=None,
        )
        sample_items = [
            SimpleNamespace(title="全新佳明泰铁时8尼龙表带"),
            SimpleNamespace(title="佳明原装钛合金表带 fenix7x/fenix8"),
            SimpleNamespace(title="佳明fenix8原装钛合金表带"),
            SimpleNamespace(title="佳明 fenix8 22mm 真皮表带"),
            SimpleNamespace(title="佳明fenix8尊荣版51钛合金表带银色"),
            SimpleNamespace(title="佳明epix原装表带"),
            SimpleNamespace(title="Garmin 表带 26mm"),
            SimpleNamespace(title="佳明 quickfit 表带"),
            SimpleNamespace(title="佳明fenix8 51mm 国行"),
            SimpleNamespace(title="Garmin fenix 8 太阳能"),
            SimpleNamespace(title="佳明 Forerunner 265"),
            SimpleNamespace(title="佳明 epix pro"),
        ]

        result = _build_scope_proposal(
            candidate=candidate,
            sample_items=sample_items,
            observed_domain_counts={"garmin_watch": 69, "apple_airpods": 1},
            targets={},
        )

        self.assertEqual(result["action"], "BLOCK")
        self.assertEqual(result["payload"]["policyMode"], "BLOCK")

    def test_build_scope_proposal_blocks_rental_cluster(self) -> None:
        candidate = SimpleNamespace(
            match_scope="CAT_TB",
            match_key="CAT_TB:50023914:50025134",
            item_count=9,
            xianyu_cat_id="50023914",
            xianyu_tb_cat_id="50025134",
            xianyu_c_cat_id=None,
        )
        sample_items = [
            SimpleNamespace(title="领克08 可租测 商务租赁 婚车租赁"),
            SimpleNamespace(title="领克10 四驱 Ultra 租赁"),
            SimpleNamespace(title="方程豹钛5 可租可测"),
            SimpleNamespace(title="小鹏P7 可租可测"),
            SimpleNamespace(title="领克900 可租测"),
            SimpleNamespace(title="方程豹豹8 可租可测"),
            SimpleNamespace(title="问界M9 商务租赁"),
            SimpleNamespace(title="特斯拉 model 3 测试测评租赁"),
            SimpleNamespace(title="蔚来 ET5 可租可测"),
        ]

        result = _build_scope_proposal(
            candidate=candidate,
            sample_items=sample_items,
            observed_domain_counts={"apple_computer": 9},
            targets={},
        )

        self.assertEqual(result["action"], "BLOCK")
        self.assertEqual(result["payload"]["policyMode"], "BLOCK")


if __name__ == "__main__":
    unittest.main()
