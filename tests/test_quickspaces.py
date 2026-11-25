"""Comprehensive tests for QuickSpaces v2:
  - Multi-modal ingestion, ACL pre-filtered hybrid RAG, PII masking, and Governance Agent
  - 40-page SHA-256 Merkle incremental indexer, multi-page table header propagation, O(1) tombstones & IR eval
  - Spec-driven AgentZ / Enterprise Workstream SQLite WAL compiler & 0-duplicate ERP idempotency
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ["QUICKSPACES_OFFLINE_LLM"] = "1"

from quickspaces.server import route_api_request
from quickspaces.spaces_catalog import QuickSpacesWorkspace


class TestQuickSpacesEngine(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.wal_db = Path(self._tmp.name) / "test_agentz_wal.db"
        self.ws = QuickSpacesWorkspace(agentz_db_path=self.wal_db)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_multimodal_seed_ingestion_and_pii_detection(self) -> None:
        snap = self.ws.get_workspace_snapshot("space-q3-cloud-arr", "vp_admin")
        self.assertEqual(len(snap["spaces"]), 3)
        self.assertGreaterEqual(len(snap["assets"]), 5)

        arr_tbl = next(a for a in snap["assets"] if a["asset_id"] == "asset-tbl-arr-cohorts")
        self.assertEqual(arr_tbl["modality"], "table")
        self.assertIn("account_exec_email", arr_tbl["detected_pii_columns"])
        self.assertIn("cfo_contact_phone", arr_tbl["detected_pii_columns"])
        self.assertGreaterEqual(arr_tbl["chunk_count"], 7)

    def test_dynamic_pii_masking_between_admin_and_analyst(self) -> None:
        admin_view = self.ws.get_asset_detail("asset-tbl-arr-cohorts", "vp_admin")
        analyst_view = self.ws.get_asset_detail("asset-tbl-arr-cohorts", "na_analyst")

        self.assertFalse(admin_view["blocked"])
        self.assertFalse(admin_view["pii_masked_for_caller"])
        self.assertEqual(
            admin_view["payload"]["rows"][0]["account_exec_email"],
            "sarah.lin@acmecloud.io",
        )

        self.assertFalse(analyst_view["blocked"])
        self.assertTrue(analyst_view["pii_masked_for_caller"])
        masked_email = analyst_view["payload"]["rows"][0]["account_exec_email"]
        self.assertNotEqual(masked_email, "sarah.lin@acmecloud.io")
        self.assertIn("***@", masked_email)

    def test_zero_leakage_acl_prefilter_blocks_external_partner(self) -> None:
        ext_detail = self.ws.get_asset_detail("asset-vtt-emea-escalation", "external_partner")
        self.assertTrue(ext_detail["blocked"])
        self.assertIsNone(ext_detail["payload"])

        ans = self.ws.ask(
            "space-q3-cloud-arr",
            "Why did EMEA FinServ NordBank ARR contract in Q3 and when does SCIM v2 ship?",
            "external_partner",
        )
        self.assertGreaterEqual(ans["acl_summary"]["blocked_assets_count"], 4)
        for cit in ans["citations"]:
            self.assertEqual(cit["classification"], "PUBLIC")
        self.assertNotIn("NordBank", ans["answer"])

    def test_cross_modal_grounded_answer_and_auto_bi_chart_for_admin(self) -> None:
        ans = self.ws.ask(
            "space-q3-cloud-arr",
            "Why did EMEA Enterprise net retention dip in Q3, how much ARR contracted, and when does SCIM ship?",
            "vp_admin",
        )
        self.assertTrue(ans["verification"]["verified"])
        self.assertEqual(ans["verification"]["citation_precision_pct"], 100.0)
        modalities_cited = {c["modality"] for c in ans["citations"]}
        self.assertGreaterEqual(len(modalities_cited), 3)
        self.assertIsNotNone(ans["chart"])
        self.assertGreaterEqual(len(ans["chart"]["points"]), 4)

    def test_live_custom_csv_ingestion_becomes_searchable_and_chartable(self) -> None:
        csv_data = (
            "service_name,q4_cost_usd,gpu_utilization_pct,owner_email\n"
            "quick-embedder,48200,84.5,ml-infra@acmecloud.io\n"
            "quick-reranker,19400,61.2,search-eng@acmecloud.io\n"
        )
        ingested = self.ws.ingest_custom_asset(
            space_id="space-q3-cloud-arr",
            title="Q4 Quick Inference GPU Spend",
            filename="q4_gpu_spend.csv",
            modality="table",
            classification="INTERNAL",
            regions=["NA"],
            raw_content=csv_data,
        )
        self.assertIn("owner_email", ingested["detected_pii_columns"])
        self.assertEqual(ingested["chunk_count"], 3)

        ans = self.ws.ask(
            "space-q3-cloud-arr",
            "What is the q4_cost_usd and gpu_utilization_pct for quick-embedder?",
            "na_analyst",
        )
        cited_ids = [c["asset_id"] for c in ans["citations"]]
        self.assertIn(ingested["ingested_asset"]["asset_id"], cited_ids)

    def test_governance_onboarding_agent_audit_and_one_click_remediation(self) -> None:
        before = self.ws.get_workspace_snapshot("space-q3-cloud-arr", "vp_admin")["governance"]
        self.assertLess(before["readiness_score"], 75)
        self.assertGreaterEqual(before["open_findings_count"], 4)

        rem = self.ws.remediate_governance("space-q3-cloud-arr")
        self.assertEqual(rem["score_after"], 100)
        self.assertEqual(rem["audit_after"]["open_findings_count"], 0)
        self.assertEqual(len(rem["audit_receipt"]["sha256_receipt"]), 64)

    def test_merkle_40page_incremental_sync_skips_over_95pct_and_propagates_headers(self) -> None:
        eval_out = self.ws.evaluate_merkle_ir(custom_q4_expansion_usd=1490000)
        msync = eval_out["merkle_incremental_sync"]

        self.assertEqual(msync["total_pages"], 40)
        self.assertEqual(msync["mutated_pages"], [28])
        self.assertGreaterEqual(msync["page_reembed_skip_pct"], 97.5)
        self.assertGreaterEqual(msync["chunk_reembed_skip_pct"], 95.0)
        self.assertNotEqual(msync["merkle_root_before"], msync["merkle_root_after"])
        self.assertIn("1490000", msync["updated_q4_top_hit"]["text"])
        self.assertIn("q4_expansion_usd=1490000", msync["updated_q4_top_hit"]["text"])

        ir = eval_out["ir_metrics"]
        # Hybrid RRF with multi-page header propagation beats Naive, BM25-only, and Dense-only
        self.assertGreater(ir["hybrid_rrf"]["ndcg_at_10"], ir["naive_chunk_rrf"]["ndcg_at_10"])
        self.assertGreater(
            ir["hybrid_rrf"]["multi_page_table_recall_at_5"],
            ir["naive_chunk_rrf"]["multi_page_table_recall_at_5"],
        )
        self.assertGreater(ir["hybrid_rrf"]["ndcg_at_10"], ir["bm25_only"]["ndcg_at_10"])
        self.assertGreater(ir["hybrid_rrf"]["ndcg_at_10"], ir["dense_only"]["ndcg_at_10"])
        self.assertGreaterEqual(ir["hybrid_rrf"]["ndcg_at_10"], 0.88)

        # O(1) bitmap tombstone blocks 100% of revoked page chunks
        tomb = eval_out["tombstone_audit"]
        self.assertEqual(tomb["post_revoke_leaked_chunks"], 0)
        self.assertEqual(tomb["tombstone_block_rate_pct"], 100.0)

    def test_agentz_spec_compiler_sqlite_wal_and_zero_duplicate_erp_tickets(self) -> None:
        res = self.ws.execute_agentz_workflow(
            preset_id="emea-finserv-arr-recovery",
            role_id="vp_admin",
            execution_key="unit-test-idem-001",
            simulate_retry=True,
        )
        self.assertEqual(res["status"], "COMPLETED")
        self.assertEqual(res["sqlite_wal"]["journal_mode"], "wal")
        self.assertEqual(len(res["steps"]), 5)
        self.assertEqual(res["idempotency_audit"]["unique_tickets_committed"], 2)
        self.assertEqual(res["idempotency_audit"]["duplicate_tickets_on_retry"], 0)
        self.assertGreaterEqual(res["idempotency_audit"]["rehydrated_upstream_steps"], 2)
        for tr in res["tool_receipts"]:
            self.assertEqual(tr["attempt_1_status"], "COMMITTED_NEW")
            self.assertEqual(tr["retry_2_status"], "DEDUPED_FROM_WAL")
            self.assertEqual(tr["invocation_count"], 2)

        # External contractor must be halted at Step 1 by approval_rules.block_external_principals
        blocked = self.ws.execute_agentz_workflow(
            preset_id="emea-finserv-arr-recovery",
            role_id="external_partner",
            execution_key="unit-test-ext-block",
            simulate_retry=False,
        )
        self.assertEqual(blocked["status"], "BLOCKED_BY_APPROVAL_GUARDRAIL")
        self.assertEqual(len(blocked["tool_receipts"]), 0)

    def test_api_routes_merkle_eval_and_agentz_execute(self) -> None:
        code_ir, payload_ir = route_api_request("GET", "/api/ir/merkle-eval", {}, {})
        self.assertEqual(code_ir, 200)
        self.assertIn("ir_metrics", payload_ir)
        self.assertIn("merkle_incremental_sync", payload_ir)

        code_az_get, payload_az_get = route_api_request("GET", "/api/agentz/execute", {}, {})
        self.assertEqual(code_az_get, 200)
        self.assertEqual(payload_az_get["status"], "COMPLETED")
        self.assertEqual(payload_az_get["idempotency_audit"]["duplicate_tickets_on_retry"], 0)

        code_bad, payload_bad = route_api_request(
            "POST",
            "/api/agentz/execute",
            {},
            {"spec": {"workflow_id": "broken-spec-missing-fields"}},
        )
        self.assertEqual(code_bad, 400)
        self.assertIn("missing required", payload_bad["error"].lower())


if __name__ == "__main__":
    unittest.main()
