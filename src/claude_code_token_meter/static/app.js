(function () {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const t = (...args) => window.I18N.t(...args);

  const fmtNum = (n) => {
    if (n === null || n === undefined) return "-";
    const abs = Math.abs(n);
    if (abs >= 1e9) return (n / 1e9).toFixed(2) + "B";
    if (abs >= 1e6) return (n / 1e6).toFixed(2) + "M";
    if (abs >= 1e3) return (n / 1e3).toFixed(1) + "K";
    return Math.round(n).toString();
  };

  const escapeHtml = (s) =>
    String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));

  // Local-timezone formatters. All backend timestamps are UTC (ISO 8601 with
  // tz offset); display in the user's resolved zone. Daily buckets are still
  // bucketed UTC-side — see ROADMAP Phase 2.5 gotcha.
  const fmtLocalDate = (iso) => {
    if (!iso) return "-";
    const d = new Date(iso);
    return Number.isNaN(d.getTime())
      ? iso
      : d.toLocaleDateString(undefined, {
          year: "numeric", month: "2-digit", day: "2-digit",
        });
  };
  const fmtLocalDateTime = (iso) => {
    if (!iso) return "-";
    const d = new Date(iso);
    return Number.isNaN(d.getTime())
      ? iso
      : d.toLocaleString(undefined, {
          dateStyle: "short", timeStyle: "short",
        });
  };
  const fmtLocalTime = (iso) => {
    if (!iso) return "-";
    const d = new Date(iso);
    return Number.isNaN(d.getTime())
      ? iso
      : d.toLocaleTimeString(undefined, {
          hour: "2-digit", minute: "2-digit",
        });
  };
  const localTz = () => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "local";
    } catch (_) {
      return "local";
    }
  };

  function bar(value, max, width) {
    const len = max > 0 ? Math.round((value / max) * width) : 0;
    return "█".repeat(len) + "░".repeat(Math.max(0, width - len));
  }

  function quotaBarStr(pct, width) {
    const clamped = Math.min(100, Math.max(0, pct));
    const filled = Math.round((clamped / 100) * width);
    return "█".repeat(filled) + "░".repeat(Math.max(0, width - filled));
  }

  function quotaBarClass(pct) {
    if (pct >= 90) return "bar bar-quota over";
    if (pct >= 50) return "bar bar-quota warn";
    return "bar bar-quota";
  }

  const SPARK = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"];
  function sparkline(values) {
    if (!values.length) return "";
    const max = Math.max(...values);
    if (max <= 0) return "▁".repeat(values.length);
    return values
      .map((v) => {
        const idx = Math.min(
          SPARK.length - 1,
          Math.max(0, Math.round((v / max) * (SPARK.length - 1)))
        );
        return SPARK[idx];
      })
      .join("");
  }

  function renderSummary(s) {
    $("#summary").innerHTML = `
      <div class="stat-box" data-tip="${escapeHtml(t("tt_sessions"))}">
        <span class="stat-value">${s.sessions_tracked}</span>
        <span class="stat-label">${escapeHtml(t("stat_sessions"))}</span>
      </div>
      <div class="stat-box" data-tip="${escapeHtml(t("tt_raw"))}">
        <span class="stat-value cyan">${fmtNum(s.raw_total)}</span>
        <span class="stat-label">${escapeHtml(t("stat_raw"))}</span>
      </div>
      <div class="stat-box" data-tip="${escapeHtml(t("tt_weighted"))}">
        <span class="stat-value orange">${fmtNum(s.weighted_total)}</span>
        <span class="stat-label">${escapeHtml(t("stat_weighted"))}</span>
      </div>
      <div class="stat-box" data-tip="${escapeHtml(t("tt_projects"))}">
        <span class="stat-value yellow">${s.projects_count}</span>
        <span class="stat-label">${escapeHtml(t("stat_projects"))}</span>
      </div>
    `;
    $("#totals").innerHTML = `
      <span data-tip="${escapeHtml(t("tt_input"))}">input: <span class="bright">${fmtNum(s.input)}</span></span> ·
      <span data-tip="${escapeHtml(t("tt_output"))}">output: <span class="bright">${fmtNum(s.output)}</span></span> ·
      <span data-tip="${escapeHtml(t("tt_cache_read"))}">cache_read: <span class="bright">${fmtNum(s.cache_read)}</span></span> ·
      <span data-tip="${escapeHtml(t("tt_cache_create"))}">cache_create: <span class="bright">${fmtNum(s.cache_create)}</span></span>
    `;
  }

  function renderDaily(rows) {
    if (!rows.length) {
      $("#daily").innerHTML = `<div class="empty">${escapeHtml(t("no_data"))}</div>`;
      return;
    }
    const max = Math.max(...rows.map((r) => r.weighted));
    $("#daily").innerHTML = rows
      .map(
        (r) => `
        <div class="row-d">
          <span class="proj">${escapeHtml(fmtLocalDate(r.started_iso) || r.date)}</span>
          <span class="bar">${bar(r.weighted, max, 40)}</span>
          <span class="num">${fmtNum(r.weighted)}</span>
        </div>
      `
      )
      .join("");
  }

  function renderProjects(rows) {
    if (!rows.length) {
      $("#projects").innerHTML = `<div class="empty">${escapeHtml(t("no_data"))}</div>`;
      return;
    }
    const max = Math.max(...rows.map((r) => r.weighted));
    $("#projects").innerHTML = rows
      .map(
        (r) => `
        <div class="row-p">
          <span class="proj" data-tip="${escapeHtml(t("tt_proj_full"))}">${escapeHtml(r.project)}</span>
          <span class="bar">${bar(r.weighted, max, 32)}</span>
          <span class="num" data-tip="${escapeHtml(t("tt_weighted"))}">${fmtNum(r.weighted)}</span>
          <span class="dim" data-tip="${escapeHtml(t("tt_share"))}">(${r.share_pct.toFixed(1)}%)</span>
          <span class="dim" data-tip="${escapeHtml(t("tt_sm"))}">s=${r.sessions} m=${r.msgs}</span>
        </div>
      `
      )
      .join("");
  }

  function renderModels(rows) {
    if (!rows.length) {
      $("#models").innerHTML = `<div class="empty">${escapeHtml(t("no_data"))}</div>`;
      return;
    }
    const max = Math.max(...rows.map((r) => r.raw));
    $("#models").innerHTML = rows
      .map(
        (r) => `
        <div class="row-p">
          <span class="proj">${escapeHtml(r.model)}</span>
          <span class="bar">${bar(r.raw, max, 32)}</span>
          <span class="num" data-tip="${escapeHtml(t("tt_raw"))}">${fmtNum(r.raw)}</span>
          <span class="dim" data-tip="${escapeHtml(t("tt_proj_share"))}">(${r.share_pct.toFixed(1)}%)</span>
          <span class="dim"></span>
        </div>
      `
      )
      .join("");
  }

  function renderTopSessions(rows) {
    if (!rows.length) {
      $("#top-sessions").innerHTML = `<div class="empty">${escapeHtml(t("no_sessions"))}</div>`;
      return;
    }
    const max = Math.max(...rows.map((r) => r.weighted));
    $("#top-sessions").innerHTML = rows
      .map(
        (r, i) => `
        <div class="row">
          <span class="dim" data-tip="${escapeHtml(t("head_rank_title"))}">${String(i + 1).padStart(2)}</span>
          <span class="date" data-tip="${escapeHtml(t("head_date_title"))}">${escapeHtml(fmtLocalDateTime(r.started_iso) || r.date)}</span>
          <span class="proj">${escapeHtml(r.project)}</span>
          <span class="msgs" data-tip="${escapeHtml(t("tt_msgs"))}">${r.msgs}</span>
          <span class="num" data-tip="${escapeHtml(t("tt_weighted"))}">${fmtNum(r.weighted)}</span>
          <span class="bar" data-tip="${escapeHtml(t("tt_relative"))}">${bar(r.weighted, max, 24)}</span>
          <span class="title"${r.session_id ? ` data-tip="${escapeHtml(r.session_id)}"` : ""}>${escapeHtml(r.title)}</span>
        </div>
      `
      )
      .join("");
  }

  function renderManualQuota(label, current, max, hintKey) {
    if (!max || max <= 0) return "";
    const pct = (current / max) * 100;
    const cls = quotaBarClass(pct);
    const barStr = quotaBarStr(pct, 24);
    const hint = `${t(hintKey)} cur=${fmtNum(current)} / cap=${fmtNum(max)}`;
    return `
      <div class="row-d" data-tip="${escapeHtml(hint)}">
        <span class="proj">${escapeHtml(t(label))}</span>
        <span class="${cls}" style="letter-spacing:0;">${barStr}</span>
        <span class="num">${pct.toFixed(0)}%</span>
      </div>`;
  }

  function renderCalibration(cal, br) {
    if (!cal) return "";
    if (!cal.ready) {
      const n = cal.n || 0;
      return `
        <div class="row-d" data-tip="${escapeHtml(t("empirical_calibrating_hint"))}">
          <span class="proj">${escapeHtml(t("empirical_5h"))}</span>
          <span class="dim">${escapeHtml(t("empirical_calibrating_text", n))}</span>
          <span class="num">—</span>
        </div>`;
    }
    const p5h = cal.p5h || 0;
    const cur5h = (br && br.last_5h && br.last_5h.weighted) || 0;
    const pct = p5h > 0 ? (cur5h / p5h) * 100 : 0;
    const cls = quotaBarClass(pct);
    const barStr = quotaBarStr(pct, 24);
    const spread = cal.spread_pct_5h !== null && cal.spread_pct_5h !== undefined
      ? ` ±${Math.round(cal.spread_pct_5h)}%`
      : "";
    const hint = t("empirical_ready_hint", cal.n, fmtNum(p5h), fmtNum(cur5h));
    return `
      <div class="row-d" data-tip="${escapeHtml(hint)}">
        <span class="proj">${escapeHtml(t("empirical_5h"))}</span>
        <span class="${cls}" style="letter-spacing:0;">${barStr}</span>
        <span class="num">${pct.toFixed(0)}% (n=${cal.n}${spread})</span>
      </div>`;
  }

  function renderBurnRate(br, cal, quota) {
    if (!br) {
      $("#burn-rate").innerHTML = "";
      return;
    }
    const rows = [
      { label: t("last_5h"), w: br.last_5h, perHour: br.last_5h.weighted_per_hour, hint: t("last_5h_hint") },
      { label: t("last_24h"), w: br.last_24h, perHour: br.last_24h.weighted_per_hour, hint: t("last_24h_hint") },
      { label: t("last_7d"), w: br.last_7d, perHour: br.last_7d.weighted_per_hour, hint: t("last_7d_hint") },
    ];
    const hourlyVals = (br.hourly_24h || []).map((h) => h.weighted);
    const spark = sparkline(hourlyVals);
    const sparkTitle = (br.hourly_24h || [])
      .map((h) => `${fmtLocalTime(h.hour)}: ${fmtNum(h.weighted)}`)
      .join("\n");

    const manual5h = quota
      ? renderManualQuota(
          "manual_5h",
          br.last_5h.weighted,
          quota.quota_5h,
          "manual_5h_hint"
        )
      : "";
    const manualWeekly = quota
      ? renderManualQuota(
          "manual_weekly",
          br.last_7d.weighted,
          quota.quota_weekly,
          "manual_weekly_hint"
        )
      : "";

    $("#burn-rate").innerHTML = `
      ${rows
        .map(
          (r) => `
        <div class="row-d" data-tip="${escapeHtml(r.hint)}">
          <span class="proj">${r.label}</span>
          <span class="dim">sessions=${r.w.sessions} · ${fmtNum(r.perHour)}/h</span>
          <span class="num">${fmtNum(r.w.weighted)}</span>
        </div>`
        )
        .join("")}
      <div class="row-d"${sparkTitle ? ` data-tip="${escapeHtml(sparkTitle)}"` : ""}>
        <span class="proj">${escapeHtml(t("sparkline"))}</span>
        <span class="bar" style="font-size:18px; letter-spacing:0; line-height:1;">${spark}</span>
        <span class="dim">${escapeHtml(t("hourly_weighted"))}</span>
      </div>
      ${manual5h}
      ${manualWeekly}
      ${renderCalibration(cal, br)}
    `;
  }

  function renderOther(other) {
    if (!other.count) {
      $("#other-sessions").innerHTML =
        `<span class="dim">${escapeHtml(t("no_other_sessions"))}</span>`;
      return;
    }
    $("#other-sessions").innerHTML = `
      <span class="dim">${escapeHtml(t("other_sessions_prefix"))}</span>
      <span class="bright">${other.count}</span>
      <span class="dim">${escapeHtml(t("session_word"))}</span>
      <span class="num">${fmtNum(other.weighted)}</span>
      <span class="dim">${escapeHtml(t("weighted_total_suffix"))}</span>
    `;
  }

  function renderMeta(stats) {
    const r = stats.range;
    const m = stats.meta;
    const days = r.days >= 1 ? `${r.days.toFixed(1)}d` : `${(r.days * 24).toFixed(1)}h`;
    $("#meta-info").textContent = t(
      "meta_template",
      days,
      m.loaded_at ? fmtLocalDateTime(m.loaded_at) : "-",
      m.parse_seconds,
      m.sessions_total,
      localTz()
    );
  }

  // ── state
  let currentDays = 7;
  let inFlight = false;
  let lastData = null; // cached for language re-render

  function renderAll(data) {
    lastData = data;
    renderSummary(data.summary);
    renderDaily(data.daily);
    renderProjects(data.projects);
    renderModels(data.models);
    renderBurnRate(data.burn_rate, data.calibration, data.quota);
    renderTopSessions(data.top_sessions);
    renderOther(data.other_sessions);
    renderMeta(data);
    renderQuotaPreview();
    renderQuotaSavedInfo(data.quota);
  }

  function quotaPctClass(pct) {
    if (pct >= 90) return "quota-preview over";
    if (pct >= 50) return "quota-preview warn";
    return "quota-preview";
  }

  // Live preview while typing %: show "current=X = Y% → cap ≈ Z".
  // If the % field is empty, show the saved cap & current % instead.
  function renderQuotaPreviewOne(previewEl, inputEl, currentBurn, savedCap) {
    const rawPct = inputEl.value.trim();
    const pct = parseFloat(rawPct);

    // Mode A: user typing a % → live cap preview
    if (rawPct !== "" && Number.isFinite(pct) && pct > 0 && pct <= 100) {
      if (!currentBurn || currentBurn <= 0) {
        previewEl.textContent = t("quota_preview_no_burn");
        previewEl.className = "quota-preview warn";
        return;
      }
      const cap = currentBurn / (pct / 100);
      previewEl.textContent = t(
        "quota_preview_calibrating",
        fmtNum(currentBurn),
        pct.toFixed(1),
        fmtNum(cap)
      );
      previewEl.className = "quota-preview";
      return;
    }

    // Mode B: nothing being typed but a cap is saved → show progress
    if (savedCap && savedCap > 0) {
      const livePct = (currentBurn / savedCap) * 100;
      previewEl.textContent = t(
        "quota_preview_active",
        fmtNum(currentBurn),
        fmtNum(savedCap),
        livePct.toFixed(0)
      );
      previewEl.className = quotaPctClass(livePct);
      return;
    }

    // Mode C: nothing typed, nothing saved
    previewEl.textContent = "";
    previewEl.className = "quota-preview";
  }

  function renderQuotaPreview() {
    if (!lastData) return;
    const br = lastData.burn_rate || {};
    const q = lastData.quota || {};
    renderQuotaPreviewOne(
      $("#quota-5h-preview"),
      $("#quota-5h-pct"),
      br.last_5h ? br.last_5h.weighted : 0,
      q.quota_5h
    );
    renderQuotaPreviewOne(
      $("#quota-weekly-preview"),
      $("#quota-weekly-pct"),
      br.last_7d ? br.last_7d.weighted : 0,
      q.quota_weekly
    );
  }

  function renderQuotaSavedInfo(quota) {
    const el = $("#quota-saved-info");
    if (!el) return;
    if (!quota) {
      el.textContent = "";
      return;
    }
    el.textContent = t(
      "quota_saved_info",
      quota.quota_5h ? fmtNum(quota.quota_5h) : null,
      quota.quota_weekly ? fmtNum(quota.quota_weekly) : null
    );
  }

  async function fetchAndRender(days) {
    if (inFlight) return;
    inFlight = true;
    currentDays = days;
    $$(".controls button[data-days]").forEach((b) => {
      b.classList.toggle("active", Number(b.dataset.days) === days);
    });
    try {
      const res = await fetch(`/api/stats?days=${days}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      renderAll(data);
    } catch (e) {
      $("#summary").innerHTML = `<span class="empty">error: ${escapeHtml(String(e))}</span>`;
    } finally {
      inFlight = false;
    }
  }

  async function refresh() {
    const btn = $("#refresh-btn");
    const orig = btn.textContent;
    btn.textContent = t("refreshing");
    btn.disabled = true;
    try {
      await fetch("/api/refresh", { method: "POST" });
      await fetchAndRender(currentDays);
    } finally {
      btn.textContent = orig;
      btn.disabled = false;
    }
  }

  // ── theme
  function detectTheme() {
    const stored = localStorage.getItem("theme");
    if (stored === "dark" || stored === "light") return stored;
    return window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark";
  }
  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
    $$("#theme-toggle button").forEach((b) => {
      b.classList.toggle("active", b.dataset.theme === theme);
    });
  }

  // ── lang
  function applyLangButtons(lang) {
    $$("#lang-toggle button").forEach((b) => {
      b.classList.toggle("active", b.dataset.lang === lang);
    });
  }

  let statusTimer = null;
  function flashStatus(messageKey, isError) {
    const el = $("#quota-status");
    if (!el) return;
    el.textContent = isError ? messageKey : t(messageKey);
    el.classList.toggle("error", !!isError);
    el.classList.add("visible");
    if (statusTimer) clearTimeout(statusTimer);
    statusTimer = setTimeout(() => {
      el.classList.remove("visible");
    }, 3000);
  }

  // Translate a typed % into an absolute cap by reading the current burn.
  // Returns null if % is empty/invalid; throws if % is set but burn is 0.
  function pctToCap(pctStr, currentBurn) {
    const trimmed = (pctStr || "").trim();
    if (trimmed === "") return null;
    const pct = parseFloat(trimmed);
    if (!Number.isFinite(pct) || pct <= 0 || pct > 100) {
      throw new Error("invalid %");
    }
    if (!currentBurn || currentBurn <= 0) {
      throw new Error("no burn to calibrate against");
    }
    return Math.round(currentBurn / (pct / 100));
  }

  async function postQuotas(payload, statusKey) {
    const saveBtn = $("#quota-save");
    const clearBtn = $("#quota-clear");
    const orig = saveBtn.textContent;
    saveBtn.disabled = true;
    if (clearBtn) clearBtn.disabled = true;
    saveBtn.textContent = "…";
    try {
      const res = await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchAndRender(currentDays);
      flashStatus(statusKey);
    } catch (e) {
      flashStatus("✗ " + String(e), true);
    } finally {
      saveBtn.textContent = orig;
      saveBtn.disabled = false;
      if (clearBtn) clearBtn.disabled = false;
    }
  }

  async function calibrateQuotas() {
    if (!lastData || !lastData.burn_rate) {
      flashStatus("✗ no data loaded yet", true);
      return;
    }
    const burn5h = lastData.burn_rate.last_5h
      ? lastData.burn_rate.last_5h.weighted
      : 0;
    const burnWeekly = lastData.burn_rate.last_7d
      ? lastData.burn_rate.last_7d.weighted
      : 0;

    let cap5h, capWeekly;
    try {
      cap5h = pctToCap($("#quota-5h-pct").value, burn5h);
    } catch (e) {
      flashStatus("✗ 5h: " + e.message, true);
      return;
    }
    try {
      capWeekly = pctToCap($("#quota-weekly-pct").value, burnWeekly);
    } catch (e) {
      flashStatus("✗ weekly: " + e.message, true);
      return;
    }

    if (cap5h === null && capWeekly === null) {
      flashStatus("✗ enter at least one %", true);
      return;
    }

    // Preserve any cap not being recalibrated this round.
    const saved = lastData.quota || {};
    await postQuotas(
      {
        quota_5h: cap5h !== null ? cap5h : saved.quota_5h,
        quota_weekly: capWeekly !== null ? capWeekly : saved.quota_weekly,
      },
      "quota_status_saved"
    );
    // Inputs hold the % the user typed; clear them after calibration so
    // the inline preview switches from "→ cap ≈ X" to live "cur / cap (Y%)".
    $("#quota-5h-pct").value = "";
    $("#quota-weekly-pct").value = "";
    renderQuotaPreview();
  }

  async function clearQuotas() {
    $("#quota-5h-pct").value = "";
    $("#quota-weekly-pct").value = "";
    await postQuotas(
      { quota_5h: null, quota_weekly: null },
      "quota_status_cleared"
    );
  }

  document.addEventListener("DOMContentLoaded", () => {
    // i18n: paint static labels first so the page doesn't flash English
    window.I18N.applyStaticI18n();
    applyLangButtons(window.I18N.getLang());

    // theme: apply before any rendering
    applyTheme(detectTheme());

    $$(".controls button[data-days]").forEach((btn) => {
      btn.addEventListener("click", () => fetchAndRender(Number(btn.dataset.days)));
    });
    $("#refresh-btn").addEventListener("click", refresh);

    $$("#theme-toggle button").forEach((btn) => {
      btn.addEventListener("click", () => applyTheme(btn.dataset.theme));
    });

    $$("#lang-toggle button").forEach((btn) => {
      btn.addEventListener("click", () => {
        window.I18N.setLang(btn.dataset.lang);
        applyLangButtons(btn.dataset.lang);
        if (lastData) renderAll(lastData);
      });
    });

    $("#quota-save").addEventListener("click", calibrateQuotas);
    $("#quota-clear").addEventListener("click", clearQuotas);
    [$("#quota-5h-pct"), $("#quota-weekly-pct")].forEach((el) => {
      el.addEventListener("input", renderQuotaPreview);
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter") calibrateQuotas();
      });
    });

    fetchAndRender(currentDays);
  });
})();
