"""Enterprise Governance Onboarding & Evaluation Agent for QuickSpaces.

Evaluates Quick Spaces and enterprise assets against 5 organizational governance controls
(PII column masking, external guest sharing, regional KMS data residency, BI metric owner SLAs,
and confidential meeting transcript retention), computes a live Readiness Score (0-100),
and executes deterministic 1-click policy remediation with a SHA-256 hash-chained audit trail.
"""
from __future__ import annotations

import datetime
import hashlib
import json
from typing import Any, Dict, List

from .models import GovernanceFinding, SpaceAsset

SEVERITY_DEDUCTION = {
    "HIGH": 16,
    "MEDIUM": 9,
    "LOW": 5,
}


def audit_space_governance(space_id: str, assets: List[SpaceAsset]) -> Dict[str, Any]:
    """Run all 5 Quick Enterprise Governance rules over a Space's assets."""
    space_assets = [a for a in assets if a.space_id == space_id]
    findings: List[GovernanceFinding] = []

    for asset in space_assets:
        # Rule 1: Unmasked PII columns in tables or inline PII in docs
        if asset.detected_pii_columns and not asset.pii_masking_enforced:
            cols_str = ", ".join(asset.detected_pii_columns)
            findings.append(
                GovernanceFinding(
                    finding_id=f"{asset.asset_id}::GOV-PII-01",
                    space_id=space_id,
                    asset_id=asset.asset_id,
                    asset_title=asset.title,
                    rule_id="GOV-PII-01",
                    severity="HIGH",
                    title=f"Unmasked PII fields detected ({cols_str})",
                    detail=(
                        f"Asset '{asset.filename}' exposes {len(asset.detected_pii_columns)} PII field(s) "
                        f"({cols_str}) without dynamic role-based masking enabled for non-Admin viewers."
                    ),
                    remediation_action="Enable dynamic column/field PII masking policy for non-privileged roles.",
                )
            )

        # Rule 2: External guest share drift on non-PUBLIC asset
        if asset.external_guest_shared and asset.classification != "PUBLIC":
            findings.append(
                GovernanceFinding(
                    finding_id=f"{asset.asset_id}::GOV-EXT-02",
                    space_id=space_id,
                    asset_id=asset.asset_id,
                    asset_title=asset.title,
                    rule_id="GOV-EXT-02",
                    severity="HIGH",
                    title=f"External guest link active on {asset.classification} asset",
                    detail=(
                        f"'{asset.filename}' is classified {asset.classification} but has an active external "
                        "partner/contractor share flag from legacy connector onboarding."
                    ),
                    remediation_action="Revoke external guest share link and enforce tenant-only ACL.",
                )
            )

        # Rule 3: EMEA Confidential asset missing regional KMS residency pin
        if (
            "EMEA" in asset.regions
            and asset.classification in ("CONFIDENTIAL", "RESTRICTED_PII")
            and not asset.residency_Pin
        ):
            findings.append(
                GovernanceFinding(
                    finding_id=f"{asset.asset_id}::GOV-RES-03",
                    space_id=space_id,
                    asset_id=asset.asset_id,
                    asset_title=asset.title,
                    rule_id="GOV-RES-03",
                    severity="MEDIUM",
                    title="EMEA confidential asset missing EU KMS residency pin",
                    detail=(
                        f"'{asset.filename}' covers EMEA enterprise accounts at {asset.classification} tier "
                        "without an explicit eu-central-1 customer-managed KMS residency boundary."
                    ),
                    remediation_action="Pin storage & vector index shards to eu-central-1 CMK boundary.",
                )
            )

        # Rule 4: BI Dashboard without verified metric owner SLA
        if asset.modality == "bi_dashboard" and not asset.owner_sla_verified:
            findings.append(
                GovernanceFinding(
                    finding_id=f"{asset.asset_id}::GOV-SLA-04",
                    space_id=space_id,
                    asset_id=asset.asset_id,
                    asset_title=asset.title,
                    rule_id="GOV-SLA-04",
                    severity="MEDIUM",
                    title="Executive BI dashboard missing verified metric owner SLA",
                    detail=(
                        f"BI asset '{asset.title}' is ground-truth indexed for AI answers without a "
                        "verified freshness & SQL lineage owner attestation."
                    ),
                    remediation_action=f"Bind verified owner attestation ({asset.owner}) & 15-min freshness check.",
                )
            )

        # Rule 5: Confidential meeting transcript missing retention lifecycle tag
        if (
            asset.modality == "transcript"
            and asset.classification in ("CONFIDENTIAL", "RESTRICTED_PII")
            and not any(t.startswith("retention:") for t in asset.tags)
        ):
            findings.append(
                GovernanceFinding(
                    finding_id=f"{asset.asset_id}::GOV-RET-05",
                    space_id=space_id,
                    asset_id=asset.asset_id,
                    asset_title=asset.title,
                    rule_id="GOV-RET-05",
                    severity="LOW",
                    title="Confidential call transcript missing lifecycle retention tag",
                    detail=(
                        f"Meeting recording transcript '{asset.filename}' lacks a mandatory "
                        "retention:90d lifecycle governance tag."
                    ),
                    remediation_action="Attach retention:90d lifecycle tag to asset metadata.",
                )
            )

    deduction = sum(SEVERITY_DEDUCTION.get(f.severity, 8) for f in findings)
    score = max(0, 100 - deduction)
    controls_total = 5
    violated_rules = {f.rule_id for f in findings}
    controls_passing = controls_total - len(violated_rules)

    return {
        "space_id": space_id,
        "readiness_score": score,
        "status_label": (
            "ENTERPRISE_READY" if score >= 90 else "ACTION_REQUIRED" if score >= 65 else "NON_COMPLIANT"
        ),
        "controls_passing": controls_passing,
        "controls_total": controls_total,
        "open_findings_count": len(findings),
        "findings": [f.to_dict() for f in findings],
    }


