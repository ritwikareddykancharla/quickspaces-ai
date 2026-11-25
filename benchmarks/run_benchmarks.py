"""Reproducible benchmark suite for QuickSpaces: Hybrid Retrieval, Zero-Leakage ACL, and Governance Agent."""
from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path

os.environ["QUICKSPACES_OFFLINE_LLM"] = "1"

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
    ws = QuickSpacesWorkspace()
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
        "benchmark_suite": "QuickSpaces Multi-Modal RAG & Enterprise Governance v1.0",
        "eval_queries": len(EVAL_QUERIES),
        "hybrid_top3_recall_pct": round((top3_hits / len(EVAL_QUERIES)) * 100.0, 1),
        "citation_span_precision_pct": round(statistics.mean(citation_precisions), 1),
        "zero_leakage_acl_block_rate_pct": round((acl_blocked / len(ADVERSARIAL_ACL_PROBES)) * 100.0, 1),
        "search_latency_p50_ms": round(p50, 2),
        "search_latency_p95_ms": round(p95, 2),
        "governance_readiness_avg_before": round(statistics.mean(scores_before), 1),
        "governance_readiness_avg_after": round(statistics.mean(scores_after), 1),
    }

    out_file = Path(__file__).resolve().parent / "latest_results.json"
    out_file.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run_benchmarks()
