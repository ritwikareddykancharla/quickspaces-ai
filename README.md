# QuickSpaces v2: Multi-Modal Enterprise AI Workspace, Merkle Hybrid IR & Spec-Driven AgentZ Flows

**Live Production App (Amazon CloudFront + Private S3 OAC + AWS Lambda + Bedrock Nova):** https://d2gltlwyzbnbxr.cloudfront.net

**QuickSpaces v2** is a full-stack enterprise workspace, multi-modal Information Retrieval engine, and spec-driven agentic execution platform built on serverless AWS infrastructure:
1. **Spaces, Format-Specific Parsers & Dynamic PII Masking**:
   - Organizes spreadsheets (`.csv`), BI KPI dashboards (`.quickbi`), timestamped call recordings (`.vtt`), and engineering RFCs (`.md`) into collaborative **Spaces** with regional residency and clearance controls.
   - Automatically detects sensitive columns (`SSN`, `API_KEY`, `email`, `phone`) on ingest and masks cells at read time for analysts while keeping a single source of truth.
2. **40-Page `SHA-256` Merkle Incremental Indexer, Multi-Page Table Header Propagation & `O(1)` Bitmap Tombstones** (`quickspaces/multimodal_agentz.py` · `/api/ir/merkle-eval`):
   - Propagates parent table titles and column/row headers onto continuation pages (`Pages 8, 9, 14, 23, 28`) across PDF page breaks so numeric cells never lose column context (`0.8998 NDCG@10` vs. `0.7183` naive fixed-page chunking).
   - Diffs binary `SHA-256` page Merkle trees on updates: modifying a single Q4 table on Page 28 skips `39 / 40` pages (`97.5%` page skip and `96.55%` chunk re-embed skip in `0.603 ms`).
   - Enforces instant `O(1)` bitwise bitmap tombstones (`0.0012 ms`, `100.0%` revoked chunks blocked) prior to candidate scoring.
3. **Spec-Driven `AgentZ` / Enterprise Workstream Flow Compiler** (`quickspaces/multimodal_agentz.py` · `/api/agentz/execute`):
   - Compiles declarative customer JSON engagement specs (`allowed_spaces`, `idempotent_erp_tools`, `sla_tier`, `approval_rules`) into a 5-stage **SQLite WAL** (`journal_mode=wal`) checkpointed workflow powered by **Amazon Bedrock (`us.amazon.nova-lite-v1:0`)**.
   - Persists deterministic `SHA-256` idempotency tokens in `agentz_idempotency_ledger` so workflow retries rehydrate upstream checkpoints and commit **0 duplicate** Jira, SAP S/4HANA, or ServiceNow tickets (`100.0%` deduplication across 3 verticals).
4. **Enterprise Governance Onboarding Agent**:
   - Audits Spaces across **5 enterprise controls** (unmasked PII columns, external guest link drift, `eu-central-1` KMS residency pins, BI owner SLAs, and `retention:90d` call lifecycle tags), lifting mean readiness from `59.7 / 100` to `100 / 100` with `SHA-256` hash-chained receipts.

![QuickSpaces CloudFront Architecture](docs/architecture.svg)

---

## Measured Benchmark Results (`benchmarks/latest_results.json`)

| Metric | Measured Result |
| :--- | :--- |
| **Multi-Modal Hybrid RRF `NDCG@10` / `MRR@10`** (16 graded IR queries, header-propagated) | **0.8998 NDCG@10 / 0.9688 MRR@10** (vs. `0.7183` naive chunking, `0.8833` BM25, `0.8478` Dense) |
| **Multi-Page Continuation Table `Recall@5`** (`BM25` vs. `Dense` vs. `Hybrid RRF`) | **72.92%** (up from **62.50%** without table header propagation) |
| **40-Page `SHA-256` Merkle Incremental Sync Skip** (single Q4 table edit on Page 28) | **96.55% chunk re-embed skip / 97.5% page skip** (`39 / 40` pages skipped in `0.603 ms`) |
| **Instant `O(1)` Bitmap Tombstone Block Rate** | **100.0% blocked** (`0` stale chunks leaked in `0.0012 ms`) |
| **AgentZ SQLite WAL Retry Idempotency** (3 customer specs, 6 outbound ERP/Jira mutations) | **0 duplicate tickets on retry** (`100.0%` dedup, `6` upstream checkpoints rehydrated) |
| **Workspace Hybrid Top-3 Asset Recall** | **90.0%** (`0.70 ms p50 / 2.20 ms p95`) |
| **Zero-Leakage Pre-Retrieval ACL Block Rate & Citation Precision** | **100.0% ACL blocked (5/5 probes) / 100.0% verified citations (10/10)** |
| **Governance Readiness Lift** (3 Enterprise Spaces, 5 controls) | **59.7 / 100 -> 100 / 100** |

---

## Interactive Capabilities in the Live Web App

1. **Merkle Multi-Modal IR & AgentZ Workflow Studio** (`Tab 03`):
   - Tune `BM25 k1`, `RRF k`, Page 28 Q4 expansion figures, and `O(1)` bitmap tombstone page masks against `/api/ir/merkle-eval` to inspect live `NDCG@10`, `MRR@10`, `Recall@5`, and continuation-page header propagation.
   - Select or edit declarative JSON customer specs (`emea-finserv-arr-recovery`, `robotics-ewr7-hotfix-rollout`, `gdpr-connector-kms-remediation`) and run `/api/agentz/execute` on **Amazon Bedrock (`us.amazon.nova-lite-v1:0`)** with SQLite WAL checkpointing and retry replay verification.
2. **Role-Based PII Masking & Pre-Search Access Isolation** (`Tab 01` & `Tab 02`):
   - Switch between `vp_admin`, `na_analyst`, and `external_partner` to verify dynamic cell masking (`[REDACTED:SSN]`, `[REDACTED:API_KEY]`), pre-retrieval asset locks, cross-file Bedrock Q&A, and automatic SVG BI chart generation.
3. **Five-Rule Security Auditor** (`Tab 04`):
   - Inspect workspace configuration drift (`45/100`, `75/100`, `59/100`) and apply 1-click remediation (`100/100`) backed by `SHA-256` receipt chains.

---

## Run Locally & Deploy to Amazon CloudFront

```bash
# 1. Run unit tests & regenerate reproducible benchmarks
PYTHONPATH=. python3 -m unittest discover -s tests -v
PYTHONPATH=. python3 benchmarks/run_benchmarks.py

# 2. Start the interactive workspace locally
PYTHONPATH=. python3 -m quickspaces.server
# -> Open http://localhost:3095

# 3. Deploy to Amazon CloudFront + Private S3 (OAC) + AWS Lambda + Amazon Bedrock (us-west-2)
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
export AWS_PROFILE=portfolio AWS_DEFAULT_REGION=us-west-2
./infra/deploy_cloudfront.sh
```
