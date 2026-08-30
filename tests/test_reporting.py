import json
import re
import tempfile
import unittest
from pathlib import Path

from ashare_pipeline.reporting import build_progress_artifact


GENERATED_AT = "2026-08-29T00:30:00+08:00"


def build_fixture(**overrides):
    pipeline_status = {
        "state_store_test_count": 21,
        "data_batch_count": 4,
        "fetched_row_count": 14478,
        "universe_count": 5549,
        "formal_pool_count": 70,
        "announcement_cutoff_reached": False,
        "market_ready": False,
        "score_run_status": "provisional",
    }
    pipeline_status.update(overrides.pop("pipeline_status", {}))
    quality = {
        "performance_coverage": 0.72,
        "governance_verified": False,
        "event_verified": False,
        "seven_dimension_ready": False,
    }
    quality.update(overrides.pop("quality", {}))
    pilot_status = {
        "datasets": [
            {
                "dataset": "security_master",
                "source": "BaoStock",
                "status": "ready",
                "row_count": 8928,
                "as_of": "2026-08-28",
                "note": "匿名接口试采成功",
            },
            {
                "dataset": "performance_report_2026H1",
                "source": "AKShare / 东方财富",
                "status": "ready",
                "row_count": 11190,
                "as_of": "2026-08-29",
                "note": "尚待沪深A股证券主表过滤",
            },
        ]
    }
    pilot_status.update(overrides.pop("pilot_status", {}))
    return build_progress_artifact(
        pipeline_status=pipeline_status,
        quality=quality,
        pilot_status=pilot_status,
        generated_at=overrides.pop("generated_at", GENERATED_AT),
        plan_path=overrides.pop("plan_path", "work/a_share_pipeline/PLAN.md"),
        scoring_spec_path=overrides.pop(
            "scoring_spec_path", "work/a_share_pipeline/SCORING_SPEC_V2.md"
        ),
    )


def dataset(artifact, dataset_id):
    return artifact["snapshot"]["datasets"][dataset_id]


