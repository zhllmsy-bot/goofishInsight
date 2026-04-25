(() => {
  const DASHBOARD_TAB_KEYS = new Set(["market", "gallery", "debug"]);
  const DASHBOARD_TAB_STORAGE_KEY = "goofish-dashboard-home-tab";

  const DOMAIN_LABELS = {
    camera_interchangeable_lens: "可换镜头",
    camera_body: "相机机身",
    graphics_card: "显卡",
    phone: "手机",
    garmin: "Garmin手表",
    garmin_watch: "Garmin手表",
    apple_m_series: "Apple电脑",
    apple_computer: "Apple电脑",
  };

  const AUTH_STATE_LABELS = {
    authenticated: "已登录",
    login_required: "需要登录",
    unknown: "未知",
    error: "异常",
  };

  const RUN_STATUS_LABELS = {
    completed: "完成",
    running: "运行中",
    failed: "失败",
    cancelled: "已取消",
    pending: "等待中",
  };

  const RELIABILITY_TIER_LABELS = {
    high: "高",
    medium: "中",
    watch: "观察",
    low: "低",
  };

  const RUNTIME_STATUS_LABELS = {
    running: "运行中",
    degraded: "部分可用",
    stopped: "已停止",
  };

  const isBlank = (value) => value === null || value === undefined || value === "";
  const safeArray = (value) => (Array.isArray(value) ? value : []);
  const normalizeText = (value, fallback = "-") => (isBlank(value) ? fallback : String(value));
  const escapeHtml = (value) =>
    String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  const safeText = (value, fallback = "-") => escapeHtml(normalizeText(value, fallback));
  const safeAttr = (value, fallback = "") => escapeHtml(normalizeText(value, fallback));
  let latestPricingSnapshot = null;

  const formatNumber = (value, digits = null) => {
    if (isBlank(value)) {
      return "-";
    }
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return safeText(value);
    }
    const minimumFractionDigits = digits ?? 0;
    const maximumFractionDigits = digits ?? (Number.isInteger(number) ? 0 : 1);
    return new Intl.NumberFormat("zh-CN", {
      minimumFractionDigits,
      maximumFractionDigits,
    }).format(number);
  };

  const formatCurrency = (value) => {
    if (isBlank(value)) {
      return "-";
    }
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return safeText(value);
    }
    if (Math.abs(number) >= 10000) {
      return `¥${(number / 10000).toFixed(2)}w`;
    }
    return `¥${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(number)}`;
  };

  const formatDeltaCurrency = (value) => {
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return "-";
    }
    return `¥${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(Math.abs(Math.round(number)))}`;
  };

  const formatPercent = (value, digits = 0) => {
    if (isBlank(value)) {
      return "-";
    }
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return safeText(value);
    }
    return `${number.toFixed(digits)}%`;
  };

  const formatRelative = (value) => {
    if (isBlank(value)) {
      return "-";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return safeText(value);
    }
    const deltaSeconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
    if (deltaSeconds < 60) {
      return `${deltaSeconds}秒前`;
    }
    if (deltaSeconds < 3600) {
      return `${Math.floor(deltaSeconds / 60)}分钟前`;
    }
    if (deltaSeconds < 86400) {
      return `${Math.floor(deltaSeconds / 3600)}小时前`;
    }
    return `${Math.floor(deltaSeconds / 86400)}天前`;
  };

  const formatDateTime = (value) => {
    if (isBlank(value)) {
      return "-";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return safeText(value);
    }
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(date);
  };

  const domainLabel = (value) => {
    if (isBlank(value)) {
      return "Unknown";
    }
    return DOMAIN_LABELS[value] || String(value).replaceAll("_", " ").replace(/\b\w/g, (match) => match.toUpperCase());
  };

  const authStateLabel = (value) => AUTH_STATE_LABELS[value] || normalizeText(value, "未知");
  const runStatusLabel = (value) => RUN_STATUS_LABELS[value] || normalizeText(value);
  const reliabilityTierLabel = (value) => RELIABILITY_TIER_LABELS[value] || normalizeText(value);

  const optionSelected = (candidate, current) =>
    String(candidate ?? "") === String(current ?? "") ? " selected" : "";

  const renderOptions = (options, current, getValue, getLabel) =>
    safeArray(options)
      .map((option) => {
        const value = getValue(option);
        const label = getLabel(option);
        return `<option value="${safeAttr(value)}"${optionSelected(value, current)}>${safeText(label)}</option>`;
      })
      .join("");

  const DASHBOARD_STRUCTURED_FILTER_KEYS = [
    "product_label",
    "spec_label",
    "display_type",
    "case_size_mm",
    "is_solar",
    "chip_family",
    "screen_size_in",
    "memory_gb",
    "storage_gb",
  ];

  const buildDashboardHref = (updates = {}, options = {}) => {
    const params = new URLSearchParams(window.location.search);
    if (options.clearStructuredFilters) {
      DASHBOARD_STRUCTURED_FILTER_KEYS.forEach((key) => params.delete(key));
    }
    Object.entries(updates).forEach(([key, value]) => {
      if (isBlank(value)) {
        params.delete(key);
      } else {
        params.set(key, String(value));
      }
    });
    const query = params.toString();
    return `${window.location.pathname}${query ? `?${query}` : ""}`;
  };

  const getFilterField = (fields, key) => safeArray(fields).find((field) => field?.key === key) || null;
  const clampPercent = (value) => Math.max(0, Math.min(100, Number(value) || 0));
  const gaugePosition = (value, min, max) => {
    const numericValue = Number(value);
    const numericMin = Number(min);
    const numericMax = Number(max);
    if (!Number.isFinite(numericValue) || !Number.isFinite(numericMin) || !Number.isFinite(numericMax) || numericMax <= numericMin) {
      return 0;
    }
    return clampPercent(((numericValue - numericMin) / (numericMax - numericMin)) * 100);
  };

  const renderTagItems = (tags, className = "tag") =>
    safeArray(tags)
      .map((tag) => `<span class="${className}">${safeText(tag)}</span>`)
      .join("");

  const runtimeStatusLabel = (value) => RUNTIME_STATUS_LABELS[value] || normalizeText(value, "未知");
  const llmTraceStatusLabel = (value) =>
    ({ success: "成功", error: "异常", broken: "损坏" }[value] || normalizeText(value, "未知"));

  const renderLlmTraceCodeBlock = (title, value, open = false) => {
    if (isBlank(value)) {
      return "";
    }
    return `
      <details class="llm-trace-code-panel"${open ? " open" : ""}>
        <summary>${safeText(title)}</summary>
        <pre class="trace-code-block">${safeText(value, "")}</pre>
      </details>
    `;
  };

  const renderLlmTraceDetail = (trace) => {
    if (!trace) {
      return `
        <article class="llm-trace-detail-card">
          <p class="focus-empty">还没有可展示的 LLM trace。先触发一次 AI 建类、属性抽取或 review 流程，这里就会出现最近调用。</p>
        </article>
      `;
    }

    const messages = safeArray(trace.messages);
    return `
      <article class="llm-trace-detail-card">
        <div class="panel-header tight">
          <div>
            <p class="eyebrow">Trace Detail</p>
            <h3>${safeText(trace.model)}</h3>
          </div>
          <div class="panel-pills">
            <span class="status-pill">${safeText(trace.provider)}</span>
            <span class="status-pill">${safeText(trace.method)}</span>
            <span class="status-pill ${safeAttr(trace.status === "success" ? "accent" : "warn")}">${safeText(llmTraceStatusLabel(trace.status))}</span>
          </div>
        </div>
        <div class="llm-trace-meta-grid">
          <div>
            <span>时间</span>
            <strong>${safeText(formatDateTime(trace.generated_at))}</strong>
            <p class="subtle-line">${safeText(formatRelative(trace.generated_at))}</p>
          </div>
          <div>
            <span>文件</span>
            <strong>${safeText(trace.file_name)}</strong>
            <p class="subtle-line">${safeText(trace.trace_key)}</p>
          </div>
          <div>
            <span>消息数</span>
            <strong>${formatNumber(trace.message_count)}</strong>
            <p class="subtle-line">${safeText(trace.url)}</p>
          </div>
        </div>
        ${
          trace.error
            ? `<div class="llm-trace-error">${safeText(trace.error)}</div>`
            : ""
        }
        <section class="llm-trace-message-section">
          <div class="panel-header tight">
            <div>
              <p class="eyebrow">Messages</p>
              <h3>Prompt 明细</h3>
            </div>
          </div>
          <div class="llm-trace-message-list">
            ${
              messages.length
                ? messages
                    .map(
                      (message) => `
                        <article class="llm-trace-message-card">
                          <div class="llm-trace-message-head">
                            <span class="status-pill">${safeText(message.role)}</span>
                            <span class="subtle-line">消息 ${formatNumber(message.index)}</span>
                          </div>
                          <pre class="trace-code-block">${safeText(message.content_text, "")}</pre>
                        </article>
                      `,
                    )
                    .join("")
                : '<p class="focus-empty">这条 trace 没有 messages 内容。</p>'
            }
          </div>
        </section>
        <section class="llm-trace-code-grid">
          ${renderLlmTraceCodeBlock("Request Headers", trace.request_headers_json)}
          ${renderLlmTraceCodeBlock("Request Payload", trace.request_payload_json, true)}
          ${renderLlmTraceCodeBlock("Response Payload", trace.response_payload_json)}
          ${renderLlmTraceCodeBlock("Raw Trace JSON", trace.raw_json)}
        </section>
      </article>
    `;
  };

  const renderDashboardLlmTraces = (data) => {
    const traces = safeArray(data.traces);
    const latestTrace = data.latest_trace || null;
    const selectedTraceKey = latestTrace?.trace_key || traces[0]?.trace_key || "";

    return `
      <section class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">LLM Prompt Trace</p>
            <h3>最近模型调用</h3>
          </div>
          <div class="panel-pills">
            <span class="status-pill ${safeAttr(data.trace_enabled ? "accent" : "warn")}">${data.trace_enabled ? "写入中" : "已关闭写入"}</span>
            <span class="status-pill">${formatNumber(data.trace_count)} 条</span>
          </div>
        </div>
        <p class="pricing-legend">
          这里直接展示本地 trace 文件里的 system/user prompt、最终 request payload 和 response payload。触发 AI 建类、属性抽取、review second pass 后，刷新看板即可看到最新调用。
        </p>
        <p class="subtle-line">Trace 目录: ${safeText(data.trace_dir)}</p>
        <div class="llm-trace-grid" data-llm-trace-panel>
          <div class="llm-trace-list">
            ${
              traces.length
                ? traces
                    .map(
                      (trace) => `
                        <button
                          type="button"
                          class="llm-trace-list-item ${trace.trace_key === selectedTraceKey ? "active" : ""}"
                          data-llm-trace-select
                          data-trace-key="${safeAttr(trace.trace_key)}"
                        >
                          <div class="llm-trace-list-head">
                            <strong>${safeText(trace.model)}</strong>
                            <span class="reliability-pill ${safeAttr(trace.status === "success" ? "high" : "watch")}">${safeText(llmTraceStatusLabel(trace.status))}</span>
                          </div>
                          <p class="subtle-line">${safeText(trace.provider)} / ${safeText(formatDateTime(trace.generated_at))}</p>
                          ${trace.system_preview ? `<p class="llm-trace-preview"><span>System</span>${safeText(trace.system_preview)}</p>` : ""}
                          ${trace.user_preview ? `<p class="llm-trace-preview"><span>User</span>${safeText(trace.user_preview)}</p>` : ""}
                          ${trace.error ? `<p class="llm-trace-preview error"><span>Error</span>${safeText(trace.error)}</p>` : ""}
                        </button>
                      `,
                    )
                    .join("")
                : '<article class="llm-trace-empty-card"><p class="focus-empty">还没有 trace 文件。先触发一次模型调用即可。</p></article>'
            }
          </div>
          <div class="llm-trace-detail" data-llm-trace-detail>
            ${renderLlmTraceDetail(latestTrace)}
          </div>
        </div>
      </section>
    `;
  };

  const renderRuntimeControls = (runtimeData) => {
    const groups = safeArray(runtimeData?.groups);
    if (!groups.length) {
      return "";
    }

    return `
      <section class="panel compact-panel">
        <div class="panel-header tight">
          <div>
            <p class="eyebrow">Runtime Controls</p>
            <h3>一键开关</h3>
          </div>
          <div class="panel-pills">
            <span class="status-pill">刷新于 ${safeText(formatRelative(runtimeData.updatedAt))}</span>
          </div>
        </div>
        <p class="runtime-panel-text">
          这里直接控制首页 Feed、Batch Collect、独立的本机模型切换能力、VLM 72B Runtime，以及默认的 Review V3 常驻链路。动作只会改对应服务，不会把当前 dashboard 页面一起关掉。
        </p>
        <div class="runtime-control-grid">
          ${groups
            .map(
              (group) => `
                <article class="runtime-card" data-runtime-card data-runtime-target-card="${safeAttr(group.key)}">
                  <div class="runtime-card-head">
                    <div>
                      <p class="eyebrow">${safeText(group.title)}</p>
                      <h3>${safeText(group.title)}</h3>
                    </div>
                    <span class="runtime-status ${safeAttr(group.status, "stopped")}">${safeText(runtimeStatusLabel(group.status))}</span>
                  </div>
                  <p class="runtime-card-text">${safeText(group.description)}</p>
                  <div class="runtime-stat-grid">
                    ${safeArray(group.stats)
                      .map(
                        (stat) => `
                          <div class="runtime-stat">
                            <span>${safeText(stat.label)}</span>
                            <strong>${safeText(stat.value)}</strong>
                          </div>
                        `,
                      )
                      .join("")}
                  </div>
                  <div class="runtime-check-list">
                    ${safeArray(group.checks)
                      .map(
                        (check) => `
                          <div class="runtime-check ${check.ok ? "ok" : "warn"}">
                            <span>${safeText(check.label)}</span>
                            <strong>${safeText(check.detail)}</strong>
                          </div>
                        `,
                      )
                      .join("")}
                  </div>
                  <div class="runtime-actions">
                    ${safeArray(group.actions)
                      .map(
                        (action) => `
                          <button
                            type="button"
                            class="${action.tone === "primary" ? "primary-button" : "secondary-button"} runtime-action-button ${safeAttr(action.tone || "secondary")}"
                            data-runtime-action
                            data-runtime-target="${safeAttr(group.key)}"
                            data-runtime-action-name="${safeAttr(action.action)}"
                          >
                            ${safeText(action.label)}
                          </button>
                        `,
                      )
                      .join("")}
                  </div>
                  <p class="runtime-feedback" data-runtime-feedback></p>
                </article>
              `,
            )
            .join("")}
        </div>
      </section>
    `;
  };

  const renderRuntimeControlsPage = (runtimeData) => `
    <div class="async-section-stack">
      <section class="hero-panel">
        <div class="hero-copy">
          <p class="eyebrow">运行控制</p>
          <h2>本机常驻任务控制台</h2>
          <p class="hero-text">
            这个页面只放运维动作，不混进首页业务看板。适合一键拉起 collectors、独立切换本机模型档位、启动 72B 视觉模型，以及控制 Review V3 常驻与批跑。
          </p>
        </div>
        <div class="hero-meta">
          <span class="refresh-pill" data-refresh-badge data-refresh-seconds="20">自动刷新 20秒</span>
          <span class="status-pill accent">只做白名单动作</span>
        </div>
      </section>
      ${renderRuntimeControls(runtimeData)}
    </div>
  `;

  const renderDashboardHero = (data) => {
    const overview = data.overview || {};
    const browserSession = overview.browser_session || {};
    const latestRun = overview.latest_run || {};
    const authLabel = browserSession.auth_state ? authStateLabel(browserSession.auth_state) : "未知";
    const latestRunTone = latestRun.status === "completed" ? "accent" : latestRun.status === "failed" ? "warn" : "";

    return `
      <section class="panel terminal-status-panel">
        <div class="terminal-status-inline">
          <span class="refresh-pill" data-refresh-badge data-refresh-seconds="60">自动刷新 60秒</span>
          <span class="status-pill ${safeAttr(latestRunTone)}">${safeText(latestRun.status ? runStatusLabel(latestRun.status) : "待运行")}</span>
          <span class="status-pill">${safeText(authLabel)}</span>
          <span class="status-pill">${safeText(formatRelative(overview.latest_seen))} 刷新</span>
        </div>
        <p class="terminal-status-caption">
          ${latestRun.display_name ? `最近任务 ${safeText(latestRun.display_name)}` : "当前没有新的执行记录"}
        </p>
      </section>
    `;
  };

  const renderDashboardSelectionBar = (data) => {
    const selectedCategoryCode = data.selected_category_code || data.selected_domain || "";
    const selectedFilterValues = data.selected_filter_values || {};
    const visibleFields = safeArray(data.visible_filter_fields);
    const productField = getFilterField(visibleFields, "product_label");
    const specField = getFilterField(visibleFields, "spec_label");
    const selectedProduct = selectedFilterValues.product_label || "";
    const selectedSpec = selectedFilterValues.spec_label || "";

    let sectionTitle = "";
    let sectionHint = "";
    let chips = "";

    if (selectedProduct && specField && safeArray(specField.options).length) {
      sectionTitle = selectedSpec ? "切换规格" : "当前型号的常看规格";
      sectionHint = selectedProduct;
      chips = [
        `
          <a class="terminal-selection-chip ${selectedSpec ? "" : "is-active"}" href="${safeAttr(buildDashboardHref({ spec_label: "" }))}">
            <span>全部规格</span>
          </a>
        `,
        ...safeArray(specField.options)
          .slice(0, 8)
          .map((option) => {
            const value = option?.value ?? "";
            const label = option?.label ?? value;
            const active = String(value) === String(selectedSpec);
            return `
              <a class="terminal-selection-chip ${active ? "is-active" : ""}" href="${safeAttr(buildDashboardHref({ spec_label: value || "" }))}">
                <span>${safeText(label)}</span>
              </a>
            `;
          }),
      ].join("");
    } else if (selectedCategoryCode && productField && safeArray(productField.options).length) {
      sectionTitle = `${domainLabel(selectedCategoryCode)} 常看型号`;
      sectionHint = "点一下就切换右侧行情";
      chips = safeArray(productField.options)
        .slice(0, 8)
        .map((option) => {
          const value = option?.value ?? "";
          const label = option?.label ?? value;
          const active = String(value) === String(selectedProduct);
          return `
            <a class="terminal-selection-chip ${active ? "is-active" : ""}" href="${safeAttr(buildDashboardHref({ product_label: value || "", spec_label: "" }))}">
              <span>${safeText(label)}</span>
            </a>
          `;
        })
        .join("");
    }

    if (!chips) {
      return `
        <section class="panel terminal-selection-bar is-muted">
          <div>
            <p class="eyebrow">快捷切换</p>
            <h3>先从左侧选一个型号</h3>
          </div>
          <p class="terminal-selection-hint">选中具体型号后，这里会出现规格和配置的快捷切换。</p>
        </section>
      `;
    }

    return `
      <section class="panel terminal-selection-bar">
        <div class="terminal-selection-copy">
          <p class="eyebrow">快捷切换</p>
          <h3>${safeText(sectionTitle)}</h3>
          <p class="terminal-selection-hint">${safeText(sectionHint)}</p>
        </div>
        <div class="terminal-selection-chip-row">
          ${chips}
        </div>
      </section>
    `;
  };

  const renderDashboardFilters = (data) => {
    const selectedCategoryCode = data.selected_category_code || data.selected_domain || "";
    const availableCategories = data.available_categories || data.available_domains || [];
    const selectedFilterValues = data.selected_filter_values || {};
    const visibleFields = safeArray(data.visible_filter_fields);
    const productField = getFilterField(visibleFields, "product_label");
    const specField = getFilterField(visibleFields, "spec_label");
    const pricingViewOptions = safeArray(data.pricing_view_options).map((entry) =>
      Array.isArray(entry) ? { value: entry[0], label: entry[1] } : entry,
    );

    const advancedFields = visibleFields
      .map((field) => {
        const fieldClass = field.layout === "wide" ? "wide-field" : "narrow-field";
        return `
          <label class="filter-field ${fieldClass}">
            <span>${safeText(field.label)}</span>
            <select name="${safeAttr(field.key)}">
              <option value="">${safeText(field.placeholder)}</option>
              ${renderOptions(field.options, selectedFilterValues[field.key], (option) => option.value, (option) => option.label)}
            </select>
          </label>
        `;
      })
      .join("");

    const filterChips = safeArray(data.active_filter_summary)
      .map((filterText) => `<span class="tag">${safeText(filterText)}</span>`)
      .join("");

    const renderSpecTree = (options) =>
      safeArray(options)
        .slice(0, 10)
        .map((option) => {
          const value = option?.value ?? "";
          const label = option?.label ?? value;
          const active = String(value ?? "") === String(selectedFilterValues.spec_label ?? "");
          return `
            <li class="terminal-tree-leaf">
              <a class="terminal-tree-link ${active ? "is-active" : ""}" href="${safeAttr(buildDashboardHref({ spec_label: value || "" }))}">
                <span>${safeText(label)}</span>
              </a>
            </li>
          `;
        })
        .join("");

    const renderProductTree = () => {
      if (!productField) {
        return '<li class="terminal-tree-empty">先选择一个有结构化价格分组的业务域。</li>';
      }
      const children = safeArray(productField.options)
        .slice(0, 10)
        .map((option) => {
          const value = option?.value ?? "";
          const label = option?.label ?? value;
          const active = String(value ?? "") === String(selectedFilterValues.product_label ?? "");
          return `
            <li class="terminal-tree-node ${active ? "is-open" : ""}">
              <a class="terminal-tree-link ${active ? "is-active" : ""}" href="${safeAttr(buildDashboardHref({ product_label: value || "", spec_label: "" }))}">
                <span>${safeText(label)}</span>
              </a>
              ${
                active && specField
                  ? `
                    <ul class="terminal-tree-children terminal-tree-children-nested">
                      <li class="terminal-tree-leaf">
                        <a class="terminal-tree-link ${selectedFilterValues.spec_label ? "" : "is-active"}" href="${safeAttr(buildDashboardHref({ spec_label: "" }))}">
                          <span>全部规格</span>
                        </a>
                      </li>
                      ${renderSpecTree(specField.options)}
                    </ul>
                  `
                  : ""
              }
            </li>
          `;
        })
        .join("");

      return `
        <li class="terminal-tree-leaf">
          <a class="terminal-tree-link ${selectedFilterValues.product_label ? "" : "is-active"}" href="${safeAttr(buildDashboardHref({ product_label: "", spec_label: "" }))}">
            <span>全部型号</span>
          </a>
        </li>
        ${children}
      `;
    };

    const businessTree = safeArray(availableCategories)
      .map((domain) => {
        const value = domain ?? "";
        const active = String(value) === String(selectedCategoryCode ?? "");
        return `
          <li class="terminal-tree-domain ${active ? "is-open" : ""}">
            <a class="terminal-tree-branch ${active ? "is-active" : ""}" href="${safeAttr(buildDashboardHref({ category_code: value }, { clearStructuredFilters: true }))}">
              <span class="terminal-tree-caret" aria-hidden="true">${active ? "▾" : "▸"}</span>
              <span>${safeText(domainLabel(domain))}</span>
            </a>
            ${active ? `<ul class="terminal-tree-children">${renderProductTree()}</ul>` : ""}
          </li>
        `;
      })
      .join("");

    return `
      <section class="terminal-sidebar-panel">
        <div class="terminal-sidebar-quick-row">
          <a class="terminal-preset-pill ${data.pricing_scope !== "all" ? "is-active" : ""}" href="${safeAttr(buildDashboardHref({ pricing_scope: "actionable" }))}">只看机会成立</a>
          <a class="terminal-preset-pill ${data.pricing_scope === "all" ? "is-active" : ""}" href="${safeAttr(buildDashboardHref({ pricing_scope: "all" }))}">查看全部</a>
        </div>

        <div class="terminal-tree-section">
          <ul class="terminal-tree-root">
            <li class="terminal-tree-domain">
              <a class="terminal-tree-branch ${selectedCategoryCode ? "" : "is-active"}" href="${safeAttr(buildDashboardHref({ category_code: "" }, { clearStructuredFilters: true }))}">
                <span class="terminal-tree-caret" aria-hidden="true">${selectedCategoryCode ? "▸" : "▾"}</span>
                <span>全部市场</span>
              </a>
            </li>
            ${businessTree}
          </ul>
        </div>

        <details class="terminal-detail-panel sidebar-detail-panel">
          <summary>偏好设置</summary>
          <form method="get" class="filters-form terminal-filters-form" data-filter-form autocomplete="off">
            <label class="filter-field wide-field">
              <span>业务域</span>
              <select name="category_code" data-category-filter>
                <option value="">全部</option>
                ${renderOptions(availableCategories, selectedCategoryCode, (domain) => domain ?? "", (domain) => domainLabel(domain))}
              </select>
            </label>
            ${advancedFields}
            <label class="filter-field narrow-field">
              <span>定价视图</span>
              <select name="pricing_view">
                ${renderOptions(pricingViewOptions, data.pricing_view, (option) => option.value, (option) => option.label)}
              </select>
            </label>
            <label class="filter-field narrow-field">
              <span>显示范围</span>
              <select name="pricing_scope">
                <option value="actionable"${optionSelected("actionable", data.pricing_scope)}>只看机会成立</option>
                <option value="all"${optionSelected("all", data.pricing_scope)}>查看全部</option>
              </select>
            </label>
            <label class="filter-field narrow-field">
              <span>看板窗口</span>
              <select name="pricing_freshness_days">
                ${renderOptions([14, 30, 45, 60, 90], data.pricing_freshness_days, (value) => value, (value) => `${value}天`)}
              </select>
            </label>
            <label class="filter-field narrow-field">
              <span>心跳阈值</span>
              <select name="heartbeat_days">
                ${renderOptions([1, 2, 3, 5, 7, 10, 14], data.heartbeat_days, (value) => value, (value) => `${value}天`)}
              </select>
            </label>
            <label class="filter-field narrow-field">
              <span>最少样本</span>
              <select name="pricing_min_samples">
                ${renderOptions([3, 4, 5, 6, 8, 10], data.pricing_min_samples, (value) => value, (value) => value)}
              </select>
            </label>
            <label class="filter-field narrow-field">
              <span>价格分组条数</span>
              <select name="pricing_limit">
                ${renderOptions([6, 12, 18, 24, 36, 48], data.pricing_limit, (value) => value, (value) => value)}
              </select>
            </label>
            <label class="filter-field narrow-field">
              <span>机会卡片条数</span>
              <select name="limit">
                ${renderOptions([12, 24, 36, 60, 90, 120], data.limit, (value) => value, (value) => value)}
              </select>
            </label>
            <div class="filter-actions">
              <button type="submit" class="primary-button">更新偏好</button>
              <a href="/" class="secondary-button">清空</a>
            </div>
          </form>
        </details>
        ${filterChips ? `<div class="filter-chip-row">${filterChips}</div>` : ""}
      </section>
    `;
  };

  const renderTrendCard = (card) => `
    <article class="terminal-trend-card">
      <div class="terminal-trend-head">
        <div>
          <p class="eyebrow">价格趋势</p>
          <h3>${safeText(card.label)}</h3>
          <p class="terminal-trend-subtitle">${safeText(card.domain_label)} / 最新中位价 ${formatCurrency(card.latest_close)}</p>
        </div>
        <div class="panel-pills">
          <span class="signal-pill ${safeAttr(card.change_class, "watch")}">${safeText(card.change_label)}</span>
          <span class="status-pill">${safeText(card.volatility_label)}</span>
        </div>
      </div>
      <div class="terminal-trend-chart">
        <svg
          class="trend-chart ${safeAttr(card.change_class, "watch")}"
          viewBox="0 0 ${safeAttr(card.chart_width)} ${safeAttr(card.chart_height)}"
          role="img"
          aria-label="${safeAttr(card.aria_label)}"
        >
          ${safeArray(card.price_ticks)
            .map(
              (tick) => `
                <line x1="54" x2="${safeAttr((card.chart_width || 0) - 18)}" y1="${safeAttr(tick.y)}" y2="${safeAttr(tick.y)}" class="trend-grid-line"></line>
                <text x="8" y="${safeAttr((tick.y || 0) + 4)}" class="trend-axis-text">${safeText(tick.label)}</text>
              `,
            )
            .join("")}
          <path d="${safeAttr(card.trend_upper_path)}" class="trend-range-line" fill="none"></path>
          <path d="${safeAttr(card.trend_lower_path)}" class="trend-range-line" fill="none"></path>
          <path d="${safeAttr(card.trend_line_path)}" class="trend-line" fill="none"></path>
          ${safeArray(card.trend_points)
            .map(
              (point) => `
                <g class="trend-point-group">
                  <title>${safeText(point.tooltip)}</title>
                  <circle cx="${safeAttr(point.center_x)}" cy="${safeAttr(point.mid_y)}" r="4.5" class="trend-point-core"></circle>
                </g>
              `,
            )
            .join("")}
          ${safeArray(card.date_ticks)
            .map(
              (tick) => `
                <text x="${safeAttr(tick.x)}" y="${safeAttr((card.chart_height || 0) - 8)}" text-anchor="middle" class="trend-axis-text">${safeText(tick.label)}</text>
              `,
            )
            .join("")}
        </svg>
      </div>
      <div class="terminal-trend-foot">
        <span>价格带 ${safeText(card.latest_range_label)}</span>
        <span>最新样本 ${formatNumber(card.latest_sample_count)}</span>
        <span>活跃卖家 ${formatNumber(card.seller_sample_count)}</span>
      </div>
      <div class="terminal-reference-summary">
        <span>${safeText((card.pricingAvailabilitySummary || {}).readinessSummary || "-")}</span>
        <span>${safeText(((card.pricingAvailability || {}).pricingBlockReasonLabel) || "价格证据可用")}</span>
      </div>
    </article>
  `;

  const renderDashboardPricing = (data) => {
    const pricingPanel = data.pricing_panel || {};
    const pricingGateSummary = data.pricing_gate_summary || {};
    const selectedPricingAvailability = data.selected_pricing_availability || {};
    const selectedPricingAvailabilitySummary = data.selected_pricing_availability_summary || {};
    const rows = safeArray(pricingPanel.rows);
    const featuredRow = rows[0] || null;
    const excludedReasons = safeArray(pricingGateSummary.excluded_reasons).filter((reason) => Number(reason.count || 0) > 0);

    if (!featuredRow) {
      latestPricingSnapshot = null;
      return `
        <section class="panel terminal-section-panel terminal-pricing-panel terminal-pricing-empty">
          <div class="terminal-pricing-head compact">
            <div>
              <p class="eyebrow">核心价格线</p>
              <h3>当前还没有稳定价格带</h3>
              <p class="pricing-legend">先在左侧点进一个型号，或者把显示范围切到“查看全部”，这里就会出现收货价和市场中位价。</p>
            </div>
            <div class="terminal-pricing-empty-stats">
              <span class="status-pill">利润池 ${formatNumber(pricingGateSummary.pricing_pool_count)}</span>
              <span class="status-pill">${formatNumber(pricingGateSummary.candidate_count)} 候选</span>
            </div>
          </div>
          <details class="terminal-detail-panel">
            <summary>展开当前利润池状态</summary>
            <div class="terminal-detail-content">
              <div class="terminal-reference-summary">
                <span>基础候选池 ${formatNumber(pricingGateSummary.candidate_count)}</span>
                <span>进入利润池 ${formatNumber(pricingGateSummary.pricing_pool_count)}</span>
                <span>Review Gate 拦截 ${formatNumber(pricingGateSummary.review_gate_filtered_count)}</span>
              </div>
              <div class="pricing-gate-reason-row">
                ${
                  excludedReasons.length
                    ? excludedReasons
                        .map(
                          (reason) => `
                            <span class="status-pill warn">${safeText(reason.label)} ${formatNumber(reason.count)}</span>
                          `,
                        )
                        .join("")
                    : '<span class="status-pill accent">当前没有 review gate 拦截</span>'
                }
              </div>
            </div>
          </details>
        </section>
      `;
    }

    latestPricingSnapshot = {
      label: featuredRow.label,
      safeBuyPrice: Number(featuredRow.safe_buy_price || 0),
      normalBuyPrice: Number(featuredRow.normal_buy_price || 0),
      marketMidPrice: Number(featuredRow.market_mid_price || 0),
    };

    const safeBuyPrice = Number(featuredRow.safe_buy_price || 0);
    const normalBuyPrice = Number(featuredRow.normal_buy_price || 0);
    const marketMidPrice = Number(featuredRow.market_mid_price || 0);
    const spreadPadding = Math.max((marketMidPrice - safeBuyPrice) * 0.35, marketMidPrice * 0.06, 1);
    const rangeMin = Math.max(0, Math.min(safeBuyPrice, normalBuyPrice, marketMidPrice) - spreadPadding);
    const rangeMax = Math.max(rangeMin + 1, Math.max(safeBuyPrice, normalBuyPrice, marketMidPrice) + spreadPadding);
    const safePosition = gaugePosition(safeBuyPrice, rangeMin, rangeMax);
    const normalPosition = gaugePosition(normalBuyPrice, rangeMin, rangeMax);
    const marketPosition = gaugePosition(marketMidPrice, rangeMin, rangeMax);
    const headline = featuredRow.spec_label || featuredRow.label;
    const subtitle = featuredRow.spec_label ? "当前选中规格" : "当前选中型号";
    const detailLine =
      featuredRow.product_label && featuredRow.product_label !== featuredRow.label
        ? `${featuredRow.product_label} / ${pricingPanel.view_label}`
        : `${pricingPanel.view_label} / ${formatNumber(featuredRow.unique_seller_count)} 个卖家样本`;

    return `
      <section class="panel terminal-section-panel terminal-pricing-panel">
        <div class="terminal-pricing-head">
          <div class="terminal-pricing-copy">
            <p class="eyebrow">核心价格线</p>
            <h3>${safeText(headline)}</h3>
            <p class="pricing-legend">${safeText(subtitle)}</p>
            <p class="terminal-pricing-detail">${safeText(detailLine)} / 近 ${formatNumber(pricingPanel.freshness_days)} 天活跃样本</p>
          </div>
          <div class="terminal-margin-pill">
            <span>预估单机毛利</span>
            <strong>${formatCurrency(featuredRow.estimated_profit_floor)} ~ ${formatCurrency(featuredRow.estimated_profit_ceiling)}</strong>
            <small>${formatPercent(featuredRow.normal_margin_pct, 1)} 毛利率</small>
          </div>
        </div>

        <div class="terminal-price-card-grid">
          <article class="terminal-price-card safe">
            <div class="terminal-price-card-top">
              <span class="terminal-price-dot" aria-hidden="true"></span>
              <span>安全收货价</span>
            </div>
            <strong class="price-display">${formatCurrency(featuredRow.safe_buy_price)}</strong>
            <small>绝佳买入线 · P15 分位</small>
          </article>
          <article class="terminal-price-card watch">
            <div class="terminal-price-card-top">
              <span class="terminal-price-dot" aria-hidden="true"></span>
              <span>正常收货价</span>
            </div>
            <strong class="price-display">${formatCurrency(featuredRow.normal_buy_price)}</strong>
            <small>可谈价格线 · P35 分位</small>
          </article>
          <article class="terminal-price-card market">
            <div class="terminal-price-card-top">
              <span class="terminal-price-dot" aria-hidden="true"></span>
              <span>市场中位价</span>
            </div>
            <strong class="price-display">${formatCurrency(featuredRow.market_mid_price)}</strong>
            <small>当前挂牌均价 · P50 分位</small>
          </article>
        </div>

        <div class="price-gauge-shell" aria-label="价格标尺">
          <div class="price-gauge-track"></div>
          <div class="price-gauge-range buy" style="left:${safeAttr(safePosition)}%; width:${safeAttr(Math.max(normalPosition - safePosition, 2))}%"></div>
          <div class="price-gauge-range watch" style="left:${safeAttr(normalPosition)}%; width:${safeAttr(Math.max(marketPosition - normalPosition, 2))}%"></div>
          <div class="price-gauge-marker buy" style="left:${safeAttr(safePosition)}%">
            <strong>${formatCurrency(featuredRow.safe_buy_price)}</strong>
            <span>安全</span>
          </div>
          <div class="price-gauge-marker watch" style="left:${safeAttr(normalPosition)}%">
            <strong>${formatCurrency(featuredRow.normal_buy_price)}</strong>
            <span>正常</span>
          </div>
          <div class="price-gauge-marker market" style="left:${safeAttr(marketPosition)}%">
            <strong>${formatCurrency(featuredRow.market_mid_price)}</strong>
            <span>中位</span>
          </div>
          <div class="price-gauge-axis">
            <span>${formatCurrency(rangeMin)}</span>
            <span>${formatCurrency(rangeMax)}</span>
          </div>
        </div>

        <div class="terminal-pricing-meta-row">
          <span class="status-pill accent">${safeText(featuredRow.opportunity_label)}</span>
          <span class="status-pill">${formatNumber(featuredRow.unique_seller_count)} 个卖家样本</span>
          <span class="status-pill">可靠度 ${formatNumber(featuredRow.reliability_score)}</span>
          <span class="status-pill">安全毛利率 ${formatPercent(featuredRow.safe_margin_pct, 1)}</span>
        </div>
        <div class="terminal-reference-summary">
          <span>${safeText((featuredRow.pricingAvailabilitySummary || selectedPricingAvailabilitySummary).readinessSummary || "-")}</span>
          <span>${safeText(selectedPricingAvailability.pricingBlockReasonLabel || "价格证据可用")}</span>
        </div>
        ${safeArray(featuredRow.dimensions).length ? `<div class="tag-row">${renderTagItems(featuredRow.dimensions.slice(0, 6))}</div>` : ""}

        <details class="terminal-detail-panel">
          <summary>展开同类型号与过滤说明</summary>
          <div class="terminal-detail-content">
            <div class="terminal-reference-summary">
              <span>基础候选池 ${formatNumber(pricingGateSummary.candidate_count)}</span>
              <span>进入利润池 ${formatNumber(pricingGateSummary.pricing_pool_count)}</span>
              <span>机会成立 ${formatNumber(pricingPanel.actionable_count)} / ${formatNumber(pricingPanel.total_count)}</span>
            </div>
            <div class="pricing-gate-reason-row">
              ${
                excludedReasons.length
                  ? excludedReasons
                      .map(
                        (reason) => `
                          <span class="status-pill warn">${safeText(reason.label)} ${formatNumber(reason.count)}</span>
                        `,
                      )
                      .join("")
                  : '<span class="status-pill accent">当前没有 review gate 拦截</span>'
              }
              ${
                Number(pricingGateSummary.structural_drop_count || 0) > 0
                  ? `<span class="status-pill">结构化再剔除 ${formatNumber(pricingGateSummary.structural_drop_count)}</span>`
                  : ""
              }
            </div>
            <div class="terminal-list-table">
              ${rows
                .map(
                  (row) => `
                    <div class="terminal-list-row">
                      <div>
                        <strong>${safeText(row.label)}</strong>
                        <span>${row.product_label && row.product_label !== row.label ? safeText(row.product_label) : safeText(domainLabel(row.business_domain))}</span>
                      </div>
                      <div>${formatCurrency(row.safe_buy_price)} / ${formatCurrency(row.normal_buy_price)}</div>
                      <div>${formatCurrency(row.market_mid_price)}</div>
                      <div>${formatCurrency(row.estimated_profit_floor)} ~ ${formatCurrency(row.estimated_profit_ceiling)}</div>
                      <div>${formatNumber(row.unique_seller_count)} 卖家</div>
                      <div>${safeText((row.pricingAvailabilitySummary || {}).readinessSummary || "-")}</div>
                    </div>
                  `,
                )
                .join("")}
            </div>
          </div>
        </details>
      </section>
    `;
  };

  const renderDashboardOps = (data) => {
    const overview = data.overview || {};
    const domainCards = safeArray(data.domain_cards);
    const recentRuns = safeArray(data.recent_runs).slice(0, 4);
    const browserSession = overview.browser_session || {};

    return `
      <div class="async-section-stack">
        <section class="ops-strip">
          <article class="stat-card compact">
            <p class="stat-label">近窗样本</p>
            <p class="stat-value compact">${formatNumber(overview.total_items)}</p>
            <p class="stat-sub">当前活跃 ${formatNumber(overview.active_items)}</p>
          </article>
          <article class="stat-card compact">
            <p class="stat-label">疑似失活</p>
            <p class="stat-value compact">${formatNumber(overview.stale_items)}</p>
            <p class="stat-sub">近窗首现 ${formatNumber(overview.new_items)}</p>
          </article>
          <article class="stat-card compact">
            <p class="stat-label">最近任务</p>
            <p class="stat-value mini">${safeText(overview.latest_run ? overview.latest_run.display_name : "-")}</p>
            <p class="stat-sub">
              ${
                overview.latest_run
                  ? `${safeText(runStatusLabel(overview.latest_run.status))} / ${formatNumber(overview.latest_run.pages_succeeded)}/${formatNumber(overview.latest_run.pages_attempted)} 页`
                  : "暂无运行记录"
              }
            </p>
          </article>
          <article class="stat-card compact">
            <p class="stat-label">最近活动</p>
            <p class="stat-value mini">${safeText(formatRelative(overview.latest_seen))}</p>
            <p class="stat-sub">
              ${
                browserSession.last_authenticated_at
                  ? `登录更新 ${safeText(formatRelative(browserSession.last_authenticated_at))}`
                  : "等待登录态同步"
              }
            </p>
          </article>
        </section>

        <section class="ops-grid">
          <article class="panel compact-panel">
            <div class="panel-header tight">
              <div>
                <p class="eyebrow">业务概览</p>
                <h3>分类概况</h3>
              </div>
            </div>
            <div class="domain-card-grid compact">
              ${
                domainCards.length
                  ? domainCards
                      .map(
                        (card) => `
                          <div class="domain-card compact">
                            <div class="domain-card-head">
                              <p class="domain-name">${safeText(card.label)}</p>
                              <span class="signal-pill ${safeAttr(card.signal_class, "watch")}">${safeText(card.signal_label)}</span>
                            </div>
                            <p class="domain-metric compact">${formatNumber(card.active_count)}</p>
                            <div class="domain-meta compact">
                              <span>近窗 ${formatNumber(card.listing_count)}</span>
                              <span>失活 ${formatNumber(card.stale_count)}</span>
                              <span>新增 ${formatNumber(card.new_count)}</span>
                            </div>
                            <div class="domain-meta compact">
                              <span>${formatCurrency(card.avg_price)}</span>
                              <span>${safeText(formatRelative(card.last_seen_at))}</span>
                            </div>
                          </div>
                        `,
                      )
                      .join("")
                  : '<div class="domain-card compact"><p class="focus-empty">当前窗口内还没有可展示的业务概况。</p></div>'
              }
            </div>
          </article>

          <article class="panel compact-panel">
            <div class="panel-header tight">
              <div>
                <p class="eyebrow">执行流</p>
                <h3>最近运行</h3>
              </div>
            </div>
            <div class="run-list compact">
              ${
                recentRuns.length
                  ? recentRuns
                      .map(
                        (run) => `
                          <div class="run-row compact">
                            <div>
                              <p class="run-title">${safeText(run.display_name)}</p>
                              <p class="run-sub">${safeText(domainLabel(run.business_domain))} / ${safeText(run.task_key)}</p>
                            </div>
                            <div class="run-status ${safeAttr(run.status, "pending")}">${safeText(runStatusLabel(run.status))}</div>
                            <div class="run-pages">${formatNumber(run.pages_succeeded)}/${formatNumber(run.pages_attempted)} 页</div>
                            <div class="run-time">${safeText(formatRelative(run.started_at))}</div>
                          </div>
                        `,
                      )
                      .join("")
                  : '<p class="focus-empty">暂无运行记录。</p>'
              }
            </div>
          </article>
        </section>
      </div>
    `;
  };

  const renderDashboardCalibration = (data) => {
    const mobileMarketPanel = data.mobile_market_panel || {};
    const rows = safeArray(mobileMarketPanel.rows).slice(0, 4);
    const topModels = safeArray(data.top_models).slice(0, 8);

    return `
      <section class="terminal-reference-view">
        <div class="terminal-reference-head">
          <div>
            <p class="eyebrow">成交校准</p>
            <h3>挂牌与真实成交对照</h3>
            <p class="pricing-legend">用移动端抓到的真实成交锚点，校正收货线和出货预期。</p>
          </div>
          <div class="panel-pills">
            ${
              mobileMarketPanel.available
                ? `
                  <span class="status-pill">${formatNumber(mobileMarketPanel.captured_model_count)} 个模型</span>
                  <span class="status-pill accent">最近同步 ${safeText(formatRelative(mobileMarketPanel.latest_captured_at))}</span>
                `
                : '<span class="status-pill">等待首次同步</span>'
            }
          </div>
        </div>
        ${
          mobileMarketPanel.available
            ? `
              <div class="terminal-calibration-grid">
                ${rows
                  .map(
                    (row) => `
                      <article class="terminal-calibration-card">
                        <div class="terminal-watch-head">
                          <div>
                            <strong>${safeText(row.model_name)}</strong>
                            <span>${safeText(row.domain_label)}</span>
                          </div>
                          <span class="signal-pill ${safeAttr(row.calibration_class, "watch")}">${safeText(row.calibration_label)}</span>
                        </div>
                        <div class="terminal-calibration-stats">
                          <div>
                            <span>挂牌锚点</span>
                            <strong>${formatCurrency(row.listed_avg_price)}</strong>
                          </div>
                          <div>
                            <span>成交锚点</span>
                            <strong>${formatCurrency(row.sold_anchor_price)}</strong>
                          </div>
                          <div>
                            <span>成交线索</span>
                            <strong>${formatNumber(row.visible_record_count)} 条</strong>
                          </div>
                        </div>
                        <p class="focus-caption">${safeText(row.calibration_detail)}</p>
                      </article>
                    `,
                  )
                  .join("")}
              </div>
            `
            : '<p class="terminal-empty-inline">当前还没有移动端成交校准结果。等第一次同步完成后，这里会出现成交锚点。</p>'
        }
        <details class="terminal-detail-panel">
          <summary>展开榜单与校准细节</summary>
          <div class="terminal-detail-content">
            <div class="terminal-list-table">
              ${
                topModels.length
                  ? topModels
                      .map((model) => {
                        const calibration = model.mobile_calibration || null;
                        return `
                          <div class="terminal-list-row">
                            <div>
                              <strong>${safeText(model.model_name)}</strong>
                              <span>${safeText(model.domain_label)}</span>
                            </div>
                            <div>${formatNumber(model.listing_count)} 挂牌</div>
                            <div>${formatCurrency(model.avg_price)}</div>
                            <div>${calibration ? formatCurrency(calibration.sold_anchor_price) : "待同步"}</div>
                            <div>${safeText(formatRelative(model.last_seen_at))}</div>
                          </div>
                        `;
                      })
                      .join("")
                  : '<p class="terminal-empty-text">当前窗口内还没有可用的模型榜单。</p>'
              }
            </div>
          </div>
        </details>
      </section>
    `;
  };

  const renderDashboardFocus = (data) => {
    const cards = safeArray(data.market_focus_cards);
    const visibleCards = cards.filter((card) => !card.empty);
    const emptyCards = cards.filter((card) => card.empty);

    return `
      <section class="panel terminal-section-panel terminal-focus-panel">
        <div class="panel-header tight">
          <div>
            <p class="eyebrow">机会速记</p>
            <h3>先盯住这些方向</h3>
          </div>
        </div>
        <div class="terminal-focus-grid">
          ${
            visibleCards.length
              ? visibleCards
                  .map((card) => {
                    return `
                      <article class="terminal-focus-card ${safeAttr(card.tone, "watch")}">
                        <div class="terminal-watch-head compact">
                          <div>
                            <p class="eyebrow">${safeText(card.title)}</p>
                            <h3>${safeText(card.label)}</h3>
                          </div>
                          <span class="focus-state ${safeAttr(card.focus_state_class, "watch")}">${safeText(card.focus_state_label)}</span>
                        </div>
                        <div class="terminal-focus-price-row">
                          <span>安全 ${formatCurrency(card.safe_buy_price)}</span>
                          <span>正常 ${formatCurrency(card.normal_buy_price)}</span>
                          <span>市场 ${formatCurrency(card.market_mid_price)}</span>
                        </div>
                        <p class="focus-caption">${safeText(card.caption)}</p>
                        <div class="terminal-focus-profit compact">
                          <strong>${safeText(card.estimated_profit_label)}</strong>
                          <span>至少要过 ${formatCurrency(card.required_profit_amount)}</span>
                        </div>
                        ${safeArray(card.dimensions).length ? `<div class="tag-row">${renderTagItems(card.dimensions.slice(0, 5))}</div>` : ""}
                        <div class="terminal-reference-summary">
                          <span>${safeText((card.pricingAvailabilitySummary || {}).readinessSummary || "-")}</span>
                          <span>${safeText(((card.pricingAvailability || {}).pricingBlockReasonLabel) || "价格证据可用")}</span>
                        </div>
                      </article>
                    `;
                  })
                  .join("")
              : '<article class="terminal-focus-card empty"><p class="focus-empty">当前还没有明确的机会摘要，先看上面的实时在售更直接。</p></article>'
          }
        </div>
        ${
          emptyCards.length
            ? `
              <div class="terminal-focus-empty-row">
                ${emptyCards
                  .map(
                    (card) => `
                      <span class="status-pill">${safeText(card.title)}: ${safeText(card.empty_text)}</span>
                    `,
                  )
                  .join("")}
              </div>
            `
            : ""
        }
      </section>
    `;
  };

  const renderDashboardInsights = (data) => {
    const overview = data.overview || {};
    const trendCards = safeArray(data.domain_trend_cards).slice(0, 3);
    const domainCards = safeArray(data.domain_cards);
    const latestRun = overview.latest_run || {};

    return `
      <section class="terminal-reference-view">
        <div class="terminal-reference-head">
          <div>
            <p class="eyebrow">价格趋势</p>
            <h3>${safeText(overview.scope_label || "全部业务域")} 参考面</h3>
            <p class="pricing-legend">看完价格线和最新挂牌，再用这里确认趋势和市场节奏。</p>
          </div>
          <div class="panel-pills">
            <span class="status-pill">近 ${formatNumber(overview.window_days)} 天</span>
            <span class="status-pill">${formatPercent(overview.stale_ratio, 1)} 疑似失活</span>
          </div>
        </div>

        <div class="terminal-reference-summary">
          <span>最近刷新 ${safeText(formatRelative(overview.latest_seen))}</span>
          <span>活跃挂牌 ${formatNumber(overview.active_items)}</span>
          <span>卖家覆盖 ${formatNumber(overview.total_sellers)}</span>
          <span>${latestRun.status ? `${safeText(runStatusLabel(latestRun.status))} / ${safeText(latestRun.display_name || "-")}` : "暂无执行记录"}</span>
        </div>

        <div class="terminal-trend-grid">
          ${
            trendCards.length
              ? trendCards.map(renderTrendCard).join("")
              : '<article class="terminal-trend-card"><p class="focus-empty">当前窗口内还没有足够的历史快照来绘制趋势图。</p></article>'
          }
        </div>

        <details class="terminal-detail-panel">
          <summary>展开市场细节</summary>
          <div class="terminal-detail-content">
            <div class="terminal-domain-grid">
              ${
                domainCards.length
                  ? domainCards
                      .map(
                        (card) => `
                          <article class="terminal-domain-card">
                            <div class="terminal-watch-head">
                              <div>
                                <strong>${safeText(card.label)}</strong>
                                <span>${safeText(domainLabel(card.business_domain))}</span>
                              </div>
                              <span class="signal-pill ${safeAttr(card.signal_class, "watch")}">${safeText(card.signal_label)}</span>
                            </div>
                            <div class="terminal-domain-metrics">
                              <span>活跃 ${formatNumber(card.active_count)}</span>
                              <span>失活 ${formatNumber(card.stale_count)}</span>
                              <span>均价 ${formatCurrency(card.avg_price)}</span>
                              <span>最近 ${safeText(formatRelative(card.last_seen_at))}</span>
                            </div>
                          </article>
                        `,
                      )
                      .join("")
                  : '<p class="terminal-empty-text">当前窗口内还没有可用的业务域摘要。</p>'
              }
            </div>
          </div>
        </details>
      </section>
    `;
  };

  const renderDashboardItems = (data) => {
    const items = safeArray(data.items);
    const pricingSnapshot = latestPricingSnapshot;
    const classifyItem = (price) => {
      const numericPrice = Number(price);
      if (!pricingSnapshot || !Number.isFinite(numericPrice)) {
        return {
          label: "最新挂牌",
          className: "neutral",
          note: "等待价格线",
          deltaLabel: "暂无对照",
          deltaClass: "muted",
        };
      }
      if (numericPrice <= pricingSnapshot.safeBuyPrice) {
        return {
          label: "机会成立",
          className: "buy",
          note: `低于安全收货价 ${formatCurrency(pricingSnapshot.safeBuyPrice)}`,
          deltaLabel: `↓ ${formatDeltaCurrency(pricingSnapshot.safeBuyPrice - numericPrice)}`,
          deltaClass: "profit",
        };
      }
      if (numericPrice <= pricingSnapshot.normalBuyPrice) {
        return {
          label: "可以谈",
          className: "watch",
          note: `已进入正常收货线 ${formatCurrency(pricingSnapshot.normalBuyPrice)}`,
          deltaLabel: `↑ ${formatDeltaCurrency(numericPrice - pricingSnapshot.safeBuyPrice)}`,
          deltaClass: "watch",
        };
      }
      if (numericPrice <= pricingSnapshot.marketMidPrice) {
        return {
          label: "贴盘观察",
          className: "market",
          note: `接近市场中位价 ${formatCurrency(pricingSnapshot.marketMidPrice)}`,
          deltaLabel: "接近中位价",
          deltaClass: "market",
        };
      }
      return {
        label: "偏高",
        className: "high",
        note: `高于正常收货线 ${formatCurrency(pricingSnapshot.normalBuyPrice)}`,
        deltaLabel: `↑ ${formatDeltaCurrency(numericPrice - pricingSnapshot.normalBuyPrice)}`,
        deltaClass: "loss",
      };
    };
    const sectionMeta = {
      buy: { title: "低于安全收货价 · 立即行动", badge: "低价机会", max: 6 },
      watch: { title: "进入正常收货线 · 可以谈", badge: "可谈标的", max: 6 },
      market: { title: "贴近市场中位价 · 观察跟踪", badge: "观察标的", max: 4 },
      high: { title: "高于正常收货线 · 暂缓", badge: "偏高", max: 4 },
      neutral: { title: "最新挂牌", badge: "最新", max: 8 },
    };
    const groupedItems = {
      buy: [],
      watch: [],
      market: [],
      high: [],
      neutral: [],
    };

    items.forEach((item) => {
      const decision = classifyItem(item.price);
      groupedItems[decision.className] = groupedItems[decision.className] || [];
      groupedItems[decision.className].push({ item, decision });
    });

    const visibleKeys = pricingSnapshot
      ? ["buy", "watch", "market", "high"].filter((key) => safeArray(groupedItems[key]).length)
      : ["neutral"];

    return `
      <section class="panel terminal-section-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">最新在售</p>
            <h3>今天先看这些刚刷到的商品</h3>
            <p class="pricing-legend">${pricingSnapshot ? `当前对照 ${safeText(pricingSnapshot.label)} 的收货线来标记机会。` : "当前还没有稳定价格线，因此先按时间展示最新挂牌。"} </p>
          </div>
          <div class="panel-pills">
            <span class="status-pill accent">${formatNumber(groupedItems.buy.length)} 个低价机会</span>
            <span class="status-pill">${formatNumber(groupedItems.watch.length)} 个可谈标的</span>
          </div>
        </div>
        ${
          items.length
            ? `
              <div class="terminal-opportunity-feed">
                ${visibleKeys
                  .map((key) => {
                    const meta = sectionMeta[key];
                    const rows = safeArray(groupedItems[key]).slice(0, meta.max);
                    if (!rows.length) {
                      return "";
                    }
                    return `
                      <section class="terminal-opportunity-section ${safeAttr(key)}">
                        <div class="terminal-opportunity-section-head">
                          <h4>${safeText(meta.title)}</h4>
                          <span class="status-pill">${formatNumber(groupedItems[key].length)} 个${safeText(meta.badge)}</span>
                        </div>
                        <div class="terminal-listing-grid">
                          ${rows
                            .map(({ item, decision }) => `
                              <article class="terminal-listing-card ${safeAttr(decision.className)}">
                                <a href="/items/${safeAttr(item.item_id)}" class="terminal-listing-thumb-link">
                                  ${
                                    item.image_url
                                      ? `<img src="${safeAttr(item.image_url)}" alt="${safeAttr(item.title)}" class="terminal-listing-thumb" />`
                                      : '<div class="terminal-listing-thumb placeholder">暂无图片</div>'
                                  }
                                </a>
                                <div class="terminal-listing-body">
                                  <div class="terminal-listing-card-head">
                                    <span class="listing-decision-pill ${safeAttr(decision.className)}">${safeText(decision.label)}</span>
                                    <span class="terminal-card-time">${safeText(formatRelative(item.last_seen_at))}</span>
                                  </div>
                                  <div class="terminal-listing-price-row">
                                    <span class="price-display">${formatCurrency(item.price)}</span>
                                    <span class="listing-delta-pill ${safeAttr(decision.deltaClass)}">${safeText(decision.deltaLabel)}</span>
                                  </div>
                                  <div class="terminal-listing-spec">${safeText(item.display_name || item.domain_label)}</div>
                                  <a href="/items/${safeAttr(item.item_id)}" class="terminal-listing-title">${safeText(item.title)}</a>
                                  <div class="terminal-threshold-note">${safeText(decision.note)}</div>
                                  <div class="terminal-listing-meta">
                                    <span>${safeText(item.region || "未知地区")}</span>
                                    <span>${safeText(item.seller_name || item.seller_id || "未知卖家")}</span>
                                    <span>${safeText(item.heartbeat_label)}</span>
                                  </div>
                                  <div class="terminal-listing-actions">
                                    ${item.listing_url ? `<a href="${safeAttr(item.listing_url)}" target="_blank" rel="noreferrer">打开闲鱼</a>` : ""}
                                    <a href="/items/${safeAttr(item.item_id)}">查看详情</a>
                                  </div>
                                </div>
                              </article>
                            `)
                            .join("")}
                        </div>
                      </section>
                    `;
                  })
                  .join("")}
              </div>
            `
            : '<p class="pricing-legend">当前筛选条件下还没有可展示的最近挂牌。</p>'
        }
      </section>
    `;
  };

  const renderProgressHeader = (data) => `
    <div class="async-section-stack">
      <section class="hero-panel">
        <div class="hero-copy">
          <p class="eyebrow">回刷监控</p>
          <h2>LLM 二次清洗进度</h2>
          <p class="hero-text">
            这里聚合展示当前 items 的 review 进度、大类完成比例，以及最近的 worker 日志事件。页面只读数据库和 reports 日志，不会触发任何写入。
          </p>
        </div>
        <div class="hero-meta">
          <span class="refresh-pill" data-refresh-badge data-refresh-seconds="60">自动刷新 60秒</span>
          <span class="status-pill">${safeText((data.selected_category_code || data.selected_domain) ? domainLabel(data.selected_category_code || data.selected_domain) : "全部大类")}</span>
          <span class="status-pill">${safeText(data.current_ai_provider)}</span>
          <span class="status-pill accent">${safeText(data.current_ai_model)}</span>
          <span class="status-pill">最近完成 ${safeText(formatRelative((data.review_overview || {}).last_reviewed_at))}</span>
        </div>
      </section>

      <section class="filters-panel">
        <div class="filter-panel-copy">
          <p class="eyebrow">筛选</p>
          <p class="filter-panel-text">按大类查看回刷队列、完成率和最近 worker 状态。</p>
        </div>
        <form method="get" class="filters-form" data-filter-form autocomplete="off">
          <label class="filter-field wide-field">
            <span>大类</span>
            <select name="category_code" data-category-filter>
              <option value="">全部</option>
              ${renderOptions(data.available_categories || data.available_domains, data.selected_category_code || data.selected_domain, (domain) => domain ?? "", (domain) => domainLabel(domain))}
            </select>
          </label>
          <div class="filter-actions">
            <button type="submit" class="primary-button">应用筛选</button>
            <a href="/progress" class="secondary-button">清空筛选</a>
          </div>
        </form>
      </section>
    </div>
  `;

  const renderProgressOverview = (data) => {
    const overview = data.review_overview || {};
    const rows = safeArray(data.review_progress_rows);

    return `
      <div class="async-section-stack">
        <section class="stats-grid">
          <article class="stat-card">
            <p class="stat-label">总体完成率</p>
            <p class="stat-value">${formatPercent(overview.completion_percent, 1)}</p>
            <p class="stat-sub">已完成 ${formatNumber(overview.reviewed_total)} / ${formatNumber(overview.review_target_total)}</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">待回刷</p>
            <p class="stat-value">${formatNumber(overview.pending_review_count)}</p>
            <p class="stat-sub">仍在 active 队列里等待领取</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">处理中</p>
            <p class="stat-value">${formatNumber(overview.in_progress_count)}</p>
            <p class="stat-sub">当前被 worker claim 的商品</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">待审队列</p>
            <p class="stat-value">${formatNumber(overview.pending_audit_count)}</p>
            <p class="stat-sub">LLM 有分歧，暂不自动落库</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">已判无效</p>
            <p class="stat-value">${formatNumber(overview.reviewed_invalid_count)}</p>
            <p class="stat-sub">包含广告、配件、回收、抵押等</p>
          </article>
        </section>

        <section class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">业务域进度</p>
              <h3>Domain Progress</h3>
            </div>
            <div class="panel-pills">
              <span class="status-pill">${formatNumber(overview.domain_count)} 个业务域</span>
              <span class="status-pill accent">${formatNumber(overview.reviewed_valid_count)} valid</span>
            </div>
          </div>
          <div class="domain-card-grid">
            ${
              rows.length
                ? rows
                    .map((row) => {
                      const completionClass = row.completion_percent >= 80 ? "high" : row.completion_percent >= 40 ? "medium" : "watch";
                      return `
                        <article class="domain-card progress-card">
                          <div class="focus-card-head">
                            <div>
                              <p class="eyebrow">${safeText(row.business_domain)}</p>
                              <h3 class="domain-name">${safeText(row.label)}</h3>
                            </div>
                            <span class="reliability-pill ${completionClass}">${formatPercent(row.completion_percent, 1)}</span>
                          </div>
                          <div class="progress-meter" aria-label="completion">
                            <span class="progress-fill" style="width: ${safeAttr(row.completion_percent)}%;"></span>
                          </div>
                          <div class="progress-metrics">
                            <div>
                              <p class="stat-label">待回刷</p>
                              <p class="stat-value compact">${formatNumber(row.pending_review_count)}</p>
                            </div>
                            <div>
                              <p class="stat-label">处理中</p>
                              <p class="stat-value compact">${formatNumber(row.in_progress_count)}</p>
                            </div>
                            <div>
                              <p class="stat-label">已通过</p>
                              <p class="stat-value compact">${formatNumber(row.reviewed_valid_count)}</p>
                            </div>
                            <div>
                              <p class="stat-label">待审</p>
                              <p class="stat-value compact">${formatNumber(row.pending_audit_count)}</p>
                            </div>
                            <div>
                              <p class="stat-label">已剔除</p>
                              <p class="stat-value compact">${formatNumber(row.reviewed_invalid_count)}</p>
                            </div>
                          </div>
                          <p class="domain-meta compact">
                            <span>active ${formatNumber(row.active_items)}</span>
                            <span>total ${formatNumber(row.total_items)}</span>
                            <span>最近 review ${safeText(formatRelative(row.last_reviewed_at))}</span>
                          </p>
                        </article>
                      `;
                    })
                    .join("")
                : '<article class="domain-card"><p class="focus-empty">当前条件下没有可展示的回刷进度。</p></article>'
            }
          </div>
        </section>
      </div>
    `;
  };

  const renderProgressUsageWorkers = (data) => {
    const usageSummary = data.usage_summary || {};
    const workerRuns = safeArray(data.worker_runs);
    const usageRows = safeArray(usageSummary.recent_usage_runs);

    return `
      <div class="async-section-stack">
        <section class="stats-grid">
          <article class="stat-card">
            <p class="stat-label">累计 Tokens</p>
            <p class="stat-value">${formatNumber(usageSummary.total_tokens)}</p>
            <p class="stat-sub">输入 ${formatNumber(usageSummary.input_tokens)} / 输出 ${formatNumber(usageSummary.output_tokens)}</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">垃圾命中</p>
            <p class="stat-value">${formatNumber(usageSummary.garbage_hit_count)}</p>
            <p class="stat-sub">规则预筛或 LLM 命中的垃圾样本</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">低置信过滤</p>
            <p class="stat-value">${formatNumber(usageSummary.low_confidence_filtered_count)}</p>
            <p class="stat-sub">模型返回但低于 90 分的样本</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">高置信保留</p>
            <p class="stat-value">${formatNumber(usageSummary.high_confidence_kept_count)}</p>
            <p class="stat-sub">进入结果文件的高置信样本</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">二次复审</p>
            <p class="stat-value">${formatNumber(usageSummary.second_pass_requested_count)}</p>
            <p class="stat-sub">当前链路触发 second-pass 的样本</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">二次救回</p>
            <p class="stat-value">${formatNumber(usageSummary.second_pass_rescued_count)}</p>
            <p class="stat-sub">二次清洗后转成高置信的样本</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">二次未解</p>
            <p class="stat-value">${formatNumber(usageSummary.second_pass_unresolved_count)}</p>
            <p class="stat-sub">二次清洗后仍低置信的样本</p>
          </article>
        </section>

        <section class="secondary-grid">
          <section class="panel">
            <div class="panel-header tight">
              <div>
                <p class="eyebrow">Token Usage</p>
                <h3>模型消耗</h3>
              </div>
              <div class="panel-pills">
                <span class="status-pill">${formatNumber(usageSummary.file_count)} 个批次</span>
                <span class="status-pill accent">${formatNumber(usageSummary.request_count)} 次请求</span>
              </div>
            </div>
            <div class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>业务域</th>
                    <th>管线</th>
                    <th>文件</th>
                    <th>请求</th>
                    <th>样本</th>
                    <th>输入 Tokens</th>
                    <th>输出 Tokens</th>
                    <th>总 Tokens</th>
                    <th>垃圾</th>
                    <th>低置信</th>
                    <th>高置信</th>
                    <th>二次复审</th>
                    <th>二次救回</th>
                    <th>二次未解</th>
                    <th>缓存</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  ${
                    usageRows.length
                      ? usageRows
                          .map(
                            (row) => `
                              <tr>
                                <td>${safeText(row.domain_label)}</td>
                                <td>${safeText(row.pipeline)}</td>
                                <td><strong>${safeText(row.file_name)}</strong></td>
                                <td>${formatNumber(row.request_count)}</td>
                                <td>${formatNumber(row.requested_item_count)}</td>
                                <td>${formatNumber(row.input_tokens)}</td>
                                <td>${formatNumber(row.output_tokens)}</td>
                                <td>${formatNumber(row.total_tokens)}</td>
                                <td>${formatNumber(row.garbage_hit_count)}</td>
                                <td>${formatNumber(row.low_confidence_filtered_count)}</td>
                                <td>${formatNumber(row.high_confidence_kept_count)}</td>
                                <td>${formatNumber(row.second_pass_requested_count)}</td>
                                <td>${formatNumber(row.second_pass_rescued_count)}</td>
                                <td>${formatNumber(row.second_pass_unresolved_count)}</td>
                                <td>${formatNumber(row.cached_tokens)}</td>
                                <td>${safeText(formatRelative(row.generated_at))}</td>
                              </tr>
                            `,
                          )
                          .join("")
                      : '<tr><td colspan="16" class="empty-cell">还没有 usage 统计文件。</td></tr>'
                  }
                </tbody>
              </table>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header tight">
              <div>
                <p class="eyebrow">Worker</p>
                <h3>最近运行</h3>
              </div>
            </div>
            <div class="worker-card-grid">
              ${
                workerRuns.length
                  ? workerRuns
                      .map((worker) => `
                        <article class="domain-card compact">
                          <div class="focus-card-head">
                            <div>
                              <p class="eyebrow">${safeText(worker.business_domain)}</p>
                              <h3 class="domain-name">${safeText(worker.domain_label)}</h3>
                            </div>
                            <span class="status-pill">${safeText(worker.pipeline || "Result")}</span>
                            <span class="focus-state ${worker.is_recent ? "actionable" : "watch"}">${worker.is_recent ? "活跃" : "较旧"}</span>
                          </div>
                          ${
                            worker.run_type === "result_file"
                              ? `
                                <p class="domain-meta compact">
                                  <span>结果文件</span>
                                  <span>${formatNumber(worker.batch_size)} 条</span>
                                  <span>${safeText(formatRelative(worker.updated_at))}</span>
                                </p>
                                <p class="subtle-line">${safeText(worker.ai_provider)} / ${safeText(worker.ai_model)}</p>
                              `
                              : `
                                <p class="domain-meta compact">
                                  <span>${formatNumber(worker.worker_count)} 并发</span>
                                  <span>batch ${formatNumber(worker.batch_size)}</span>
                                  <span>pending ${formatNumber(worker.pending_reviews)}</span>
                                  <span>${safeText(formatRelative(worker.updated_at))}</span>
                                </p>
                                <p class="subtle-line">${safeText(worker.worker_label)} / ${safeText(worker.ai_provider)} / ${safeText(worker.ai_model)}</p>
                              `
                          }
                          <div class="worker-event-list">
                            ${safeArray(worker.recent_events)
                              .map(
                                (event) => `
                                  <div class="worker-event-row ${safeAttr(event.status_class, "watch")}">
                                    <strong>${safeText(event.title)}</strong>
                                    <span>${safeText(event.summary)}</span>
                                  </div>
                                `,
                              )
                              .join("")}
                          </div>
                          <p class="subtle-line">${safeText(worker.log_name)}</p>
                        </article>
                      `)
                      .join("")
                  : '<article class="domain-card compact"><p class="focus-empty">还没有发现 worker 日志。</p></article>'
              }
            </div>
          </section>
        </section>
      </div>
    `;
  };

  const renderProgressAudits = (data) => {
    const auditQueueRows = safeArray(data.audit_queue_rows);
    const invalidReasonRows = safeArray(data.invalid_reason_rows);

    return `
      <section class="secondary-grid">
        <section class="panel">
          <div class="panel-header tight">
            <div>
              <p class="eyebrow">Audit Queue</p>
              <h3>待审分歧</h3>
            </div>
          </div>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>业务域</th>
                  <th>商品</th>
                  <th>原因</th>
                  <th>模型结论</th>
                  <th>置信度</th>
                  <th>字段变更</th>
                  <th>时间</th>
                </tr>
              </thead>
              <tbody>
                ${
                  auditQueueRows.length
                    ? auditQueueRows
                        .map(
                          (row) => `
                            <tr>
                              <td>${safeText(row.domain_label)}</td>
                              <td><strong>${safeText(row.title)}</strong><br><span class="subtle-line">${safeText(row.item_id)}</span></td>
                              <td>${safeText(row.audit_reason)}</td>
                              <td>${safeText(row.decision_status)}${row.invalid_reason ? ` / ${safeText(row.invalid_reason)}` : ""}</td>
                              <td>${isBlank(row.confidence) ? "-" : formatPercent(row.confidence, 1)}</td>
                              <td>${formatNumber(row.field_change_count)}</td>
                              <td>${safeText(formatRelative(row.reviewed_at))}</td>
                            </tr>
                          `,
                        )
                        .join("")
                    : '<tr><td colspan="7" class="empty-cell">当前没有待审分歧。</td></tr>'
                }
              </tbody>
            </table>
          </div>
        </section>

        <section class="panel">
          <div class="panel-header tight">
            <div>
              <p class="eyebrow">Invalid Reasons</p>
              <h3>最近剔除原因</h3>
            </div>
          </div>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>业务域</th>
                  <th>原因</th>
                  <th>数量</th>
                  <th>最近时间</th>
                </tr>
              </thead>
              <tbody>
                ${
                  invalidReasonRows.length
                    ? invalidReasonRows
                        .map(
                          (row) => `
                            <tr>
                              <td>${safeText(row.domain_label)}</td>
                              <td><strong>${safeText(row.reason)}</strong></td>
                              <td>${formatNumber(row.item_count)}</td>
                              <td>${safeText(formatRelative(row.last_reviewed_at))}</td>
                            </tr>
                          `,
                        )
                        .join("")
                    : '<tr><td colspan="4" class="empty-cell">还没有 invalid reason 统计。</td></tr>'
                }
              </tbody>
            </table>
          </div>
        </section>
      </section>
    `;
  };

  const SECTION_RENDERERS = {
    "dashboard-hero": renderDashboardHero,
    "dashboard-filters": renderDashboardFilters,
    "dashboard-selection-bar": renderDashboardSelectionBar,
    "dashboard-focus": renderDashboardFocus,
    "dashboard-insights": renderDashboardInsights,
    "dashboard-pricing": renderDashboardPricing,
    "dashboard-ops": renderDashboardOps,
    "dashboard-llm-traces": renderDashboardLlmTraces,
    "runtime-controls-page": renderRuntimeControlsPage,
    "dashboard-calibration": renderDashboardCalibration,
    "dashboard-items": renderDashboardItems,
    "progress-header": renderProgressHeader,
    "progress-overview": renderProgressOverview,
    "progress-usage-workers": renderProgressUsageWorkers,
    "progress-audits": renderProgressAudits,
  };

  const buildSectionUrl = (baseUrl) => {
    const currentQuery = window.location.search;
    if (!currentQuery) {
      return baseUrl;
    }
    return `${baseUrl}${baseUrl.includes("?") ? "&" : "?"}${currentQuery.slice(1)}`;
  };

  const getActiveDashboardTab = () => {
    const params = new URLSearchParams(window.location.search);
    const requestedTab = params.get("tab");
    if (requestedTab && DASHBOARD_TAB_KEYS.has(requestedTab)) {
      return requestedTab;
    }
    const storedTab = window.sessionStorage.getItem(DASHBOARD_TAB_STORAGE_KEY);
    if (storedTab && DASHBOARD_TAB_KEYS.has(storedTab)) {
      return storedTab;
    }
    return "market";
  };

  const getRefreshableSections = () =>
    Array.from(document.querySelectorAll("[data-async-section]")).filter((container) => {
      const hiddenPanel = container.closest("[data-dashboard-tab-panel][hidden]");
      return !hiddenPanel;
    });

  const renderError = (container, message) => {
    container.innerHTML = `
      <article class="panel async-error-panel">
        <p class="eyebrow">加载失败</p>
        <h3>分块接口暂时不可用</h3>
        <p class="async-error-text">${safeText(message)}</p>
        <button type="button" class="secondary-button" data-async-retry>重试</button>
      </article>
    `;
  };

  const getDeclaredSkeletonHeight = (container) => {
    const rawValue = Number(container.dataset.asyncSkeletonHeight || 0);
    return Number.isFinite(rawValue) && rawValue > 0 ? rawValue : 0;
  };

  const setRuntimeFeedback = (card, message, isError = false) => {
    if (!(card instanceof HTMLElement)) {
      return;
    }
    const feedback = card.querySelector("[data-runtime-feedback]");
    if (!(feedback instanceof HTMLElement)) {
      return;
    }
    feedback.textContent = message;
    feedback.dataset.error = isError ? "true" : "false";
  };

  const setRuntimeButtonsDisabled = (card, disabled) => {
    if (!(card instanceof HTMLElement)) {
      return;
    }
    Array.from(card.querySelectorAll("[data-runtime-action]")).forEach((button) => {
      if (button instanceof HTMLButtonElement) {
        button.disabled = disabled;
      }
    });
  };

  const reserveSectionHeight = (container) => {
    const declaredSkeletonHeight = getDeclaredSkeletonHeight(container);
    const currentHeight = Math.ceil(container.getBoundingClientRect().height);
    const nextHeight =
      container.dataset.asyncLoaded === "true" && currentHeight > 0
        ? currentHeight
        : declaredSkeletonHeight;
    if (nextHeight > 0) {
      container.style.minHeight = `${nextHeight}px`;
    }
  };

  const releaseSectionHeight = (container) => {
    const measuredHeight = Math.ceil(container.scrollHeight);
    if (measuredHeight > 0) {
      container.style.minHeight = `${measuredHeight}px`;
    }
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        container.style.removeProperty("min-height");
      });
    });
  };

  const loadSection = async (container) => {
    const endpoint = container.dataset.asyncSection;
    const rendererName = container.dataset.asyncRenderer;
    const renderer = rendererName ? SECTION_RENDERERS[rendererName] : null;
    if (!endpoint || container.dataset.asyncLoading === "true") {
      return;
    }
    if (!renderer) {
      renderError(container, `未找到渲染器: ${rendererName || "unknown"}`);
      return;
    }

    container.dataset.asyncLoading = "true";
    reserveSectionHeight(container);
    try {
      const response = await fetch(buildSectionUrl(endpoint), {
        headers: {
          "X-Requested-With": "goofish-dashboard-shell",
          Accept: "application/json",
        },
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      container.innerHTML = renderer(payload || {});
      releaseSectionHeight(container);
      container.dataset.asyncLoaded = "true";
      delete container.dataset.asyncLoading;
    } catch (error) {
      delete container.dataset.asyncLoading;
      renderError(container, error instanceof Error ? error.message : "Unknown error");
    }
  };

  const refreshSections = async () => {
    const sections = getRefreshableSections();
    const highPrioritySections = sections.filter((container) => container.dataset.asyncPriority === "high");
    const normalSections = sections.filter((container) => container.dataset.asyncPriority !== "high");

    if (highPrioritySections.length > 0) {
      await Promise.all(highPrioritySections.map((container) => loadSection(container)));
    }
    if (normalSections.length > 0) {
      await Promise.all(normalSections.map((container) => loadSection(container)));
    }
  };

  const setupAutoRefresh = () => {
    const refreshBadge = () => document.querySelector("[data-refresh-badge]");
    const refreshSeconds = Number(refreshBadge()?.dataset.refreshSeconds || 0);
    if (!refreshSeconds || refreshSeconds <= 0) {
      return;
    }

    let remaining = refreshSeconds;
    const updateBadge = () => {
      const badge = refreshBadge();
      if (badge) {
        badge.textContent = `自动刷新 ${remaining}秒`;
      }
    };

    updateBadge();
    window.setInterval(async () => {
      remaining -= 1;
      if (remaining <= 0) {
        remaining = refreshSeconds;
        await refreshSections();
      }
      updateBadge();
    }, 1000);
  };

  const setupAsyncSections = () => {
    const sections = Array.from(document.querySelectorAll("[data-async-section]"));
    if (sections.length === 0) {
      return;
    }

    sections.forEach((container) => {
      reserveSectionHeight(container);
      container.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }
        if (target.closest("[data-async-retry]")) {
          void loadSection(container);
        }
      });
    });

    void refreshSections();
    setupAutoRefresh();
  };

  const setupDashboardTabs = () => {
    const shell = document.querySelector("[data-dashboard-tabs]");
    if (!(shell instanceof HTMLElement)) {
      return;
    }

    const buttons = Array.from(shell.querySelectorAll("[data-dashboard-tab]")).filter(
      (button) => button instanceof HTMLButtonElement,
    );
    const panels = Array.from(shell.querySelectorAll("[data-dashboard-tab-panel]")).filter(
      (panel) => panel instanceof HTMLElement,
    );
    if (!buttons.length || !panels.length) {
      return;
    }

    const tabInputs = Array.from(document.querySelectorAll("[data-dashboard-tab-input]")).filter(
      (input) => input instanceof HTMLInputElement,
    );

    const syncUrl = (tab) => {
      const url = new URL(window.location.href);
      url.searchParams.set("tab", tab);
      window.history.replaceState({}, "", `${url.pathname}?${url.searchParams.toString()}`);
    };

    const activateTab = (tab, options = {}) => {
      const nextTab = DASHBOARD_TAB_KEYS.has(tab) ? tab : "market";
      const { syncHistory = true, loadVisible = true } = options;

      buttons.forEach((button) => {
        const isActive = button.dataset.dashboardTab === nextTab;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-selected", isActive ? "true" : "false");
      });

      panels.forEach((panel) => {
        panel.hidden = panel.dataset.dashboardTabPanel !== nextTab;
      });

      tabInputs.forEach((input) => {
        input.value = nextTab;
      });

      window.sessionStorage.setItem(DASHBOARD_TAB_STORAGE_KEY, nextTab);
      if (syncHistory) {
        syncUrl(nextTab);
      }
      if (loadVisible) {
        void refreshSections();
      }
    };

    const initialTab = getActiveDashboardTab();
    activateTab(initialTab, { syncHistory: false, loadVisible: false });

    shell.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const button = target.closest("[data-dashboard-tab]");
      if (!(button instanceof HTMLButtonElement)) {
        return;
      }
      const tab = button.dataset.dashboardTab || "market";
      if (!DASHBOARD_TAB_KEYS.has(tab)) {
        return;
      }
      event.preventDefault();
      activateTab(tab);
    });
  };

  const setupHomeReferenceDeck = () => {
    const deck = document.querySelector("[data-home-reference-deck]");
    if (!(deck instanceof HTMLElement)) {
      return;
    }

    const tabs = Array.from(deck.querySelectorAll("[data-home-reference-tab]")).filter(
      (button) => button instanceof HTMLButtonElement,
    );
    const panels = Array.from(deck.querySelectorAll("[data-home-reference-panel]")).filter(
      (panel) => panel instanceof HTMLElement,
    );
    const toggle = deck.querySelector("[data-home-reference-toggle]");
    const body = deck.querySelector(".dashboard-reference-body");

    if (!tabs.length || !panels.length || !(body instanceof HTMLElement)) {
      return;
    }

    const activateTab = (tabName) => {
      const nextTab = tabs.some((button) => button.dataset.homeReferenceTab === tabName) ? tabName : "trend";
      tabs.forEach((button) => {
        const active = button.dataset.homeReferenceTab === nextTab;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
      });
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.homeReferencePanel !== nextTab;
      });
    };

    const setCollapsed = (collapsed) => {
      deck.dataset.collapsed = collapsed ? "true" : "false";
      body.hidden = collapsed;
      if (toggle instanceof HTMLButtonElement) {
        toggle.textContent = collapsed ? "展开" : "收起";
        toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      }
    };

    const initialTab = tabs.find((button) => button.classList.contains("is-active"))?.dataset.homeReferenceTab || "trend";
    activateTab(initialTab);
    setCollapsed(false);

    deck.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }

      const tabButton = target.closest("[data-home-reference-tab]");
      if (tabButton instanceof HTMLButtonElement) {
        event.preventDefault();
        activateTab(tabButton.dataset.homeReferenceTab || "trend");
        return;
      }

      const toggleButton = target.closest("[data-home-reference-toggle]");
      if (toggleButton instanceof HTMLButtonElement) {
        event.preventDefault();
        setCollapsed(deck.dataset.collapsed !== "true");
      }
    });
  };

  const setupTrendModal = () => {
    const trendModal = document.querySelector("[data-trend-modal]");
    const trendModalContent = trendModal?.querySelector("[data-trend-modal-content]");
    const trendModalTitle = trendModal?.querySelector("#trend-modal-title");
    const trendModalCloseButton = trendModal?.querySelector(".trend-modal-close");
    if (!trendModal || !trendModalContent) {
      return;
    }

    let previousBodyOverflow = "";
    let previousActiveElement = null;

    const closeTrendModal = () => {
      if (trendModal.hidden) {
        return;
      }
      trendModal.hidden = true;
      trendModalContent.replaceChildren();
      document.body.style.overflow = previousBodyOverflow;
      if (previousActiveElement instanceof HTMLElement) {
        previousActiveElement.focus();
      }
    };

    const openTrendModal = (trigger) => {
      const trendCard = trigger.closest(".trend-card");
      if (!trendCard) {
        return;
      }

      previousActiveElement = document.activeElement;
      previousBodyOverflow = document.body.style.overflow;

      const clonedCard = trendCard.cloneNode(true);
      const clonedTrigger = clonedCard.querySelector("[data-trend-modal-trigger]");
      if (clonedTrigger) {
        const clonedChart = clonedTrigger.querySelector(".trend-chart");
        if (clonedChart) {
          clonedTrigger.replaceWith(clonedChart);
        } else {
          clonedTrigger.remove();
        }
      }

      const nextTitle = trendCard.querySelector(".trend-header h3")?.textContent?.trim() || "价格带波动";
      if (trendModalTitle) {
        trendModalTitle.textContent = nextTitle;
      }
      trendModalContent.replaceChildren(clonedCard);
      trendModal.hidden = false;
      document.body.style.overflow = "hidden";
      trendModalCloseButton?.focus();
    };

    document.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const trigger = target.closest("[data-trend-modal-trigger]");
      if (trigger instanceof HTMLElement) {
        openTrendModal(trigger);
        return;
      }
      if (target.closest("[data-trend-modal-close]")) {
        closeTrendModal();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeTrendModal();
      }
    });
  };

  const setupRuntimeControls = () => {
    document.addEventListener("click", async (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const button = target.closest("[data-runtime-action]");
      if (!(button instanceof HTMLButtonElement)) {
        return;
      }

      const actionTarget = button.dataset.runtimeTarget;
      const actionName = button.dataset.runtimeActionName;
      if (!actionTarget || !actionName) {
        return;
      }

      event.preventDefault();
      const card = button.closest("[data-runtime-card]");
      setRuntimeButtonsDisabled(card, true);
      setRuntimeFeedback(card, "正在执行，稍后刷新状态...");

      try {
        const response = await fetch("/api/dashboard/runtime/actions", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({
            target: actionTarget,
            action: actionName,
          }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          const errorMessage = payload?.detail || `HTTP ${response.status}`;
          throw new Error(errorMessage);
        }

        const container = button.closest("[data-async-section]");
        if (container instanceof HTMLElement) {
          await loadSection(container);
        } else {
          await refreshSections();
        }
      } catch (error) {
        setRuntimeButtonsDisabled(card, false);
        setRuntimeFeedback(
          card,
          `执行失败: ${error instanceof Error ? error.message : "未知错误"}`,
          true,
        );
      }
    });
  };

  const setupLlmTracePanel = () => {
    document.addEventListener("click", async (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const button = target.closest("[data-llm-trace-select]");
      if (!(button instanceof HTMLButtonElement)) {
        return;
      }

      event.preventDefault();
      const traceKey = button.dataset.traceKey;
      const panel = button.closest("[data-llm-trace-panel]");
      const detail = panel?.querySelector("[data-llm-trace-detail]");
      if (!traceKey || !(panel instanceof HTMLElement) || !(detail instanceof HTMLElement)) {
        return;
      }

      Array.from(panel.querySelectorAll("[data-llm-trace-select]")).forEach((node) => {
        if (node instanceof HTMLElement) {
          node.classList.toggle("active", node === button);
        }
      });
      detail.innerHTML = `
        <article class="llm-trace-detail-card">
          <p class="focus-empty">正在载入 trace 详情...</p>
        </article>
      `;

      try {
        const response = await fetch(`/api/dashboard/llm-traces/${encodeURIComponent(traceKey)}`, {
          headers: {
            "X-Requested-With": "goofish-dashboard-shell",
            Accept: "application/json",
          },
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        detail.innerHTML = renderLlmTraceDetail(payload.trace || null);
      } catch (error) {
        detail.innerHTML = `
          <article class="llm-trace-detail-card">
            <div class="llm-trace-error">加载失败: ${safeText(error instanceof Error ? error.message : "未知错误")}</div>
          </article>
        `;
      }
    });
  };

  const setupFilterLinkage = () => {
    document.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLSelectElement)) {
        return;
      }
      if (target.name !== "category_code") {
        return;
      }
      const form = target.closest("form[data-filter-form]");
      if (!(form instanceof HTMLFormElement)) {
        return;
      }

      const dependentNames = ["product_label", "spec_label"];
      dependentNames.forEach((name) => {
        const field = form.elements.namedItem(name);
        if (field instanceof HTMLSelectElement || field instanceof HTMLInputElement) {
          field.value = "";
        }
      });
      form.requestSubmit();
    });
  };

  document.addEventListener("DOMContentLoaded", () => {
    setupDashboardTabs();
    setupHomeReferenceDeck();
    setupAsyncSections();
    setupRuntimeControls();
    setupLlmTracePanel();
    setupTrendModal();
    setupFilterLinkage();
  });
})();
