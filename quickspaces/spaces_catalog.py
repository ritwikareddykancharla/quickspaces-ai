"""Stateful QuickSpaces Workspace Catalog, Personas, Multi-Modal Seed Assets & Live Mutations."""
from __future__ import annotations

import copy
import datetime
import re
import uuid
from typing import Any, Dict, List, Optional

from .governance_agent import audit_space_governance, remediate_space_governance
from .grounded_agent import answer_space_question
from .hybrid_retrieval import HybridSpaceIndex
from .models import PrincipalContext, QuickSpace, SpaceAsset
from .multimodal_ingest import EMAIL_VALUE_RE, SSN_VALUE_RE, ingest_Space_asset, mask_pii_value

PRINCIPALS: Dict[str, PrincipalContext] = {
    "vp_admin": PrincipalContext(
        role_id="vp_admin",
        display_name="VP Engineering (Admin)",
        title="Full NA + EMEA + APAC · CONFIDENTIAL Clearance · Raw PII Allowed",
        tenant_id="acme-cloud",
        max_classification="CONFIDENTIAL",
        allowed_regions=["NA", "EMEA", "APAC"],
        can_view_raw_pii=True,
        is_external=False,
    ),
    "na_analyst": PrincipalContext(
        role_id="na_analyst",
        display_name="RevOps Analyst (NA Internal)",
        title="NA Region Only · INTERNAL Clearance · Dynamic PII Masking Enforced",
        tenant_id="acme-cloud",
        max_classification="INTERNAL",
        allowed_regions=["NA"],
        can_view_raw_pii=False,
        is_external=False,
    ),
    "external_partner": PrincipalContext(
        role_id="external_partner",
        display_name="External Partner (Contractor)",
        title="External Guest · PUBLIC Assets Only · Zero Confidential/Internal Access",
        tenant_id="acme-cloud",
        max_classification="PUBLIC",
        allowed_regions=["NA", "EMEA", "APAC"],
        can_view_raw_pii=False,
        is_external=True,
    ),
}


def _seed_spaces() -> List[QuickSpace]:
    return [
        QuickSpace(
            space_id="space-q3-cloud-arr",
            tenant_id="acme-cloud",
            name="Q3 Cloud Revenue & Retention",
            department="RevOps · EMEA Sales · Identity Eng",
            description=(
                "Unifies Q3 ARR cohort tables, Executive NRR BI KPIs, the Oct 14 EMEA FinServ "
                "customer escalation call transcript, and the SCIM v2 + EU KMS engineering RFC."
            ),
            icon="chart",
            suggested_questions=[
                "Why did EMEA Enterprise net retention dip in Q3, how much ARR contracted, and when does the SCIM fix ship?",
                "Compare NA vs EMEA account NRR and show which accounts expanded the most in Q3.",
                "What are the public Enterprise seat tiers and uptime SLA commitments?",
            ],
        ),
        QuickSpace(
            space_id="space-fulfillment-launch",
            tenant_id="acme-cloud",
            name="Fulfillment Robotics Launch",
            department="Hardware Ops · Sortation Systems",
            description=(
                "Tracks regional fulfillment hub pick rates, conveyor jam anomalies on firmware v4.12.0, "
                "morning ops standup transcripts, and Peak canary rollout gates."
            ),
            icon="box",
            suggested_questions=[
                "Which fulfillment hub had a conveyor jam spike, what caused it on v4.12.0, and what did shadow patch v4.12.2 achieve?",
                "What are the 3 canary gate thresholds required before Peak deployment freeze?",
            ],
        ),
        QuickSpace(
            space_id="space-ai-governance",
            tenant_id="acme-cloud",
            name="Enterprise AI Governance & GDPR",
            department="Security · Data Platform · Compliance",
            description=(
                "Audits enterprise knowledge connectors (SharePoint, Snowflake, Salesforce, S3), "
                "EU-GDPR KMS boundaries, PII masking standards, and Workspace adoption telemetry."
            ),
            icon="shield",
            suggested_questions=[
                "Which enterprise connectors have PII exposure or sync lag, and what is our EU-GDPR KMS standard?",
                "How many weekly active seats and what citation precision does QuickSpaces maintain?",
            ],
        ),
    ]


