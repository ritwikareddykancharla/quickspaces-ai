"""Multi-Modal Asset Ingestion Pipeline for QuickSpaces.

Parses 4 enterprise modalities into typed structured payloads + searchable chunks:
  1. `table` (CSV)       -> typed schema, numeric column rollups, PII column scan, row-level & summary chunks
  2. `transcript` (VTT)  -> speaker turns + [MM:SS] timestamps for exact audio/video citation grounding
  3. `document` (MD/PDF) -> hierarchical H1/H2 section chunks with section anchors
  4. `bi_dashboard`      -> KPI metric cards, chart series, SQL lineage, and anomaly flags
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any, Dict, List, Tuple

from .models import AssetChunk, SpaceAsset

PII_HEADER_PATTERNS = re.compile(
    r"(email|e_mail|phone|mobile|ssn|tax_id|iban|passport|dob|contact)",
    re.IGNORECASE,
)
EMAIL_VALUE_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_VALUE_RE = re.compile(r"\+?\d[\d\-\s()]{7,}\d")
SSN_VALUE_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def mask_pii_value(val: str, col_name: str = "") -> str:
    """Deterministic PII masking for non-privileged viewers."""
    s = str(val or "")
    if EMAIL_VALUE_RE.search(s) or "email" in col_name.lower():
        parts = s.split("@")
        if len(parts) == 2:
            prefix = parts[0][:2] + "***"
            return f"{prefix}@{parts[1]}"
        return "[MASKED_EMAIL]"
    if SSN_VALUE_RE.search(s) or "ssn" in col_name.lower():
        return "***-**-" + s[-4:] if len(s) >= 4 else "[MASKED_SSN]"
    if PHONE_VALUE_RE.search(s) or "phone" in col_name.lower():
        digits = re.sub(r"\D", "", s)
        tail = digits[-4:] if len(digits) >= 4 else "XXXX"
        return f"+*-***-***-{tail}"
    return "[MASKED_PII]"


def _try_float(val: str) -> float | None:
    cleaned = str(val or "").strip().replace("$", "").replace(",", "").replace("%", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_table_csv(
    asset_id: str,
    space_id: str,
    title: str,
    raw_csv: str,
    classification: str,
    regions: List[str],
    updated_at: str,
) -> Tuple[Dict[str, Any], List[str], List[AssetChunk]]:
    """Parse CSV table into typed columns, detect PII columns, compute numeric rollups & chunks."""
    reader = csv.DictReader(io.StringIO(raw_csv.strip()))
    headers = list(reader.fieldnames or [])
    rows: List[Dict[str, str]] = [dict(r) for r in reader]

    pii_cols: List[str] = []
    col_types: Dict[str, str] = {}
    numeric_stats: Dict[str, Dict[str, float]] = {}

    for col in headers:
        values = [str(r.get(col, "")).strip() for r in rows if str(r.get(col, "")).strip()]
        is_pii = bool(PII_HEADER_PATTERNS.search(col)) or any(
            EMAIL_VALUE_RE.search(v) or SSN_VALUE_RE.search(v) for v in values[:10]
        )
        if is_pii:
            pii_cols.append(col)

        nums = [_try_float(v) for v in values]
        valid_nums = [n for n in nums if n is not None]
        if values and len(valid_nums) == len(values) and not is_pii:
            col_types[col] = "numeric"
            numeric_stats[col] = {
                "sum": round(sum(valid_nums), 2),
                "avg": round(sum(valid_nums) / len(valid_nums), 2),
                "min": round(min(valid_nums), 2),
                "max": round(max(valid_nums), 2),
                "count": len(valid_nums),
            }
        else:
            col_types[col] = "pii_string" if is_pii else "categorical"

    # Build a rich summary chunk + individual row chunks (with PII stripped from retrieval text)
    safe_headers = [h for h in headers if h not in pii_cols]
    rollup_lines = [
        f"{col}: sum={st['sum']}, avg={st['avg']}, min={st['min']}, max={st['max']}"
        for col, st in numeric_stats.items()
    ]
    summary_text = (
        f"Table '{title}' ({len(rows)} rows, columns: {', '.join(safe_headers)}). "
        f"Aggregated column metrics: {'; '.join(rollup_lines)}."
    )
    chunks: List[AssetChunk] = [
        AssetChunk(
            chunk_id=f"{asset_id}::summary",
            asset_id=asset_id,
            space_id=space_id,
            modality="table",
            title=title,
            locator=f"Table Rollup ({len(rows)} rows)",
            text=summary_text,
            classification=classification,
            regions=list(regions),
            effective_date=updated_at,
            structured_facts={"numeric_stats": numeric_stats, "row_count": len(rows)},
        )
    ]

    for idx, row in enumerate(rows, start=1):
        kv_pairs = [f"{h}={row.get(h, '')}" for h in safe_headers]
        row_text = f"Table '{title}' Row {idx}: " + ", ".join(kv_pairs)
        chunks.append(
            AssetChunk(
                chunk_id=f"{asset_id}::row-{idx}",
                asset_id=asset_id,
                space_id=space_id,
                modality="table",
                title=title,
                locator=f"Row {idx}",
                text=row_text,
                classification=classification,
                regions=list(regions),
                effective_date=updated_at,
                structured_facts={"row_index": idx, "row": {h: row.get(h, "") for h in safe_headers}},
            )
        )

    payload = {
        "headers": headers,
        "column_types": col_types,
        "rows": rows,
        "row_count": len(rows),
        "numeric_stats": numeric_stats,
    }
    return payload, pii_cols, chunks


TRANSCRIPT_LINE_RE = re.compile(r"^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*([^:]+):\s*(.+)$")


def parse_transcript_vtt(
    asset_id: str,
    space_id: str,
    title: str,
    raw_vtt: str,
    classification: str,
    regions: List[str],
    updated_at: str,
) -> Tuple[Dict[str, Any], List[AssetChunk]]:
    """Parse timestamped meeting transcript lines `[MM:SS] Speaker: Utterance`."""
    turns: List[Dict[str, str]] = []
    chunks: List[AssetChunk] = []

    for raw_line in raw_vtt.strip().splitlines():
        line = raw_line.strip()
        if not line or line.upper() == "WEBVTT":
            continue
        m = TRANSCRIPT_LINE_RE.match(line)
        if m:
            ts, speaker, utterance = m.group(1), m.group(2).strip(), m.group(3).strip()
        else:
            ts, speaker, utterance = "00:00", "Speaker", line
        turn_idx = len(turns) + 1
        turns.append({"timestamp": ts, "speaker": speaker, "text": utterance})
        chunks.append(
            AssetChunk(
                chunk_id=f"{asset_id}::turn-{turn_idx}",
                asset_id=asset_id,
                space_id=space_id,
                modality="transcript",
                title=title,
                locator=f"[{ts}] {speaker}",
                text=f"Meeting '{title}' at [{ts}] {speaker}: {utterance}",
                classification=classification,
                regions=list(regions),
                effective_date=updated_at,
                structured_facts={"timestamp": ts, "speaker": speaker},
            )
        )

    speakers = sorted({t["speaker"] for t in turns})
    payload = {
        "turn_count": len(turns),
        "speakers": speakers,
        "turns": turns,
    }
    return payload, chunks


def parse_document_markdown(
    asset_id: str,
    space_id: str,
    title: str,
    raw_md: str,
    classification: str,
    regions: List[str],
    updated_at: str,
) -> Tuple[Dict[str, Any], List[AssetChunk]]:
    """Split markdown/RFC document by section headings (`#` / `##` / `###`) preserving anchors."""
    sections: List[Dict[str, str]] = []
    current_heading = "Overview"
    buf: List[str] = []

    for line in raw_md.strip().splitlines():
        if line.startswith("#"):
            if buf:
                body = "\n".join(buf).strip()
                if body:
                    sections.append({"heading": current_heading, "body": body})
                buf = []
            current_heading = line.lstrip("#").strip()
        else:
            buf.append(line)
    if buf:
        body = "\n".join(buf).strip()
        if body:
            sections.append({"heading": current_heading, "body": body})

    chunks: List[AssetChunk] = []
    for idx, sec in enumerate(sections, start=1):
        chunks.append(
            AssetChunk(
                chunk_id=f"{asset_id}::sec-{idx}",
                asset_id=asset_id,
                space_id=space_id,
                modality="document",
                title=title,
                locator=sec["heading"],
                text=f"Document '{title}' — {sec['heading']}: {sec['body']}",
                classification=classification,
                regions=list(regions),
                effective_date=updated_at,
                structured_facts={"section": sec["heading"]},
            )
        )

    return {"sections": sections, "section_count": len(sections)}, chunks


def build_bi_dashboard_chunks(
    asset_id: str,
    space_id: str,
    title: str,
    dashboard_spec: Dict[str, Any],
    classification: str,
    regions: List[str],
    updated_at: str,
) -> List[AssetChunk]:
    """Index KPI tiles, time-series points, SQL lineage, and anomaly callouts from a BI dashboard."""
    kpis = dashboard_spec.get("kpis", [])
    series = dashboard_spec.get("series", [])
    anomaly = dashboard_spec.get("anomaly_note", "")
    sql_lineage = dashboard_spec.get("sql_lineage", "")

    kpi_summary = "; ".join(
        f"{k['label']}={k['value']} ({k.get('delta', '')})" for k in kpis
    )
    series_summary = "; ".join(
        f"{pt['label']}: {pt['value']}{dashboard_spec.get('unit', '')}" for pt in series
    )
    text = (
        f"BI Dashboard '{title}'. KPIs: {kpi_summary}. "
        f"Series ({dashboard_spec.get('chart_title', 'Trend')}): {series_summary}. "
        f"Anomaly insight: {anomaly}. SQL Lineage: {sql_lineage}"
    )
    return [
        AssetChunk(
            chunk_id=f"{asset_id}::bi-overview",
            asset_id=asset_id,
            space_id=space_id,
            modality="bi_dashboard",
            title=title,
            locator="KPI & Trend Summary",
            text=text,
            classification=classification,
            regions=list(regions),
            effective_date=updated_at,
            structured_facts={"kpis": kpis, "series": series, "anomaly_note": anomaly},
        )
    ]


def ingest_Space_asset(asset: SpaceAsset) -> SpaceAsset:
    """Run modality-specific extraction, PII detection, and chunk generation on an asset."""
    if asset.modality == "table":
        payload, pii_cols, chunks = parse_table_csv(
            asset_id=asset.asset_id,
            space_id=asset.space_id,
            title=asset.title,
            raw_csv=asset.raw_content,
            classification=asset.classification,
            regions=asset.regions,
            updated_at=asset.updated_at,
        )
        asset.structured_payload = payload
        asset.detected_pii_columns = pii_cols
        asset.chunks = chunks
    elif asset.modality == "transcript":
        payload, chunks = parse_transcript_vtt(
            asset_id=asset.asset_id,
            space_id=asset.space_id,
            title=asset.title,
            raw_vtt=asset.raw_content,
            classification=asset.classification,
            regions=asset.regions,
            updated_at=asset.updated_at,
        )
        asset.structured_payload = payload
        asset.chunks = chunks
    elif asset.modality == "bi_dashboard":
        asset.chunks = build_bi_dashboard_chunks(
            asset_id=asset.asset_id,
            space_id=asset.space_id,
            title=asset.title,
            dashboard_spec=asset.structured_payload,
            classification=asset.classification,
            regions=asset.regions,
            updated_at=asset.updated_at,
        )
    else:
        payload, chunks = parse_document_markdown(
            asset_id=asset.asset_id,
            space_id=asset.space_id,
            title=asset.title,
            raw_md=asset.raw_content,
            classification=asset.classification,
            regions=asset.regions,
            updated_at=asset.updated_at,
        )
        asset.structured_payload = payload
        # Scan raw doc text for unmasked emails/SSNs too
        if EMAIL_VALUE_RE.search(asset.raw_content) or SSN_VALUE_RE.search(asset.raw_content):
            asset.detected_pii_columns = ["inline_document_pii"]
        asset.chunks = chunks
    return asset
