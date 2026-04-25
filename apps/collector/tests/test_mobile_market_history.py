from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from goofish_insight.application.services.mobile_market_history import (
    MobileMarketSnapshot,
    detect_screen_state,
    extract_market_summary,
    extract_query,
    extract_visible_sale_records,
    find_market_suggestion,
    find_recent_query_chip,
    load_ui_nodes,
)


class MobileMarketHistoryTests(unittest.TestCase):
    def test_detects_market_screen_and_extracts_summary_and_record(self) -> None:
        xml_path = self._write_xml(
            """
            <hierarchy rotation="0">
              <node text="m2ultra192g" resource-id="com.taobao.idlefish:id/keyword_text" class="android.widget.TextView" clickable="false" focused="false" bounds="[174,149][418,198]" />
              <node text="" content-desc="行情" class="android.widget.TextView" clickable="false" focused="false" bounds="[493,266][587,333]" />
              <node text="" content-desc="近7日成交均价" class="android.view.View" clickable="false" focused="false" bounds="[35,745][353,805]" />
              <node text="" content-desc="¥" class="android.view.View" clickable="false" focused="false" bounds="[35,855][74,924]" />
              <node text="" content-desc="37995" class="android.view.View" clickable="false" focused="false" bounds="[79,809][394,932]" />
              <node text="" content-desc="成交记录" class="android.view.View" clickable="false" focused="false" bounds="[35,1628][230,1688]" />
              <node text="" content-desc="成交区间" class="android.view.View" clickable="false" focused="false" bounds="[58,1750][208,1795]" />
              <node text="" content-desc="¥32850-37995" class="android.view.View" clickable="false" focused="false" bounds="[219,1750][495,1795]" />
              <node text="" content-desc="99新 苹果 M2Ultra Mac Studio 192G+1T 主机工作站" class="android.view.View" clickable="false" focused="false" bounds="[253,2038][1042,2098]" />
              <node text="" content-desc="Apple/苹果" class="android.view.View" clickable="false" focused="false" bounds="[253,2112][430,2160]" />
              <node text="" content-desc="轻微使用痕迹" class="android.view.View" clickable="false" focused="false" bounds="[461,2112][671,2160]" />
              <node text="" content-desc="发布价¥38199" class="android.view.View" clickable="false" focused="false" bounds="[253,2178][475,2220]" />
              <node text="" content-desc="发布5天后成交" class="android.view.View" clickable="false" focused="false" bounds="[506,2178][734,2220]" />
              <node text="" content-desc="成交价" class="android.view.View" clickable="false" focused="false" bounds="[943,2115][1045,2157]" />
              <node text="" content-desc="¥37995" class="android.view.View" clickable="false" focused="false" bounds="[898,2175][1045,2223]" />
            </hierarchy>
            """
        )

        nodes = load_ui_nodes(xml_path)
        snapshot = MobileMarketSnapshot(
            captured_at="2026-03-31T00:00:00+00:00",
            activity="com.taobao.idlefish/.search_implement.SearchResultActivity",
            state=detect_screen_state(nodes),
            query="m2ultra192g",
            xml_path=str(xml_path),
            screenshot_path="/tmp/example.png",
        )

        extract_market_summary(snapshot, nodes)
        extract_visible_sale_records(snapshot, nodes)

        self.assertEqual(snapshot.state, "market")
        self.assertEqual(snapshot.recent_avg_price_7d, 37995)
        self.assertEqual(snapshot.sold_price_range_low, 32850)
        self.assertEqual(snapshot.sold_price_range_high, 37995)
        self.assertEqual(len(snapshot.visible_records), 1)
        self.assertEqual(snapshot.visible_records[0].sold_price, 37995)
        self.assertEqual(snapshot.visible_records[0].published_price, 38199)
        self.assertEqual(snapshot.visible_records[0].sold_after_days, 5)

    def test_detects_search_discovery_and_recent_chip(self) -> None:
        xml_path = self._write_xml(
            """
            <hierarchy rotation="0">
              <node text="" content-desc="历史搜索" class="android.view.View" clickable="false" focused="false" bounds="[42,396][156,453]" />
              <node text="" content-desc="m2ultra192g" class="android.view.View" clickable="true" focused="false" bounds="[74,566][302,614]" />
              <node text="" content-desc="猜你可能在找" class="android.view.View" clickable="false" focused="false" bounds="[48,935][300,986]" />
            </hierarchy>
            """
        )

        nodes = load_ui_nodes(xml_path)

        self.assertEqual(detect_screen_state(nodes), "search_discovery")
        chip = find_recent_query_chip(nodes, "m2ultra192g")
        assert chip is not None
        self.assertEqual(chip.normalized_text, "m2ultra192g")

    def test_detects_home_state_and_does_not_extract_hint_as_query(self) -> None:
        xml_path = self._write_xml(
            """
            <hierarchy rotation="0">
              <node text="" resource-id="com.taobao.idlefish:id/home_container" class="android.widget.FrameLayout" clickable="false" focused="false" bounds="[0,0][1080,2250]" />
              <node text="" resource-id="com.taobao.idlefish:id/default_search" class="android.widget.FrameLayout" clickable="false" focused="false" bounds="[168,108][1044,240]" />
              <node text="搜索,点击跳转到搜索激活页" class="android.widget.TextView" clickable="false" focused="false" bounds="[250,142][840,206]" />
            </hierarchy>
            """
        )
        nodes = load_ui_nodes(xml_path)

        self.assertEqual(detect_screen_state(nodes), "home")
        self.assertIsNone(extract_query(nodes))

    def test_detects_search_result_suggestion_and_query(self) -> None:
        xml_path = self._write_xml(
            """
            <hierarchy rotation="0">
              <node text="返回, 返回按钮" class="android.widget.ImageView" clickable="true" focused="false" bounds="[57,141][129,213]" />
              <node text="fenix8" class="android.widget.EditText" clickable="true" focused="true" bounds="[135,144][918,204]" />
              <node text="fenix8 查询宝贝成交价" class="android.view.View" clickable="true" focused="false" bounds="[48,980][1032,1112]" />
              <node text="fenix8 近7日成交均价 ¥4967" class="android.view.View" clickable="true" focused="false" bounds="[48,1112][1032,1245]" />
              <node text="fenix843" class="android.view.View" clickable="false" focused="false" bounds="[0,0][0,0]" />
            </hierarchy>
            """
        )
        nodes = load_ui_nodes(xml_path)

        self.assertEqual(detect_screen_state(nodes), "search_result")
        self.assertEqual(extract_query(nodes), "fenix8")
        suggestion = find_market_suggestion(nodes, "fenix8")
        assert suggestion is not None
        self.assertTrue(
            "近7日成交均价" in suggestion.normalized_text or "查询宝贝成交价" in suggestion.normalized_text
        )

    def test_extract_query_does_not_mistake_clear_button_for_query(self) -> None:
        xml_path = self._write_xml(
            """
            <hierarchy rotation="0">
              <node text="返回, 返回按钮" class="android.widget.ImageView" clickable="true" focused="false" bounds="[57,141][129,213]" />
              <node text="macminim4" class="android.widget.EditText" clickable="true" focused="true" bounds="[135,144][918,204]" />
              <node text="清除" class="android.widget.ImageView" clickable="true" focused="false" bounds="[948,132][1032,216]" />
              <node text="macminim4 行情" class="android.view.View" clickable="true" focused="false" bounds="[48,444][1032,578]" />
            </hierarchy>
            """
        )
        nodes = load_ui_nodes(xml_path)
        self.assertEqual(detect_screen_state(nodes), "search_result")
        self.assertEqual(extract_query(nodes), "macminim4")

    def test_detects_usb_dialog(self) -> None:
        xml_path = self._write_xml(
            """
            <hierarchy rotation="0">
              <node text="" content-desc="USB 连接方式" class="android.widget.TextView" clickable="false" focused="false" bounds="[108,1601][972,1682]" />
              <node text="" content-desc="取消" class="android.widget.Button" clickable="true" focused="false" bounds="[84,2184][996,2292]" />
            </hierarchy>
            """
        )

        nodes = load_ui_nodes(xml_path)
        self.assertEqual(detect_screen_state(nodes), "usb_dialog")

    def test_detects_camera_search_screen(self) -> None:
        xml_path = self._write_xml(
            """
            <hierarchy rotation="0">
              <node text="翻转" class="android.widget.TextView" clickable="true" focused="false" bounds="[925,151][1003,190]" />
              <node text="闪光灯" class="android.widget.TextView" clickable="true" focused="false" bounds="[907,313][1021,352]" />
              <node text="拍图搜" class="android.widget.TextView" clickable="true" focused="false" bounds="[865,2291][984,2361]" />
            </hierarchy>
            """
        )
        nodes = load_ui_nodes(xml_path)
        self.assertEqual(detect_screen_state(nodes), "camera_search")

    def test_detects_market_variant_with_trade_record_tabs(self) -> None:
        xml_path = self._write_xml(
            """
            <hierarchy rotation="0">
              <node text="instinct" class="android.widget.TextView" clickable="false" focused="false" bounds="[174,149][313,198]" />
              <node text="行情" class="android.widget.TextView" clickable="false" focused="false" bounds="[734,273][824,326]" />
              <node text="成交记录" class="android.view.View" clickable="false" focused="false" bounds="[35,1603][230,1663]" />
              <node text="在售宝贝" class="android.view.View" clickable="false" focused="false" bounds="[279,1606][465,1660]" />
              <node text="最近成交" class="android.view.View" clickable="false" focused="false" bounds="[854,1612][995,1654]" />
            </hierarchy>
            """
        )
        nodes = load_ui_nodes(xml_path)
        self.assertEqual(detect_screen_state(nodes), "market")

    def test_extracts_record_when_trade_card_starts_higher_on_screen(self) -> None:
        xml_path = self._write_xml(
            """
            <hierarchy rotation="0">
              <node text="forerunner265" resource-id="com.taobao.idlefish:id/keyword_text" class="android.widget.TextView" clickable="false" focused="false" bounds="[174,149][449,198]" />
              <node text="" content-desc="行情" class="android.widget.TextView" clickable="false" focused="false" bounds="[732,266][826,333]" />
              <node text="" content-desc="成交记录" class="android.view.View" clickable="false" focused="false" bounds="[35,753][230,813]" />
              <node text="" content-desc="在售宝贝" class="android.view.View" clickable="false" focused="false" bounds="[279,756][465,810]" />
              <node text="" content-desc="最近成交" class="android.view.View" clickable="false" focused="false" bounds="[854,762][995,804]" />
              <node text="" content-desc="成交区间" class="android.view.View" clickable="false" focused="false" bounds="[58,876][208,921]" />
              <node text="" content-desc="¥1380-1380" class="android.view.View" clickable="false" focused="false" bounds="[219,876][441,921]" />
              <node text="" content-desc="99新 Garmin佳明 Forerunner 265极夜黑，京" class="android.view.View" clickable="false" focused="false" bounds="[253,991][1042,1051]" />
              <node text="" content-desc="几乎全新" class="android.view.View" clickable="false" focused="false" bounds="[253,1065][394,1113]" />
              <node text="" content-desc="Garmin/佳明" class="android.view.View" clickable="false" focused="false" bounds="[425,1065][623,1113]" />
              <node text="" content-desc="发布价¥1450" class="android.view.View" clickable="false" focused="false" bounds="[253,1130][457,1172]" />
              <node text="" content-desc="发布当天成交" class="android.view.View" clickable="false" focused="false" bounds="[488,1130][698,1172]" />
              <node text="" content-desc="成交价" class="android.view.View" clickable="false" focused="false" bounds="[943,1068][1045,1110]" />
              <node text="" content-desc="¥1380" class="android.view.View" clickable="false" focused="false" bounds="[925,1127][1045,1175]" />
            </hierarchy>
            """
        )
        nodes = load_ui_nodes(xml_path)
        snapshot = MobileMarketSnapshot(
            captured_at="2026-04-02T00:00:00+00:00",
            activity="com.taobao.idlefish/.search_implement.SearchResultActivity",
            state=detect_screen_state(nodes),
            query="forerunner265",
            xml_path=str(xml_path),
            screenshot_path="/tmp/example.png",
        )

        extract_market_summary(snapshot, nodes)
        extract_visible_sale_records(snapshot, nodes)

        self.assertEqual(snapshot.state, "market")
        self.assertEqual(snapshot.sold_price_range_low, 1380)
        self.assertEqual(snapshot.sold_price_range_high, 1380)
        self.assertEqual(len(snapshot.visible_records), 1)
        self.assertEqual(snapshot.visible_records[0].sold_price, 1380)
        self.assertEqual(snapshot.visible_records[0].published_price, 1450)
        self.assertEqual(snapshot.visible_records[0].sold_after_days, 0)

    def _write_xml(self, body: str) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="mobile-history-test-"))
        path = temp_dir / "dump.xml"
        path.write_text(body.strip(), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
