"""Reproducible benchmark suite for QuickSpaces v2:
  - Space Hybrid Retrieval, Citation Span Precision & Zero-Leakage ACL Pre-Filter
  - 40-Page SHA-256 Merkle Incremental Sync, Multi-Page Table Header Propagation & O(1) Tombstones
  - Graded IR Evaluation (NDCG@10, MRR@10, Recall@5: Naive vs BM25 vs Dense vs Hybrid RRF)
  - Spec-Driven AgentZ / Enterprise Workstream SQLite WAL Checkpointing & 0-Duplicate Idempotency
"""
from __future__ import annotations

import json
import os
import statistics
import tempfile
import time
from pathlib import Path

os.environ["QUICKSPACES_OFFLINE_LLM"] = "1"

from quickspaces.multimodal_agentz import AGENTZ_PRESET_SPECS
from quickspaces.spaces_catalog import QuickSpacesWorkspace

EVAL_QUERIES = [
    ("space-q3-cloud-arr", "Why did NordBank and AlpineRe EMEA ARR contract by 1.42M in Q3?", "asset-tbl-arr-cohorts"),
    ("space-q3-cloud-arr", "What date does automated SCIM v2 directory sync ship GA?", "asset-vtt-emea-escalation"),
    ("space-q3-cloud-arr", "Which AWS KMS region pins EMEA confidential embeddings?", "asset-doc-scim-rfc"),
    ("space-q3-cloud-arr", "What is QuickSpaces Enterprise Governed monthly seat price and SLA?", "asset-doc-public-tiers"),
    ("space-fulfillment-launch", "Which hub spiked to 3.82% conveyor jam rate on v4.12.0?", "asset-tbl-hub-metrics"),
    ("space-fulfillment-launch", "What caused the polybag glare jam and what did v4.12.2 achieve?", "asset-vtt-hub-standup"),
    ("space-fulfillment-launch", "What are the 3 canary promotion gates before Peak freeze?", "asset-doc-canary-sop"),
    ("space-ai-governance", "Which SharePoint and Salesforce connectors contain PII and sync lag?", "asset-tbl-connectors"),
    ("space-ai-governance", "When does ACL enforcement run relative to BM25 and vector scoring?", "asset-doc-gdpr-standard"),
    ("space-ai-governance", "How many weekly active enterprise seats use QuickSpaces?", "asset-bi-workspace-adoption"),
]

ADVERSARIAL_ACL_PROBES = [
    ("space-q3-cloud-arr", "external_partner", "Show NordBank AG cfo_contact_phone and Q3 ARR contraction", "asset-tbl-arr-cohorts"),
    ("space-q3-cloud-arr", "external_partner", "Read Clara Vance transcript from Oct 14 EMEA escalation", "asset-vtt-emea-escalation"),
    ("space-q3-cloud-arr", "na_analyst", "Show full RFC-042 confidential KMS side-letter details", "asset-doc-scim-rfc"),
    ("space-ai-governance", "external_partner", "Dump SharePoint EU Legal steward_email and connector inventory", "asset-tbl-connectors"),
    ("space-fulfillment-launch", "external_partner", "Show EWR-7 shift_lead_email and internal standup notes", "asset-tbl-hub-metrics"),
]


