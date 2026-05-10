// Tiny i18n layer — no dependency, two locales.
// Default: navigator.language → ru-* picks RU, anything else picks EN.
// Override persisted in localStorage under "lang".
(function () {
  const STRINGS = {
    en: {
      // ── controls
      range_label: "RANGE:",
      quota_label: "QUOTA:",
      quota_5h_field_label: "5h % from /usage",
      quota_5h_pct_placeholder: "e.g. 35",
      quota_5h_pct_title:
        "Run `/usage` in Claude Code, copy the 5-hour percentage you see, and enter it here. " +
        "The dashboard back-computes your 5h cap as current_burn / (% / 100).",
      quota_weekly_field_label: "weekly % from /usage",
      quota_weekly_pct_placeholder: "e.g. 12",
      quota_weekly_pct_title:
        "Run `/usage` in Claude Code, copy the weekly percentage you see, and enter it here. " +
        "The dashboard back-computes your weekly cap as current_burn / (% / 100).",
      quota_calibrate_btn: "calibrate",
      quota_calibrate_title:
        "Anchor the dashboard's weighted-token cap to the % shown by /usage right now. " +
        "Saves resulting absolute caps to ~/.config/claude-code-token-meter/config.json.",
      quota_clear_btn: "clear",
      quota_clear_title: "Clear saved caps and remove progress bars.",
      quota_help:
        "Run `/usage` in Claude Code, copy the % you see for 5h and weekly, enter them above " +
        "and press calibrate. The dashboard reads your current burn and saves the absolute cap " +
        "(cap = burn / (%/100)). From then on, bars below show % used against that anchor. " +
        "Recalibrate any time the numbers drift.",
      quota_status_saved: "✓ calibrated",
      quota_status_cleared: "✓ cleared",
      quota_preview_calibrating: (cur, pct, cap) =>
        `current ${cur} = ${pct}% → cap ≈ ${cap}`,
      quota_preview_active: (cur, cap, pct) => `${cur} / ${cap}  (${pct}%)`,
      quota_preview_no_burn: "no recent burn — use Claude Code to generate data first",
      quota_saved_info: (cap5h, capWeekly) => {
        const parts = [];
        if (cap5h) parts.push(`5h cap = ${cap5h}`);
        if (capWeekly) parts.push(`weekly cap = ${capWeekly}`);
        return parts.length ? `currently saved: ${parts.join(" · ")}` : "";
      },
      refresh_btn: "↻ refresh",
      refreshing: "↻ refreshing…",
      theme_label: "THEME:",
      theme_dark: "🌙",
      theme_light: "☀",
      lang_label: "LANG:",

      // ── legend
      legend_summary: "what these values mean",
      legend_sessions_dt: "sessions tracked",
      legend_sessions_dd:
        "Unique Claude Code sessions in the selected range (one sessionId = one session).",
      legend_raw_dt: "raw tokens",
      legend_raw_dd_prefix: "Sum of all token kinds: ",
      legend_raw_dd_suffix: ". Total volume that flowed through the model.",
      legend_weighted_dt: "weighted (cost proxy)",
      legend_weighted_dd_prefix: "Weighted sum using Anthropic cost ratios: ",
      legend_weighted_dd_suffix:
        ". Not equal to % of subscription quota (Anthropic doesn't publish the formula), but gives a correct relative ranking.",
      legend_projects_dt: "projects",
      legend_projects_dd: "Unique cwd values where Claude Code was active.",
      legend_input_dt: "input",
      legend_input_dd: "Fresh input tokens — not from cache, charged in full.",
      legend_output_dt: "output",
      legend_output_dd: "Generated responses. Most expensive: ×5 weight.",
      legend_cache_read_dt: "cache_read",
      legend_cache_read_dd:
        "Read from prompt cache. Cheapest (×0.1) — usually the largest share of raw, smallest share of weighted.",
      legend_cache_create_dt: "cache_create",
      legend_cache_create_dd:
        "Writing a new entry to prompt cache (×1.25). Happens on session start and as context grows.",
      legend_msgs_dt: "msgs",
      legend_msgs_dd:
        "Number of assistant messages with usage in the session. Not 'user prompts' but model responses (including internal tool calls).",
      legend_sm_dt: "s= / m=",
      legend_sm_dd:
        "Compact counters in the projects row: s = number of sessions in this project, m = number of assistant-messages across them (including internal tool calls).",
      legend_title_dt: "title (8-char hash)",
      legend_title_dd: "First 8 chars of sessionId. Hover for the full UUID.",
      legend_pct_dt: "%",
      legend_pct_dd: "Share of weighted in this row vs. the range total.",
      legend_burn_dt: "burn rate",
      legend_burn_dd:
        "Weighted-token consumption speed in rolling windows (5h / 24h / 7d), measured from now, regardless of the range above. Sparkline = hourly sums for the last 24h.",

      // ── section headers
      h2_daily: "daily --by weighted",
      h2_daily_title: "weighted tokens per day inside the selected range",
      h2_projects: "projects --sort weighted",
      h2_projects_title: "total weighted per project — by the last two cwd segments",
      h2_models: "models --share",
      h2_models_title: "raw-token share between models (opus / sonnet / haiku)",
      h2_burnrate: "burn rate --rolling",
      h2_burnrate_title:
        "rolling-window burn rate. Not % of plan quota — Anthropic doesn't publish the formula. Speed of weighted-token consumption independent of the range above",
      h2_top: "top sessions --by weighted --limit 30",
      h2_top_title:
        "30 sessions with the highest weighted in range; everything else is summed in the line below",

      // ── stat boxes
      stat_sessions: "sessions tracked",
      stat_raw: "raw tokens",
      stat_weighted: "weighted (cost proxy)",
      stat_projects: "projects",

      // ── head row
      head_rank: "#",
      head_rank_title: "rank by weighted",
      head_date: "date",
      head_date_title: "first assistant-message timestamp of the session (local time)",
      head_project: "project",
      head_project_title: "last two segments of cwd",
      head_msgs: "msgs",
      head_msgs_title: "number of assistant-messages with usage",
      head_weight: "weight",
      head_weight_title:
        "weighted = input×1 + output×5 + cache_create×1.25 + cache_read×0.1",
      head_relative: "relative",
      head_relative_title: "bar relative to the max in this range",
      head_title: "title",
      head_title_title: "first 8 chars of sessionId; full UUID in hover",

      // ── empty / loading
      no_data: "no data in range",
      no_sessions: "no sessions in range",
      no_other_sessions: "no sessions beyond top 30 in this range.",
      other_sessions_prefix: "other sessions beyond top 30:",
      session_word: "session(s),",
      weighted_total_suffix: "weighted total",

      // ── burn rate rows
      last_5h: "last 5h",
      last_5h_hint: "rolling 5h window from now",
      last_24h: "last 24h",
      last_24h_hint: "rolling 24h window",
      last_7d: "last 7d",
      last_7d_hint: "rolling 7d window",
      sparkline: "24h sparkline",
      hourly_weighted: "hourly weighted",
      empirical_5h: "empirical 5h limit",
      empirical_calibrating_hint:
        "Need ≥3 limit-hit observations in JSONL for an estimate. Hits accumulate automatically — keep using Claude Code.",
      empirical_calibrating_text: (n) => `calibrating — ${n}/3 limit hits recorded`,
      empirical_ready_hint: (n, p5h, cur5h) =>
        `Empirical estimate of your 5h limit based on ${n} recorded "usage limit reached" events. ` +
        `Median weighted_5h at block time = ${p5h}. Current weighted_5h = ${cur5h}. ` +
        `Accuracy improves with more observations; 30-day window.`,
      manual_5h: "calibrated 5h limit",
      manual_5h_hint:
        "Progress toward the 5h cap calibrated from /usage in QUOTA above. Source: rolling 5h burn rate.",
      manual_weekly: "calibrated weekly limit",
      manual_weekly_hint:
        "Progress toward the weekly cap calibrated from /usage in QUOTA above. Source: rolling 7d burn rate.",

      // ── meta
      meta_template: (range, loaded, parse, total, tz) =>
        `range=${range}  ·  loaded=${loaded}  ·  parse=${parse}s  ·  total=${total}  ·  tz=${tz}`,

      // ── footnote
      footnote_formula:
        "weight = input×1 + output×5 + cache_create×1.25 + cache_read×0.1 — approximate cost proxy by token cost ratios. Not an exact % of plan quota (Anthropic doesn't publish the formula), but gives correct relative ranking.",
      footnote_data: "data: ~/.claude/projects/*/*.jsonl",

      // ── tooltips reused in tables
      tt_sessions:
        "Unique Claude Code sessions in the selected range (one sessionId = one session).",
      tt_raw:
        "Sum of all token kinds: input + output + cache_read + cache_create.",
      tt_weighted:
        "Weighted sum by Anthropic cost ratios:\ninput×1 + output×5 + cache_create×1.25 + cache_read×0.1.\nNot equal to % of subscription quota.",
      tt_projects: "Unique cwd values where Claude Code was active.",
      tt_input: "Fresh input tokens — not from cache, charged in full.",
      tt_output: "Generated responses. Most expensive: ×5 weight.",
      tt_cache_read: "Read from prompt cache. Cheapest: ×0.1 weight.",
      tt_cache_create: "Cache write entry: ×1.25 weight.",
      tt_msgs:
        "Assistant-messages with usage in the session (including tool calls).",
      tt_share: "This row's weighted share of the range total.",
      tt_proj_full: "last two cwd segments",
      tt_proj_share: "share of model raw tokens vs. range total",
      tt_relative: "bar relative to the max in this range",
      tt_sm: "s = sessions, m = assistant-messages",
    },

    ru: {
      // ── controls
      range_label: "ДИАПАЗОН:",
      quota_label: "КВОТА:",
      quota_5h_field_label: "5ч % из /usage",
      quota_5h_pct_placeholder: "напр. 35",
      quota_5h_pct_title:
        "Запусти `/usage` в Claude Code, посмотри сколько % показывает для 5ч-лимита и введи сюда. " +
        "Дашборд обратно посчитает cap = текущий_burn / (% / 100).",
      quota_weekly_field_label: "недельный % из /usage",
      quota_weekly_pct_placeholder: "напр. 12",
      quota_weekly_pct_title:
        "Запусти `/usage` в Claude Code, посмотри сколько % показывает для недельного лимита и введи сюда. " +
        "Дашборд обратно посчитает cap = текущий_burn / (% / 100).",
      quota_calibrate_btn: "калибровать",
      quota_calibrate_title:
        "Привязать наши weighted-токены к % из /usage прямо сейчас. " +
        "Сохранит абсолютные cap'ы в ~/.config/claude-code-token-meter/config.json.",
      quota_clear_btn: "сбросить",
      quota_clear_title: "Очистить сохранённые cap'ы и убрать прогресс-бары.",
      quota_help:
        "Запусти `/usage` в Claude Code, посмотри проценты для 5ч и недельного лимита, " +
        "введи их в поля выше и нажми «калибровать». Дашборд возьмёт твой текущий burn " +
        "и сохранит абсолютный cap (cap = burn / (%/100)). Дальше бары ниже покажут % " +
        "использования относительно этого якоря. Перекалибровывай когда цифры разойдутся.",
      quota_status_saved: "✓ откалибровано",
      quota_status_cleared: "✓ очищено",
      quota_preview_calibrating: (cur, pct, cap) =>
        `сейчас ${cur} = ${pct}% → cap ≈ ${cap}`,
      quota_preview_active: (cur, cap, pct) => `${cur} / ${cap}  (${pct}%)`,
      quota_preview_no_burn:
        "нет недавнего расхода — сначала попользуйся Claude Code",
      quota_saved_info: (cap5h, capWeekly) => {
        const parts = [];
        if (cap5h) parts.push(`5ч cap = ${cap5h}`);
        if (capWeekly) parts.push(`недельный cap = ${capWeekly}`);
        return parts.length ? `сейчас сохранено: ${parts.join(" · ")}` : "";
      },
      refresh_btn: "↻ обновить",
      refreshing: "↻ обновляю…",
      theme_label: "ТЕМА:",
      theme_dark: "🌙",
      theme_light: "☀",
      lang_label: "ЯЗЫК:",

      // ── legend
      legend_summary: "что значат показатели?",
      legend_sessions_dt: "sessions tracked",
      legend_sessions_dd:
        "Уникальные сессии Claude Code в выбранном диапазоне (один sessionId = одна сессия).",
      legend_raw_dt: "raw tokens",
      legend_raw_dd_prefix: "Сумма всех типов токенов: ",
      legend_raw_dd_suffix: ". Просто объём прошедшего через модель.",
      legend_weighted_dt: "weighted (cost proxy)",
      legend_weighted_dd_prefix: "Взвешенная сумма по соотношениям стоимости Anthropic: ",
      legend_weighted_dd_suffix:
        ". Не равно % от лимита подписки (формулу Anthropic не публикует), но даёт корректный относительный ранкинг.",
      legend_projects_dt: "projects",
      legend_projects_dd:
        "Уникальные cwd, в которых был активен Claude Code.",
      legend_input_dt: "input",
      legend_input_dd:
        "Новые входные токены — то, что не попало в кеш и оплачивается полностью.",
      legend_output_dt: "output",
      legend_output_dd:
        "Сгенерированные ответы. Самые «дорогие»: вес ×5 в weighted.",
      legend_cache_read_dt: "cache_read",
      legend_cache_read_dd:
        "Чтение из prompt cache. Самые дешёвые (×0.1) — обычно львиная доля raw, но малая доля weighted.",
      legend_cache_create_dt: "cache_create",
      legend_cache_create_dd:
        "Запись новой записи в prompt cache (×1.25). Случается на старте сессии и при росте контекста.",
      legend_msgs_dt: "msgs",
      legend_msgs_dd:
        "Количество assistant-сообщений с usage в сессии. Это не «промпты пользователя», а ответы модели (включая внутренние тул-вызовы).",
      legend_sm_dt: "s= / m=",
      legend_sm_dd:
        "Компактные счётчики в строке проекта: s = число сессий в проекте, m = число assistant-сообщений в них (включая внутренние тул-вызовы).",
      legend_title_dt: "title (8-символьный hash)",
      legend_title_dd:
        "Первые 8 символов sessionId. Ховер показывает полный UUID.",
      legend_pct_dt: "%",
      legend_pct_dd:
        "Доля weighted этой строки от общего weighted в выбранном диапазоне.",
      legend_burn_dt: "burn rate",
      legend_burn_dd:
        "Скорость расхода weighted-токенов в скользящих окнах (5h / 24h / 7d), считается от текущего времени, независимо от выбранного диапазона выше. Sparkline — почасовые суммы за последние 24 часа.",

      // ── section headers
      h2_daily: "daily --by weighted",
      h2_daily_title: "weighted-токены по дням внутри выбранного диапазона",
      h2_projects: "projects --sort weighted",
      h2_projects_title:
        "суммарный weighted по проектам — по последним двум сегментам cwd",
      h2_models: "models --share",
      h2_models_title: "доля raw-токенов между моделями (opus / sonnet / haiku)",
      h2_burnrate: "burn rate --rolling",
      h2_burnrate_title:
        "rolling-window burn rate. Не процент от лимита подписки — Anthropic не публикует формулу. Это скорость расхода weighted-токенов «независимо от диапазона выше»",
      h2_top: "top sessions --by weighted --limit 30",
      h2_top_title:
        "30 сессий с наибольшим weighted в диапазоне; всё что вне топа — в строке ниже",

      // ── stat boxes
      stat_sessions: "sessions tracked",
      stat_raw: "raw tokens",
      stat_weighted: "weighted (cost proxy)",
      stat_projects: "projects",

      // ── head row
      head_rank: "#",
      head_rank_title: "ранг по weighted",
      head_date: "date",
      head_date_title:
        "время первого assistant-сообщения сессии (локальное время)",
      head_project: "project",
      head_project_title: "последние два сегмента cwd",
      head_msgs: "msgs",
      head_msgs_title: "число assistant-сообщений с usage",
      head_weight: "weight",
      head_weight_title:
        "weighted = input×1 + output×5 + cache_create×1.25 + cache_read×0.1",
      head_relative: "relative",
      head_relative_title: "бар относительно максимума в диапазоне",
      head_title: "title",
      head_title_title: "первые 8 символов sessionId; полный UUID — в hover",

      // ── empty / loading
      no_data: "нет данных в диапазоне",
      no_sessions: "нет сессий в диапазоне",
      no_other_sessions: "нет сессий за пределами топ-30 в этом диапазоне.",
      other_sessions_prefix: "прочие сессии за пределами топ-30:",
      session_word: "сессий,",
      weighted_total_suffix: "weighted всего",

      // ── burn rate rows
      last_5h: "last 5h",
      last_5h_hint: "скользящее окно 5 часов от текущего времени",
      last_24h: "last 24h",
      last_24h_hint: "скользящее окно 24 часа",
      last_7d: "last 7d",
      last_7d_hint: "скользящее окно 7 дней",
      sparkline: "24h sparkline",
      hourly_weighted: "hourly weighted",
      empirical_5h: "empirical 5h limit",
      empirical_calibrating_hint:
        "Нужно ≥3 наблюдений лимит-хитов в JSONL для оценки. Лимиты накапливаются автоматически — продолжайте пользоваться Claude Code.",
      empirical_calibrating_text: (n) =>
        `калибровка — ${n}/3 лимит-хитов записано`,
      empirical_ready_hint: (n, p5h, cur5h) =>
        `Эмпирическая оценка вашего 5-часового лимита по ${n} зафиксированным ` +
        `моментам "usage limit reached". Медиана weighted_5h в момент блокировки = ` +
        `${p5h}. Текущий weighted_5h = ${cur5h}. ` +
        `Точность растёт с числом наблюдений; окно 30 дней.`,
      manual_5h: "calibrated 5h limit",
      manual_5h_hint:
        "Прогресс к 5ч cap'у, откалиброванному из /usage в QUOTA выше. Источник: rolling 5h burn rate.",
      manual_weekly: "calibrated weekly limit",
      manual_weekly_hint:
        "Прогресс к недельному cap'у, откалиброванному из /usage в QUOTA выше. Источник: rolling 7d burn rate.",

      // ── meta
      meta_template: (range, loaded, parse, total, tz) =>
        `range=${range}  ·  loaded=${loaded}  ·  parse=${parse}s  ·  total=${total}  ·  tz=${tz}`,

      // ── footnote
      footnote_formula:
        "weight = input×1 + output×5 + cache_create×1.25 + cache_read×0.1 — приблизительный прокси «стоимости» по token cost ratios. Это не точный процент от лимита подписки (Anthropic не публикует формулу), но даёт правильный относительный ранкинг сессий.",
      footnote_data: "данные: ~/.claude/projects/*/*.jsonl",

      // ── tooltips reused in tables
      tt_sessions:
        "Уникальные сессии Claude Code в выбранном диапазоне (один sessionId = одна сессия).",
      tt_raw: "Сумма всех типов токенов: input + output + cache_read + cache_create.",
      tt_weighted:
        "Взвешенная сумма по соотношениям стоимости Anthropic:\ninput×1 + output×5 + cache_create×1.25 + cache_read×0.1.\nНе равно % от лимита подписки.",
      tt_projects: "Уникальные cwd, в которых был активен Claude Code.",
      tt_input:
        "Новые входные токены — без кеша, оплачиваются полностью.",
      tt_output:
        "Сгенерированные ответы. Самые «дорогие»: вес ×5 в weighted.",
      tt_cache_read: "Чтение из prompt cache. Самые дешёвые: вес ×0.1.",
      tt_cache_create: "Запись новой записи в prompt cache: вес ×1.25.",
      tt_msgs:
        "Число assistant-сообщений с usage в сессии (включая тул-вызовы).",
      tt_share:
        "Доля weighted строки от общего weighted в выбранном диапазоне.",
      tt_proj_full: "последние два сегмента cwd",
      tt_proj_share:
        "доля raw-токенов модели от суммы по диапазону",
      tt_relative: "бар относительно максимума в диапазоне",
      tt_sm: "s = sessions, m = assistant-сообщений",
    },
  };

  function detectLang() {
    const stored = localStorage.getItem("lang");
    if (stored === "ru" || stored === "en") return stored;
    const nav = (navigator.language || "").toLowerCase();
    return nav.startsWith("ru") ? "ru" : "en";
  }

  let currentLang = detectLang();

  function t(key, ...args) {
    const dict = STRINGS[currentLang] || STRINGS.en;
    const v = dict[key] !== undefined ? dict[key] : STRINGS.en[key];
    if (typeof v === "function") return v(...args);
    return v !== undefined ? v : key;
  }

  function getLang() {
    return currentLang;
  }

  function setLang(lang) {
    if (lang !== "ru" && lang !== "en") return;
    currentLang = lang;
    localStorage.setItem("lang", lang);
    document.documentElement.lang = lang;
    applyStaticI18n();
  }

  // Apply translations to all elements with data-i18n / data-i18n-tip.
  // Dynamic content (rendered by app.js) calls t() directly during render.
  function applyStaticI18n(root) {
    const r = root || document;
    r.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.dataset.i18n);
    });
    r.querySelectorAll("[data-i18n-tip]").forEach((el) => {
      const v = t(el.dataset.i18nTip);
      if (v) el.setAttribute("data-tip", v);
      else el.removeAttribute("data-tip");
    });
    r.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.placeholder = t(el.dataset.i18nPlaceholder);
    });
  }

  document.documentElement.lang = currentLang;

  window.I18N = { t, getLang, setLang, applyStaticI18n };
})();