def _seed_assets() -> List[SpaceAsset]:
    raw_assets = [
        # ---------------- SPACE 1: Q3 Cloud Revenue & Retention ----------------
        SpaceAsset(
            asset_id="asset-tbl-arr-cohorts",
            space_id="space-q3-cloud-arr",
            tenant_id="acme-cloud",
            title="Q3 Enterprise ARR & Net Retention Cohorts",
            filename="q3_arr_retention_cohorts.csv",
            modality="table",
            classification="INTERNAL",
            regions=["NA", "EMEA"],
            owner="revops-analytics@acmecloud.io",
            updated_at="2026-11-12",
            tags=["arr", "nrr", "emea", "finserv", "cohorts"],
            favorite=True,
            producer_service="snowflake-sync-worker",
            pii_masking_enforced=False,  # Governance Agent will catch & fix!
            external_guest_shared=True,  # Governance Agent will catch & revoke!
            raw_content="""account_name,region,segment,q2_arr_usd,q3_arr_usd,nrr_pct,arr_delta_usd,primary_driver,account_exec_email,cfo_contact_phone
CascadeHealth,NA,Healthcare,1850000,2240000,121.1,390000,Agentic Workspace Seat Expansion,sarah.lin@acmecloud.io,+1-206-555-0142
PacificRetail,NA,Commerce,1420000,1670000,117.6,250000,Multi-Modal BI Connectors,devon.price@acmecloud.io,+1-425-555-0198
NordBank AG,EMEA,FinServ,2100000,1480000,70.5,-620000,SCIM Provisioning Latency (19d),lukas.weber@acmecloud.io,+49-69-5550-1120
AlpineRe Zurich,EMEA,FinServ,1650000,1190000,72.1,-460000,SCIM + EU KMS Residency Audit,elena.rossi@acmecloud.io,+41-44-555-0833
EuroClear Desk,EMEA,FinServ,1280000,940000,73.4,-340000,Manual SAML Subsidiary Mapping,lukas.weber@acmecloud.io,+32-2-555-0491
ThamesMedia,EMEA,Media,980000,1140000,116.3,160000,Transcript Search Rollout,claire.benson@acmecloud.io,+44-20-5550-7721
""",
        ),
        SpaceAsset(
            asset_id="asset-bi-nrr-dashboard",
            space_id="space-q3-cloud-arr",
            tenant_id="acme-cloud",
            title="Executive Net Dollar Retention & Regional ARR Pulse",
            filename="exec_nrr_pulse.quickbi",
            modality="bi_dashboard",
            classification="INTERNAL",
            regions=["NA", "EMEA"],
            owner="bi-platform@acmecloud.io",
            updated_at="2026-11-14",
            tags=["bi", "kpi", "nrr", "executive"],
            favorite=True,
            producer_service="quicksight-metric-publisher",
            owner_sla_verified=False,  # Governance Agent will verify SLA!
            structured_payload={
                "chart_title": "Quarterly Net Dollar Retention (%) — Blended vs EMEA FinServ",
                "unit": "%",
                "kpis": [
                    {"label": "NA Enterprise NRR", "value": "119.6%", "delta": "+3.1% QoQ"},
                    {"label": "EMEA Blended NRR", "value": "79.0%", "delta": "-29.4% QoQ"},
                    {"label": "EMEA FinServ Contraction", "value": "-$1.42M", "delta": "3 Accounts Impacted"},
                    {"label": "Q4 Committed Recovery", "value": "+$1.15M", "delta": "Tied to SCIM v2 GA"},
                ],
                "series": [
                    {"label": "Q4 '25", "value": 119.0, "sub": "Blended"},
                    {"label": "Q1 '26", "value": 120.4, "sub": "Blended"},
                    {"label": "Q2 '26", "value": 118.2, "sub": "Blended"},
                    {"label": "Q3 '26 (NA)", "value": 119.6, "sub": "NA Healthy"},
                    {"label": "Q3 '26 (EMEA)", "value": 79.0, "sub": "FinServ Dip"},
                ],
                "anomaly_note": (
                    "EMEA FinServ contracted by -$1.42M across NordBank (-$620K), AlpineRe (-$460K), "
                    "and EuroClear (-$340K) while waiting on automated SCIM v2 & Frankfurt KMS pinning."
                ),
                "sql_lineage": (
                    "SELECT region, segment, ROUND(100.0 * SUM(q3_arr_usd) / SUM(q2_arr_usd), 1) AS nrr_pct "
                    "FROM governed_lake.arr_retention_cohorts GROUP BY 1, 2;"
                ),
            },
        ),
        SpaceAsset(
            asset_id="asset-vtt-emea-escalation",
            space_id="space-q3-cloud-arr",
            tenant_id="acme-cloud",
            title="Oct 14 EMEA FinServ Customer Escalation Review (Audio Transcript)",
            filename="oct14_emea_finserv_escalation.vtt",
            modality="transcript",
            classification="CONFIDENTIAL",
            regions=["NA", "EMEA"],
            owner="vp-sales-emea@acmecloud.io",
            updated_at="2026-10-14",
            tags=["escalation", "scim", "emea", "transcript"],
            favorite=False,
            producer_service="chime-transcribe-indexer",
            residency_Pin=None,  # Governance Agent will pin eu-central-1-kms!
            raw_content="""WEBVTT
[02:14] Clara Vance (VP EMEA Sales): NordBank, AlpineRe, and EuroClear did not churn off the platform, but they paused 3,100 new analyst seats—$1.42M in Q3 ARR contraction—because manual SAML subsidiary group mapping takes 19 days per business unit.
[05:40] Marcus Reid (Principal SA): All three CISOs also asked for cryptographic proof that Quick Space vector indexes for EMEA stay pinned to customer-managed KMS keys in eu-central-1 Frankfurt.
[08:45] Priya Nair (Identity & Governance Lead): Our automated SCIM v2 directory sync plus eu-central-1 CMK residency pinning cuts subsidiary onboarding from 19 days down to 12 minutes. Feature-complete build is in staging now and ships GA on November 18, 2026.
[12:10] David Chen (SVP Product): NordBank and AlpineRe signed renewal side-letters committing $1.15M in seat expansion within 14 days of the November 18 SCIM v2 GA release.
""",
        ),
        SpaceAsset(
            asset_id="asset-doc-scim-rfc",
            space_id="space-q3-cloud-arr",
            tenant_id="acme-cloud",
            title="RFC-042: Automated SCIM v2 Sync & EU-Central KMS Residency",
            filename="rfc_042_scim_v2_eu_residency.md",
            modality="document",
            classification="CONFIDENTIAL",
            regions=["NA", "EMEA"],
            owner="identity-eng@acmecloud.io",
            updated_at="2026-11-04",
            tags=["rfc", "scim", "kms", "eu-central-1"],
            favorite=True,
            producer_service="git-docs-ingestor",
            residency_Pin="eu-central-1-kms",
            raw_content="""# Executive Summary
RFC-042 eliminates the 19-day manual SAML group mapping bottleneck blocking EMEA Financial Services seat expansion ($1.42M Q3 ARR impact) and introduces regional KMS shard pinning.

## §2.1 Automated SCIM v2 Group & ACL Push
IdP group changes in Okta and Entra ID propagate into Quick Space ACLs in under 12 minutes (p99 < 45 seconds per incremental delta) with zero manual ticket intervention. GA release date: November 18, 2026.

## §3.1 EU-Central-1 Frankfurt CMK Residency Boundary
Spaces tagged with EMEA residency encrypt all document chunks, table snapshots, and embeddings under a tenant-owned AWS KMS key in eu-central-1. Cross-region retrieval from non-EMEA principals without explicit clearance is rejected prior to vector scoring.

## §4.0 Commercial Recovery Target
Unlocks $1.15M in contracted Q4 expansion across NordBank AG and AlpineRe Zurich before December 15, 2026.
""",
        ),
        SpaceAsset(
            asset_id="asset-doc-public-tiers",
            space_id="space-q3-cloud-arr",
            tenant_id="acme-cloud",
            title="QuickSpaces Public Enterprise Packaging & SLA Guide (2026)",
            filename="quickspaces_public_packaging_2026.md",
            modality="document",
            classification="PUBLIC",
            regions=["NA", "EMEA", "APAC"],
            owner="product-marketing@acmecloud.io",
            updated_at="2026-11-01",
            tags=["public", "pricing", "sla", "packaging"],
            favorite=False,
            producer_service="cms-public-sync",
            raw_content="""# Standard & Enterprise Editions
QuickSpaces Pro is priced at $24/user/month for collaborative Spaces, multi-modal search across PDFs, CSVs, and BI dashboards, and grounded AI answers. QuickSpaces Enterprise Governed is $45/user/month and includes SCIM v2, dynamic PII column masking, and regional KMS residency pinning.

## Service Level Agreement (SLA)
All Enterprise workspaces carry a 99.95% monthly availability SLA, zero training on customer content, and sub-500ms p95 hybrid retrieval latency.
""",
        ),
        # ---------------- SPACE 2: Fulfillment Robotics Launch ----------------
        SpaceAsset(
            asset_id="asset-tbl-hub-metrics",
            space_id="space-fulfillment-launch",
            tenant_id="acme-cloud",
            title="Regional Fulfillment Hub Throughput & Jam Telemetry",
            filename="regional_hub_pick_rates.csv",
            modality="table",
            classification="INTERNAL",
            regions=["NA"],
            owner="robotics-telemetry@acmecloud.io",
            updated_at="2026-11-15",
            tags=["fulfillment", "robotics", "firmware", "throughput"],
            favorite=True,
            producer_service="iot-kinesis-ingestor",
            pii_masking_enforced=False,
            raw_content="""hub_id,city,firmware_version,units_per_hour,jam_rate_pct,sort_p99_ms,on_time_cpt_pct,shift_lead_email
SEA-4,Sumner WA,v4.12.2,4820,0.38,142,99.6,m.torres@acmecloud.io
DFW-2,Irving TX,v4.11.9,4610,0.44,155,99.5,k.patel@acmecloud.io
EWR-7,Newark NJ,v4.12.0,3390,3.82,418,96.1,r.oconnor@acmecloud.io
ORD-5,Joliet IL,v4.11.9,4590,0.47,159,99.4,j.nguyen@acmecloud.io
PHX-3,Goodyear AZ,v4.12.2,4790,0.41,146,99.6,a.gomez@acmecloud.io
""",
        ),
        SpaceAsset(
            asset_id="asset-vtt-hub-standup",
            space_id="space-fulfillment-launch",
            tenant_id="acme-cloud",
            title="Nov 15 Robotics Sortation Escalation Standup",
            filename="nov15_sortation_standup.vtt",
            modality="transcript",
            classification="INTERNAL",
            regions=["NA"],
            owner="fulfillment-sre@acmecloud.io",
            updated_at="2026-11-15",
            tags=["ewr-7", "firmware", "standup"],
            favorite=True,
            raw_content="""WEBVTT
[03:18] Liam Brooks (Robotics Firmware Lead): EWR-7 conveyor jam rate jumped to 3.82% after firmware v4.12.0 enabled aggressive lidar debounce under high-gloss polybag glare, dropping on-time CPT to 96.1%.
[07:05] Hannah Cho (Site Reliability): Hotfix firmware v4.12.2 restores adaptive optical gain. On SEA-4 and PHX-3 canary cells, jam rate dropped to 0.38%-0.41% at 4,820 units/hour with 99.6% on-time CPT.
[09:50] Liam Brooks (Robotics Firmware Lead): We are rolling v4.12.2 to EWR-7 tonight at 02:00 EST maintenance window ahead of the Peak freeze.
""",
        ),
        SpaceAsset(
            asset_id="asset-bi-hub-sla",
            space_id="space-fulfillment-launch",
            tenant_id="acme-cloud",
            title="Peak Sortation CPT & Conveyor Jam Monitor",
            filename="peak_sortation_sla.quickbi",
            modality="bi_dashboard",
            classification="INTERNAL",
            regions=["NA"],
            owner="ops-bi@acmecloud.io",
            updated_at="2026-11-15",
            tags=["bi", "cpt", "jam-rate"],
            favorite=False,
            owner_sla_verified=False,
            structured_payload={
                "chart_title": "Conveyor Jam Rate (%) by Regional Hub",
                "unit": "%",
                "kpis": [
                    {"label": "Fleet Target CPT", "value": "99.4%", "delta": "Peak Gate"},
                    {"label": "EWR-7 CPT (v4.12.0)", "value": "96.1%", "delta": "-3.3% Below Gate"},
                    {"label": "SEA-4 Canary (v4.12.2)", "value": "0.38% Jam", "delta": "4,820 units/hr"},
                ],
                "series": [
                    {"label": "SEA-4", "value": 0.38, "sub": "v4.12.2"},
                    {"label": "PHX-3", "value": 0.41, "sub": "v4.12.2"},
                    {"label": "DFW-2", "value": 0.44, "sub": "v4.11.9"},
                    {"label": "ORD-5", "value": 0.47, "sub": "v4.11.9"},
                    {"label": "EWR-7", "value": 3.82, "sub": "v4.12.0 Anomaly"},
                ],
                "anomaly_note": "EWR-7 on v4.12.0 exhibits 3.82% jam rate vs <0.50% fleet norm; v4.12.2 canary resolves glare false-stops.",
                "sql_lineage": "SELECT hub_id, jam_rate_pct, on_time_cpt_pct FROM robotics.hub_hourly_rollup;",
            },
        ),
        SpaceAsset(
            asset_id="asset-doc-canary-sop",
            space_id="space-fulfillment-launch",
            tenant_id="acme-cloud",
            title="Peak Robotics Firmware Canary & Rollback SOP",
            filename="canary_firmware_deployment_sop.md",
            modality="document",
            classification="PUBLIC",
            regions=["NA", "EMEA"],
            owner="release-eng@acmecloud.io",
            updated_at="2026-11-08",
            tags=["sop", "canary", "public"],
            favorite=False,
            raw_content="""# 3-Stage Canary Promotion Gates
Every robotic sortation firmware build must clear three automated gates over 24 hours before fleet promotion:
1. Conveyor Jam Rate strictly below 0.60% across 50,000+ sorted parcels.
2. Sortation p99 decision latency at or below 180 ms.
3. Critical Pull Time (CPT) on-time fulfillment >= 99.4%.

## Automatic Rollback Trigger
Any hub exceeding 1.5% jam rate for 15 consecutive minutes triggers automatic drain and rollback to the last pinned golden image.
""",
        ),
        # ---------------- SPACE 3: Enterprise AI Governance & GDPR ----------------
        SpaceAsset(
            asset_id="asset-tbl-connectors",
            space_id="space-ai-governance",
            tenant_id="acme-cloud",
            title="Enterprise Knowledge Connector Inventory & Audit",
            filename="enterprise_connector_audit.csv",
            modality="table",
            classification="CONFIDENTIAL",
            regions=["NA", "EMEA"],
            owner="secops-ai@acmecloud.io",
            updated_at="2026-11-16",
            tags=["connectors", "gdpr", "pii", "audit"],
            favorite=True,
            pii_masking_enforced=False,
            external_guest_shared=True,
            residency_Pin=None,
            raw_content="""connector_id,source_system,indexed_assets,sync_lag_min,contains_pii,kms_region,steward_email
CONN-SP-01,SharePoint EU Legal,42800,4,YES,eu-central-1,anna.keller@acmecloud.io
CONN-SF-02,Snowflake RevOps Mart,1840,2,YES,us-west-2,raj.mehta@acmecloud.io
CONN-CRM-03,Salesforce Enterprise Escalations,9650,18,YES,eu-central-1,claire.benson@acmecloud.io
CONN-JIRA-04,Jira Engineering RFCs,31200,3,NO,us-west-2,dev-infra@acmecloud.io
""",
        ),
        SpaceAsset(
            asset_id="asset-doc-gdpr-standard",
            space_id="space-ai-governance",
            tenant_id="acme-cloud",
            title="Enterprise AI Data Boundary & Zero-Leakage ACL Standard",
            filename="enterprise_ai_data_boundary_standard.md",
            modality="document",
            classification="INTERNAL",
            regions=["NA", "EMEA"],
            owner="ciso-office@acmecloud.io",
            updated_at="2026-11-10",
            tags=["gdpr", "acl", "kms", "pii"],
            favorite=True,
            raw_content="""# Pre-Retrieval ACL Enforcement
QuickSpaces enforces tenant, regional residency, and classification clearance checks BEFORE BM25 or vector candidate generation so restricted chunks never enter prompt assembly.

## Mandatory PII Column Masking & KMS Residency
1. Tables containing email, phone, or national ID fields must enforce dynamic column masking for non-Admin principals.
2. EMEA Confidential connectors (such as SharePoint EU Legal and Salesforce Escalations) must pin KMS keys to eu-central-1 and disable external guest links.
""",
        ),
        SpaceAsset(
            asset_id="asset-bi-workspace-adoption",
            space_id="space-ai-governance",
            tenant_id="acme-cloud",
            title="QuickSpaces Enterprise Adoption & Citation Precision Telemetry",
            filename="workspace_adoption_telemetry.quickbi",
            modality="bi_dashboard",
            classification="PUBLIC",
            regions=["NA", "EMEA", "APAC"],
            owner="quick-core-telemetry@acmecloud.io",
            updated_at="2026-11-16",
            tags=["adoption", "precision", "latency"],
            favorite=False,
            owner_sla_verified=True,
            structured_payload={
                "chart_title": "Weekly Active Enterprise Seats (Thousands)",
                "unit": "k",
                "kpis": [
                    {"label": "Weekly Active Seats", "value": "14,800", "delta": "+38% MoM"},
                    {"label": "Citation Span Precision", "value": "98.4%", "delta": "Verified Spans"},
                    {"label": "Hybrid Search p95", "value": "310 ms", "delta": "BM25 + Vector RRF"},
                ],
                "series": [
                    {"label": "Aug", "value": 6.2, "sub": "k seats"},
                    {"label": "Sep", "value": 8.9, "sub": "k seats"},
                    {"label": "Oct", "value": 10.7, "sub": "k seats"},
                    {"label": "Nov", "value": 14.8, "sub": "k seats"},
                ],
                "anomaly_note": "Zero cross-tenant or cross-clearance leaks across 1.2M grounded Space queries.",
                "sql_lineage": "SELECT month, active_seats_k FROM quick_telemetry.workspace_adoption;",
            },
        ),
    ]
    return [ingest_Space_asset(a) for a in raw_assets]


