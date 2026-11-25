/* QuickSpaces Interactive Enterprise Workspace Frontend — ritwikareddykancharla.github.io Blueprint Edition */
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
    if (mod === "bi_dashboard") return "BI KPIs";
    if (mod === "transcript") return "Transcript";
    return "RFC / Doc";
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
      "<strong>ACTIVE POLICY:</strong> " + esc(p.display_name) + " &mdash; " + esc(p.title);

    const originKind = location.hostname.includes("cloudfront.net")
      ? "CloudFront + S3 (OAC) + /api/*"
      : "Local Dev -> Live AWS Bedrock";
    document.getElementById("runtime-telemetry").textContent =
      originKind + " · tenant=" + p.tenant_id;
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
        const scoreStyle =
          sp.readiness_score >= 90 ? "color:var(--ok);font-weight:600;" : "color:var(--signal);font-weight:600;";
        return `
          <button type="button" class="space-item ${active}" data-space="${esc(sp.space_id)}">
            <div class="space-item-top">${esc(sp.name)}</div>
            <div class="space-item-meta">
              <span>${sp.accessible_count}/${sp.asset_count} open</span>
              <span style="${scoreStyle}">Gov ${sp.readiness_score}/100</span>
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
      badge.className = "st st-done";
    } else {
      badge.textContent = gov.open_findings_count + " open";
      badge.className = "st st-prog";
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

  function renderAssetsStrip() {
    const list = getFilteredAssets();
    const strip = document.getElementById("assets-list");
    const banner = document.getElementById("search-results-banner");

    if (state.searchHits) {
      banner.classList.remove("hidden");
      const blockedCount = (state.searchHits.blocked_assets || []).length;
      banner.innerHTML = `
        <span><strong>HYBRID RRF:</strong> ${state.searchHits.hits.length} authorized hit(s) for "${esc(state.searchQuery)}"${
        blockedCount > 0 ? ` &middot; <strong>${blockedCount} restricted asset(s) pre-filtered out</strong>` : ""
      }</span>
        <button type="button" class="chip-btn" id="clear-search-btn">Clear</button>
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
      strip.innerHTML = `<div class="mono-dim" style="grid-column:1/-1;padding:10px 0;">0 assets match this filter for your active governance clearance.</div>`;
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
              <span class="st">${esc(modLabel(a.modality))}</span>
              <button type="button" class="fav-star ${a.favorite ? "active" : ""}" data-fav="${esc(a.asset_id)}" title="Star asset">&#9733;</button>
            </div>
            <div class="asset-card-title">${!a.access_allowed ? "[LOCKED] " : ""}${esc(a.title)}</div>
            ${
              sh
                ? `<div class="mono-dim" style="color:var(--cobalt);">RRF ${sh.rrf_score} (BM25 ${sh.bm25_score})</div>`
                : `<div class="mono-dim">${esc(a.filename)}</div>`
            }
            <div class="asset-card-foot">
              <span class="st cls-${esc(a.classification)}">${esc(a.classification)}</span>
              <span>${esc(a.regions.join(","))} &middot; ${a.chunk_count}c</span>
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
        <div class="panel-k" style="color:var(--ink);margin-bottom:8px;">${esc(title)}</div>
        ${points
          .map((pt) => {
            const val = Number(pt.value) || 0;
            const pct = Math.max(3, Math.round((Math.abs(val) / maxAbs) * 100));
            const neg = val < 0 ? "negative" : "";
            return `
              <div class="bar-row">
                <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(pt.label)}">${esc(pt.label)}</span>
                <div class="bar-track"><div class="bar-fill ${neg}" style="width:${pct}%"></div></div>
                <span style="text-align:right;color:var(--ink);font-weight:600;">${esc(val)}${esc(unit || "")}</span>
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
    box.innerHTML = `<div class="mono-dim">Loading multi-modal inspector...</div>`;

    try {
      const detail = await apiGet(
        `/api/assets/${encodeURIComponent(assetId)}?role=${encodeURIComponent(state.roleId)}`
      );
      const a = detail.asset;

      if (detail.blocked) {
        box.innerHTML = `
          <div class="inspector-head">
            <span class="st cls-${esc(a.classification)}">${esc(a.classification)}</span>
            <h4 class="inspector-title">[ACCESS DENIED] ${esc(a.title)}</h4>
            <div class="mono-dim">${esc(a.filename)} &middot; Regions: ${esc(a.regions.join(", "))}</div>
          </div>
          <div class="pii-banner masked">
            <span><strong>ACL PRE-FILTER BLOCKED:</strong> ${esc(detail.block_reason)}. Switch <em>VIEWING AS</em> in the section header to <strong>VP Engineering (Admin)</strong> to inspect this file.</span>
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
                 <span><strong>DYNAMIC PII MASKING ACTIVE:</strong> Columns <code>${esc(
                   Array.from(piiCols).join(", ")
                 )}</code> masked for <strong>${esc(state.snapshot.principal.display_name)}</strong>.</span>
                 <span>Switch to VP Admin for raw PII</span>
               </div>`
            : `<div class="pii-banner">
                 <span><strong>ADMIN RAW PII CLEARANCE:</strong> Detected PII columns <code>${esc(
                   Array.from(piiCols).join(", ")
                 )}</code>. ${
                a.pii_masking_enforced
                  ? "Default non-admin policy: MASKED."
                  : "Warning: Default column policy unlocked (see Governance Agent)."
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
                   <div class="kpi-box-label">${esc(col)}</div>
                   <div class="kpi-box-val">${esc(st.sum.toLocaleString())}</div>
                   <div class="kpi-box-delta">avg ${esc(st.avg.toLocaleString())} &middot; [${esc(st.min)}, ${esc(st.max)}]</div>
                 </div>`
                 )
                 .join("")}
             </div>`
          : "";

        bodyHtml = `
          ${piiNotice}
          ${rollupHtml}
          <div class="tablewrap">
            <table>
              <thead>
                <tr>
                  ${(p.headers || [])
                    .map((h) => `<th>${esc(h)}${piiCols.has(h) ? " [PII]" : ""}</th>`)
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
          <div class="doc-sec" style="margin-top:12px;">
            <p><strong>Anomaly Callout:</strong> ${esc(p.anomaly_note || "")}</p>
            <div class="mono-dim" style="margin-top:6px;">SQL Lineage: <code>${esc(p.sql_lineage || "")}</code></div>
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
                  <span>${esc(t.speaker)}</span>
                </div>
                <p class="turn-body">${esc(t.text)}</p>
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
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
            <span class="st">${esc(modLabel(a.modality))}</span>
            <span class="st cls-${esc(a.classification)}">${esc(a.classification)}</span>
            ${a.residency_pin ? `<span class="st st-done">KMS: ${esc(a.residency_pin)}</span>` : ""}
            ${a.owner_sla_verified ? `<span class="st st-done">SLA Verified</span>` : `<span class="st st-prog">Unverified SLA</span>`}
          </div>
          <h4 class="inspector-title">${esc(a.title)}</h4>
          <div class="mono-dim">file=<code>${esc(a.filename)}</code> &middot; owner=${esc(a.owner)} &middot; producer=<code>${esc(a.producer_service)}</code> &middot; ${a.chunk_count} indexed chunks</div>
        </div>
        ${bodyHtml}
      `;

      if (flashHighlight) {
        box.classList.remove("flash");
        void box.offsetWidth;
        box.classList.add("flash");
        box.scrollIntoView({ behavior: "smooth", block: "nearest" });
        setTimeout(() => box.classList.remove("flash"), 1400);
      }
    } catch (err) {
      box.innerHTML = `<div class="mono-dim" style="color:var(--bad);">Failed to load asset: ${esc(err.message)}</div>`;
    }
  }

  function renderGovernanceTab() {
    const snap = state.snapshot;
    if (!snap) return;
    const gov = snap.governance;
    const container = document.getElementById("governance-container");
    const scoreColor = gov.readiness_score >= 90 ? "var(--ok)" : "var(--signal)";

    const findingsHtml = gov.findings.length
      ? `<div class="finding-list">
           ${gov.findings
             .map(
               (f) => `
             <div class="finding-card ${esc(f.severity)}">
               <div>
                 <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px;">
                   <span class="st ${f.severity === "HIGH" ? "st-prog" : ""}">${esc(f.severity)} &middot; ${esc(f.rule_id)}</span>
                   <strong>${esc(f.title)}</strong>
                 </div>
                 <p class="turn-body" style="font-size:0.98rem;margin-bottom:5px;">${esc(f.detail)}</p>
                 <div class="mono-dim" style="color:var(--cobalt);">Remediation: ${esc(f.remediation_action)}</div>
               </div>
               <button type="button" class="btn fix-single-btn" data-fid="${esc(f.finding_id)}">Apply Fix</button>
             </div>`
             )
             .join("")}
         </div>`
      : `<div class="pii-banner" style="border-left-color:var(--ok);">
           <span><strong>ALL 5 ENTERPRISE GOVERNANCE CONTROLS PASSING (100/100):</strong> Dynamic PII column masking, tenant ACLs, eu-central-1 KMS residency pinning, BI owner SLAs, and transcript retention tags enforced.</span>
         </div>`;

    const auditRows = (snap.audit_trail || []).length
      ? `<div style="margin-top:18px;">
           <p class="panel-k">Immutable Governance &amp; Ingestion Audit Chain (SHA-256)</p>
           <div class="finding-list">
             ${snap.audit_trail
               .map(
                 (ev) => `
               <div class="turn-card">
                 <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;font:500 11px var(--mono);">
                   <span>${esc(ev.event)} &mdash; ${esc(ev.detail)}</span>
                   <span class="mono-dim">${esc(ev.timestamp.slice(0, 19))}Z</span>
                 </div>
                 ${
                   ev.sha256_receipt
                     ? `<div class="mono-dim" style="color:var(--ok);margin-top:4px;">sha256=${esc(ev.sha256_receipt)}</div>`
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
          <p class="panel-k">Enterprise Governance Onboarding &amp; Evaluation Agent</p>
          <div style="display:flex;align-items:baseline;gap:10px;">
            <span class="gov-score-num" style="color:${scoreColor};">${gov.readiness_score}/100</span>
            <span class="st ${gov.readiness_score >= 90 ? "st-done" : "st-prog"}">${esc(gov.status_label)}</span>
          </div>
          <div class="mono-dim" style="margin-top:4px;">
            ${gov.controls_passing} of ${gov.controls_total} controls passing across Space <strong>${esc(snap.active_space.name)}</strong>
          </div>
        </div>
        ${
          gov.open_findings_count > 0
            ? `<button type="button" class="btn primary" id="remediate-all-btn">Auto-Remediate All (${gov.open_findings_count}) Violations &rarr;</button>`
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
        remAll.textContent = "Applying Policies...";
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

    const empty = feed.querySelector(".chat-empty");
    if (empty) empty.remove();

    const userBubble = document.createElement("div");
    userBubble.className = "msg-user";
    userBubble.textContent = q;
    feed.appendChild(userBubble);

    const aiBubble = document.createElement("div");
    aiBubble.className = "msg-ai";
    aiBubble.innerHTML = `<div class="mono-dim">ACL Pre-Filter &rarr; Hybrid BM25+Cosine RRF &rarr; Amazon Bedrock Nova synthesis...</div>`;
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
          <span class="st">${esc(llm.engine || "Grounded Synthesizer")}</span>
          <span class="st st-done">${ver.citation_precision_pct ?? 100}% Verified</span>
          ${
            acl.blocked_assets_count > 0
              ? `<span class="st st-prog">ACL Blocked ${acl.blocked_assets_count}</span>`
              : `<span class="st">${acl.allowed_assets_searched} Assets</span>`
          }
          <span class="st">${esc(res.total_wall_ms)} ms</span>
        </div>
        <div class="ai-answer-body">${formatAnswerWithClickableCitations(res.answer, res.citations)}</div>
        ${chartHtml}
        ${
          res.citations && res.citations.length
            ? `<div class="citations-drawer">
                 <span class="panel-k" style="margin-bottom:2px;">Cited Sources (click to inspect):</span>
                 ${res.citations
                   .map(
                     (c) => `
                   <button type="button" class="citation-pill-btn" data-cite-asset="${esc(c.asset_id)}">
                     <span><strong>[${esc(c.ref)}]</strong> ${esc(c.title)} &middot; ${esc(c.locator)}</span>
                     <span>${esc(modLabel(c.modality))}</span>
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
      aiBubble.innerHTML = `<div class="mono-dim" style="color:var(--bad);">Query error: ${esc(err.message)}</div>`;
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = "Run Grounded Query &rarr;";
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
    // Theme Toggle (matching ritwikareddykancharla.github.io)
    const themeBtn = document.getElementById("theme-toggle-btn");
    if (themeBtn) {
      themeBtn.addEventListener("click", () => {
        const root = document.documentElement;
        const next = root.dataset.theme === "dark" ? "light" : "dark";
        root.dataset.theme = next;
        history.replaceState(null, "", next === "dark" ? "#theme=dark" : location.pathname);
      });
    }

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
          renderAssetsStrip();
          return;
        }
        state.searchHits = await apiGet(
          `/api/spaces/${encodeURIComponent(state.spaceId)}/search?q=${encodeURIComponent(val)}&role=${encodeURIComponent(state.roleId)}`
        );
        renderAssetsStrip();
      }, 220);
    });

    document.querySelectorAll("#modality-pills .chip-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("#modality-pills .chip-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.modalityFilter = btn.getAttribute("data-mod");
        renderAssetsStrip();
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
        btn.textContent = "Parse, Scan PII & Index \u2192";
      }
    });
  }

  bindEvents();
  refreshWorkspace(true);
})();