def remediate_space_governance(
    space_id: str,
    assets: List[SpaceAsset],
    actor: str = "quick-governance-agent",
    prev_chain_hash: str = "GENESIS",
    finding_id: str | None = None,
) -> Dict[str, Any]:
    """Apply deterministic governance fixes across open violations (or a single finding) and emit audit receipt."""
    before = audit_space_governance(space_id, assets)
    actions_applied: List[Dict[str, str]] = []

    for asset in assets:
        if asset.space_id != space_id:
            continue

        if asset.detected_pii_columns and not asset.pii_masking_enforced:
            fid = f"{asset.asset_id}::GOV-PII-01"
            if finding_id in (None, fid):
                asset.pii_masking_enforced = True
                actions_applied.append(
                    {
                        "finding_id": fid,
                        "asset_id": asset.asset_id,
                        "rule_id": "GOV-PII-01",
                        "action": f"Enabled dynamic PII masking on {', '.join(asset.detected_pii_columns)}",
                    }
                )

        if asset.external_guest_shared and asset.classification != "PUBLIC":
            fid = f"{asset.asset_id}::GOV-EXT-02"
            if finding_id in (None, fid):
                asset.external_guest_shared = False
                actions_applied.append(
                    {
                        "finding_id": fid,
                        "asset_id": asset.asset_id,
                        "rule_id": "GOV-EXT-02",
                        "action": f"Revoked external guest share on {asset.filename}",
                    }
                )

        if (
            "EMEA" in asset.regions
            and asset.classification in ("CONFIDENTIAL", "RESTRICTED_PII")
            and not asset.residency_Pin
        ):
            fid = f"{asset.asset_id}::GOV-RES-03"
            if finding_id in (None, fid):
                asset.residency_Pin = "eu-central-1-kms"
                actions_applied.append(
                    {
                        "finding_id": fid,
                        "asset_id": asset.asset_id,
                        "rule_id": "GOV-RES-03",
                        "action": f"Pinned {asset.filename} to eu-central-1 CMK residency boundary",
                    }
                )

        if asset.modality == "bi_dashboard" and not asset.owner_sla_verified:
            fid = f"{asset.asset_id}::GOV-SLA-04"
            if finding_id in (None, fid):
                asset.owner_sla_verified = True
                actions_applied.append(
                    {
                        "finding_id": fid,
                        "asset_id": asset.asset_id,
                        "rule_id": "GOV-SLA-04",
                        "action": f"Verified BI owner SLA attestation ({asset.owner})",
                    }
                )

        if (
            asset.modality == "transcript"
            and asset.classification in ("CONFIDENTIAL", "RESTRICTED_PII")
            and not any(t.startswith("retention:") for t in asset.tags)
        ):
            fid = f"{asset.asset_id}::GOV-RET-05"
            if finding_id in (None, fid):
                asset.tags.append("retention:90d")
                actions_applied.append(
                    {
                        "finding_id": fid,
                        "asset_id": asset.asset_id,
                        "rule_id": "GOV-RET-05",
                        "action": f"Attached retention:90d lifecycle policy to {asset.filename}",
                    }
                )

    after = audit_space_governance(space_id, assets)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    receipt_payload = {
        "timestamp": ts,
        "actor": actor,
        "space_id": space_id,
        "score_before": before["readiness_score"],
        "score_after": after["readiness_score"],
        "actions_count": len(actions_applied),
        "prev_hash": prev_chain_hash,
    }
    chain_hash = hashlib.sha256(json.dumps(receipt_payload, sort_keys=True).encode("utf-8")).hexdigest()

    return {
        "score_before": before["readiness_score"],
        "score_after": after["readiness_score"],
        "actions_applied": actions_applied,
        "audit_after": after,
        "audit_receipt": {
            **receipt_payload,
            "sha256_receipt": chain_hash,
        },
    }
