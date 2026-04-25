import unittest

from goofish_insight.models import Base


class CatalogModelTests(unittest.TestCase):
    def test_catalog_tables_are_registered_in_metadata(self) -> None:
        table_names = set(Base.metadata.tables)

        self.assertTrue(
            {
                "category",
                "category_runtime_profile",
                "category_model_catalog",
                "category_model_alias",
                "attribute_definition",
                "attribute_option",
                "category_attr_template",
                "category_attr_template_item",
                "sku_spec_schema_snapshots",
                "crawl_task_query",
                "crawl_task_lexicon",
                "xianyu_category_mapping",
                "xianyu_category_onboarding_queue",
                "product_spu",
                "product_sku",
                "product_spu_attr_value",
                "product_sku_attr_value",
                "outbox_event",
                "product_attr_audit_log",
                "item_ingest_rejection",
                "buy_watch_target",
                "buy_price_baseline",
                "buy_opportunity",
                "buy_opportunity_risk",
                "buy_alert_event",
                "notification_delivery",
                "buy_decision_feedback",
                "collector_job_run",
                "collector_job_checkpoint",
                "data_quality_metric",
            }.issubset(table_names)
        )

    def test_product_sku_table_has_signature_uniqueness(self) -> None:
        product_sku = Base.metadata.tables["product_sku"]
        constraint_columns = {
            tuple(constraint.columns.keys())
            for constraint in product_sku.constraints
            if getattr(constraint, "columns", None) is not None
        }

        self.assertIn(("sku_code",), constraint_columns)
        self.assertIn(("spu_id", "sales_signature_hash"), constraint_columns)

    def test_attribute_value_json_columns_use_sql_null_for_none(self) -> None:
        spu_attr = Base.metadata.tables["product_spu_attr_value"]
        sku_attr = Base.metadata.tables["product_sku_attr_value"]

        self.assertTrue(spu_attr.c.json_value.type.none_as_null)
        self.assertTrue(sku_attr.c.json_value.type.none_as_null)

    def test_item_table_has_xianyu_category_signal_columns(self) -> None:
        item_table = Base.metadata.tables["items"]

        self.assertIn("xianyu_cat_id", item_table.c)
        self.assertIn("xianyu_tb_cat_id", item_table.c)
        self.assertIn("xianyu_c_cat_id", item_table.c)
        self.assertNotIn("title_tokens", item_table.c)

    def test_ingest_rejection_table_is_minimal_and_unique_by_platform_item(self) -> None:
        rejection_table = Base.metadata.tables["item_ingest_rejection"]
        constraint_columns = {
            tuple(constraint.columns.keys())
            for constraint in rejection_table.constraints
            if getattr(constraint, "columns", None) is not None
        }

        self.assertIn("item_id", rejection_table.c)
        self.assertIn("source_platform", rejection_table.c)
        self.assertIn("rejection_reason", rejection_table.c)
        self.assertIn("hit_count", rejection_table.c)
        self.assertNotIn("title", rejection_table.c)
        self.assertNotIn("title_tokens", rejection_table.c)
        self.assertIn(("source_platform", "item_id"), constraint_columns)

    def test_crawl_task_table_has_category_runtime_columns(self) -> None:
        crawl_task = Base.metadata.tables["crawl_tasks"]

        self.assertIn("category_id", crawl_task.c)
        self.assertIn("task_type", crawl_task.c)
        self.assertIn("profile_key", crawl_task.c)
        self.assertIn("parallel_tabs", crawl_task.c)
        self.assertIn("metadata_json", crawl_task.c)

    def test_category_runtime_profile_table_has_expected_columns_and_constraints(self) -> None:
        runtime_profile = Base.metadata.tables["category_runtime_profile"]
        constraint_columns = {
            tuple(constraint.columns.keys())
            for constraint in runtime_profile.constraints
            if getattr(constraint, "columns", None) is not None
        }

        self.assertIn("category_id", runtime_profile.c)
        self.assertIn("active_template_id", runtime_profile.c)
        self.assertIn("prompt_profile", runtime_profile.c)
        self.assertIn("extractor_profile", runtime_profile.c)
        self.assertIn("validator_profile", runtime_profile.c)
        self.assertIn(("category_id",), constraint_columns)

    def test_collector_runtime_tables_have_expected_columns_and_job_link(self) -> None:
        crawl_run = Base.metadata.tables["crawl_runs"]
        collector_job_run = Base.metadata.tables["collector_job_run"]
        collector_job_checkpoint = Base.metadata.tables["collector_job_checkpoint"]

        self.assertIn("job_run_id", crawl_run.c)
        self.assertIn("job_name", collector_job_run.c)
        self.assertIn("phase", collector_job_run.c)
        self.assertIn("status", collector_job_run.c)
        self.assertIn("metadata_json", collector_job_run.c)
        self.assertIn("scope_key", collector_job_checkpoint.c)
        self.assertIn("checkpoint_mode", collector_job_checkpoint.c)
        self.assertIn("cursor_pending", collector_job_checkpoint.c)
        self.assertIn("cursor_committed", collector_job_checkpoint.c)

    def test_category_model_and_task_extension_tables_have_expected_uniqueness(self) -> None:
        model_catalog = Base.metadata.tables["category_model_catalog"]
        model_alias = Base.metadata.tables["category_model_alias"]
        task_query = Base.metadata.tables["crawl_task_query"]
        task_lexicon = Base.metadata.tables["crawl_task_lexicon"]

        model_catalog_constraints = {
            tuple(constraint.columns.keys())
            for constraint in model_catalog.constraints
            if getattr(constraint, "columns", None) is not None
        }
        model_alias_constraints = {
            tuple(constraint.columns.keys())
            for constraint in model_alias.constraints
            if getattr(constraint, "columns", None) is not None
        }
        task_query_constraints = {
            tuple(constraint.columns.keys())
            for constraint in task_query.constraints
            if getattr(constraint, "columns", None) is not None
        }
        task_lexicon_constraints = {
            tuple(constraint.columns.keys())
            for constraint in task_lexicon.constraints
            if getattr(constraint, "columns", None) is not None
        }

        self.assertIn(("category_id", "model_code"), model_catalog_constraints)
        self.assertIn(("model_id", "alias_normalized"), model_alias_constraints)
        self.assertIn(("task_id", "query_text"), task_query_constraints)
        self.assertIn(("task_id", "lexicon_type", "term"), task_lexicon_constraints)

    def test_buy_side_tables_have_expected_columns_and_constraints(self) -> None:
        watch_target = Base.metadata.tables["buy_watch_target"]
        price_baseline = Base.metadata.tables["buy_price_baseline"]
        opportunity = Base.metadata.tables["buy_opportunity"]
        opportunity_risk = Base.metadata.tables["buy_opportunity_risk"]
        alert_event = Base.metadata.tables["buy_alert_event"]
        notification_delivery = Base.metadata.tables["notification_delivery"]
        feedback = Base.metadata.tables["buy_decision_feedback"]
        outreach = Base.metadata.tables["outreach_records"]

        def constraint_columns(table_name: str) -> set[tuple[str, ...]]:
            return {
                tuple(constraint.columns.keys())
                for constraint in Base.metadata.tables[table_name].constraints
                if getattr(constraint, "columns", None) is not None
            }

        self.assertIn("budget_ceiling", watch_target.c)
        self.assertIn("risk_tolerance", watch_target.c)
        self.assertIn("notify_cooldown_minutes", watch_target.c)
        self.assertIn(
            ("category_id", "model_catalog_id", "target_name", "profile_key"),
            constraint_columns("buy_watch_target"),
        )

        self.assertIn("fair_price", price_baseline.c)
        self.assertIn("buy_ceiling", price_baseline.c)
        self.assertIn("confidence", price_baseline.c)
        self.assertIn("schema_id", price_baseline.c)
        self.assertIn(
            ("category_id", "model_catalog_id", "schema_id", "baseline_key", "baseline_date"),
            constraint_columns("buy_price_baseline"),
        )

        self.assertIn("discount_rate", opportunity.c)
        self.assertIn("opportunity_score", opportunity.c)
        self.assertIn("risk_score", opportunity.c)
        self.assertIn(("item_id_ref", "watch_target_id"), constraint_columns("buy_opportunity"))

        self.assertIn("risk_code", opportunity_risk.c)
        self.assertIn("risk_level", opportunity_risk.c)
        self.assertIn(("opportunity_id", "risk_code"), constraint_columns("buy_opportunity_risk"))

        self.assertIn("alert_channel", alert_event.c)
        self.assertIn("sent_at", alert_event.c)
        self.assertIn("alert_event_id", notification_delivery.c)
        self.assertIn("next_retry_at", notification_delivery.c)
        self.assertIn("attempt_count", notification_delivery.c)
        self.assertIn("feedback_label", feedback.c)
        self.assertIn("purchase_price", feedback.c)
        self.assertIn("outcome_status", outreach.c)
        self.assertIn("deal_price", outreach.c)
        self.assertIn("closed_at", outreach.c)
        self.assertIn("operator_note", outreach.c)

    def test_template_item_has_pricing_role_contract_columns(self) -> None:
        template_item = Base.metadata.tables["category_attr_template_item"]

        self.assertIn("role", template_item.c)
        self.assertIn("weight", template_item.c)
        self.assertIn("normalization", template_item.c)
        self.assertIn("enum_values", template_item.c)

    def test_spec_schema_snapshot_table_has_versioned_contract_columns(self) -> None:
        schema_snapshot = Base.metadata.tables["sku_spec_schema_snapshots"]
        constraint_columns = {
            tuple(constraint.columns.keys())
            for constraint in schema_snapshot.constraints
            if getattr(constraint, "columns", None) is not None
        }

        self.assertIn("schema_id", schema_snapshot.c)
        self.assertIn("category_code", schema_snapshot.c)
        self.assertIn("template_version", schema_snapshot.c)
        self.assertIn("locking_attrs", schema_snapshot.c)
        self.assertIn("required_attrs", schema_snapshot.c)
        self.assertIn("variant_attrs", schema_snapshot.c)
        self.assertIn("condition_attrs", schema_snapshot.c)
        self.assertIn("weights", schema_snapshot.c)
        self.assertIn("valid_from", schema_snapshot.c)
        self.assertIn("valid_to", schema_snapshot.c)
        self.assertIn(("category_code", "template_version"), constraint_columns)


if __name__ == "__main__":
    unittest.main()
