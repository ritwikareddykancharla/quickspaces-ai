/* QuickSpaces Interactive Enterprise Workspace Frontend (CloudFront + S3 Static Origin) */
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
    if (mod === "table") return "CSV Table";
    if (mod === "bi_dashboard") return "BI Dashboard";
    if (mod === "transcript") return "Transcript";
    return "Document";
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

  function renderClearanceBar() {
    const snap = state.snapshot;
    if (!snap) return;
    const p = snap.principal;
    const bar = document.getElementById("clearance-bar");
    bar.className =
      "clearance-bar " +
      (p.role_id === "na_analyst"
        ? "role-analyst"
        : p.role_id === "external_partner"
        ? "role-external"
        : "");

    document.getElementById("clearance-summary").innerHTML =
      "<strong>Active Governance Policy:</strong> " +
      esc(p.display_name) +
      " &mdash; " +
      esc(p.title);

    const originKind = location.hostname.includes("cloudfront.net")
      ? "Amazon CloudFront + S3 (OAC) + /api/*"
      : "Local Dev Server -> Live AWS Bedrock";
    document.getElementById("runtime-telemetry").textContent =
      originKind + " · Tenant: " + p.tenant_id;
  }

  function renderRoleSelector() {
    const snap = state.snapshot;
    if (!snap) return;
    const sel = document.getElementById("role-select");
    sel.innerHTML = snap.available_principals
      .map(
        (p) =>
          `<option value="${esc(p.role_id)}" ${
            p.role_id === state.roleId ? "selected" : ""
          }>${esc(p.display_name)}</option>`
      )
      .join("");
  }

  function renderSpacesSidebar() {
    const snap = state.snapshot;
    if (!snap) return;
    const box = document.getElementById("spaces-list");
    box.innerHTML = snap.spaces
      .map((sp) => {
        const active = sp.space_id === state.spaceId ? "active" : "";
        const scoreColor =
          sp.readiness_score >= 90
            ? "color:var(--ok);font-weight:700;"
            : "color:var(--warn);font-weight:700;";
        return `
          <button type="button" class="space-item ${active}" data-space="${esc(sp.space_id)}">
            <div class="space-item-top">
              <span>${esc(sp.name)}</span>
            </div>
            <div class="space-item-meta">
              <span>${sp.accessible_count}/${sp.asset_count} accessible</span>
              <span style="${scoreColor}">Gov ${sp.readiness_score}/100</span>
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

  function renderSpaceHeroAndTabs() {
    const snap = state.snapshot;
    if (!snap) return;
    const sp = snap.active_space;
    document.getElementById("space-dept").textContent = sp.department;
    document.getElementById("space-title").textContent = sp.name;
    document.getElementById("space-desc").textContent = sp.description;

    const gov = snap.governance;
    const badge = document.getElementById("gov-tab-badge");
    if (gov.open_findings_count === 0) {
      badge.textContent = "100/100 Ready";
      badge.className = "tab-badge ok";
    } else {
      badge.textContent = gov.open_findings_count + " open";
      badge.className = "tab-badge";
    }

    // Suggested questions in right panel
    const sqBox = document.getElementById("suggested-questions");
    sqBox.innerHTML = (sp.suggested_questions || [])
      .map(
        (q) =>
          `<button type="button" class="sug-btn" data-q="${esc(q)}">${esc(q)}</button>`
      )
      .join("");
    sqBox.querySelectorAll(".sug-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        askQuestion(btn.getAttribute("data-q"));
      });
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

  function renderAssetsStrip() {
    const list = getFilteredAssets();
    const strip = document.getElementById("assets-list");
    const banner = document.getElementById("search-results-banner");

    if (state.searchHits) {
      banner.classList.remove("hidden");
      const blockedCount = (state.searchHits.blocked_assets || []).length;
      banner.innerHTML = `
        <span><strong>Hybrid RRF Search:</strong> ${state.searchHits.hits.length} authorized asset(s) matched "${esc(state.searchQuery)}" ${
        blockedCount > 0
          ? `&middot; <strong>${blockedCount} restricted asset(s) pre-filtered out for role</strong>`
          : ""
      }</span>
        <button type="button" class="pill" id="clear-search-btn">Clear Search</button>
      `;
      document.getElementById("clear-search-btn").onclick = () => {
        state.searchQuery = "";
        state.searchHits = null;
        document.getElementById("asset-search-input").value = "";
        renderAssetsStrip();
      };
    } else {
      banner.classList.add("hidden");
    }

    if (!list.length) {
      strip.innerHTML = `<div style="grid-column:1/-1;color:var(--ink-muted);padding:10px;">No assets match this filter for your active governance clearance.</div>`;
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
              <span class="mod-tag mod-${esc(a.modality)}">${esc(modLabel(a.modality))}</span>
              <button type="button" class="fav-star ${a.favorite ? "active" : ""}" data-fav="${esc(a.asset_id)}" title="Toggle Space Favorite">&#9733;</button>
            </div>
            <div class="asset-card-title">
              ${!a.access_allowed ? "&#128274; " : ""}${esc(a.title)}
            </div>
            ${
              sh
                ? `<div class="mono" style="font-size:10.5px;color:var(--accent);">RRF ${sh.rrf_score} (BM25 ${sh.bm25_score} · Sem ${sh.semantic_score})</div>`
                : `<div style="font-size:11px;color:var(--ink-muted);">${esc(a.filename)}</div>`
            }
            <div class="asset-card-foot">
              <span class="cls-badge cls-${esc(a.classification)}">${esc(a.classification)}</span>
              <span>${esc(a.regions.join(", "))} &middot; ${a.chunk_count} chunks</span>
            </div>
          </div>
        `;
      })
      .join("");

    strip.querySelectorAll(".asset-card").forEach((card) => {
      card.addEventListener("click", (e) => {
        if (e.target.closest(".fav-star")) return;
        state.selectedAssetId = card.getAttribute("data-asset");
        renderAssetsStrip();
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
      <div class="bar-chart-card">
        <div style="font-weight:700;font-size:12.5px;margin-bottom:8px;">${esc(title)}</div>
        ${points
          .map((pt) => {
            const val = Number(pt.value) || 0;
            const pct = Math.max(4, Math.round((Math.abs(val) / maxAbs) * 100));
            const neg = val < 0 ? "negative" : "";
            return `
              <div class="bar-row">
                <span style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(pt.label)}">${esc(pt.label)}</span>
                <div class="bar-track"><div class="bar-fill ${neg}" style="width:${pct}%"></div></div>
                <span class="mono" style="text-align:right;font-weight:700;">${esc(val)}${esc(unit || "")}</span>
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
    box.innerHTML = `<div style="color:var(--ink-muted);">Loading multi-modal inspector...</div>`;

    try {
      const detail = await apiGet(
        `/api/assets/${encodeURIComponent(assetId)}?role=${encodeURIComponent(state.roleId)}`
      );
      const a = detail.asset;

      if (detail.blocked) {
        box.innerHTML = `
          <div class="inspector-head">
            <div>
              <span class="cls-badge cls-${esc(a.classification)}">${esc(a.classification)}</span>
              <h3 class="inspector-title">&#128274; ${esc(a.title)}</h3>
              <div class="inspector-meta">${esc(a.filename)} &middot; Regions: ${esc(a.regions.join(", "))}</div>
            </div>
          </div>
          <div style="background:var(--danger-soft);border:1px solid #fecaca;color:#991b1b;padding:12px;border-radius:8px;">
            <strong>Blocked by Quick Enterprise Governance Pre-Filter:</strong> ${esc(detail.block_reason)}.
            <div style="margin-top:6px;font-size:12px;">Switch <strong>Viewing As Role</strong> in the top-right header to <em>VP Engineering (Admin)</em> to inspect this asset.</div>
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
            ? `<div class="pii-banner masked">
                 <span>&#128737; <strong>Dynamic PII Masking Active:</strong> Columns <code>${esc(
                   Array.from(piiCols).join(", ")
                 )}</code> are masked for role <strong>${esc(state.snapshot.principal.display_name)}</strong>.</span>
                 <span>Switch to VP Admin to view raw PII</span>
               </div>`
            : `<div class="pii-banner raw">
                 <span>&#128065; <strong>Raw PII Visible (Admin Clearance):</strong> Columns <code>${esc(
                   Array.from(piiCols).join(", ")
                 )}</code> detected by ingestion scanner. ${
                a.pii_masking_enforced
                  ? "Policy status: Masked for non-admins."
                  : "Warning: Default column policy not yet locked (see Governance Agent)."
              }</span>
               </div>`
          : "";

        const statsEntries = Object.entries(p.numeric_stats || {}).slice(0, 4);
        const rollupHtml = statsEntries.length
          ? `<div class="kpi-strip">
               ${statsEntries
                 .map(
                   ([col, st]) => `
                 <div class="kpi-box">
                   <div class="kpi-box-label">Column: <code>${esc(col)}</code></div>
                   <div class="kpi-box-val">${esc(st.sum.toLocaleString())}</div>
                   <div class="kpi-box-delta">Avg ${esc(st.avg.toLocaleString())} &middot; Min ${esc(st.min)} / Max ${esc(st.max)}</div>
                 </div>`
                 )
                 .join("")}
             </div>`
          : "";

        bodyHtml = `
          ${piiNotice}
          ${rollupHtml}
          <div class="table-scroll">
            <table class="data-table">
              <thead>
                <tr>
                  ${(p.headers || [])
                    .map(
                      (h) =>
                        `<th>${esc(h)} ${
                          piiCols.has(h)
                            ? `<span class="cls-badge cls-CONFIDENTIAL">PII</span>`
                            : ""
                        }</th>`
                    )
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
          <div class="kpi-strip">
            ${(p.kpis || [])
              .map(
                (k) => `
              <div class="kpi-box">
                <div class="kpi-box-label">${esc(k.label)}</div>
                <div class="kpi-box-val">${esc(k.value)}</div>
                <div class="kpi-box-delta">${esc(k.delta || "")}</div>
              </div>`
              )
              .join("")}
          </div>
          ${renderBarChartHtml(p.chart_title || a.title, p.series || [], p.unit || "")}
          <div style="margin-top:10px;background:#fff;border:1px solid var(--border);border-radius:8px;padding:9px 11px;font-size:12px;">
            <div><strong>Anomaly Insight:</strong> ${esc(p.anomaly_note || "")}</div>
            <div style="margin-top:5px;color:var(--ink-muted);"><strong>Warehouse SQL Lineage:</strong> <code>${esc(p.sql_lineage || "")}</code></div>
          </div>
        `;
      } else if (a.modality === "transcript") {
        bodyHtml = `
          <div class="transcript-list">
            ${(p.turns || [])
              .map(
                (t) => `
              <div class="turn-card">
                <div class="turn-head">
                  <span class="ts-pill">[${esc(t.timestamp)}]</span>
                  <strong>${esc(t.speaker)}</strong>
                </div>
                <div style="font-size:12.5px;color:var(--ink-secondary);">${esc(t.text)}</div>
              </div>`
              )
              .join("")}
          </div>
        `;
      } else {
        bodyHtml = `
          <div class="doc-sections">
            ${(p.sections || [])
              .map(
                (s) => `
              <div class="doc-sec">
                <h4>${esc(s.heading)}</h4>
                <p>${esc(s.body)}</p>
              </div>`
              )
              .join("")}
          </div>
        `;
      }

      box.innerHTML = `
        <div class="inspector-head">
          <div>
            <div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap;">
              <span class="mod-tag mod-${esc(a.modality)}">${esc(modLabel(a.modality))}</span>
              <span class="cls-badge cls-${esc(a.classification)}">${esc(a.classification)}</span>
              ${a.residency_pin ? `<span class="meta-chip ok">KMS: ${esc(a.residency_pin)}</span>` : ""}
              ${a.owner_sla_verified ? `<span class="meta-chip ok">Owner SLA Verified</span>` : `<span class="meta-chip warn">Unverified Owner SLA</span>`}
            </div>
            <h3 class="inspector-title">${esc(a.title)}</h3>
            <div class="inspector-meta">File: <code>${esc(a.filename)}</code> &middot; Owner: ${esc(a.owner)} &middot; Producer: <code>${esc(a.producer_service)}</code> &middot; Indexed into ${a.chunk_count} multi-modal chunks</div>
          </div>
        </div>
        ${bodyHtml}
      `;

      if (flashHighlight) {
        box.classList.remove("flash");
        void box.offsetWidth;
        box.classList.add("flash");
        box.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    } catch (err) {
      box.innerHTML = `<div style="color:var(--danger);">Failed to load asset: ${esc(err.message)}</div>`;
    }
  }

  function renderGovernanceTab() {
    const snap = state.snapshot;
    if (!snap) return;
    const gov = snap.governance;
    const container = document.getElementById("governance-container");
    const scoreColor =
      gov.readiness_score >= 90 ? "var(--ok)" : gov.readiness_score >= 65 ? "var(--warn)" : "var(--danger)";

    const findingsHtml = gov.findings.length
      ? `<div class="finding-list">
           ${gov.findings
             .map(
               (f) => `
             <div class="finding-card ${esc(f.severity)}">
               <div>
                 <div style="display:flex;align-items:center;gap:7px;margin-bottom:4px;">
                   <span class="cls-badge cls-${f.severity === "HIGH" ? "CONFIDENTIAL" : "INTERNAL"}">${esc(f.severity)} &middot; ${esc(f.rule_id)}</span>
                   <strong>${esc(f.title)}</strong>
                 </div>
                 <div style="font-size:12.2px;color:var(--ink-secondary);margin-bottom:4px;">${esc(f.detail)}</div>
                 <div style="font-size:11.8px;color:var(--accent);font-weight:600;">Agent Fix: ${esc(f.remediation_action)}</div>
               </div>
               <button type="button" class="pill fix-single-btn" data-fid="${esc(f.finding_id)}">Fix Policy</button>
             </div>`
             )
             .join("")}
         </div>`
      : `<div style="background:var(--ok-soft);border:1px solid #6ee7b7;color:#065f46;padding:14px;border-radius:8px;font-weight:600;">
           &#10003; All 5 Enterprise Governance controls passing (100/100 Readiness). PII column masking, tenant ACLs, EU-Central KMS residency, BI owner SLAs, and transcript retention policies are active.
         </div>`;

    const auditRows = (snap.audit_trail || []).length
      ? `<div style="margin-top:14px;">
           <div class="section-heading">Immutable Governance &amp; Ingestion Audit Log (SHA-256 Receipt Chain)</div>
           <div class="finding-list">
             ${snap.audit_trail
               .map(
                 (ev) => `
               <div style="background:#fff;border:1px solid var(--border);border-radius:7px;padding:8px 11px;font-size:12px;">
                 <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;">
                   <strong>${esc(ev.event)} &mdash; ${esc(ev.detail)}</strong>
                   <span class="mono" style="color:var(--ink-muted);">${esc(ev.timestamp.slice(0, 19))}Z</span>
                 </div>
                 ${
                   ev.sha256_receipt
                     ? `<div class="mono" style="font-size:11px;color:var(--ok);margin-top:3px;">SHA-256 Receipt: ${esc(ev.sha256_receipt)}</div>`
                     : ""
                 }
               </div>`
               )
               .join("")}
           </div>
         </div>`
      : "";

    container.innerHTML = `
      <div class="gov-hero">
        <div>
          <div class="section-heading">Enterprise Governance Onboarding &amp; Evaluation Agent</div>
          <div class="gov-score-ring">
            <span class="gov-score-num" style="color:${scoreColor};">${gov.readiness_score}/100</span>
            <span style="font-weight:700;color:${scoreColor};">${esc(gov.status_label)}</span>
          </div>
          <div style="font-size:12px;color:var(--ink-secondary);margin-top:2px;">
            ${gov.controls_passing} of ${gov.controls_total} governance controls passing across Space <strong>${esc(snap.active_space.name)}</strong>
          </div>
        </div>
        ${
          gov.open_findings_count > 0
            ? `<button type="button" class="primary-btn" id="remediate-all-btn">&#9889; Auto-Remediate All (${gov.open_findings_count}) Violations</button>`
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
        remAll.textContent = "Applying Governance Policies...";
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
      return `<button type="button" class="cite-inline" data-cite-asset="${esc(c.asset_id)}" title="Inspect ${esc(c.title)} (${esc(c.locator)})">[${esc(ref)}]</button>`;
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
    submitBtn.textContent = "Synthesizing...";

    const welcome = feed.querySelector(".chat-welcome");
    if (welcome) welcome.remove();

    const userBubble = document.createElement("div");
    userBubble.className = "msg-user";
    userBubble.textContent = q;
    feed.appendChild(userBubble);

    const aiBubble = document.createElement("div");
    aiBubble.className = "msg-ai";
    aiBubble.innerHTML = `<div style="color:var(--ink-muted);">Running ACL Pre-Filter &rarr; Hybrid BM25+Vector RRF &rarr; Amazon Bedrock Nova synthesis...</div>`;
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
          <span class="meta-chip purple">${esc(llm.engine || "Grounded Synthesizer")}</span>
          <span class="meta-chip ok">${ver.citation_precision_pct ?? 100}% Citation Verified</span>
          ${
            acl.blocked_assets_count > 0
              ? `<span class="meta-chip warn">ACL Blocked ${acl.blocked_assets_count} Restricted Asset(s)</span>`
              : `<span class="meta-chip">Searched ${acl.allowed_assets_searched} Assets</span>`
          }
          <span class="meta-chip">${esc(res.total_wall_ms)} ms</span>
        </div>
        <div class="ai-answer-body">${formatAnswerWithClickableCitations(res.answer, res.citations)}</div>
        ${chartHtml}
        ${
          res.citations && res.citations.length
            ? `<div class="citations-drawer">
                 <div style="font-size:10.5px;font-weight:700;color:var(--ink-muted);text-transform:uppercase;">Click any source to inspect exact table / timestamp / section:</div>
                 ${res.citations
                   .map(
                     (c) => `
                   <button type="button" class="citation-pill-btn" data-cite-asset="${esc(c.asset_id)}">
                     <span><strong>[${esc(c.ref)}]</strong> ${esc(c.title)} &middot; <em>${esc(c.locator)}</em></span>
                     <span class="mod-tag mod-${esc(c.modality)}">${esc(modLabel(c.modality))}</span>
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
          renderAssetsStrip();
          loadAssetInspector(aid, true);
        });
      });
    } catch (err) {
      aiBubble.innerHTML = `<div style="color:var(--danger);">Query failed: ${esc(err.message)}</div>`;
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = "Ask Space AI &rarr;";
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
    renderRoleSelector();
    renderClearanceBar();
    renderSpacesSidebar();
    renderSpaceHeroAndTabs();
    renderAssetsStrip();
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

    // Search input
    let searchTimer = null;
    document.getElementById("asset-search-input").addEventListener("input", (e) => {
      clearTimeout(searchTimer);
      const val = e.target.value.trim();
      searchTimer = setTimeout(async () => {
        state.searchQuery = val;
        if (!val) {
          state.searchHits = null;
          renderAssetsStrip();
          return;
        }
        state.searchHits = await apiGet(
          `/api/spaces/${encodeURIComponent(state.spaceId)}/search?q=${encodeURIComponent(val)}&role=${encodeURIComponent(state.roleId)}`
        );
        renderAssetsStrip();
      }, 220);
    });

    // Modality pills
    document.querySelectorAll("#modality-pills .pill").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("#modality-pills .pill").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.modalityFilter = btn.getAttribute("data-mod");
        renderAssetsStrip();
      });
    });

    // Chat submit
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

    // Reset button
    document.getElementById("reset-btn").onclick = async () => {
      await apiPost("/api/reset", {});
      state.roleId = "vp_admin";
      state.spaceId = "space-q3-cloud-arr";
      state.searchHits = null;
      state.searchQuery = "";
      document.getElementById("asset-search-input").value = "";
      await refreshWorkspace(true);
    };

    // Guided 1-click Tour buttons
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

    // Ingest Modal
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
      btn.textContent = "Parsing & Indexing...";
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
        btn.textContent = "Parse, Scan PII & Index into Space";
      }
    });

    // Architecture Modal
    const archModal = document.getElementById("arch-modal");
    document.getElementById("arch-btn").onclick = () => archModal.classList.remove("hidden");
    document.getElementById("close-arch-btn").onclick = () => archModal.classList.add("hidden");
  }

  bindEvents();
  refreshWorkspace(true);
})();