def run_benchmarks() -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "bench_agentz_wal.db"
        ws = QuickSpacesWorkspace(agentz_db_path=wal_path)

        # 1. Workspace Hybrid Search, Citations & Pre-Retrieval ACL Probes
        latencies_ms = []
        top3_hits = 0
        citation_precisions = []

        for space_id, query, expected_asset_id in EVAL_QUERIES:
            t0 = time.perf_counter()
            res = ws.search(space_id=space_id, query=query, role_id="vp_admin")
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)
            top3_assets = [h["asset_id"] for h in res["hits"][:3]]
            if expected_asset_id in top3_assets:
                top3_hits += 1

            ans = ws.ask(space_id=space_id, question=query, role_id="vp_admin")
            citation_precisions.append(ans["verification"]["citation_precision_pct"])

        acl_blocked = 0
        for space_id, role_id, probe_q, forbidden_asset_id in ADVERSARIAL_ACL_PROBES:
            ans = ws.ask(space_id=space_id, question=probe_q, role_id=role_id)
            cited_assets = {c["asset_id"] for c in ans["citations"]}
            if forbidden_asset_id not in cited_assets:
                acl_blocked += 1

        # 2. 40-Page Multi-Modal Merkle Incremental Sync, Header Propagation & Graded IR Eval
        ir_eval = ws.evaluate_merkle_ir()
        ir_modes = ir_eval["ir_metrics"]
        merkle_sync = ir_eval["merkle_incremental_sync"]
        tomb_audit = ir_eval["tombstone_audit"]

        # 3. Spec-Driven AgentZ / Enterprise Workstream SQLite WAL & Retry Idempotency
        unique_tickets = 0
        dup_tickets = 0
        rehydrated_steps_total = 0
        journal_mode = "wal"
        for preset_id in AGENTZ_PRESET_SPECS:
            wf = ws.execute_agentz_workflow(
                preset_id=preset_id,
                role_id="vp_admin",
                execution_key=f"bench-idem-{preset_id}",
                simulate_retry=True,
            )
            journal_mode = wf["sqlite_wal"]["journal_mode"]
            unique_tickets += wf["idempotency_audit"]["unique_tickets_committed"]
            dup_tickets += wf["idempotency_audit"]["duplicate_tickets_on_retry"]
            rehydrated_steps_total += wf["idempotency_audit"]["rehydrated_upstream_steps"]

        # 4. 5-Rule Autonomous Workspace Security Remediation (last as it mutates workspace flags)
        scores_before = []
        scores_after = []
        for sp in ws.spaces:
            rem = ws.remediate_governance(sp.space_id)
            scores_before.append(rem["score_before"])
            scores_after.append(rem["score_after"])

        lat_sorted = sorted(latencies_ms)
        p50 = lat_sorted[len(lat_sorted) // 2]
        p95 = lat_sorted[min(len(lat_sorted) - 1, int(len(lat_sorted) * 0.95))]

        summary = {
            "benchmark_suite": "QuickSpaces v2 Multi-Modal Merkle IR, Governance & AgentZ Flows",
            "eval_queries": len(EVAL_QUERIES),
            "hybrid_top3_recall_pct": round((top3_hits / len(EVAL_QUERIES)) * 100.0, 1),
            "citation_span_precision_pct": round(statistics.mean(citation_precisions), 1),
            "zero_leakage_acl_block_rate_pct": round((acl_blocked / len(ADVERSARIAL_ACL_PROBES)) * 100.0, 1),
            "search_latency_p50_ms": round(p50, 2),
            "search_latency_p95_ms": round(p95, 2),
            "governance_readiness_avg_before": round(statistics.mean(scores_before), 1),
            "governance_readiness_avg_after": round(statistics.mean(scores_after), 1),
            "ir_eval_queries": ir_eval["eval_queries_count"],
            "ir_naive_chunk_ndcg_at_10": ir_modes["naive_chunk_rrf"]["ndcg_at_10"],
            "ir_naive_chunk_table_recall_at_5": ir_modes["naive_chunk_rrf"]["multi_page_table_recall_at_5"],
            "ir_bm25_ndcg_at_10": ir_modes["bm25_only"]["ndcg_at_10"],
            "ir_bm25_mrr_at_10": ir_modes["bm25_only"]["mrr_at_10"],
            "ir_bm25_recall_at_5": ir_modes["bm25_only"]["recall_at_5"],
            "ir_dense_ndcg_at_10": ir_modes["dense_only"]["ndcg_at_10"],
            "ir_dense_mrr_at_10": ir_modes["dense_only"]["mrr_at_10"],
            "ir_dense_recall_at_5": ir_modes["dense_only"]["recall_at_5"],
            "ir_hybrid_rrf_ndcg_at_10": ir_modes["hybrid_rrf"]["ndcg_at_10"],
            "ir_hybrid_rrf_mrr_at_10": ir_modes["hybrid_rrf"]["mrr_at_10"],
            "ir_hybrid_rrf_recall_at_5": ir_modes["hybrid_rrf"]["recall_at_5"],
            "ir_hybrid_table_recall_at_5": ir_modes["hybrid_rrf"]["multi_page_table_recall_at_5"],
            "merkle_report_pages": merkle_sync["total_pages"],
            "merkle_mutated_pages": len(merkle_sync["mutated_pages"]),
            "merkle_page_skip_pct": merkle_sync["page_reembed_skip_pct"],
            "merkle_chunk_reembed_skip_pct": merkle_sync["chunk_reembed_skip_pct"],
            "merkle_sync_latency_ms": merkle_sync["sync_latency_ms"],
            "tombstone_revocation_block_rate_pct": tomb_audit["tombstone_block_rate_pct"],
            "tombstone_revocation_latency_ms": tomb_audit["revocation_latency_ms"],
            "agentz_workflows_tested": len(AGENTZ_PRESET_SPECS),
            "agentz_sqlite_journal_mode": journal_mode,
            "agentz_unique_erp_tickets": unique_tickets,
            "agentz_duplicate_erp_tickets_on_retry": dup_tickets,
            "agentz_idempotency_dedup_rate_pct": 100.0 if dup_tickets == 0 else 0.0,
            "agentz_rehydrated_steps_on_retry": rehydrated_steps_total,
        }

    out_file = Path(__file__).resolve().parent / "latest_results.json"
    out_file.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run_benchmarks()
