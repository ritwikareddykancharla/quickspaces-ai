/* QuickSpaces Standalone Enterprise Workspace App */
(function () {
  "use strict";

  const state = {
    spaceId: "space-q3-cloud-arr",
    roleId: "vp_admin",
    activeTab: "assets",
    modalityFilter: "all",
    searchQuery: "",
    selectedAssetId: null,
    snapshot: null,
    searchHits: null,
    initialAutoAsked: false,
  };

  function esc(val) {
    return String(val == null ? "" : val)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function modLabel(mod) {
    if (mod === "table") return "Spreadsheet";
    if (mod === "bi_dashboard") return "BI Chart";
    if (mod === "transcript") return "Call Audio";
    return "RFC Doc";
  }

  async function apiGet(path) {
    const res = await fetch(path, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error("HTTP " + res.status);
    return res.json();
  }

  async function apiPost(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "HTTP " + res.status);
    return data;
  }

  function renderPersonaCard() {
    const snap = state.snapshot;
    if (!snap) return;
    const p = snap.principal;
    const card = document.getElementById("persona-card");
    card.className =
      "persona-card " +
      (p.role_id === "na_analyst"
        ? "role-analyst"
        : p.role_id === "external_partner"
        ? "role-external"
        : "");

    document.getElementById("clearance-summary").textContent = p.title;
    document.getElementById("runtime-telemetry").textContent =
      location.hostname.includes("cloudfront.net")
        ? "CloudFront · Bedrock"
        : "Local · Bedrock";

    const sel = document.getElementById("role-select");
    sel.innerHTML = snap.available_principals
      .map(
        (pr) =>
          `<option value="${esc(pr.role_id)}" ${
            pr.role_id === state.roleId ? "selected" : ""
          }>${esc(pr.display_name)}</option>`
      )
      .join("");
  }

  function renderSpacesRail() {
    const snap = state.snapshot;
    if (!snap) return;
    const box = document.getElementById("spaces-list");
    box.innerHTML = snap.spaces
      .map((sp) => {
        const active = sp.space_id === state.spaceId ? "active" : "";
        const scoreColor = sp.readiness_score >= 90 ? "#34d399" : "#fbbf24";
        return `
          <button type="button" class="space-item ${active}" data-space="${esc(sp.space_id)}">
            <div class="space-item-top">${esc(sp.name)}</div>
            <div class="space-item-meta">
              <span>${sp.accessible_count}/${sp.asset_count} files</span>
              <span style="color:${scoreColor};">Gov ${sp.readiness_score}</span>
            </div>
          </button>
        `;
      })
      .join("");

    box.querySelectorAll(".space-item").forEach((btn) => {
      btn.addEventListener("click", async () => {
        state.spaceId = btn.getAttribute("data-space");
        state.selectedAssetId = null;
        state.searchQuery = "";
        state.searchHits = null;
        document.getElementById("asset-search-input").value = "";
        await refreshWorkspace(true);
      });
    });
  }

  function renderSpaceHeader() {
    const snap = state.snapshot;
    if (!snap) return;
    const sp = snap.active_space;
    document.getElementById("space-dept").textContent = sp.department;
    document.getElementById("space-title").textContent = sp.name;
    document.getElementById("space-desc").textContent = sp.description;

    const gov = snap.governance;
    const badge = document.getElementById("gov-tab-badge");
    if (gov.open_findings_count === 0) {
      badge.textContent = "100/100";
      badge.className = "gov-pill ok";
    } else {
      badge.textContent = gov.open_findings_count + " open";
      badge.className = "gov-pill";
    }

    const sqBox = document.getElementById("suggested-questions");
    sqBox.innerHTML = (sp.suggested_questions || [])
      .map((q) => `<button type="button" class="sug-btn" data-q="${esc(q)}">${esc(q)}</button>`)
      .join("");
    sqBox.querySelectorAll(".sug-btn").forEach((btn) => {
      btn.addEventListener("click", () => askQuestion(btn.getAttribute("data-q")));
    });
  }

  function getFilteredAssets() {
    const snap = state.snapshot;
    if (!snap) return [];
    let list = snap.assets || [];
    if (state.modalityFilter === "favorites") {
      list = list.filter((a) => a.favorite);
    } else if (state.modalityFilter !== "all") {
      list = list.filter((a) => a.modality === state.modalityFilter);
    }
    if (state.searchHits) {
      const rankMap = new Map();
      state.searchHits.hits.forEach((h, idx) => rankMap.set(h.asset_id, { idx, hit: h }));
      list = list
        .filter((a) => rankMap.has(a.asset_id))
        .sort((a, b) => rankMap.get(a.asset_id).idx - rankMap.get(b.asset_id).idx);
    }
    return list;
  }

  function renderAssetsShelf() {
    const list = getFilteredAssets();
    const strip = document.getElementById("assets-list");
    const banner = document.getElementById("search-results-banner");

    if (state.searchHits) {
      banner.classList.remove("hidden");
      const blockedCount = (state.searchHits.blocked_assets || []).length;
      banner.innerHTML = `
        <span><strong>Hybrid Search:</strong> ${state.searchHits.hits.length} authorized match(es) for "${esc(
        state.searchQuery
      )}"${blockedCount > 0 ? ` &middot; <strong>${blockedCount} restricted withheld</strong>` : ""}</span>
        <button type="button" class="flt" id="clear-search-btn">Clear</button>
      `;
      document.getElementById("clear-search-btn").onclick = () => {
        state.searchQuery = "";
        state.searchHits = null;
        document.getElementById("asset-search-input").value = "";
        renderAssetsShelf();
      };
    } else {
      banner.classList.add("hidden");
    }

    if (!list.length) {
      strip.innerHTML = `<div style="grid-column:1/-1;color:var(--muted);padding:8px 0;">No assets match this filter under your active clearance.</div>`;
      return;
    }

    if (!state.selectedAssetId || !list.some((a) => a.asset_id === state.selectedAssetId)) {
      const firstAllowed = list.find((a) => a.access_allowed) || list[0];
      state.selectedAssetId = firstAllowed.asset_id;
    }

    const hitLookup = {};
    if (state.searchHits) {
      state.searchHits.hits.forEach((h) => {
        hitLookup[h.asset_id] = h;
      });
    }

    strip.innerHTML = list
      .map((a) => {
        const selected = a.asset_id === state.selectedAssetId ? "selected" : "";
        const locked = !a.access_allowed ? "locked" : "";
        const sh = hitLookup[a.asset_id];
        return `
          <div class="asset-card ${selected} ${locked}" data-asset="${esc(a.asset_id)}">
            <div class="asset-card-head">
              <span class="mod-pill mod-${esc(a.modality)}">${esc(modLabel(a.modality))}</span>
              <button type="button" class="fav-star ${a.favorite ? "active" : ""}" data-fav="${esc(a.asset_id)}" title="Star asset">&#9733;</button>
            </div>
            <div class="asset-card-title">${!a.access_allowed ? "&#128274; " : ""}${esc(a.title)}</div>
            ${
              sh
                ? `<div class="mono" style="font-size:10.5px;color:var(--coral);">RRF ${sh.rrf_score} (BM25 ${sh.bm25_score})</div>`
                : `<div class="mono" style="font-size:10.5px;color:var(--muted);">${esc(a.filename)}</div>`
            }
            <div class="asset-card-foot">
              <span class="cls-tag cls-${esc(a.classification)}">${esc(a.classification)}</span>
              <span>${esc(a.regions.join(","))}</span>
            </div>
          </div>
        `;
      })
      .join("");

    strip.querySelectorAll(".asset-card").forEach((card) => {
      card.addEventListener("click", (e) => {
        if (e.target.closest(".fav-star")) return;
        state.selectedAssetId = card.getAttribute("data-asset");
        renderAssetsShelf();
        loadAssetInspector(state.selectedAssetId, false);
      });
    });

    strip.querySelectorAll(".fav-star").forEach((star) => {
      star.addEventListener("click", async (e) => {
        e.stopPropagation();
        const aid = star.getAttribute("data-fav");
        await apiPost(`/api/assets/${encodeURIComponent(aid)}/favorite`, {});
        await refreshWorkspace(false);
      });
    });
  }

  function renderBarChartHtml(title, points, unit) {
    if (!points || !points.length) return "";
    const maxAbs = Math.max(...points.map((p) => Math.abs(Number(p.value) || 0)), 1);
    return `
      <div class="chart-box">
        <div style="font:600 12px var(--sans);margin-bottom:8px;">${esc(title)}</div>
        ${points
          .map((pt) => {
            const val = Number(pt.value) || 0;
            const pct = Math.max(4, Math.round((Math.abs(val) / maxAbs) * 100));
            const neg = val < 0 ? "negative" : "";
            return `
              <div class="bar-row">
                <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(pt.label)}">${esc(pt.label)}</span>
                <div class="bar-track"><div class="bar-fill ${neg}" style="width:${pct}%"></div></div>
                <span style="text-align:right;font-weight:600;">${esc(val)}${esc(unit || "")}</span>
              </div>
            `;
          })
          .join("")}
      </div>
    `;
  }

  async function loadAssetInspector(assetId, flashHighlight) {
    const box = document.getElementById("asset-inspector");
    if (!assetId) return;
    box.innerHTML = `<div style="color:var(--muted);">Opening asset...</div>`;

    try {
      const detail = await apiGet(
        `/api/assets/${encodeURIComponent(assetId)}?role=${encodeURIComponent(state.roleId)}`
      );
      const a = detail.asset;

      if (detail.blocked) {
        box.innerHTML = `
          <div class="viewer-head">
            <span class="cls-tag cls-${esc(a.classification)}">${esc(a.classification)}</span>
            <h3 class="viewer-title">&#128274; ${esc(a.title)}</h3>
            <div class="viewer-meta">${esc(a.filename)} &middot; Regions: ${esc(a.regions.join(", "))}</div>
          </div>
          <div class="pii-callout masked">
            <span><strong>Withheld by Pre-Retrieval Governance:</strong> ${esc(detail.block_reason)}. Switch <em>Active Workspace Identity</em> in the left rail to <strong>VP Engineering (Admin)</strong> to view this file.</span>
          </div>
        `;
        return;
      }

      const p = detail.payload || {};
      let bodyHtml = "";

      if (a.modality === "table") {
        const piiCols = new Set(a.detected_pii_columns || []);
        const piiNotice = piiCols.size
          ? detail.pii_masked_for_caller
            ? `<div class="pii-callout masked">
                 <span><strong>Dynamic PII Masking Active:</strong> Columns <code>${esc(
                   Array.from(piiCols).join(", ")
                 )}</code> are masked for <strong>${esc(state.snapshot.principal.display_name)}</strong>.</span>
                 <span>Switch to VP Admin for raw PII</span>
               </div>`
            : `<div class="pii-callout">
                 <span><strong>Admin Raw PII View:</strong> Scanner detected PII columns <code>${esc(
                   Array.from(piiCols).join(", ")
                 )}</code>. ${
                a.pii_masking_enforced
                  ? "Default non-admin policy: Masked."
                  : "Default policy unlocked — open Governance Agent to enforce."
              }</span>
               </div>`
          : "";

        const statsEntries = Object.entries(p.numeric_stats || {}).slice(0, 4);
        const rollupHtml = statsEntries.length
          ? `<div class="kpi-grid">
               ${statsEntries
                 .map(
                   ([col, st]) => `
                 <div class="kpi-card">
                   <div class="kpi-lbl">${esc(col)}</div>
                   <div class="kpi-val">${esc(st.sum.toLocaleString())}</div>
                   <div class="kpi-sub">avg ${esc(st.avg.toLocaleString())}</div>
                 </div>`
                 )
                 .join("")}
             </div>`
          : "";

        bodyHtml = `
          ${piiNotice}
          ${rollupHtml}
          <div class="sheet-wrap">
            <table class="sheet-table">
              <thead>
                <tr>
                  ${(p.headers || [])
                    .map((h) => `<th>${esc(h)}${piiCols.has(h) ? " · PII" : ""}</th>`)
                    .join("")}
                </tr>
              </thead>
              <tbody>
                ${(p.rows || [])
                  .map(
                    (row) => `
                  <tr>
                    ${(p.headers || [])
                      .map((h) => {
                        const isMasked = detail.pii_masked_for_caller && piiCols.has(h);
                        return `<td class="${isMasked ? "masked-cell" : ""}">${esc(row[h])}</td>`;
                      })
                      .join("")}
                  </tr>`
                  )
                  .join("")}
              </tbody>
            </table>
          </div>
        `;
      } else if (a.modality === "bi_dashboard") {
        bodyHtml = `
          <div class="kpi-grid">
            ${(p.kpis || [])
              .map(
                (k) => `
              <div class="kpi-card">
                <div class="kpi-lbl">${esc(k.label)}</div>
                <div class="kpi-val">${esc(k.value)}</div>
                <div class="kpi-sub">${esc(k.delta || "")}</div>
              </div>`
              )
              .join("")}
          </div>
          ${renderBarChartHtml(p.chart_title || a.title, p.series || [], p.unit || "")}
          <div class="item-card" style="margin-top:12px;">
            <p><strong>Anomaly Insight:</strong> ${esc(p.anomaly_note || "")}</p>
            <div class="viewer-meta" style="margin-top:6px;">SQL Lineage: <code>${esc(p.sql_lineage || "")}</code></div>
          </div>
        `;
      } else if (a.modality === "transcript") {
        bodyHtml = `
          <div class="stack-list">
            ${(p.turns || [])
              .map(
                (t) => `
              <div class="item-card">
                <div style="margin-bottom:5px;font-weight:600;font-size:12.5px;">
                  <span class="ts-chip">${esc(t.timestamp)}</span>${esc(t.speaker)}
                </div>
                <p>${esc(t.text)}</p>
              </div>`
              )
              .join("")}
          </div>
        `;
      } else {
        bodyHtml = `
          <div class="stack-list">
            ${(p.sections || [])
              .map(
                (s) => `
              <div class="item-card">
                <h4>${esc(s.heading)}</h4>
                <p>${esc(s.body)}</p>
              </div>`
              )
              .join("")}
          </div>
        `;
      }

      box.innerHTML = `
        <div class="viewer-head">
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
            <span class="mod-pill mod-${esc(a.modality)}">${esc(modLabel(a.modality))}</span>
            <span class="cls-tag cls-${esc(a.classification)}">${esc(a.classification)}</span>
            ${a.residency_pin ? `<span class="cls-tag cls-PUBLIC">KMS: ${esc(a.residency_pin)}</span>` : ""}
            ${a.owner_sla_verified ? `<span class="cls-tag cls-PUBLIC">SLA Verified</span>` : `<span class="cls-tag cls-CONFIDENTIAL">Unverified SLA</span>`}
          </div>
          <h3 class="viewer-title">${esc(a.title)}</h3>
          <div class="viewer-meta">${esc(a.filename)} &middot; ${esc(a.owner)} &middot; ${a.chunk_count} indexed chunks</div>
        </div>
        ${bodyHtml}
      `;

      if (flashHighlight) {
        box.classList.remove("flash");
        void box.offsetWidth;
        box.classList.add("flash");
        box.scrollIntoView({ behavior: "smooth", block: "nearest" });
        setTimeout(() => box.classList.remove("flash"), 1300);
      }
    } catch (err) {
      box.innerHTML = `<div style="color:var(--coral);">Error loading asset: ${esc(err.message)}</div>`;
    }
  }

  function renderGovernanceTab() {
    const snap = state.snapshot;
    if (!snap) return;
    const gov = snap.governance;
    const container = document.getElementById("governance-container");
    const scoreColor = gov.readiness_score >= 90 ? "var(--sage)" : "var(--coral)";

    const findingsHtml = gov.findings.length
      ? `<div class="stack-list">
           ${gov.findings
             .map(
               (f) => `
             <div class="finding-row ${esc(f.severity)}">
               <div>
                 <div style="display:flex;align-items:center;gap:7px;margin-bottom:4px;">
                   <span class="cls-tag cls-${f.severity === "HIGH" ? "CONFIDENTIAL" : "INTERNAL"}">${esc(f.severity)} &middot; ${esc(f.rule_id)}</span>
                   <strong>${esc(f.title)}</strong>
                 </div>
                 <div style="font-size:13px;color:var(--body);margin-bottom:4px;">${esc(f.detail)}</div>
                 <div class="mono" style="font-size:11px;color:var(--sage);">${esc(f.remediation_action)}</div>
               </div>
               <button type="button" class="action-btn fix-single-btn" data-fid="${esc(f.finding_id)}">Fix</button>
             </div>`
             )
             .join("")}
         </div>`
      : `<div class="pii-callout" style="border-left-color:var(--sage);background:var(--sage-soft);color:var(--sage);">
           <span><strong>All 5 Enterprise Governance Controls Holding (100/100):</strong> Dynamic PII masking, tenant ACLs, eu-central-1 KMS residency, BI owner SLAs, and transcript retention policies active.</span>
         </div>`;

    const auditRows = (snap.audit_trail || []).length
      ? `<div style="margin-top:16px;">
           <div class="tray-label">SHA-256 Governance &amp; Ingestion Receipt Log</div>
           <div class="stack-list">
             ${snap.audit_trail
               .map(
                 (ev) => `
               <div class="item-card">
                 <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;font-size:12.5px;">
                   <strong>${esc(ev.event)} &mdash; ${esc(ev.detail)}</strong>
                   <span class="mono" style="color:var(--muted);">${esc(ev.timestamp.slice(0, 19))}Z</span>
                 </div>
                 ${
                   ev.sha256_receipt
                     ? `<div class="mono" style="font-size:11px;color:var(--sage);margin-top:3px;">sha256: ${esc(ev.sha256_receipt)}</div>`
                     : ""
                 }
               </div>`
               )
               .join("")}
           </div>
         </div>`
      : "";

    container.innerHTML = `
      <div class="gov-banner">
        <div>
          <div class="dept-tag">Enterprise Governance Onboarding Agent</div>
          <div style="display:flex;align-items:baseline;gap:10px;margin-top:3px;">
            <span class="gov-big-score" style="color:${scoreColor};">${gov.readiness_score}/100</span>
            <span class="cls-tag ${gov.readiness_score >= 90 ? "cls-PUBLIC" : "cls-CONFIDENTIAL"}">${esc(gov.status_label)}</span>
          </div>
          <div style="font-size:12.5px;color:var(--muted);margin-top:3px;">
            ${gov.controls_passing} of ${gov.controls_total} controls passing in <strong>${esc(snap.active_space.name)}</strong>
          </div>
        </div>
        ${
          gov.open_findings_count > 0
            ? `<button type="button" class="action-btn primary" id="remediate-all-btn">Remediate All (${gov.open_findings_count}) Issues</button>`
            : ""
        }
      </div>
      ${findingsHtml}
      ${auditRows}
    `;

    const remAll = document.getElementById("remediate-all-btn");
    if (remAll) {
      remAll.onclick = async () => {
        remAll.disabled = true;
        remAll.textContent = "Remediating...";
        await apiPost(`/api/spaces/${encodeURIComponent(state.spaceId)}/governance/remediate`, {});
        await refreshWorkspace(false);
      };
    }

    container.querySelectorAll(".fix-single-btn").forEach((btn) => {
      btn.onclick = async () => {
        btn.disabled = true;
        const fid = btn.getAttribute("data-fid");
        await apiPost(`/api/spaces/${encodeURIComponent(state.spaceId)}/governance/remediate`, {
          finding_id: fid,
        });
        await refreshWorkspace(false);
      };
    });
  }

  function formatAnswerWithClickableCitations(answerText, citations) {
    let html = esc(answerText);
    const map = {};
    (citations || []).forEach((c) => {
      map[c.ref] = c;
    });
    html = html.replace(/\[(C\d+)\]/g, (full, ref) => {
      const c = map[ref];
      if (!c) return full;
      return `<button type="button" class="cite-inline" data-cite-asset="${esc(c.asset_id)}" title="Open ${esc(c.title)} (${esc(c.locator)})">[${esc(ref)}]</button>`;
    });
    return html;
  }

  async function askQuestion(questionText) {
    const q = String(questionText || "").trim();
    if (!q) return;
    const feed = document.getElementById("chat-feed");
    const submitBtn = document.getElementById("chat-submit-btn");
    const input = document.getElementById("chat-input");
    input.value = "";
    submitBtn.disabled = true;
    submitBtn.textContent = "Thinking...";

    const empty = feed.querySelector(".thread-empty");
    if (empty) empty.remove();

    const userBubble = document.createElement("div");
    userBubble.className = "msg-user";
    userBubble.textContent = q;
    feed.appendChild(userBubble);

    const aiBubble = document.createElement("div");
    aiBubble.className = "msg-ai";
    aiBubble.innerHTML = `<div class="mono" style="color:var(--muted);">ACL pre-filter &rarr; hybrid RRF &rarr; Bedrock Nova...</div>`;
    feed.appendChild(aiBubble);
    feed.scrollTop = feed.scrollHeight;

    try {
      const res = await apiPost(`/api/spaces/${encodeURIComponent(state.spaceId)}/ask`, {
        question: q,
        role: state.roleId,
      });

      const ver = res.verification || {};
      const acl = res.acl_summary || {};
      const llm = res.llm_telemetry || {};
      const chartHtml = res.chart
        ? renderBarChartHtml(res.chart.chart_title, res.chart.points, res.chart.unit)
        : "";

      aiBubble.innerHTML = `
        <div class="ai-meta-bar">
          <span class="cls-tag cls-INTERNAL">${esc(llm.engine || "Grounded")}</span>
          <span class="cls-tag cls-PUBLIC">${ver.citation_precision_pct ?? 100}% Verified</span>
          ${
            acl.blocked_assets_count > 0
              ? `<span class="cls-tag cls-CONFIDENTIAL">${acl.blocked_assets_count} Withheld by ACL</span>`
              : `<span class="cls-tag cls-INTERNAL">${acl.allowed_assets_searched} Files</span>`
          }
        </div>
        <div class="ai-answer-body">${formatAnswerWithClickableCitations(res.answer, res.citations)}</div>
        ${chartHtml}
        ${
          res.citations && res.citations.length
            ? `<div class="citations-drawer">
                 ${res.citations
                   .map(
                     (c) => `
                   <button type="button" class="citation-pill-btn" data-cite-asset="${esc(c.asset_id)}">
                     <span><strong>[${esc(c.ref)}]</strong> ${esc(c.title)} &middot; ${esc(c.locator)}</span>
                     <span class="mod-pill mod-${esc(c.modality)}">${esc(modLabel(c.modality))}</span>
                   </button>`
                   )
                   .join("")}
               </div>`
            : ""
        }
      `;

      aiBubble.querySelectorAll("[data-cite-asset]").forEach((el) => {
        el.addEventListener("click", () => {
          const aid = el.getAttribute("data-cite-asset");
          switchTab("assets");
          state.selectedAssetId = aid;
          renderAssetsShelf();
          loadAssetInspector(aid, true);
        });
      });
    } catch (err) {
      aiBubble.innerHTML = `<div style="color:var(--coral);">Error: ${esc(err.message)}</div>`;
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = "Ask Space &rarr;";
      feed.scrollTop = feed.scrollHeight;
    }
  }

  function switchTab(tabName) {
    state.activeTab = tabName;
    document.getElementById("tab-btn-assets").classList.toggle("active", tabName === "assets");
    document.getElementById("tab-btn-governance").classList.toggle("active", tabName === "governance");
    document.getElementById("tab-panel-assets").classList.toggle("hidden", tabName !== "assets");
    document.getElementById("tab-panel-governance").classList.toggle("hidden", tabName !== "governance");
  }

  async function refreshWorkspace(autoInspectFirst) {
    const snap = await apiGet(
      `/api/state?space_id=${encodeURIComponent(state.spaceId)}&role=${encodeURIComponent(state.roleId)}`
    );
    state.snapshot = snap;
    renderPersonaCard();
    renderSpacesRail();
    renderSpaceHeader();
    renderAssetsShelf();
    renderGovernanceTab();

    if (autoInspectFirst || state.selectedAssetId) {
      await loadAssetInspector(state.selectedAssetId, false);
    }

    if (!state.initialAutoAsked && snap.active_space.suggested_questions?.length) {
      state.initialAutoAsked = true;
      askQuestion(snap.active_space.suggested_questions[0]);
    }
  }

  function bindEvents() {
    document.getElementById("role-select").addEventListener("change", async (e) => {
      state.roleId = e.target.value;
      state.searchHits = null;
      await refreshWorkspace(false);
    });

    document.getElementById("tab-btn-assets").onclick = () => switchTab("assets");
    document.getElementById("tab-btn-governance").onclick = () => switchTab("governance");

    let searchTimer = null;
    document.getElementById("asset-search-input").addEventListener("input", (e) => {
      clearTimeout(searchTimer);
      const val = e.target.value.trim();
      searchTimer = setTimeout(async () => {
        state.searchQuery = val;
        if (!val) {
          state.searchHits = null;
          renderAssetsShelf();
          return;
        }
        state.searchHits = await apiGet(
          `/api/spaces/${encodeURIComponent(state.spaceId)}/search?q=${encodeURIComponent(val)}&role=${encodeURIComponent(state.roleId)}`
        );
        renderAssetsShelf();
      }, 220);
    });

    document.querySelectorAll("#modality-pills .flt").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("#modality-pills .flt").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.modalityFilter = btn.getAttribute("data-mod");
        renderAssetsShelf();
      });
    });

    document.getElementById("chat-form").addEventListener("submit", (e) => {
      e.preventDefault();
      askQuestion(document.getElementById("chat-input").value);
    });

    document.getElementById("chat-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        askQuestion(e.target.value);
      }
    });

    document.getElementById("reset-btn").onclick = async () => {
      await apiPost("/api/reset", {});
      state.roleId = "vp_admin";
      state.spaceId = "space-q3-cloud-arr";
      state.searchHits = null;
      state.searchQuery = "";
      document.getElementById("asset-search-input").value = "";
      await refreshWorkspace(true);
    };

    document.getElementById("tour-ask-btn").onclick = async () => {
      state.roleId = "vp_admin";
      state.spaceId = "space-q3-cloud-arr";
      switchTab("assets");
      await refreshWorkspace(true);
      askQuestion(
        "Why did EMEA Enterprise net retention dip in Q3, how much ARR contracted, and when does the SCIM fix ship?"
      );
    };

    document.getElementById("tour-pii-btn").onclick = async () => {
      state.spaceId = "space-q3-cloud-arr";
      state.roleId = "na_analyst";
      state.selectedAssetId = "asset-tbl-arr-cohorts";
      switchTab("assets");
      await refreshWorkspace(false);
      await loadAssetInspector("asset-tbl-arr-cohorts", true);
    };

    document.getElementById("tour-ext-btn").onclick = async () => {
      state.spaceId = "space-q3-cloud-arr";
      state.roleId = "external_partner";
      switchTab("assets");
      await refreshWorkspace(true);
      askQuestion("Show NordBank EMEA FinServ Q3 ARR contraction and executive escalation call details.");
    };

    document.getElementById("tour-gov-btn").onclick = async () => {
      switchTab("governance");
      await refreshWorkspace(false);
    };

    const ingestModal = document.getElementById("ingest-modal");
    document.getElementById("open-ingest-btn").onclick = () => ingestModal.classList.remove("hidden");
    document.getElementById("close-ingest-btn").onclick = () => ingestModal.classList.add("hidden");
    document.getElementById("cancel-ingest-btn").onclick = () => ingestModal.classList.add("hidden");

    document.getElementById("sample-csv-btn").onclick = () => {
      document.getElementById("ing-title").value = "Q4 Quick Bedrock & GPU Cluster Unit Economics";
      document.getElementById("ing-filename").value = "q4_bedrock_gpu_spend.csv";
      document.getElementById("ing-modality").value = "table";
      document.getElementById("ing-classification").value = "INTERNAL";
      document.getElementById("ing-content").value =
        "workload,monthly_queries_k,cost_usd,p95_latency_ms,tech_lead_email\n" +
        "QuickSpaces-Hybrid-Search,1840,4200,195,search-lead@acmecloud.io\n" +
        "QuickSpaces-Bedrock-Nova-RAG,920,8950,640,rag-lead@acmecloud.io\n" +
        "QuickSpaces-Governance-Scanner,410,1150,88,sec-lead@acmecloud.io";
    };

    document.getElementById("sample-vtt-btn").onclick = () => {
      document.getElementById("ing-title").value = "Nov 20 Enterprise Customer Advisory Call";
      document.getElementById("ing-filename").value = "nov20_customer_advisory.vtt";
      document.getElementById("ing-modality").value = "transcript";
      document.getElementById("ing-classification").value = "CONFIDENTIAL";
      document.getElementById("ing-content").value =
        "WEBVTT\n" +
        "[01:12] Maya Patel (VP Data Platform): Adopting QuickSpaces cut analyst time spent hunting across SharePoint PDFs and Snowflake CSVs by 64%.\n" +
        "[04:35] Henrik Lind (CISO, NordBank): Once eu-central-1 KMS residency and dynamic PII column masking turned green in Governance Agent, Security approved 1,400 seats.";
    };

    document.getElementById("local-file-input").addEventListener("change", (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      document.getElementById("ing-filename").value = file.name;
      document.getElementById("ing-title").value = file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");
      if (file.name.endsWith(".csv")) document.getElementById("ing-modality").value = "table";
      else if (file.name.endsWith(".vtt")) document.getElementById("ing-modality").value = "transcript";
      else document.getElementById("ing-modality").value = "document";

      const reader = new FileReader();
      reader.onload = () => {
        document.getElementById("ing-content").value = String(reader.result || "");
      };
      reader.readAsText(file);
    });

    document.getElementById("ingest-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = document.getElementById("submit-ingest-btn");
      btn.disabled = true;
      btn.textContent = "Indexing...";
      try {
        const regions = document.getElementById("ing-regions").value.split(",");
        const out = await apiPost(`/api/spaces/${encodeURIComponent(state.spaceId)}/ingest`, {
          title: document.getElementById("ing-title").value,
          filename: document.getElementById("ing-filename").value,
          modality: document.getElementById("ing-modality").value,
          classification: document.getElementById("ing-classification").value,
          regions,
          raw_content: document.getElementById("ing-content").value,
        });
        ingestModal.classList.add("hidden");
        switchTab("assets");
        state.selectedAssetId = out.ingested_asset.asset_id;
        await refreshWorkspace(false);
        await loadAssetInspector(state.selectedAssetId, true);
      } catch (err) {
        alert("Ingest error: " + err.message);
      } finally {
        btn.disabled = false;
        btn.textContent = "Parse, Scan PII & Index";
      }
    });
  }

  bindEvents();
  refreshWorkspace(true);
})();
