import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from goofish_insight.application.services.review_v3_mapping import (
    V3_STATUS_MANUAL_AUDIT_REQUIRED,
    V3_STATUS_VALID_READY_FOR_PRICING,
    CatalogCandidate,
    _should_direct_map,
    apply_second_pass_resolution,
    camera_body_model_hint_tokens,
    garmin_model_hint_tokens,
    infer_lens_mount,
    normalize_brand,
    normalize_mount,
    resolve_category,
)
from goofish_insight.application.services.review_v3_profiles import (
    AIRPODS_PROFILE,
    APPLE_PROFILE,
    CAMERA_BODY_PROFILE,
    GARMIN_PROFILE,
    PHONE_PROFILE,
)


class ReviewV3MappingTests(unittest.TestCase):
    def test_resolve_category_prefers_profile_business_domain_over_legacy_item_domain(self) -> None:
        profile_category = SimpleNamespace(id="phone-category", code="phone")

        class _Result:
            def __init__(self, value):
                self._value = value

            def scalar_one_or_none(self):
                return self._value

        session = Mock()
        session.execute.side_effect = [_Result(profile_category)]
        item = SimpleNamespace(resolved_category_id="legacy-apple", business_domain="apple_computer")

        category = resolve_category(session, item=item, profile=PHONE_PROFILE)

        self.assertEqual(category.id, "phone-category")
        session.get.assert_not_called()

    def test_normalize_brand_handles_mixed_separator_value(self) -> None:
        self.assertEqual(normalize_brand('Garmin/佳明'), 'garmin')
        self.assertEqual(normalize_brand('Apple / 苹果'), 'apple')

    def test_normalize_mount_understands_named_mounts(self) -> None:
        self.assertEqual(normalize_mount('Z卡口'), 'z')
        self.assertEqual(normalize_mount('F卡口'), 'f')
        self.assertEqual(normalize_mount('RF卡口'), 'rf')

    def test_infer_lens_mount_does_not_confuse_aperture_f_with_f_mount(self) -> None:
        self.assertEqual(
            infer_lens_mount(
                model_name='NIKKOR Z 24-70mm f/2.8 S',
                alias_text='尼康 Z 24-70 2.8 S',
                model_code='nikon_z_24_70_f28_s',
            ),
            'z',
        )

    def test_camera_body_model_hint_tokens_understand_sony_m_shorthand(self) -> None:
        tokens = camera_body_model_hint_tokens('A7M3')
        self.assertIn('a7m3', tokens)
        self.assertIn('a7iii', tokens)

    def test_garmin_model_hint_tokens_normalize_mixed_tactix_phrase(self) -> None:
        tokens = garmin_model_hint_tokens('tactix 8 泰铁时8代')
        self.assertIn('tactix8', tokens)

    def test_should_direct_map_accepts_exactish_garmin_model_hint_match(self) -> None:
        candidate = CatalogCandidate(
            model_catalog_id='garmin-venu-2s',
            model_code='garmin_watch_venu_2s',
            model_name='Venu 2S',
            brand_name='Garmin',
            alias_text='Garmin Venu 2S',
            score=0.82,
            reasons=('brand_match', 'product_line_match', 'model_hint_match'),
        )
        self.assertTrue(
            _should_direct_map(
                top_candidate=candidate,
                candidates=[candidate, CatalogCandidate(
                    model_catalog_id='garmin-venu',
                    model_code='garmin_watch_venu',
                    model_name='Venu',
                    brand_name='Garmin',
                    alias_text='Venu',
                    score=0.62,
                    reasons=('brand_match', 'product_line_match'),
                )],
                profile=GARMIN_PROFILE,
                features={'product_line': 'Venu', 'model_hint': 'Venu 2S'},
                confidence=0.9,
            )
        )

    def test_should_direct_map_accepts_strong_apple_chip_match(self) -> None:
        candidate = CatalogCandidate(
            model_catalog_id='apple-m2max',
            model_code='apple_computer_macbook_pro_14_m2_max_96g_4096g',
            model_name='MacBook Pro 14 M2 Max 96G 4096G',
            brand_name='Apple',
            alias_text='MacBook Pro 14 M2 Max 96G 4T',
            score=0.78,
            reasons=('brand_match', 'product_line_match', 'chip_match', 'memory_match', 'storage_match', 'screen_match'),
        )
        self.assertTrue(
            _should_direct_map(
                top_candidate=candidate,
                candidates=[candidate],
                profile=APPLE_PROFILE,
                features={'product_line': 'MacBook Pro', 'chip_family': 'M2 Max', 'memory_gb': 96, 'storage_gb': 4096, 'screen_size_in': 14},
                confidence=0.95,
            )
        )

    def test_should_direct_map_accepts_apple_without_product_line_when_specs_are_exact(self) -> None:
        top = CatalogCandidate(
            model_catalog_id='apple-m2max-96-4t',
            model_code='apple_computer_macbook_pro_14_m2_max_96g_4096g',
            model_name='MacBook Pro 14 M2 Max 96G 4096G',
            brand_name='Apple',
            alias_text='MacBook Pro 14 M2 Max 96G 4T',
            score=0.78,
            reasons=('brand_match', 'chip_match', 'memory_match', 'storage_match', 'screen_match'),
        )
        second = CatalogCandidate(
            model_catalog_id='apple-studio-m2max',
            model_code='apple_computer_mac_studio_m2_max_32g_512g',
            model_name='Mac Studio M2 Max 32G 512G',
            brand_name='Apple',
            alias_text='Mac Studio M2 Max',
            score=0.60,
            reasons=('brand_match', 'chip_match'),
        )
        self.assertTrue(
            _should_direct_map(
                top_candidate=top,
                candidates=[top, second],
                profile=APPLE_PROFILE,
                features={'chip_family': 'M2 Max', 'memory_gb': 96, 'storage_gb': 4096, 'screen_size_in': 14},
                confidence=0.85,
            )
        )

    def test_should_direct_map_rejects_garmin_when_top_two_candidates_tie(self) -> None:
        top = CatalogCandidate(
            model_catalog_id='garmin-venu-2',
            model_code='garmin_watch_venu_2',
            model_name='Venu 2',
            brand_name='Garmin',
            alias_text='Garmin Venu 2',
            score=0.82,
            reasons=('brand_match', 'product_line_match', 'model_hint_match'),
        )
        second = CatalogCandidate(
            model_catalog_id='garmin-venu-2-plus',
            model_code='garmin_watch_venu_2_plus',
            model_name='Venu 2 Plus',
            brand_name='Garmin',
            alias_text='Garmin Venu 2 Plus',
            score=0.82,
            reasons=('brand_match', 'product_line_match', 'model_hint_match'),
        )
        self.assertFalse(
            _should_direct_map(
                top_candidate=top,
                candidates=[top, second],
                profile=GARMIN_PROFILE,
                features={'product_line': 'Venu', 'model_hint': 'Venu 2'},
                confidence=0.7,
            )
        )

    def test_should_direct_map_accepts_garmin_exact_hint_with_small_gap(self) -> None:
        top = CatalogCandidate(
            model_catalog_id='garmin-fr-265',
            model_code='garmin_watch_forerunner_265',
            model_name='Forerunner 265',
            brand_name='Garmin',
            alias_text='佳明265',
            score=0.90,
            reasons=('brand_match', 'product_line_match', 'model_hint_exact_match'),
        )
        second = CatalogCandidate(
            model_catalog_id='garmin-fr-265s',
            model_code='garmin_watch_forerunner_265s',
            model_name='Forerunner 265S',
            brand_name='Garmin',
            alias_text='Forerunner265S',
            score=0.82,
            reasons=('brand_match', 'product_line_match', 'model_hint_match'),
        )
        self.assertTrue(
            _should_direct_map(
                top_candidate=top,
                candidates=[top, second],
                profile=GARMIN_PROFILE,
                features={'product_line': 'Forerunner', 'model_hint': '265'},
                confidence=0.8,
            )
        )

    def test_apply_second_pass_resolution_rejects_apple_chip_conflict(self) -> None:
        status, model_catalog_id, detail = apply_second_pass_resolution(
            candidate_payload=[
                {
                    'model_code': 'apple_computer_mac_studio_m3',
                    'model_catalog_id': 'model-apple-m3',
                    'name': 'Mac Studio M3',
                    'alias': 'Mac Studio',
                }
            ],
            review_payload={
                'is_resolved': True,
                'needs_human': False,
                'resolved_model_code': 'apple_computer_mac_studio_m3',
            },
            features={
                'product_line': 'Mac Studio',
                'chip_family': 'M3 Ultra',
                'memory_gb': 96,
                'storage_gb': 1024,
            },
            profile=APPLE_PROFILE,
        )

        self.assertEqual(status, V3_STATUS_MANUAL_AUDIT_REQUIRED)
        self.assertIsNone(model_catalog_id)
        self.assertEqual(detail['reason'], 'feature_conflict')
        self.assertIn('chip_family_conflict', detail['conflicts'])

    def test_apply_second_pass_resolution_accepts_matching_garmin_candidate(self) -> None:
        status, model_catalog_id, detail = apply_second_pass_resolution(
            candidate_payload=[
                {
                    'model_code': 'garmin_watch_fenix_8_47mm_amoled',
                    'model_catalog_id': 'model-garmin-fenix8',
                    'name': 'Fenix 8 47mm AMOLED',
                    'alias': 'Fenix 8',
                }
            ],
            review_payload={
                'is_resolved': True,
                'needs_human': False,
                'resolved_model_code': 'garmin_watch_fenix_8_47mm_amoled',
            },
            features={
                'product_line': 'Fenix',
                'model_hint': 'Fenix 8',
                'case_size_mm': 47,
                'display_type': 'AMOLED',
                'is_solar': False,
            },
            profile=GARMIN_PROFILE,
        )

        self.assertEqual(status, V3_STATUS_VALID_READY_FOR_PRICING)
        self.assertEqual(model_catalog_id, 'model-garmin-fenix8')
        self.assertTrue(detail['accepted'])

    def test_apply_second_pass_resolution_accepts_matching_camera_body_candidate(self) -> None:
        status, model_catalog_id, detail = apply_second_pass_resolution(
            candidate_payload=[
                {
                    'model_code': 'camera_body_sony_a7r_iv',
                    'model_catalog_id': 'model-sony-a7riv',
                    'name': 'Sony A7R IV',
                    'alias': 'Sony A7R4',
                }
            ],
            review_payload={
                'is_resolved': True,
                'needs_human': False,
                'resolved_model_code': 'camera_body_sony_a7r_iv',
            },
            features={
                'product_line': 'Alpha',
                'model_hint': 'A7R IV',
            },
            profile=CAMERA_BODY_PROFILE,
        )

        self.assertEqual(status, V3_STATUS_VALID_READY_FOR_PRICING)
        self.assertEqual(model_catalog_id, 'model-sony-a7riv')
        self.assertTrue(detail['accepted'])

    def test_apply_second_pass_resolution_rejects_phone_storage_conflict(self) -> None:
        status, model_catalog_id, detail = apply_second_pass_resolution(
            candidate_payload=[
                {
                    'model_code': 'phone_iphone_16_128g',
                    'model_catalog_id': 'model-iphone-16-128',
                    'name': 'iPhone 16 128G',
                    'alias': '苹果16 128G',
                }
            ],
            review_payload={
                'is_resolved': True,
                'needs_human': False,
                'resolved_model_code': 'phone_iphone_16_128g',
            },
            features={
                'product_line': 'iPhone',
                'model_hint': 'iPhone 16',
                'storage_gb': 256,
            },
            profile=PHONE_PROFILE,
        )

        self.assertEqual(status, V3_STATUS_MANUAL_AUDIT_REQUIRED)
        self.assertIsNone(model_catalog_id)
        self.assertIn('storage_conflict', detail['conflicts'])

    def test_apply_second_pass_resolution_accepts_matching_airpods_candidate(self) -> None:
        status, model_catalog_id, detail = apply_second_pass_resolution(
            candidate_payload=[
                {
                    'model_code': 'apple_airpods_4_anc',
                    'model_catalog_id': 'model-airpods-4-anc',
                    'name': 'AirPods 4 ANC',
                    'alias': 'AirPods 4 主动降噪',
                }
            ],
            review_payload={
                'is_resolved': True,
                'needs_human': False,
                'resolved_model_code': 'apple_airpods_4_anc',
            },
            features={
                'product_line': 'AirPods',
                'model_hint': 'AirPods 4 ANC',
                'has_anc': True,
            },
            profile=AIRPODS_PROFILE,
        )

        self.assertEqual(status, V3_STATUS_VALID_READY_FOR_PRICING)
        self.assertEqual(model_catalog_id, 'model-airpods-4-anc')
        self.assertTrue(detail['accepted'])


if __name__ == '__main__':
    unittest.main()
