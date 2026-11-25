"""ACL-Pre-Filtered Hybrid Search Engine (BM25 + N-Gram Dense Cosine + RRF) for QuickSpaces."""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from .models import AssetChunk, PrincipalContext, SpaceAsset

TOKEN_RE = re.compile(r"[a-z0-9_.$%]+")
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "what", "why", "when",
    "how", "did", "does", "are", "was", "were", "into", "our", "their", "have",
    "has", "had", "will", "would", "can", "about", "which", "who",
}


def tokenize(text: str) -> List[str]:
    return [
        t for t in TOKEN_RE.findall(text.lower())
        if len(t) > 1 and t not in STOPWORDS
    ]


def char_ngrams(text: str, n: int = 4) -> Counter[str]:
    cleaned = re.sub(r"\s+", " ", text.lower()).strip()
    if len(cleaned) < n:
        return Counter({cleaned: 1}) if cleaned else Counter()
    return Counter(cleaned[i : i + n] for i in range(len(cleaned) - n + 1))


def cosine_counter(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    common = set(a.keys()) & set(b.keys())
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class HybridSpaceIndex:
    """Executes zero-leakage ACL pre-filtering followed by BM25 + Semantic N-Gram RRF ranking."""

    def __init__(self, assets: List[SpaceAsset]) -> None:
        self.assets = assets
        self.asset_map: Dict[str, SpaceAsset] = {a.asset_id: a for a in assets}

    def search_chunks(
        self,
        space_id: str,
        query: str,
        principal: PrincipalContext,
        modality_filter: Optional[str] = None,
        favorites_only: bool = False,
        top_k: int = 8,
        diversify_modalities: bool = False,
        dedupe_by_asset: bool = False,
    ) -> Dict[str, Any]:
        space_assets = [a for a in self.assets if a.space_id == space_id]
        allowed_assets: List[SpaceAsset] = []
        blocked_audit: List[Dict[str, str]] = []

        # 1. Zero-Leakage ACL Pre-Filter BEFORE any lexical/semantic scoring
        for asset in space_assets:
            if modality_filter and modality_filter != "all" and asset.modality != modality_filter:
                continue
            if favorites_only and not asset.favorite:
                continue
            ok, reason = principal.can_access_asset(asset)
            if ok:
                allowed_assets.append(asset)
            else:
                blocked_audit.append(
                    {
                        "asset_id": asset.asset_id,
                        "title": asset.title,
                        "modality": asset.modality,
                        "classification": asset.classification,
                        "reason": reason,
                    }
                )

        candidate_chunks: List[Tuple[SpaceAsset, AssetChunk]] = []
        for asset in allowed_assets:
            for ch in asset.chunks:
                candidate_chunks.append((asset, ch))

        if not candidate_chunks:
            return {
                "hits": [],
                "allowed_asset_count": len(allowed_assets),
                "blocked_assets": blocked_audit,
                "total_candidate_chunks": 0,
            }

        q_clean = (query or "").strip()
        if not q_clean:
            # Browse mode: return summary chunks ordered by favorite + recency
            default_hits = []
            seen_assets = set()
            for asset, ch in sorted(
                candidate_chunks,
                key=lambda pair: (pair[0].favorite, pair[0].updated_at),
                reverse=True,
            ):
                if asset.asset_id in seen_assets:
                    continue
                seen_assets.add(asset.asset_id)
                default_hits.append(
                    {
                        "chunk_id": ch.chunk_id,
                        "asset_id": asset.asset_id,
                        "title": asset.title,
                        "filename": asset.filename,
                        "modality": asset.modality,
                        "classification": asset.classification,
                        "locator": ch.locator,
                        "snippet": ch.text[:280],
                        "full_text": ch.text,
                        "bm25_score": 1.0,
                        "semantic_score": 1.0,
                        "rrf_score": 1.0,
                        "favorite": asset.favorite,
                        "updated_at": asset.updated_at,
                    }
                )
            return {
                "hits": default_hits[:top_k],
                "allowed_asset_count": len(allowed_assets),
                "blocked_assets": blocked_audit,
                "total_candidate_chunks": len(candidate_chunks),
            }

        q_tokens = tokenize(q_clean)
        q_ngrams = char_ngrams(q_clean, 4)

        # 2. BM25 Okapi over ACL-cleared chunks
        doc_tokens = [tokenize(ch.text + " " + asset.title + " " + " ".join(asset.tags)) for asset, ch in candidate_chunks]
        n_docs = len(doc_tokens)
        avgdl = max(1.0, sum(len(dt) for dt in doc_tokens) / n_docs)
        df: Counter[str] = Counter()
        for dt in doc_tokens:
            for term in set(dt):
                df[term] += 1

        k1, b = 1.5, 0.75
        bm25_scores: List[float] = []
        semantic_scores: List[float] = []

        for idx, (asset, ch) in enumerate(candidate_chunks):
            tf = Counter(doc_tokens[idx])
            dl = len(doc_tokens[idx])
            score = 0.0
            for qt in q_tokens:
                if qt not in tf:
                    continue
                idf = math.log(1.0 + (n_docs - df[qt] + 0.5) / (df[qt] + 0.5))
                denom = tf[qt] + k1 * (1.0 - b + b * (dl / avgdl))
                score += idf * ((tf[qt] * (k1 + 1.0)) / denom)
            bm25_scores.append(score)

            ch_ngrams = char_ngrams(ch.text + " " + asset.title, 4)
            sem = cosine_counter(q_ngrams, ch_ngrams)
            semantic_scores.append(sem)

        # 3. Reciprocal Rank Fusion (RRF) + favorite boost
        bm25_order = sorted(range(n_docs), key=lambda i: bm25_scores[i], reverse=True)
        sem_order = sorted(range(n_docs), key=lambda i: semantic_scores[i], reverse=True)
        bm25_rank = {doc_i: rank for rank, doc_i in enumerate(bm25_order, start=1)}
        sem_rank = {doc_i: rank for rank, doc_i in enumerate(sem_order, start=1)}

        rrf_k = 20.0
        scored_items: List[Tuple[float, int]] = []
        for idx, (asset, _ch) in enumerate(candidate_chunks):
            # Require at least minimal lexical or character overlap
            if bm25_scores[idx] == 0.0 and semantic_scores[idx] < 0.05:
                continue
            rrf = (1.0 / (rrf_k + bm25_rank[idx])) + (1.0 / (rrf_k + sem_rank[idx]))
            if asset.favorite:
                rrf *= 1.06
            scored_items.append((rrf, idx))

        scored_items.sort(key=lambda x: x[0], reverse=True)

        # Optional cross-modal promotion so Research Agent sees top Table + Transcript + Doc + BI
        selected_indices: List[Tuple[float, int]] = []
        if diversify_modalities and scored_items:
            seen_mod: set[str] = set()
            # First pass: grab highest-scoring hit per modality if relevant
            for rrf_val, idx in scored_items:
                mod = candidate_chunks[idx][0].modality
                if mod not in seen_mod and (bm25_scores[idx] > 0.0 or semantic_scores[idx] >= 0.08):
                    seen_mod.add(mod)
                    selected_indices.append((rrf_val, idx))
                    if len(selected_indices) >= min(4, top_k):
                        break
            picked = {i for _, i in selected_indices}
            for rrf_val, idx in scored_items:
                if len(selected_indices) >= top_k:
                    break
                if idx not in picked:
                    selected_indices.append((rrf_val, idx))
                    picked.add(idx)
        elif dedupe_by_asset and scored_items:
            seen_asset_ids: set[str] = set()
            for rrf_val, idx in scored_items:
                aid = candidate_chunks[idx][0].asset_id
                if aid not in seen_asset_ids:
                    seen_asset_ids.add(aid)
                    selected_indices.append((rrf_val, idx))
                    if len(selected_indices) >= top_k:
                        break
        else:
            selected_indices = scored_items[:top_k]

        hits = []
        for rrf_val, idx in selected_indices:
            asset, ch = candidate_chunks[idx]
            hits.append(
                {
                    "chunk_id": ch.chunk_id,
                    "asset_id": asset.asset_id,
                    "title": asset.title,
                    "filename": asset.filename,
                    "modality": asset.modality,
                    "classification": asset.classification,
                    "locator": ch.locator,
                    "snippet": ch.text[:300],
                    "full_text": ch.text,
                    "structured_facts": ch.structured_facts,
                    "bm25_score": round(bm25_scores[idx], 3),
                    "semantic_score": round(semantic_scores[idx], 3),
                    "rrf_score": round(rrf_val, 4),
                    "favorite": asset.favorite,
                    "updated_at": asset.updated_at,
                }
            )

        return {
            "hits": hits,
            "allowed_asset_count": len(allowed_assets),
            "blocked_assets": blocked_audit,
            "total_candidate_chunks": len(candidate_chunks),
        }
