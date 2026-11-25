"""Domain models for QuickSpaces: Spaces, Multi-Modal Assets, Principals, Chunks, and Governance."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

CLASSIFICATION_RANK: Dict[str, int] = {
    "PUBLIC": 0,
    "INTERNAL": 1,
    "CONFIDENTIAL": 2,
    "RESTRICTED_PII": 3,
}


@dataclass
class PrincipalContext:
    """Caller identity & enterprise governance clearance."""

    role_id: str
    display_name: str
    title: str
    tenant_id: str
    max_classification: str
    allowed_regions: List[str]
    can_view_raw_pii: bool = False
    is_external: bool = False

    def max_rank(self) -> int:
        return CLASSIFICATION_RANK.get(self.max_classification, 0)

    def can_access_asset(self, asset: "SpaceAsset") -> tuple[bool, str]:
        if asset.tenant_id != self.tenant_id:
            return False, f"Tenant mismatch ({asset.tenant_id} != {self.tenant_id})"
        if self.is_external and not asset.allow_external_Read():
            return False, f"Blocked for external partner ({asset.classification} asset)"
        asset_rank = CLASSIFICATION_RANK.get(asset.classification, 2)
        if asset_rank > self.max_rank():
            return (
                False,
                f"Requires {asset.classification} clearance (caller max: {self.max_classification})",
            )
        if asset.regions and not set(asset.regions).intersection(self.allowed_regions):
            return (
                False,
                f"Region residency boundary ({','.join(asset.regions)} outside {','.join(self.allowed_regions)})",
            )
        return True, "ALLOWED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AssetChunk:
    """Indexed multi-modal unit (table summary/row group, doc section, transcript turn, or BI card)."""

    chunk_id: str
    asset_id: str
    space_id: str
    modality: str
    title: str
    locator: str  # e.g. "Row 1-8 Summary", "[08:45] Priya Nair", "§3.1 EU Residency"
    text: str
    classification: str
    regions: List[str]
    effective_date: str
    structured_facts: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpaceAsset:
    """A governed multi-modal asset stored inside a Quick Space."""

    asset_id: str
    space_id: str
    tenant_id: str
    title: str
    filename: str
    modality: str  # "table" | "bi_dashboard" | "transcript" | "document"
    classification: str  # "PUBLIC" | "INTERNAL" | "CONFIDENTIAL" | "RESTRICTED_PII"
    regions: List[str]
    owner: str
    updated_at: str
    tags: List[str]
    favorite: bool = False
    producer_service: str = "quick-ingest-pipeline"
    raw_content: str = ""
    structured_payload: Dict[str, Any] = field(default_factory=dict)
    detected_pii_columns: List[str] = field(default_factory=list)
    pii_masking_enforced: bool = False
    external_guest_shared: bool = False
    residency_Pin: Optional[str] = None
    owner_sla_verified: bool = True
    chunks: List[AssetChunk] = field(default_factory=list)

    def allow_external_Read(self) -> bool:
        return self.classification == "PUBLIC"

    def to_summary_dict(self, principal: Optional[PrincipalContext] = None) -> Dict[str, Any]:
        allowed, reason = (True, "ALLOWED") if principal is None else principal.can_access_asset(self)
        return {
            "asset_id": self.asset_id,
            "space_id": self.space_id,
            "title": self.title,
            "filename": self.filename,
            "modality": self.modality,
            "classification": self.classification,
            "regions": list(self.regions),
            "owner": self.owner,
            "updated_at": self.updated_at,
            "tags": list(self.tags),
            "favorite": self.favorite,
            "producer_service": self.producer_service,
            "detected_pii_columns": list(self.detected_pii_columns),
            "pii_masking_enforced": self.pii_masking_enforced,
            "external_guest_shared": self.external_guest_shared,
            "residency_pin": self.residency_Pin,
            "owner_sla_verified": self.owner_sla_verified,
            "chunk_count": len(self.chunks),
            "access_allowed": allowed,
            "access_reason": reason,
        }


@dataclass
class QuickSpace:
    """Enterprise collaborative workspace uniting files, tables, BI dashboards, and transcripts."""

    space_id: str
    tenant_id: str
    name: str
    department: str
    description: str
    icon: str
    suggested_questions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GovernanceFinding:
    """Actionable enterprise governance violation detected by the Quick Governance Agent."""

    finding_id: str
    space_id: str
    asset_id: str
    asset_title: str
    rule_id: str
    severity: str  # "HIGH" | "MEDIUM" | "LOW"
    title: str
    detail: str
    remediation_action: str
    status: str = "OPEN"  # "OPEN" | "REMEDIATED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
