"""Comprehensive tests for QuickSpaces: multi-modal ingestion, ACL pre-filtered hybrid RAG, PII masking, and Governance Agent."""
from __future__ import annotations

import os
import unittest

os.environ["QUICKSPACES_OFFLINE_LLM"] = "1"

from quickspaces.spaces_catalog import QuickSpacesWorkspace


class TestQuickSpacesEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = QuickSpacesWorkspace()

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

        # Asking confidential EMEA ARR contraction question as External Partner must NOT leak $1.42M or NordBank
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
        # Should pull across multiple modalities (e.g. table/bi_dashboard + transcript + document)
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


if __name__ == "__main__":
    unittest.main()
