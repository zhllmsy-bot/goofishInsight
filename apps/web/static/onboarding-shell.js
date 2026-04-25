(() => {
  const root = document.querySelector("[data-xianyu-onboarding-page]");
  if (!(root instanceof HTMLElement)) {
    return;
  }

  const controlsForm = root.querySelector("[data-onboarding-controls]");
  const feedbackNode = root.querySelector("[data-onboarding-feedback]");
  const coverageGrid = root.querySelector("[data-onboarding-coverage-grid]");
  const queueList = root.querySelector("[data-onboarding-queue-list]");
  const detailPanel = root.querySelector("[data-onboarding-detail]");
  const draftPanel = root.querySelector("[data-onboarding-draft]");
  const totalBadge = root.querySelector("[data-onboarding-queue-total]");

  let queueItems = [];
  let selectedQueueId = null;
  let currentDraft = null;
  let lastPersistResult = null;

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

  const formatPercent = (value) => {
    if (isBlank(value)) {
      return "-";
    }
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return safeText(value);
    }
    return `${(number * 100).toFixed(1)}%`;
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

  const toJsonPreview = (value, fallback = {}) =>
    escapeHtml(JSON.stringify(value ?? fallback, null, 2));

  const displaySampleValue = (value) => {
    if (value === null || value === undefined) {
      return "-";
    }
    if (typeof value === "object") {
      return JSON.stringify(value);
    }
    return String(value);
  };

  const ATTRIBUTE_CODE_RULES = [
    { pattern: /(品牌|brand)/i, code: "brand_name" },
    { pattern: /(产品线|系列|lineage)/i, code: "product_line" },
    { pattern: /(型号|model)/i, code: "model_name" },
    { pattern: /(代际|代数|generation)/i, code: "generation" },
    { pattern: /(芯片|处理器系列|chip)/i, code: "chip_family" },
    { pattern: /(cpu)/i, code: "cpu_model" },
    { pattern: /(gpu型号|显卡型号|gpu model)/i, code: "gpu_model" },
    { pattern: /(gpu厂商|显卡厂商|gpu vendor)/i, code: "gpu_vendor" },
    { pattern: /(显存|vram)/i, code: "vram_gb" },
    { pattern: /(内存|memory|ram)/i, code: "memory_gb" },
    { pattern: /(存储|硬盘|容量|storage|ssd)/i, code: "storage_gb" },
    { pattern: /(屏幕|尺寸|screen)/i, code: "screen_size_in" },
    { pattern: /(表径|case size)/i, code: "case_size_mm" },
    { pattern: /(显示|屏幕类型|display)/i, code: "display_type" },
    { pattern: /(光圈|aperture)/i, code: "max_aperture" },
    { pattern: /(焦段|焦距|focal)/i, code: "focal_length_range" },
    { pattern: /(卡口|mount)/i, code: "mount_system" },
    { pattern: /(镜头系列|lens series)/i, code: "lens_series" },
    { pattern: /(机身系列|camera series)/i, code: "camera_series" },
    { pattern: /(传感器|sensor)/i, code: "sensor_format" },
    { pattern: /(手机系列|phone series)/i, code: "phone_series" },
    { pattern: /(颜色|color|colour)/i, code: "device_color" },
    { pattern: /(乐器类型|乐器品类|instrument)/i, code: "instrument_family" },
    { pattern: /(solar|太阳能)/i, code: "is_solar" },
    { pattern: /(edition|版本标签|标签)/i, code: "edition_tags" },
  ];

  const slugifyCodeCandidate = (value) =>
    String(value || "")
      .trim()
      .toLowerCase()
      .replaceAll(/[^a-z0-9]+/g, "_")
      .replaceAll(/^_+|_+$/g, "")
      .slice(0, 48);

  const suggestAttributeCode = (name, fallback = "custom_attr") => {
    const label = String(name || "").trim();
    if (!label) {
      return fallback;
    }
    const matchedRule = ATTRIBUTE_CODE_RULES.find((entry) => entry.pattern.test(label));
    if (matchedRule) {
      return matchedRule.code;
    }
    const slug = slugifyCodeCandidate(label);
    if (slug) {
      return slug;
    }
    return fallback;
  };

  const suggestOptionCode = (name, index) => {
    const label = String(name || "").trim();
    if (!label) {
      return `option_${index}`;
    }
    const colorMap = [
      { pattern: /(黑色|曜黑|black)/i, code: "black" },
      { pattern: /(白色|white)/i, code: "white" },
      { pattern: /(银色|silver)/i, code: "silver" },
      { pattern: /(金色|gold)/i, code: "gold" },
      { pattern: /(蓝色|blue)/i, code: "blue" },
      { pattern: /(绿色|green)/i, code: "green" },
      { pattern: /(紫色|purple)/i, code: "purple" },
      { pattern: /(粉色|pink)/i, code: "pink" },
      { pattern: /(红色|red)/i, code: "red" },
      { pattern: /(全画幅|full frame)/i, code: "full_frame" },
      { pattern: /(aps-c|半画幅|apsc)/i, code: "aps_c" },
    ];
    const matchedRule = colorMap.find((entry) => entry.pattern.test(label));
    if (matchedRule) {
      return matchedRule.code;
    }
    const slug = slugifyCodeCandidate(label);
    if (slug) {
      return slug;
    }
    return `option_${index}`;
  };

  const formatOptionLines = (options) =>
    safeArray(options)
      .map((option, index) => {
        const name = normalizeText(option?.optionName, "").trim();
        if (!name) {
          return "";
        }
        const code = normalizeText(option?.optionCode, "").trim() || suggestOptionCode(name, index + 1);
        return `${code}|${name}`;
      })
      .filter(Boolean)
      .join("\n");

  const parseDraftOptionsText = (value) =>
    String(value || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line, index) => {
        const parts = line.split("|").map((entry) => entry.trim()).filter(Boolean);
        const optionName = parts.length > 1 ? parts[1] : parts[0] || "";
        const optionCode = parts.length > 1 ? parts[0] : suggestOptionCode(optionName, index + 1);
        return {
          optionCode,
          optionName,
          sortNo: (index + 1) * 10,
          status: "ACTIVE",
        };
      })
      .filter((entry) => entry.optionCode && entry.optionName);

  const readJsonDataAttr = (node, attrName, fallback = []) => {
    if (!(node instanceof HTMLElement)) {
      return fallback;
    }
    const raw = node.dataset[attrName];
    if (!raw) {
      return fallback;
    }
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : fallback;
    } catch (_error) {
      return fallback;
    }
  };

  const checkboxChecked = (value) => (value ? "checked" : "");
  const selectedAttr = (candidate, current) =>
    String(candidate ?? "") === String(current ?? "") ? "selected" : "";

  const getFilters = () => {
    if (!(controlsForm instanceof HTMLFormElement)) {
      return {};
    }
    const formData = new FormData(controlsForm);
    return {
      operatorId: normalizeText(formData.get("operatorId"), "").trim(),
      sourceKeyword: normalizeText(formData.get("sourceKeyword"), "").trim(),
      taskKey: normalizeText(formData.get("taskKey"), "").trim(),
      businessDomain: normalizeText(formData.get("businessDomain"), "").trim(),
      profileKey: normalizeText(formData.get("profileKey"), "default").trim() || "default",
      discoveryPages: Number(formData.get("discoveryPages") || 1),
      status: normalizeText(formData.get("status"), "").trim(),
      itemScanLimit: Number(formData.get("itemScanLimit") || 2000),
      includeClosed: formData.get("includeClosed") === "on",
    };
  };

  const setFeedback = (message, state = "info") => {
    if (!(feedbackNode instanceof HTMLElement)) {
      return;
    }
    feedbackNode.textContent = message;
    feedbackNode.dataset.state = state;
    feedbackNode.dataset.error = state === "error" ? "true" : "false";
  };

  const buildQuery = (params) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === null || value === undefined || value === "" || value === false) {
        return;
      }
      query.set(key, String(value));
    });
    const serialized = query.toString();
    return serialized ? `?${serialized}` : "";
  };

  const fetchJson = async (url, options = null) => {
    const response = await fetch(url, {
      headers: {
        Accept: "application/json",
        ...(options?.headers || {}),
      },
      ...options,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload?.detail || `HTTP ${response.status}`);
    }
    return payload;
  };

  const getSelectedQueueItem = () => queueItems.find((item) => item.id === selectedQueueId) || null;

  const clearDraft = (message) => {
    currentDraft = null;
    lastPersistResult = null;
    if (!(draftPanel instanceof HTMLElement)) {
      return;
    }
    draftPanel.innerHTML = `<p class="runtime-panel-text">${safeText(
      message || "先从左侧选择一个 queue 项，再点击“生成草稿”。",
    )}</p>`;
  };

  const renderCoverage = (payload) => {
    if (!(coverageGrid instanceof HTMLElement)) {
      return;
    }
    const counts = payload?.counts || {};
    const coverage = payload?.coverage || {};
    const filters = payload?.filters || {};
    const showEmptyHint = Number(counts.totalItems || 0) === 0 && !isBlank(filters.sourceKeyword);
    coverageGrid.innerHTML = `
      <article class="stat-card compact">
        <p class="eyebrow">Items</p>
        <strong>${safeText(counts.totalItems)}</strong>
        <span>当前筛选下的 Xianyu 商品总量</span>
      </article>
      <article class="stat-card compact">
        <p class="eyebrow">Raw Response</p>
        <strong>${safeText(counts.itemsWithCurrentRawResponse)}</strong>
        <span>仍保留原始响应，可回填 raw cate</span>
      </article>
      <article class="stat-card compact">
        <p class="eyebrow">Any Signal</p>
        <strong>${safeText(counts.itemsWithAnyRawCategorySignal)}</strong>
        <span>已带任意 raw cate signal</span>
      </article>
      <article class="stat-card compact">
        <p class="eyebrow">Complete Signal</p>
        <strong>${safeText(counts.itemsWithCompleteRawCategorySignal)}</strong>
        <span>三段 raw cate signal 都齐全</span>
      </article>
      <article class="stat-card compact">
        <p class="eyebrow">Backfill</p>
        <strong>${safeText(counts.backfillCandidateItems)}</strong>
        <span>仍可从 RawResponse 补录的商品数</span>
      </article>
      <article class="stat-card compact">
        <p class="eyebrow">Coverage</p>
        <strong>${safeText(formatPercent(coverage.rawSignalCoverageRatio))}</strong>
        <span>raw cate signal 覆盖率</span>
      </article>
      ${
        showEmptyHint
          ? `
            <article class="stat-card compact warn">
              <p class="eyebrow">No Samples</p>
              <strong>这轮没有抓到商品</strong>
              <span>关键词可能过窄，或者页面返回了空结果 / 风控页。</span>
            </article>
          `
          : ""
      }
    `;
  };

  const renderQueueList = () => {
    if (!(queueList instanceof HTMLElement) || !(totalBadge instanceof HTMLElement)) {
      return;
    }
    totalBadge.textContent = `${queueItems.length} 项`;
    if (!queueItems.length) {
      const filters = getFilters();
      queueList.innerHTML = `
        <article class="panel compact-panel">
          <p class="eyebrow">Queue</p>
          <h3>当前没有待办项</h3>
          <p class="runtime-panel-text">${
            filters.sourceKeyword
              ? `关键词“${safeText(filters.sourceKeyword)}”这轮还没有形成 queue。可能是没有抓到样本，或者命中的 raw cate 已经全部映射。`
              : "可以先点击“同步队列”，或者切换包含已关闭查看历史项。"
          }</p>
        </article>
      `;
      renderDetail(null);
      return;
    }

    if (!selectedQueueId || !queueItems.some((item) => item.id === selectedQueueId)) {
      selectedQueueId = queueItems[0].id;
    }

    queueList.innerHTML = queueItems
      .map(
        (item) => `
          <button
            type="button"
            class="onboarding-queue-card ${item.id === selectedQueueId ? "is-active" : ""}"
            data-onboarding-queue-card
            data-queue-id="${safeAttr(item.id)}"
          >
            <div class="onboarding-queue-card-head">
              <span class="onboarding-status-pill ${safeAttr(String(item.status || "").toLowerCase())}">${safeText(item.status)}</span>
              <strong>${safeText(item.itemCountSnapshot)}</strong>
            </div>
            <h3>${safeText(item.matchKey)}</h3>
            <p class="onboarding-queue-meta">${safeText(item.xianyuCCatId || item.xianyuCatId || item.xianyuTbCatId)}</p>
            <p class="onboarding-queue-samples">${safeText(
              safeArray(item.sampleTitles).slice(0, 2).join(" / "),
              "暂无样本标题",
            )}</p>
            <div class="onboarding-queue-foot">
              <span>${safeText(safeArray(item.businessDomains).join(", "), "未标注业务域")}</span>
              <span>${safeText(formatRelative(item.updatedAt))}</span>
            </div>
          </button>
        `,
      )
      .join("");

    renderDetail(getSelectedQueueItem());
  };

  const renderDetail = (item) => {
    if (!(detailPanel instanceof HTMLElement)) {
      return;
    }
    if (!item) {
      detailPanel.innerHTML =
        '<p class="runtime-panel-text">选择左侧 queue 项后，这里会展示 raw cate、样本标题、状态和候选 match keys。</p>';
      return;
    }

    const metadata = item.metadata || {};
    const candidateKeys = safeArray(metadata.candidateMatchKeys);
    const canMarkInProgress = item.status !== "IN_PROGRESS";
    const canMarkIgnored = item.status !== "IGNORED";
    const canReopen = item.status !== "PENDING";
    detailPanel.innerHTML = `
      <div class="onboarding-detail-block">
        <p class="eyebrow">Raw Cate</p>
        <h3>${safeText(item.matchKey)}</h3>
        <div class="onboarding-detail-grid">
          <div><span>C_CAT</span><strong>${safeText(item.xianyuCCatId)}</strong></div>
          <div><span>CAT</span><strong>${safeText(item.xianyuCatId)}</strong></div>
          <div><span>TB_CAT</span><strong>${safeText(item.xianyuTbCatId)}</strong></div>
          <div><span>状态</span><strong>${safeText(item.status)}</strong></div>
          <div><span>Owner</span><strong>${safeText(item.ownerOperatorId)}</strong></div>
          <div><span>样本数</span><strong>${safeText(item.itemCountSnapshot)}</strong></div>
        </div>
      </div>
      <div class="onboarding-detail-block">
        <p class="eyebrow">样本标题</p>
        <div class="tag-cluster">
          ${safeArray(item.sampleTitles)
            .map((title) => `<span class="tag">${safeText(title)}</span>`)
            .join("") || '<span class="tag">暂无</span>'}
        </div>
      </div>
      <div class="onboarding-detail-block">
        <p class="eyebrow">候选 Match Keys</p>
        <div class="tag-cluster">
          ${
            candidateKeys.map((value) => `<span class="tag">${safeText(value)}</span>`).join("") ||
            '<span class="tag">暂无</span>'
          }
        </div>
      </div>
      <div class="onboarding-detail-block">
        <p class="eyebrow">已解析映射</p>
        <pre class="onboarding-json-block">${toJsonPreview(item.resolvedMapping, {})}</pre>
      </div>
      <div class="onboarding-detail-actions">
        <button type="button" class="secondary-button" data-onboarding-status="IN_PROGRESS" ${canMarkInProgress ? "" : "disabled"}>标记处理中</button>
        <button type="button" class="secondary-button" data-onboarding-status="IGNORED" ${canMarkIgnored ? "" : "disabled"}>标记忽略</button>
        <button type="button" class="primary-button" data-onboarding-status="PENDING" ${canReopen ? "" : "disabled"}>恢复待办</button>
      </div>
    `;
  };

  const renderDraft = () => {
    if (!(draftPanel instanceof HTMLElement)) {
      return;
    }
    if (!currentDraft) {
      clearDraft("先从左侧选择一个 queue 项，再点击“生成草稿”。");
      return;
    }

    const analysis = currentDraft.analysis || {};
    const payload = currentDraft.payload || {};
    const catalog = payload.catalog || {};
    const category = catalog.category || {};
    const template = catalog.template || {};
    const attributeObservations = new Map(
      safeArray(analysis.attributeObservations).map((entry) => [String(entry.attributeCode || ""), entry]),
    );
    const catalogAttributeMap = new Map(
      safeArray(catalog.attributes).map((entry) => [String(entry.code || ""), entry]),
    );
    const templateItemMap = new Map(
      safeArray(template.items).map((entry) => [String(entry.attributeCode || ""), entry]),
    );
    const resolveAttributeLabel = (code) => {
      const normalizedCode = String(code || "");
      const observation = attributeObservations.get(normalizedCode) || {};
      const templateItem = templateItemMap.get(normalizedCode) || {};
      return observation.attributeName || templateItem.attributeName || normalizedCode;
    };
    const rows = safeArray(analysis.attributeObservations)
      .filter((entry) => entry?.visible !== false)
      .map((observation) => {
        const code = String(observation.attributeCode || "");
        const attribute = catalogAttributeMap.get(code) || {};
        const templateItem = templateItemMap.get(code) || {};
        return {
          code,
          name: observation.attributeName || attribute.name || code,
          dataType: observation.dataType || attribute.dataType || "TEXT",
          valueScope: observation.valueScope || attribute.valueScope || "SPU",
          isMulti: Boolean(observation.isMulti ?? attribute.isMulti),
          unit: observation.unit || attribute.unit || "",
          isRequired: Boolean(templateItem.isRequired),
          isSale: Boolean(templateItem.isSale),
          isFilter: Boolean(templateItem.isFilter),
          isSearch:
            templateItem.isSearch === undefined ? code === "brand_name" || code === "model_name" : Boolean(templateItem.isSearch),
          isDisplay: templateItem.isDisplay === undefined ? true : Boolean(templateItem.isDisplay),
          sortNo: Number(templateItem.sortNo || observation.sortNo || 0),
          observedCount: Number(observation.observedCount || 0),
          sampleValues: safeArray(observation.sampleValues),
          selected: Boolean(observation.selected),
          profileSuggested: Boolean(observation.profileSuggested),
          suggestedCode: String(observation.suggestedCode || code || "custom_attr"),
          optionSuggestions: safeArray(observation.optionSuggestions),
          options: safeArray(attribute.options),
        };
      })
      .sort((left, right) => left.sortNo - right.sortNo || left.code.localeCompare(right.code, "zh-CN"));

    const selection = currentDraft.selection || {};
    const matchedProfiles = safeArray(analysis.categoryHints);
    const reuseSuggestion = currentDraft.reuseSuggestion || payload.reuseSuggestion || null;
    const reuseCoverage = reuseSuggestion?.coverage || {};
    const coveredSuggestedCodes = safeArray(reuseCoverage.coveredSuggestedAttributeCodes);
    const missingSuggestedCodes = safeArray(reuseCoverage.missingSuggestedAttributeCodes);
    const extraTemplateCodes = safeArray(reuseCoverage.extraTemplateAttributeCodes);
    draftPanel.innerHTML = `
      <div class="onboarding-draft-summary">
        <div class="panel-pills">
          <span class="status-pill">样本数 ${safeText(analysis.sampleCount)}</span>
          <span class="status-pill">Raw ${safeText(selection.xianyuCCatId || selection.xianyuCatId || selection.xianyuTbCatId)}</span>
          <span class="status-pill accent">Mappings ${safeText(safeArray(payload.mappings).length)}</span>
        </div>
        <p class="runtime-panel-text">
          这份草稿来自当前 queue 项的真实样本。你可以调整分类元数据、勾选有效属性，并在落库前先做 dry-run 预演。
        </p>
        <div class="tag-cluster">
          ${
            matchedProfiles
              .map(
                (profile) =>
                  `<span class="tag">${safeText(profile.name)} · ${safeText(formatPercent(profile.confidence))}</span>`,
              )
              .join("") || '<span class="tag">暂无 profile hint</span>'
          }
        </div>
        <div class="tag-cluster">
          ${safeArray(analysis.sampleTitles)
            .map((title) => `<span class="tag">${safeText(title)}</span>`)
            .join("") || '<span class="tag">暂无样本标题</span>'}
        </div>
      </div>

      ${
        reuseSuggestion
          ? `
            <div class="onboarding-detail-block">
              <div class="onboarding-draft-row-head">
                <div>
                  <p class="eyebrow">Canonical Reuse</p>
                  <p class="runtime-panel-text">
                    建议直接复用现有大类模板
                    <strong>${safeText(reuseSuggestion.category?.name || reuseSuggestion.category?.code)}</strong>，
                    这次落库只补 raw cate 到模板的映射，不重复创建 category/template。
                  </p>
                </div>
                <label class="onboarding-toggle">
                  <input type="checkbox" data-draft-category-field="reuseExistingTemplate" checked />
                  <span>复用现有模板</span>
                </label>
              </div>
              <div class="panel-pills">
                <span class="status-pill accent">${safeText(reuseSuggestion.category?.code)}</span>
                <span class="status-pill">Template v${safeText(reuseSuggestion.template?.version)}</span>
                <span class="status-pill">${safeText(reuseSuggestion.template?.status)}</span>
                <span class="status-pill">覆盖 ${safeText(formatPercent(reuseCoverage.coverageRatio))}</span>
              </div>
              <div class="tag-cluster">
                ${coveredSuggestedCodes
                  .map((code) => `<span class="tag">${safeText(resolveAttributeLabel(code))}</span>`)
                  .join("") || '<span class="tag">暂无已覆盖属性</span>'}
              </div>
              ${
                missingSuggestedCodes.length
                  ? `
                    <p class="runtime-panel-text">
                      这些候选属性当前模板还没覆盖。保持“复用现有模板”时，它们不会被自动写进已有模板，后续如有需要再做模板升级。
                    </p>
                    <div class="tag-cluster">
                      ${missingSuggestedCodes
                        .map((code) => `<span class="tag">${safeText(resolveAttributeLabel(code))}</span>`)
                        .join("")}
                    </div>
                  `
                  : ""
              }
              ${
                extraTemplateCodes.length
                  ? `
                    <p class="runtime-panel-text">现有模板里还有这些额外属性，会继续沿用：</p>
                    <div class="tag-cluster">
                      ${extraTemplateCodes
                        .map((code) => `<span class="tag">${safeText(resolveAttributeLabel(code))}</span>`)
                        .join("")}
                    </div>
                  `
                  : ""
              }
            </div>
          `
          : ""
      }

      <div class="onboarding-draft-meta">
        <label class="filter-field">
          <span>Request ID</span>
          <input type="text" data-draft-category-field="requestId" value="${safeAttr(payload.requestId)}" />
        </label>
        <label class="filter-field">
          <span>Category Code</span>
          <input type="text" data-draft-category-field="categoryCode" value="${safeAttr(category.code)}" />
        </label>
        <label class="filter-field wide-field">
          <span>Category Name</span>
          <input type="text" data-draft-category-field="categoryName" value="${safeAttr(category.name)}" />
        </label>
        <label class="filter-field wide-field">
          <span>Category Path</span>
          <input type="text" data-draft-category-field="categoryPath" value="${safeAttr(category.path)}" />
        </label>
        <label class="filter-field">
          <span>Level</span>
          <input type="number" min="1" max="9" data-draft-category-field="categoryLevel" value="${safeAttr(category.level || 2)}" />
        </label>
        <label class="filter-field">
          <span>Template Version</span>
          <input type="number" min="1" max="999" data-draft-category-field="templateVersion" value="${safeAttr(template.version || 1)}" />
        </label>
      </div>

      <div class="onboarding-draft-list">
        ${rows
          .map(
            (row) => `
              <article class="onboarding-draft-row" data-draft-row>
                <div class="onboarding-draft-row-head">
                  <label class="onboarding-toggle">
                    <input type="checkbox" data-draft-field="enabled" ${checkboxChecked(row.selected)} />
                    <span>启用属性</span>
                  </label>
                  <div class="panel-pills">
                    <span class="status-pill">命中 ${safeText(row.observedCount)}</span>
                    <span class="status-pill">${safeText(row.dataType)}</span>
                    <span class="status-pill">${safeText(row.valueScope)}</span>
                    ${row.profileSuggested ? '<span class="status-pill warn">Profile</span>' : ""}
                  </div>
                </div>
                <div class="onboarding-draft-row-grid" data-sample-values="${safeAttr(JSON.stringify(row.sampleValues))}">
                  <label class="filter-field">
                    <span>Code</span>
                    <input type="text" data-draft-field="code" value="${safeAttr(row.code)}" />
                    <span class="draft-helper" data-draft-code-hint>建议 ${safeText(row.suggestedCode)}</span>
                    <button type="button" class="secondary-button small-button" data-draft-row-action="apply-code-suggestion">使用建议</button>
                  </label>
                  <label class="filter-field">
                    <span>Name</span>
                    <input type="text" data-draft-field="name" value="${safeAttr(row.name)}" />
                  </label>
                  <label class="filter-field">
                    <span>Data Type</span>
                    <select data-draft-field="dataType">
                      <option value="TEXT" ${selectedAttr("TEXT", row.dataType)}>TEXT</option>
                      <option value="NUMBER" ${selectedAttr("NUMBER", row.dataType)}>NUMBER</option>
                      <option value="BOOLEAN" ${selectedAttr("BOOLEAN", row.dataType)}>BOOLEAN</option>
                      <option value="ENUM" ${selectedAttr("ENUM", row.dataType)}>ENUM</option>
                      <option value="JSON" ${selectedAttr("JSON", row.dataType)}>JSON</option>
                    </select>
                  </label>
                  <label class="filter-field">
                    <span>Value Scope</span>
                    <select data-draft-field="valueScope">
                      <option value="SPU" ${selectedAttr("SPU", row.valueScope)}>SPU</option>
                      <option value="SKU" ${selectedAttr("SKU", row.valueScope)}>SKU</option>
                    </select>
                  </label>
                  <label class="filter-field">
                    <span>Unit</span>
                    <input type="text" data-draft-field="unit" value="${safeAttr(row.unit)}" />
                  </label>
                  <label class="filter-field">
                    <span>Sort No</span>
                    <input type="number" min="0" data-draft-field="sortNo" value="${safeAttr(row.sortNo)}" />
                  </label>
                </div>
                <div class="onboarding-draft-enum ${row.dataType === "ENUM" ? "" : "is-hidden"}" data-draft-enum-block>
                  <div class="onboarding-draft-enum-head">
                    <span class="eyebrow">枚举选项</span>
                    <button type="button" class="secondary-button small-button" data-draft-row-action="fill-enum-from-samples">用样例生成</button>
                  </div>
                  <textarea
                    rows="4"
                    class="draft-textarea"
                    data-draft-field="optionsText"
                    data-option-suggestions="${safeAttr(JSON.stringify(row.optionSuggestions.length ? row.optionSuggestions : row.options))}"
                  >${safeText(formatOptionLines(row.options.length ? row.options : row.optionSuggestions), "")}</textarea>
                  <p class="runtime-panel-text">每行填写 <code>optionCode|optionName</code>。切到 <code>ENUM</code> 时会带着这些值一起落库。</p>
                </div>
                <div class="onboarding-draft-row-flags">
                  <label class="onboarding-toggle"><input type="checkbox" data-draft-field="isMulti" ${checkboxChecked(row.isMulti)} /><span>多值</span></label>
                  <label class="onboarding-toggle"><input type="checkbox" data-draft-field="isRequired" ${checkboxChecked(row.isRequired)} /><span>必填</span></label>
                  <label class="onboarding-toggle"><input type="checkbox" data-draft-field="isSale" ${checkboxChecked(row.isSale)} /><span>销售属性</span></label>
                  <label class="onboarding-toggle"><input type="checkbox" data-draft-field="isFilter" ${checkboxChecked(row.isFilter)} /><span>可筛选</span></label>
                  <label class="onboarding-toggle"><input type="checkbox" data-draft-field="isSearch" ${checkboxChecked(row.isSearch)} /><span>可搜索</span></label>
                  <label class="onboarding-toggle"><input type="checkbox" data-draft-field="isDisplay" ${checkboxChecked(row.isDisplay)} /><span>可展示</span></label>
                </div>
                <div class="onboarding-draft-samples">
                  <span class="eyebrow">样例值</span>
                  <div class="tag-cluster">
                    ${
                      row.sampleValues
                        .map((value) => `<span class="tag">${safeText(displaySampleValue(value))}</span>`)
                        .join("") || '<span class="tag">暂无</span>'
                    }
                  </div>
                </div>
              </article>
            `,
          )
          .join("")}
      </div>

      ${
        lastPersistResult
          ? `
            <div class="onboarding-detail-block">
              <p class="eyebrow">最近一次落库结果</p>
              <pre class="onboarding-json-block">${toJsonPreview(lastPersistResult, {})}</pre>
            </div>
          `
          : ""
      }
    `;
    Array.from(draftPanel.querySelectorAll("[data-draft-row]")).forEach((rowElement) => {
      if (rowElement instanceof HTMLElement) {
        updateDraftRowPresentation(rowElement);
      }
    });
  };

  const updateDraftRowPresentation = (rowElement) => {
    if (!(rowElement instanceof HTMLElement)) {
      return;
    }
    const field = (name) => rowElement.querySelector(`[data-draft-field="${name}"]`);
    const enabledField = field("enabled");
    const nameValue = normalizeText(field("name")?.value, "").trim();
    const codeField = field("code");
    const codeHint = rowElement.querySelector("[data-draft-code-hint]");
    const suggestedCode = suggestAttributeCode(nameValue, normalizeText(codeField?.value, "custom_attr"));
    if (codeHint instanceof HTMLElement) {
      codeHint.textContent = `建议 ${suggestedCode}`;
    }
    if (codeField instanceof HTMLInputElement) {
      codeField.dataset.suggestedCode = suggestedCode;
    }
    rowElement.dataset.suggestedCode = suggestedCode;
    rowElement.classList.toggle("is-disabled", enabledField instanceof HTMLInputElement && !enabledField.checked);

    const enumBlock = rowElement.querySelector("[data-draft-enum-block]");
    const dataType = normalizeText(field("dataType")?.value, "").trim().toUpperCase();
    if (enumBlock instanceof HTMLElement) {
      enumBlock.classList.toggle("is-hidden", dataType !== "ENUM");
    }
  };

  const populateEnumOptionsFromSamples = (rowElement) => {
    if (!(rowElement instanceof HTMLElement)) {
      return;
    }
    const optionsField = rowElement.querySelector('[data-draft-field="optionsText"]');
    if (!(optionsField instanceof HTMLTextAreaElement)) {
      return;
    }
    const suggestions = readJsonDataAttr(optionsField, "optionSuggestions", []);
    if (suggestions.length) {
      optionsField.value = formatOptionLines(suggestions);
      return;
    }
    const sampleValues = readJsonDataAttr(rowElement.querySelector("[data-sample-values]"), "sampleValues", []);
    optionsField.value = formatOptionLines(
      sampleValues.map((value, index) => ({
        optionCode: suggestOptionCode(value, index + 1),
        optionName: String(value),
      })),
    );
  };

  const loadCoverage = async () => {
    const filters = getFilters();
    const payload = await fetchJson(
      `/api/onboarding/xianyu/coverage${buildQuery({
        source_keyword: filters.sourceKeyword,
        business_domain: filters.businessDomain,
        item_scan_limit: filters.itemScanLimit,
      })}`,
    );
    renderCoverage(payload);
    return payload;
  };

  const loadQueue = async () => {
    const filters = getFilters();
    const payload = await fetchJson(
      `/api/onboarding/xianyu/queue${buildQuery({
        status: filters.status,
        include_closed: filters.includeClosed,
        limit: 80,
      })}`,
    );
    queueItems = safeArray(payload.items);
    renderQueueList();
    return payload;
  };

  const refreshPage = async () => {
    const [coveragePayload, queuePayload] = await Promise.all([loadCoverage(), loadQueue()]);
    return { coveragePayload, queuePayload };
  };

  const syncQueue = async () => {
    const filters = getFilters();
    if (!filters.operatorId) {
      throw new Error("operatorId 不能为空");
    }
    return fetchJson("/api/onboarding/xianyu/queue/sync", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        operatorId: filters.operatorId,
        sourceKeyword: filters.sourceKeyword || null,
        businessDomain: filters.businessDomain || null,
        itemScanLimit: filters.itemScanLimit,
        apply: true,
      }),
    });
  };

  const runDiscovery = async () => {
    const filters = getFilters();
    if (!filters.sourceKeyword) {
      throw new Error("请先输入关键词");
    }
    return fetchJson("/api/onboarding/xianyu/discovery", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        sourceKeyword: filters.sourceKeyword,
        taskKey: filters.taskKey || null,
        businessDomain: filters.businessDomain || null,
        pages: Math.max(1, Number(filters.discoveryPages || 1)),
        profileKey: filters.profileKey || "default",
        loginWaitSeconds: 180,
      }),
    });
  };

  const updateQueueStatus = async (status) => {
    const filters = getFilters();
    const current = getSelectedQueueItem();
    if (!current) {
      throw new Error("请先选择一个 queue 项");
    }
    if (!filters.operatorId) {
      throw new Error("operatorId 不能为空");
    }
    const statusNote = window.prompt("可选：输入状态备注", "") || "";
    return fetchJson("/api/onboarding/xianyu/queue/status", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        operatorId: filters.operatorId,
        status,
        queueId: current.id,
        statusNote: statusNote || null,
        apply: true,
      }),
    });
  };

  const generateDraft = async () => {
    const current = getSelectedQueueItem();
    const filters = getFilters();
    if (!current) {
      throw new Error("请先选择一个 queue 项");
    }
    const payload = await fetchJson("/api/onboarding/xianyu/draft", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        sourceKeyword: filters.sourceKeyword || safeArray(current.sourceKeywords)[0] || null,
        businessDomain: filters.businessDomain || safeArray(current.businessDomains)[0] || null,
        xianyuCatId: current.xianyuCatId || null,
        xianyuTbCatId: current.xianyuTbCatId || null,
        xianyuCCatId: current.xianyuCCatId || null,
        sampleLimit: 25,
        preferUnmapped: false,
      }),
    });
    currentDraft = payload;
    lastPersistResult = null;
    renderDraft();
    return payload;
  };

  const collectDraftRows = () => {
    if (!(draftPanel instanceof HTMLElement)) {
      return [];
    }
    return Array.from(draftPanel.querySelectorAll("[data-draft-row]")).map((rowElement) => {
      const field = (name) => rowElement.querySelector(`[data-draft-field="${name}"]`);
      const inputValue = (name) => normalizeText(field(name)?.value, "").trim();
      const checkboxValue = (name) => Boolean(field(name)?.checked);
      return {
        enabled: checkboxValue("enabled"),
        code: inputValue("code"),
        name: inputValue("name"),
        dataType: inputValue("dataType") || "TEXT",
        valueScope: inputValue("valueScope") || "SPU",
        unit: inputValue("unit") || null,
        sortNo: Number(inputValue("sortNo") || 0),
        isMulti: checkboxValue("isMulti"),
        isRequired: checkboxValue("isRequired"),
        isSale: checkboxValue("isSale"),
        isFilter: checkboxValue("isFilter"),
        isSearch: checkboxValue("isSearch"),
        isDisplay: checkboxValue("isDisplay"),
        options: parseDraftOptionsText(inputValue("optionsText")),
      };
    });
  };

  const buildPersistPayload = () => {
    if (!currentDraft || !(draftPanel instanceof HTMLElement)) {
      throw new Error("请先生成草稿");
    }

    const categoryField = (name) =>
      normalizeText(draftPanel.querySelector(`[data-draft-category-field="${name}"]`)?.value, "").trim();
    const activeRows = collectDraftRows().filter((row) => row.enabled && row.code && row.name);
    if (!activeRows.length) {
      throw new Error("至少保留一个有效属性");
    }

    const requestId = categoryField("requestId") || normalizeText(currentDraft.payload?.requestId, "xianyu-onboarding-request");
    const reuseSuggestion = currentDraft.reuseSuggestion || currentDraft.payload?.reuseSuggestion || null;
    const reuseEnabled = Boolean(
      draftPanel.querySelector('[data-draft-category-field="reuseExistingTemplate"]')?.checked &&
        reuseSuggestion?.category?.id &&
        reuseSuggestion?.template?.id,
    );
    const template = currentDraft.payload?.catalog?.template || {};
    const category = currentDraft.payload?.catalog?.category || {};
    if (reuseEnabled) {
      return {
        requestId,
        categoryId: normalizeText(reuseSuggestion.category.id, "").trim(),
        templateId: normalizeText(reuseSuggestion.template.id, "").trim(),
        mappings: safeArray(currentDraft.payload?.mappings).map((mapping) => ({ ...mapping })),
      };
    }
    return {
      requestId,
      catalog: {
        requestId,
        category: {
          code: categoryField("categoryCode") || normalizeText(category.code, ""),
          name: categoryField("categoryName") || normalizeText(category.name, ""),
          path: categoryField("categoryPath") || normalizeText(category.path, ""),
          level: Number(categoryField("categoryLevel") || category.level || 2),
          status: normalizeText(category.status, "ACTIVE"),
        },
        attributes: activeRows.map((row) => ({
          scopeType: "PLATFORM",
          scopeId: "platform",
          code: row.code,
          name: row.name,
          dataType: row.dataType,
          valueScope: row.valueScope,
          isMulti: row.isMulti,
          unit: row.unit || null,
          status: "DRAFT",
          options: row.dataType === "ENUM" ? row.options : [],
        })),
        template: {
          version: Number(categoryField("templateVersion") || template.version || 1),
          status: normalizeText(template.status, "DRAFT"),
          items: activeRows
            .sort((left, right) => left.sortNo - right.sortNo || left.code.localeCompare(right.code, "zh-CN"))
            .map((row) => ({
              attributeCode: row.code,
              isRequired: row.isRequired,
              isSale: row.isSale,
              isFilter: row.isFilter,
              isSearch: row.isSearch,
              isDisplay: row.isDisplay,
              sortNo: row.sortNo,
            })),
        },
      },
      mappings: safeArray(currentDraft.payload?.mappings).map((mapping) => ({ ...mapping })),
    };
  };

  const persistDraft = async (apply) => {
    const filters = getFilters();
    if (!filters.operatorId) {
      throw new Error("operatorId 不能为空");
    }
    const payload = buildPersistPayload();
    const result = await fetchJson("/api/onboarding/xianyu/persist", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        operatorId: filters.operatorId,
        payload,
        apply,
      }),
    });
    lastPersistResult = result;
    renderDraft();
    return result;
  };

  root.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const rowElement = target.closest("[data-draft-row]");
    if (!(rowElement instanceof HTMLElement)) {
      return;
    }
    updateDraftRowPresentation(rowElement);
  });

  root.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const rowElement = target.closest("[data-draft-row]");
    if (!(rowElement instanceof HTMLElement)) {
      return;
    }
    if (target.matches('[data-draft-field="dataType"]')) {
      const select = target;
      if (select instanceof HTMLSelectElement && String(select.value).toUpperCase() === "ENUM") {
        const optionsField = rowElement.querySelector('[data-draft-field="optionsText"]');
        if (optionsField instanceof HTMLTextAreaElement && !optionsField.value.trim()) {
          populateEnumOptionsFromSamples(rowElement);
        }
      }
    }
    updateDraftRowPresentation(rowElement);
  });

  root.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const queueCard = target.closest("[data-onboarding-queue-card]");
    if (queueCard instanceof HTMLElement) {
      selectedQueueId = queueCard.dataset.queueId || null;
      currentDraft = null;
      lastPersistResult = null;
      renderQueueList();
      clearDraft("已切换 queue 项。点击“生成草稿”开始编辑模板。");
      return;
    }

    const draftRowAction = target.closest("[data-draft-row-action]");
    if (draftRowAction instanceof HTMLButtonElement) {
      event.preventDefault();
      const rowElement = draftRowAction.closest("[data-draft-row]");
      if (!(rowElement instanceof HTMLElement)) {
        return;
      }
      if (draftRowAction.dataset.draftRowAction === "apply-code-suggestion") {
        const codeField = rowElement.querySelector('[data-draft-field="code"]');
        if (codeField instanceof HTMLInputElement) {
          codeField.value = rowElement.dataset.suggestedCode || codeField.value;
          updateDraftRowPresentation(rowElement);
        }
      } else if (draftRowAction.dataset.draftRowAction === "fill-enum-from-samples") {
        populateEnumOptionsFromSamples(rowElement);
      }
      return;
    }

    const statusButton = target.closest("[data-onboarding-status]");
    if (statusButton instanceof HTMLButtonElement) {
      event.preventDefault();
      try {
        setFeedback("正在更新 queue 状态...");
        await updateQueueStatus(statusButton.dataset.onboardingStatus || "PENDING");
        await refreshPage();
        setFeedback("状态已更新。");
      } catch (error) {
        setFeedback(`状态更新失败: ${error instanceof Error ? error.message : "未知错误"}`, "error");
      }
      return;
    }

    const draftActionButton = target.closest("[data-onboarding-draft-action]");
    if (draftActionButton instanceof HTMLButtonElement) {
      event.preventDefault();
      try {
        if (draftActionButton.dataset.onboardingDraftAction === "generate") {
          setFeedback("正在生成 onboarding 草稿...");
          const payload = await generateDraft();
          setFeedback(`草稿已生成：sample=${normalizeText(payload.analysis?.sampleCount, "0")} attrs=${normalizeText(payload.analysis?.selectedAttributeCodes?.length, "0")}`);
        } else if (draftActionButton.dataset.onboardingDraftAction === "preview-persist") {
          setFeedback("正在执行 dry-run 预演...");
          const result = await persistDraft(false);
          setFeedback(`dry-run 完成：mapping=${normalizeText(result.mappingCount, "0")} queue_resolved=${normalizeText(result.resolvedQueueCount, "0")}`);
        } else if (draftActionButton.dataset.onboardingDraftAction === "apply-persist") {
          if (!window.confirm("确认正式创建属性、模板和 raw cate 映射吗？")) {
            return;
          }
          setFeedback("正在正式创建模板与映射...");
          const result = await persistDraft(true);
          await refreshPage();
          setFeedback(`创建完成：mapping=${normalizeText(result.mappingCount, "0")} queue_resolved=${normalizeText(result.resolvedQueueCount, "0")}`);
        }
      } catch (error) {
        setFeedback(`草稿操作失败: ${error instanceof Error ? error.message : "未知错误"}`, "error");
      }
      return;
    }

    const actionButton = target.closest("[data-onboarding-action]");
    if (!(actionButton instanceof HTMLButtonElement)) {
      return;
    }
    event.preventDefault();
      try {
        if (actionButton.dataset.onboardingAction === "discovery") {
          setFeedback("正在执行 discovery collect...", "pending");
          const discovery = await runDiscovery();
          const syncResult = await syncQueue();
          const refreshed = await refreshPage();
          const totalItems = Number(refreshed.coveragePayload?.counts?.totalItems || 0);
          const createdCount = Number(syncResult.createdCount || 0);
          if (totalItems === 0) {
            setFeedback(
              `discovery 已执行，但没有抓到商品样本。pages=${normalizeText(
                discovery.run?.pagesSucceeded,
                "0",
              )}/${normalizeText(discovery.run?.pagesAttempted, "0")}，建议换更自然的关键词重试。`,
              "warn",
            );
          } else {
            setFeedback(
              `discovery 完成：items=${normalizeText(totalItems, "0")} queue_created=${normalizeText(
                createdCount,
                "0",
              )}`,
              "success",
            );
          }
        } else if (actionButton.dataset.onboardingAction === "sync") {
          setFeedback("正在同步 queue...", "pending");
          const payload = await syncQueue();
          const refreshed = await refreshPage();
          const queueTotal = Number(refreshed.queuePayload?.total || 0);
          if (queueTotal === 0) {
            setFeedback(
              `队列同步完成，但当前没有待办项。created=${normalizeText(payload.createdCount, "0")} resolved=${normalizeText(
                payload.resolvedCount,
                "0",
              )}`,
              "warn",
            );
          } else {
            setFeedback(
              `队列同步完成：created=${normalizeText(payload.createdCount, "0")} resolved=${normalizeText(
                payload.resolvedCount,
                "0",
              )} total=${normalizeText(queueTotal, "0")}`,
              "success",
            );
          }
        } else if (actionButton.dataset.onboardingAction === "refresh") {
          setFeedback("正在刷新页面数据...", "pending");
          await refreshPage();
          setFeedback("已刷新。", "success");
        }
      } catch (error) {
      setFeedback(`操作失败: ${error instanceof Error ? error.message : "未知错误"}`, "error");
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    clearDraft("先从左侧选择一个 queue 项，再点击“生成草稿”。");
    void refreshPage().catch((error) => {
      setFeedback(`初始化失败: ${error instanceof Error ? error.message : "未知错误"}`, "error");
    });
  });
})();