class QuickSpacesWorkspace:
    """In-memory + optional DynamoDB-backed stateful service for QuickSpaces."""

    def __init__(self) -> None:
        self.spaces: List[QuickSpace] = _seed_spaces()
        self.assets: List[SpaceAsset] = _seed_assets()
        self.audit_trail: List[Dict[str, Any]] = []

    def reset(self) -> None:
        self.spaces = _seed_spaces()
        self.assets = _seed_assets()
        self.audit_trail = []

    def get_principal(self, role_id: Optional[str]) -> PrincipalContext:
        return PRINCIPALS.get(role_id or "vp_admin", PRINCIPALS["vp_admin"])

    def get_workspace_snapshot(self, space_id: str, role_id: str) -> Dict[str, Any]:
        principal = self.get_principal(role_id)
        active_space = next((s for s in self.spaces if s.space_id == space_id), self.spaces[0])
        sid = active_space.space_id

        space_summaries = []
        for sp in self.spaces:
            sp_assets = [a for a in self.assets if a.space_id == sp.space_id]
            gov = audit_space_governance(sp.space_id, self.assets)
            space_summaries.append(
                {
                    **sp.to_dict(),
                    "asset_count": len(sp_assets),
                    "accessible_count": sum(1 for a in sp_assets if principal.can_access_asset(a)[0]),
                    "readiness_score": gov["readiness_score"],
                    "open_findings": gov["open_findings_count"],
                }
            )

        assets_list = [
            a.to_summary_dict(principal)
            for a in self.assets
            if a.space_id == sid
        ]
        # Sort favorites first, then updated_at desc
        assets_list.sort(key=lambda x: (x["favorite"], x["updated_at"]), reverse=True)

        governance = audit_space_governance(sid, self.assets)

        return {
            "active_space": active_space.to_dict(),
            "spaces": space_summaries,
            "principal": principal.to_dict(),
            "available_principals": [p.to_dict() for p in PRINCIPALS.values()],
            "assets": assets_list,
            "governance": governance,
            "audit_trail": list(reversed(self.audit_trail[-12:])),
        }

    def get_asset_detail(self, asset_id: str, role_id: str) -> Dict[str, Any]:
        principal = self.get_principal(role_id)
        asset = next((a for a in self.assets if a.asset_id == asset_id), None)
        if not asset:
            raise KeyError(f"Asset '{asset_id}' not found")

        allowed, reason = principal.can_access_asset(asset)
        summary = asset.to_summary_dict(principal)
        if not allowed:
            return {
                "asset": summary,
                "blocked": True,
                "block_reason": reason,
                "payload": None,
            }

        payload = copy.deepcopy(asset.structured_payload)
        should_mask_pii = (not principal.can_view_raw_pii) or asset.pii_masking_enforced
        # Note: VP Admin can inspect raw PII unless viewing as non-admin; when pii_masking_enforced is True,
        # non-Admin roles ALWAYS see masked PII, and we also annotate masked columns clearly.
        mask_active = bool(asset.detected_pii_columns) and (not principal.can_view_raw_pii)

        if asset.modality == "table" and mask_active:
            masked_rows = []
            for row in payload.get("rows", []):
                new_row = dict(row)
                for col in asset.detected_pii_columns:
                    if col in new_row:
                        new_row[col] = mask_pii_value(new_row[col], col)
                masked_rows.append(new_row)
            payload["rows"] = masked_rows

        elif asset.modality == "document" and mask_active:
            for sec in payload.get("sections", []):
                sec["body"] = EMAIL_VALUE_RE.sub("[MASKED_EMAIL]", SSN_VALUE_RE.sub("[MASKED_SSN]", sec["body"]))

        return {
            "asset": summary,
            "blocked": False,
            "pii_masked_for_caller": mask_active,
            "pii_policy_enforced": asset.pii_masking_enforced,
            "payload": payload,
        }

    def search(
        self,
        space_id: str,
        query: str,
        role_id: str,
        modality: Optional[str] = None,
        favorites_only: bool = False,
    ) -> Dict[str, Any]:
        principal = self.get_principal(role_id)
        idx = HybridSpaceIndex(self.assets)
        res = idx.search_chunks(
            space_id=space_id,
            query=query,
            principal=principal,
            modality_filter=modality,
            favorites_only=favorites_only,
            top_k=12,
            dedupe_by_asset=True,
        )
        # Strip full_text from search cards
        for h in res["hits"]:
            h.pop("full_text", None)
        return res

    def ask(self, space_id: str, question: str, role_id: str) -> Dict[str, Any]:
        principal = self.get_principal(role_id)
        return answer_space_question(
            space_id=space_id,
            question=question,
            assets=self.assets,
            principal=principal,
        )

    def toggle_favorite(self, asset_id: str) -> Dict[str, Any]:
        asset = next((a for a in self.assets if a.asset_id == asset_id), None)
        if not asset:
            raise KeyError(f"Asset '{asset_id}' not found")
        asset.favorite = not asset.favorite
        return {"asset_id": asset.asset_id, "favorite": asset.favorite}

    def ingest_custom_asset(
        self,
        space_id: str,
        title: str,
        filename: str,
        modality: str,
        classification: str,
        regions: List[str],
        raw_content: str,
        owner: str = "workspace-upload@acmecloud.io",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        clean_mod = modality if modality in ("table", "transcript", "document") else "document"
        clean_class = classification if classification in ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED_PII") else "INTERNAL"
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:24] or "upload"
        asset_id = f"asset-custom-{slug}-{uuid.uuid4().hex[:6]}"
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

        new_asset = SpaceAsset(
            asset_id=asset_id,
            space_id=space_id,
            tenant_id="acme-cloud",
            title=title.strip(),
            filename=filename.strip() or f"{slug}.txt",
            modality=clean_mod,
            classification=clean_class,
            regions=regions or ["NA", "EMEA"],
            owner=owner,
            updated_at=today,
            tags=tags or ["custom-upload", clean_mod],
            favorite=True,
            producer_service="quick-browser-ingest",
            raw_content=raw_content.strip(),
            pii_masking_enforced=False,
        )
        ingest_Space_asset(new_asset)
        self.assets.insert(0, new_asset)

        self.audit_trail.append(
            {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "event": "ASSET_INGESTED",
                "space_id": space_id,
                "detail": (
                    f"Ingested {new_asset.filename} ({new_asset.modality}, {len(new_asset.chunks)} chunks, "
                    f"PII fields detected: {len(new_asset.detected_pii_columns)})"
                ),
            }
        )
        return {
            "ingested_asset": new_asset.to_summary_dict(),
            "chunk_count": len(new_asset.chunks),
            "detected_pii_columns": new_asset.detected_pii_columns,
        }

    def remediate_governance(self, space_id: str, finding_id: Optional[str] = None) -> Dict[str, Any]:
        prev_hash = (
            self.audit_trail[-1].get("sha256_receipt", "GENESIS")
            if self.audit_trail
            else "GENESIS"
        )
        out = remediate_space_governance(
            space_id=space_id,
            assets=self.assets,
            actor="quick-governance-onboarding-agent",
            prev_chain_hash=prev_hash,
            finding_id=finding_id,
        )
        self.audit_trail.append(
            {
                "timestamp": out["audit_receipt"]["timestamp"],
                "event": "GOVERNANCE_REMEDIATED",
                "space_id": space_id,
                "detail": (
                    f"Readiness {out['score_before']} -> {out['score_after']}/100 "
                    f"({len(out['actions_applied'])} policy fix(es) applied)"
                ),
                "sha256_receipt": out["audit_receipt"]["sha256_receipt"],
            }
        )
        return out