def normalize_generated_at(value):
    if isinstance(value, dict):
        return {
            key: ("<generated_at>" if key in {"generatedAt", "executed_at"} else normalize_generated_at(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [normalize_generated_at(item) for item in value]
    return value


class ProgressArtifactTests(unittest.TestCase):
    def test_top_level_shape_title_match_and_partial_notice(self):
        artifact = build_fixture()

        self.assertEqual(set(artifact), {"surface", "manifest", "snapshot", "sources"})
        self.assertEqual(artifact["surface"], "report")
        self.assertEqual(artifact["manifest"]["surface"], "report")
        self.assertEqual(artifact["snapshot"]["status"], "partial")
        title = artifact["manifest"]["title"]
        self.assertEqual(artifact["manifest"]["blocks"][0]["body"], f"# {title}")
        rendered = json.dumps(artifact, ensure_ascii=False)
        self.assertIn("partial", rendered)
        self.assertIn("正式评分未冻结", rendered)

    def test_seven_dimensions_have_complete_roles_and_weights_sum_to_100(self):
        rows = dataset(build_fixture(), "scoring_dimensions")

        self.assertEqual(len(rows), 7)
        self.assertEqual(sum(row["weight_pct"] for row in rows), 100)
        self.assertTrue(all(row["role"] and row["missing_handling"] for row in rows))
        roles = " ".join(row["role"] for row in rows)
        self.assertIn("成长等级", roles)
        self.assertIn("估值等级", roles)
        self.assertIn("风险等级", roles)
        self.assertIn("买点等级", roles)
        self.assertIn("越高越安全", roles)

    def test_limit_table_covers_text_verification_industry_templates_and_sensitivity(self):
        rows = dataset(build_fixture(), "method_limits")
        rendered = json.dumps(rows, ensure_ascii=False)

        self.assertIn("财报正文", rendered)
        self.assertIn("行业模板", rendered)
        self.assertIn("权重±5个百分点", rendered)
        self.assertIn("阈值±10分", rendered)

    def test_formal_pool_is_zero_before_freeze_even_if_input_claims_nonzero(self):
        metrics = dataset(build_fixture(), "headline_metrics")[0]

        self.assertEqual(metrics["formal_pool_count"], 0)

    def test_missing_values_remain_null_instead_of_becoming_zero(self):
        artifact = build_progress_artifact(
            pipeline_status={},
            quality=None,
            pilot_status=None,
            generated_at=GENERATED_AT,
            plan_path="work/a_share_pipeline/PLAN.md",
            scoring_spec_path="work/a_share_pipeline/SCORING_SPEC_V2.md",
        )
        metrics = dataset(artifact, "headline_metrics")[0]

        pool_fields = {"strong_pool_count", "wait_pool_count", "formal_pool_count"}
        for field, value in metrics.items():
            if field in pool_fields:
                self.assertEqual(value, 0, field)
            else:
                self.assertIsNone(value, field)
        self.assertEqual(dataset(artifact, "source_status")[0]["row_count"], None)

    def test_explicit_zero_evidence_is_not_replaced_by_a_fallback_value(self):
        artifact = build_fixture(
            pipeline_status={"fetched_row_count": 0, "universe_count": 0, "performance_coverage": 0.8},
            quality={"performance_coverage": 0.0},
            pilot_status={"total_rows": 99, "universe_count": 88, "datasets": []},
        )
        metrics = dataset(artifact, "headline_metrics")[0]

        self.assertEqual(metrics["fetched_row_count"], 0)
        self.assertEqual(metrics["universe_count"], 0)
        self.assertEqual(metrics["performance_coverage"], 0.0)

    def test_orchestrator_status_shape_is_consumed_without_manual_reshaping(self):
        artifact = build_progress_artifact(
            pipeline_status={
                "curated": {
                    "universe": {"universe_count": 100},
                    "quality": {"coverage_rate": 0.8},
                },
                "source_batches": [
                    {"source": "baostock", "dataset": "security_master", "status": "succeeded", "rows": 10},
                    {"source": "akshare", "dataset": "performance_report", "status": "succeeded", "rows": 5},
                    {"source": "akshare", "dataset": "spot", "status": "circuit_open"},
                ],
            },
            quality=None,
            pilot_status=None,
            generated_at=GENERATED_AT,
            plan_path="work/a_share_pipeline/PLAN.md",
            scoring_spec_path="work/a_share_pipeline/SCORING_SPEC_V2.md",
        )
        metrics = dataset(artifact, "headline_metrics")[0]

        self.assertEqual(metrics["data_batch_count"], 2)
        self.assertEqual(metrics["fetched_row_count"], 15)
        self.assertEqual(metrics["universe_count"], 100)
        self.assertEqual(metrics["performance_coverage"], 0.8)
        self.assertEqual(len(dataset(artifact, "source_status")), 3)

    def test_actual_orchestrator_status_payload_builds_without_adapter_reshaping(self):
        from ashare_pipeline.orchestrator import run_command

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            payload, exit_code = run_command(
                root,
                Path(directory) / "state.sqlite3",
                "status",
                now_cn="2026-08-29T09:00:00+08:00",
            )
            artifact = build_progress_artifact(
                pipeline_status=payload,
                quality=payload.get("curated", {}).get("quality"),
                pilot_status=None,
                generated_at=GENERATED_AT,
                plan_path="work/a_share_pipeline/PLAN.md",
                scoring_spec_path="work/a_share_pipeline/SCORING_SPEC_V2.md",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(artifact["snapshot"]["status"], "partial")
        self.assertIn("operational_status", artifact["snapshot"]["datasets"])

    def test_full_producer_status_fields_are_visible_and_missing_batch_source_is_inferred(self):
        artifact = build_progress_artifact(
            pipeline_status={
                "pipeline_state": "blocked",
                "curated": {
                    "quality": {
                        "cutoff_passed": True,
                        "eligible_universe_count": 100,
                        "disclosed_unique_count": 96,
                        "disclosure_coverage_rate": 0.96,
                        "core_field_completeness": 0.97,
                    },
                    "prefilter": {
                        "candidate_count": 120,
                        "is_official_score": False,
                        "reason": "仅供深抓排序，不是V2正式总分",
                    },
                },
                "source_batches": [
                    {"dataset": "balance_sheet", "status": "succeeded", "rows": 12},
                ],
                "source_errors": [
                    {
                        "source": "akshare",
                        "dataset": "spot",
                        "classification": "retryable",
                        "error": "remote disconnect",
                    }
                ],
                "circuit_breakers": ["akshare"],
                "blocked_reasons": ["formal_v2_scores_unavailable"],
                "next_actions": ["补齐完整七维特征"],
            },
            quality=None,
            pilot_status=None,
            generated_at=GENERATED_AT,
            plan_path="work/a_share_pipeline/PLAN.md",
            scoring_spec_path="work/a_share_pipeline/SCORING_SPEC_V2.md",
        )

        metrics = dataset(artifact, "headline_metrics")[0]
        balance = next(row for row in dataset(artifact, "source_status") if row["dataset"] == "balance_sheet")
        operations = json.dumps(dataset(artifact, "operational_status"), ensure_ascii=False)
        self.assertEqual(metrics["prefilter_candidate_count"], 120)
        self.assertEqual(balance["source"], "AKShare")
        for expected in ("spot", "akshare", "formal_v2_scores_unavailable", "补齐完整七维特征"):
            self.assertIn(expected, operations)

    def test_performance_coverage_card_is_distinct_from_core_completeness_gate(self):
        artifact = build_fixture(
            quality={"performance_coverage": 0.8, "core_field_completeness": 0.96}
        )
        metrics = dataset(artifact, "headline_metrics")[0]
        completeness_gate = next(
            row for row in dataset(artifact, "release_gates") if row["gate"] == "核心字段完整率"
        )

        self.assertEqual(metrics["performance_coverage"], 0.8)
        self.assertEqual(completeness_gate["status"], "通过")
        self.assertIn("96.0%", completeness_gate["evidence"])

    def test_disclosure_coverage_and_five_cell_completeness_have_separate_95_percent_gates(self):
        artifact = build_fixture(
            quality={
                "eligible_universe_count": 100,
                "disclosed_unique_count": 96,
                "disclosure_coverage_rate": 0.96,
                "core_field_completeness": 0.94,
            }
        )
        gates = {row["gate"]: row for row in dataset(artifact, "release_gates")}
        source = next(item for item in artifact["sources"] if item["id"] == "pipeline_status_snapshot")
        definitions = " ".join(source["query"]["metric_definitions"])

        self.assertEqual(gates["已披露合格证券覆盖率"]["status"], "通过")
        self.assertEqual(gates["核心字段完整率"]["status"], "未通过")
        self.assertIn("96/100", gates["已披露合格证券覆盖率"]["evidence"])
        self.assertIn("五个必需核心单元格", gates["核心字段完整率"]["requirement"])
        self.assertIn("唯一已披露合格证券数/合格证券宇宙数", definitions)
        self.assertIn("已披露合格证券数×5", definitions)

    def test_artifact_never_echoes_absolute_paths_or_credentials(self):
        artifact = build_fixture(
            pipeline_status={"token": "pipeline-secret"},
            pilot_status={
                "datasets": [
                    {
                        "dataset": "pilot",
                        "source": "C:\\Users\\Analyst\\private.csv",
                        "status": "ready",
                        "row_count": 1,
                        "note": "api_key=super-secret-value; Authorization: Bearer bearer-secret-value",
                    }
                ]
            },
        )
        rendered = json.dumps(artifact, ensure_ascii=False)

        self.assertNotIn("C:\\\\Users", rendered)
        self.assertNotIn("pipeline-secret", rendered)
        self.assertNotIn("super-secret-value", rendered)
        self.assertNotIn("bearer-secret-value", rendered)
        self.assertNotIn("api_key=", rendered.lower())

        with self.assertRaises(ValueError):
            build_fixture(plan_path="C:/Users/Analyst/PLAN.md")

    def test_recursive_sanitization_redacts_adversarial_paths_and_secret_forms(self):
        secrets = [
            r"C:\\Users\\Analyst\\secret.txt",
            r"\\\\server\\share\\secret.csv",
            "/tmp/private.json",
            "/mnt/data/private.parquet",
            "/Volumes/Desk/private.xlsx",
            "/etc/passwd",
            "/workspace/project/file.csv",
            "/data/private.sqlite",
            "/srv/app/runtime.log",
            "url-password",
            "query-token",
            "bearer-token",
            "basic-token",
            "quoted-password",
            "quoted-api-key",
        ]
        public_url = "https://example.test/public/report?view=summary"
        artifact = build_progress_artifact(
            pipeline_status={
                "pipeline_state": "blocked",
                "curated": {"quality": {"cutoff_passed": True}},
                "source_errors": [
                    {
                        "source": r"\\server\share\source",
                        "dataset": "/tmp/data.csv",
                        "classification": "retryable",
                        "error": (
                            "C:\\Users\\Analyst\\secret.txt /mnt/data/private.parquet /etc/passwd "
                            "/workspace/project/file.csv /data/private.sqlite /srv/app/runtime.log "
                            f"{public_url} "
                            "https://user:url-password@example.test/a?token=query-token "
                            "Authorization: Bearer bearer-token Basic basic-token "
                            '{"password":"quoted-password","api_key":"quoted-api-key"}'
                        ),
                    }
                ],
                "blocked_reasons": ["/Volumes/Desk/private.xlsx"],
                "next_actions": ["inspect /tmp/private.json"],
            },
            quality=None,
            pilot_status=None,
            generated_at=GENERATED_AT,
            plan_path="work/a_share_pipeline/PLAN.md",
            scoring_spec_path="work/a_share_pipeline/SCORING_SPEC_V2.md",
        )
        rendered = json.dumps(artifact, ensure_ascii=False)
        limits = json.dumps(dataset(artifact, "method_limits"), ensure_ascii=False)

        for secret in secrets:
            self.assertNotIn(secret, rendered)
        self.assertNotRegex(rendered, r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
        self.assertNotIn("\\\\server", rendered)
        self.assertIn(public_url, rendered)
        self.assertIn("已知敏感模式", limits)
        self.assertIn("不能保证识别所有秘密", limits)

    def test_every_native_card_and_table_has_resolvable_canonical_source(self):
        artifact = build_fixture()
        manifest = artifact["manifest"]
        manifest_sources = {source["id"]: source for source in manifest["sources"]}
        top_sources = {source["id"]: source for source in artifact["sources"]}

        for item in [*manifest["cards"], *manifest["charts"], *manifest["tables"]]:
            self.assertIn("sourceId", item)
            self.assertIn(item["sourceId"], manifest_sources)
            self.assertIn(item["sourceId"], top_sources)
            query = top_sources[item["sourceId"]]["query"]
            self.assertTrue(query["description"])
            self.assertTrue(query["filters"])
            self.assertTrue(query["metric_definitions"])
            self.assertIn("SELECT", query["sql"].upper())

    def test_only_chart_is_the_explainable_seven_dimension_weight_comparison(self):
        artifact = build_fixture()
        charts = artifact["manifest"]["charts"]
        chart_blocks = [
            block for block in artifact["manifest"]["blocks"] if block["type"] == "chart"
        ]

        self.assertEqual(len(charts), 1)
        self.assertEqual(len(chart_blocks), 1)
        self.assertEqual(charts[0]["dataset"], "scoring_dimensions")
        self.assertEqual(charts[0]["encodings"]["x"]["field"], "dimension")
        self.assertEqual(charts[0]["encodings"]["y"]["field"], "weight_pct")
        self.assertIn("不表示采集趋势", charts[0]["subtitle"])

    def test_each_peer_section_is_a_separate_markdown_block(self):
        markdown_blocks = [
            block for block in build_fixture()["manifest"]["blocks"] if block["type"] == "markdown"
        ]

        self.assertGreaterEqual(len(markdown_blocks), 7)
        for block in markdown_blocks[1:]:
            peer_headings = [line for line in block["body"].splitlines() if line.startswith("## ")]
            self.assertEqual(len(peer_headings), 1, block["id"])

    def test_quantitative_markdown_blocks_resolve_to_one_correct_source(self):
        artifact = build_fixture()
        source_ids = {source["id"] for source in artifact["sources"]}
        markdown = {
            block["id"]: block
            for block in artifact["manifest"]["blocks"]
            if block["type"] == "markdown"
        }

        self.assertEqual(markdown["method_summary"]["sourceId"], "scoring_spec_v2")
        self.assertEqual(markdown["lifecycle_summary"]["sourceId"], "lifecycle_status_snapshot")
        self.assertEqual(markdown["pipeline_next_steps"]["sourceId"], "execution_plan")
        self.assertEqual(markdown["sensitivity_next_step"]["sourceId"], "scoring_spec_v2")
        for block_id, block in markdown.items():
            if block_id == "report_title":
                continue
            if re.search(r"\d|%|±", block["body"]):
                self.assertIn("sourceId", block, block_id)
                self.assertIn(block["sourceId"], source_ids)

    def test_source_status_truncation_is_auditable_and_prioritizes_failures(self):
        rows = [
            {"dataset": f"ok-{index:02d}", "source": "test", "status": "succeeded", "row_count": index}
            for index in range(30)
        ]
        rows.append(
            {
                "dataset": "zzz-failure",
                "source": "test",
                "status": "retryable_failed",
                "note": "must stay visible",
            }
        )
        artifact = build_fixture(pilot_status={"datasets": rows})
        visible = dataset(artifact, "source_status")
        meta = dataset(artifact, "source_status_meta")[0]
        table = next(item for item in artifact["manifest"]["tables"] if item["id"] == "source_status_table")
        source = next(item for item in artifact["sources"] if item["id"] == "pilot_status_snapshot")
        source_metadata = " ".join(source["query"]["filters"])

        self.assertEqual(meta["reviewed_row_count"], 31)
        self.assertEqual(meta["shown_row_count"], 25)
        self.assertEqual(meta["truncated"], True)
        self.assertIn("失败/阻断/可重试优先", meta["selection_rule"])
        self.assertEqual(visible[0]["dataset"], "zzz-failure")
        self.assertIn("审阅31条", table["subtitle"])
        self.assertIn("展示25条", table["subtitle"])
        self.assertIn("truncated=true", source_metadata)

    def test_operational_truncation_is_auditable_and_never_hides_release_blockers(self):
        source_errors = [
            {
                "source": "test",
                "dataset": f"source-{index:02d}",
                "classification": "retryable",
                "error": f"ordinary error {index}",
            }
            for index in range(30)
        ]
        artifact = build_fixture(
            pipeline_status={
                "pipeline_state": "blocked",
                "curated": {"quality": {"cutoff_passed": True}},
                "source_errors": source_errors,
                "blocked_reasons": ["formal_v2_scores_unavailable"],
                "next_actions": ["补齐七维正式特征"],
            }
        )
        visible = dataset(artifact, "operational_status")
        meta = dataset(artifact, "operational_status_meta")[0]
        table = next(
            item for item in artifact["manifest"]["tables"]
            if item["id"] == "operational_status_table"
        )
        source = next(
            item for item in artifact["sources"]
            if item["id"] == "operational_status_snapshot"
        )
        source_metadata = " ".join(source["query"]["filters"])

        self.assertEqual(meta["reviewed_row_count"], 32)
        self.assertEqual(meta["shown_row_count"], 25)
        self.assertTrue(meta["truncated"])
        self.assertEqual(visible[0]["category"], "发布阻断")
        self.assertIn("formal_v2_scores_unavailable", visible[0]["detail"])
        self.assertIn("审阅32条", table["subtitle"])
        self.assertIn("展示25条", table["subtitle"])
        self.assertIn("truncated=true", source_metadata)
        self.assertIn("发布阻断优先", meta["selection_rule"])

    def test_deep_progress_counts_are_exposed_without_individual_financial_values(self):
        artifact = build_fixture(
            pipeline_status={
                "deep": {
                    "deep_candidate_count": 2,
                    "candidate_financial_coverage": {
                        "numerator": 1,
                        "denominator": 2,
                        "rate": 0.5,
                    },
                    "deep_statement_job_counts": {
                        "balance_sheet": {"succeeded": 2},
                        "profit_sheet": {"succeeded": 2},
                        "cash_flow_sheet": {"pending": 1, "succeeded": 1},
                    },
                    "statement_snapshot_counts": {
                        "balance_sheet": 2,
                        "profit_sheet": 2,
                        "cash_flow_sheet": 1,
                    },
                    "feature_set_counts": {
                        "partial": 1,
                        "financial_ready": 1,
                        "blocked": 0,
                    },
                    "incomplete_candidates": [
                        {
                            "security_id": "SH600001",
                            "missing_datasets": ["cash_flow_sheet"],
                            "job_states": ["pending"],
                            "error_classifications": ["pending"],
                        }
                    ],
                    "expired_current_lease_count": 0,
                    "unknown_failure_count": 0,
                    "active_circuit_breakers": [],
                    "latest_feature_contract_version": "feature-contract-v1",
                }
            }
        )

        operations = dataset(artifact, "operational_status")
        deep_rows = [row for row in operations if row["category"] == "深抓进度"]
        self.assertTrue(deep_rows)
        self.assertIn("1/2", " ".join(row["detail"] for row in deep_rows))
        self.assertNotIn("SH600001", json.dumps(deep_rows, ensure_ascii=False))

    def test_snapshot_datasets_are_bounded_and_do_not_copy_raw_input(self):
        many_rows = [
            {"dataset": f"dataset-{index:03d}", "source": "test", "status": "ready", "row_count": index}
            for index in range(100)
        ]
        artifact = build_fixture(pilot_status={"datasets": many_rows, "raw": "x" * 100_000})

        self.assertLessEqual(len(dataset(artifact, "source_status")), 25)
        self.assertTrue(all(len(rows) <= 25 for rows in artifact["snapshot"]["datasets"].values()))
        self.assertLessEqual(sum(len(rows) for rows in artifact["snapshot"]["datasets"].values()), 75)
        self.assertNotIn("x" * 1000, repr(artifact))

    def test_lifecycle_pre_cutoff_post_cutoff_blocked_and_final_are_input_driven(self):
        pre = build_fixture(
            pipeline_status={"pipeline_state": "partial", "curated": {"quality": {"cutoff_passed": False}}}
        )
        pre_cutoff_blocked = build_fixture(
            pipeline_status={
                "pipeline_state": "blocked",
                "curated": {"quality": {"cutoff_passed": False}},
                "blocked_reasons": ["cutoff_not_passed"],
            }
        )
        post_cutoff_blocked = build_fixture(
            pipeline_status={
                "pipeline_state": "blocked",
                "curated": {"quality": {"cutoff_passed": True}},
                "blocked_reasons": ["market_2026_08_31_missing"],
            }
        )
        ready_pipeline = {
            "pipeline_state": "final",
            "score_run_status": "final",
            "final_evidence": {
                "status": "final",
                "finalized_at": "2026-09-01T06:30:00+08:00",
            },
            "formal_pool_counts": {"strong": 20, "wait": 50},
            "market_ready": True,
            "formal_score_ready": True,
            "curated": {
                "quality": {
                    "cutoff_passed": True,
                    "market_ready": True,
                    "disclosure_coverage_rate": 0.96,
                    "core_field_completeness": 0.97,
                    "formal_score_ready": True,
                }
            },
        }
        ready_quality = {
            "disclosure_coverage_rate": 0.96,
            "core_field_completeness": 0.97,
            "governance_verified": True,
            "event_verified": True,
            "seven_dimension_ready": True,
            "formal_score_ready": True,
        }
        final = build_fixture(
            pipeline_status=ready_pipeline,
            quality=ready_quality,
        )
        missing_counts = build_fixture(
            pipeline_status={key: value for key, value in ready_pipeline.items() if key != "formal_pool_counts"},
            quality=ready_quality,
        )
        contradictory = build_fixture(
            pipeline_status={
                "pipeline_state": "final",
                "final_evidence": {"anything": True},
                "formal_pool_counts": {"strong": 20, "wait": 50},
                "curated": {"quality": {"cutoff_passed": True}},
            },
            quality={
                "disclosure_coverage_rate": 0.72,
                "core_field_completeness": 0.90,
                "governance_verified": False,
                "event_verified": False,
                "seven_dimension_ready": False,
                "formal_score_ready": False,
            },
        )
        zero_pool = build_fixture(
            pipeline_status={**ready_pipeline, "formal_pool_counts": {"strong": 0, "wait": 0}},
            quality=ready_quality,
        )

        pre_metrics = dataset(pre, "headline_metrics")[0]
        pre_blocked_text = json.dumps(pre_cutoff_blocked, ensure_ascii=False)
        post_blocked_text = json.dumps(post_cutoff_blocked, ensure_ascii=False)
        final_metrics = dataset(final, "headline_metrics")[0]
        missing_metrics = dataset(missing_counts, "headline_metrics")[0]
        self.assertEqual(pre["snapshot"]["status"], "partial")
        self.assertEqual(
            (pre_metrics["strong_pool_count"], pre_metrics["wait_pool_count"], pre_metrics["formal_pool_count"]),
            (0, 0, 0),
        )
        self.assertEqual(pre_cutoff_blocked["snapshot"]["status"], "partial")
        self.assertEqual(dataset(pre_cutoff_blocked, "lifecycle_status")[0]["derived_lifecycle_state"], "pre_cutoff_blocked")
        self.assertIn("cutoff_not_passed", pre_blocked_text)
        self.assertNotIn("公告截止已经通过", pre_blocked_text)
        self.assertEqual(post_cutoff_blocked["snapshot"]["status"], "blocked")
        self.assertIn("market_2026_08_31_missing", post_blocked_text)
        self.assertNotIn("尚未到公告截止", post_blocked_text)
        self.assertEqual(final["snapshot"]["status"], "ready")
        self.assertEqual(
            (final_metrics["strong_pool_count"], final_metrics["wait_pool_count"], final_metrics["formal_pool_count"]),
            (20, 50, 70),
        )
        self.assertNotIn("accessIssues", final["snapshot"])
        lifecycle_row = dataset(final, "lifecycle_status")[0]
        self.assertTrue(lifecycle_row["all_release_gates_passed"])
        self.assertTrue(lifecycle_row["final_marker"])
        self.assertEqual(lifecycle_row["derived_lifecycle_state"], "ready")
        self.assertEqual(missing_counts["snapshot"]["status"], "blocked")
        self.assertEqual(
            (missing_metrics["strong_pool_count"], missing_metrics["wait_pool_count"], missing_metrics["formal_pool_count"]),
            (0, 0, 0),
        )
        self.assertEqual(contradictory["snapshot"]["status"], "blocked")
        self.assertFalse(dataset(contradictory, "lifecycle_status")[0]["all_release_gates_passed"])
        self.assertEqual(zero_pool["snapshot"]["status"], "ready")
        self.assertEqual(dataset(zero_pool, "headline_metrics")[0]["formal_pool_count"], 0)

    def test_output_is_deterministic_and_only_generated_at_fields_change(self):
        first = build_fixture()
        second = build_fixture(generated_at="2026-08-29T01:30:00+08:00")

        self.assertEqual(normalize_generated_at(first), normalize_generated_at(second))
        self.assertNotEqual(first["manifest"]["generatedAt"], second["manifest"]["generatedAt"])


if __name__ == "__main__":
    unittest.main()
