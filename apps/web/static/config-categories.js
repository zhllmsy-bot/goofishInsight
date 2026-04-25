(() => {
  const root = document.querySelector("[data-category-config-page]");
  if (!(root instanceof HTMLElement)) {
    return;
  }

  const controlsForm = root.querySelector("[data-category-config-controls]");
  const editForm = root.querySelector("[data-category-config-form]");
  const feedbackNode = root.querySelector("[data-category-config-feedback]");
  const totalNode = root.querySelector("[data-category-config-total]");
  const listNode = root.querySelector("[data-category-config-list]");
  const summaryNode = root.querySelector("[data-category-config-summary]");
  const studioTitleNode = root.querySelector("[data-category-studio-title]");
  const studioDescriptionNode = root.querySelector("[data-category-studio-description]");
  const workflowContextNode = root.querySelector("[data-category-workflow-context]");
  const workflowSummaryNode = root.querySelector("[data-category-workflow-summary]");
  const workflowAttributeForm = root.querySelector("[data-category-workflow-attribute-form]");
  const workflowTemplateForm = root.querySelector("[data-category-workflow-template-form]");
  const workflowTemplateDiffNode = root.querySelector("[data-category-workflow-template-diff]");
  const workflowBindForm = root.querySelector("[data-category-workflow-bind-form]");
  const categoryEditorHintNode = root.querySelector("[data-category-editor-hint]");
  const categoryContextLinkNodes = Array.from(root.querySelectorAll("[data-category-context-link]"));
  const categoryModelLinkNodes = Array.from(root.querySelectorAll("[data-category-model-link]"));
  const categoryModelCountBadge = root.querySelector("[data-category-model-count-badge]");
  const workflowModalNodes = Array.from(root.querySelectorAll("[data-category-workflow-modal]"));
  const aiFeedbackNode = root.querySelector("[data-category-ai-feedback]");
  const aiForm = root.querySelector("[data-category-ai-form]");
  const aiDraftSummaryNode = root.querySelector("[data-category-ai-draft-summary]");
  const aiDraftOverviewNode = root.querySelector("[data-category-ai-draft-overview]");
  const aiGovernanceNode = root.querySelector("[data-category-ai-governance]");
  const aiLayoutNode = root.querySelector("[data-category-ai-layout]");
  const aiDraftFieldsNode = root.querySelector("[data-category-ai-draft-fields]");
  const aiAttributesPanelNode = root.querySelector("[data-category-ai-attributes-panel]");
  const aiAttributesListNode = root.querySelector("[data-category-ai-attributes-list]");
  const aiTemplatePanelNode = root.querySelector("[data-category-ai-template-panel]");
  const aiTemplateItemsListNode = root.querySelector("[data-category-ai-template-items-list]");

  let categoryItems = [];
  let selectedCategoryId = null;
  let activeWorkflowModal = null;
  let aiDraftState = null;
  let aiEditorVisible = false;
  const query = new URLSearchParams(window.location.search);
  const preferredCategoryCode = String(query.get("category_code") || "").trim();
  let preferredCategoryCodeApplied = false;

  const isBlank = (value) => value === null || value === undefined || value === "";
  const normalizeText = (value, fallback = "") => (isBlank(value) ? fallback : String(value));
  const escapeHtml = (value) =>
    String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  const safeText = (value, fallback = "-") => escapeHtml(normalizeText(value, fallback));
  const safeAttr = (value, fallback = "") => escapeHtml(normalizeText(value, fallback));
  const selectedAttr = (candidate, current) =>
    String(candidate ?? "") === String(current ?? "") ? "selected" : "";
  const toBoolean = (value) => value === "1" || /^true$/i.test(String(value || ""));
  const filteredConfigHref = (path, categoryCode) => {
    const normalized = normalizeText(categoryCode).trim();
    return normalized ? `${path}?category_code=${encodeURIComponent(normalized)}` : path;
  };
  const templateConfigHref = (categoryCode) => filteredConfigHref("/config/templates", categoryCode);
  const modelConfigHref = (categoryCode) => {
    return filteredConfigHref("/config/models", categoryCode);
  };

  const TEMPLATE_PRESET_ROWS = {
    camera_interchangeable_lens_extract_v1: [
      { attributeCode: "brand_name", isRequired: true },
      { attributeCode: "model_name", isRequired: true },
      { attributeCode: "mount_system", isRequired: true },
      { attributeCode: "focal_length_range", isRequired: true },
      { attributeCode: "max_aperture", isRequired: true },
      { attributeCode: "lens_series", isRequired: false },
    ],
    camera_body_extract_v1: [
      { attributeCode: "brand_name", isRequired: true },
      { attributeCode: "model_name", isRequired: true },
      { attributeCode: "mount_system", isRequired: true },
      { attributeCode: "sensor_format", isRequired: true },
      { attributeCode: "pixel_resolution", isRequired: false },
      { attributeCode: "camera_type", isRequired: false },
      { attributeCode: "generation", isRequired: false },
    ],
    apple_computer_extract_v1: [
      { attributeCode: "brand_name", isRequired: true },
      { attributeCode: "model_name", isRequired: true },
      { attributeCode: "chip_family", isRequired: true },
      { attributeCode: "screen_size_in", isRequired: false },
      { attributeCode: "memory_gb", isRequired: true },
      { attributeCode: "storage_gb", isRequired: true },
    ],
    garmin_watch_extract_v1: [
      { attributeCode: "brand_name", isRequired: true },
      { attributeCode: "model_name", isRequired: true },
      { attributeCode: "case_size_mm", isRequired: false },
      { attributeCode: "display_type", isRequired: false },
      { attributeCode: "is_solar", isRequired: false },
      { attributeCode: "edition_tags", isRequired: false },
    ],
    smartphone_extract_v1: [
      { attributeCode: "brand_name", isRequired: true },
      { attributeCode: "model_name", isRequired: true },
      { attributeCode: "phone_series", isRequired: false },
      { attributeCode: "memory_gb", isRequired: true },
      { attributeCode: "storage_gb", isRequired: true },
      { attributeCode: "device_color", isRequired: false },
    ],
  };
  const DEFAULT_TEMPLATE_PRESET = [
    { attributeCode: "brand_name", isRequired: true },
    { attributeCode: "model_name", isRequired: true },
  ];

  const setFeedback = (message, state = "info") => {
    if (!(feedbackNode instanceof HTMLElement)) {
      return;
    }
    feedbackNode.textContent = message;
    feedbackNode.dataset.state = state;
  };

  const setAIFeedback = (message, state = "info") => {
    if (!(aiFeedbackNode instanceof HTMLElement)) {
      return;
    }
    aiFeedbackNode.textContent = message;
    aiFeedbackNode.dataset.state = state;
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

  const formDataObject = (form) => {
    if (!(form instanceof HTMLFormElement)) {
      return {};
    }
    const data = new FormData(form);
    return Object.fromEntries(data.entries());
  };

  const lockBodyScrollIfNeeded = () => {
    const hasVisibleModal = workflowModalNodes.some((node) => !node.hidden);
    document.body.style.overflow = hasVisibleModal ? "hidden" : "";
  };

  const getWorkflowModal = (kind) =>
    workflowModalNodes.find((node) => normalizeText(node.getAttribute("data-category-workflow-modal")).trim() === normalizeText(kind).trim());

  const closeWorkflowModal = (modalNode = null) => {
    const target = modalNode instanceof HTMLElement ? modalNode : activeWorkflowModal;
    if (!(target instanceof HTMLElement)) {
      lockBodyScrollIfNeeded();
      return;
    }
    target.hidden = true;
    if (activeWorkflowModal === target) {
      activeWorkflowModal = null;
    }
    lockBodyScrollIfNeeded();
  };

  const openWorkflowModal = (kind) => {
    const modal = getWorkflowModal(kind);
    if (!(modal instanceof HTMLElement)) {
      throw new Error(`未找到 ${kind} 弹窗。`);
    }
    if (activeWorkflowModal instanceof HTMLElement && activeWorkflowModal !== modal) {
      activeWorkflowModal.hidden = true;
    }
    modal.hidden = false;
    activeWorkflowModal = modal;
    lockBodyScrollIfNeeded();
    const focusTarget =
      modal.querySelector("input:not([type='hidden'])")
      || modal.querySelector("textarea")
      || modal.querySelector("select")
      || modal.querySelector("button");
    if (focusTarget instanceof HTMLElement) {
      window.setTimeout(() => focusTarget.focus(), 30);
    }
  };

  const parseEnumOptions = (value) =>
    normalizeText(value)
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line, index) => {
        const [optionCode, optionName] = line.split("|").map((part) => part.trim());
        return {
          optionCode: optionCode || optionName,
          optionName: optionName || optionCode,
          sortNo: (index + 1) * 10,
          status: "ACTIVE",
        };
      });

  const parseTemplateItemsText = (value) =>
    normalizeText(value)
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line, index) => {
        const [attributeCode, required, sale, filter, search, display, sortNo] = line
          .split("|")
          .map((part) => part.trim());
        return {
          attributeCode: normalizeText(attributeCode).trim(),
          isRequired: toBoolean(required),
          isSale: toBoolean(sale),
          isFilter: toBoolean(filter),
          isSearch: toBoolean(search),
          isDisplay: !(display === "0" || /^false$/i.test(display || "")),
          sortNo: Number(sortNo || (index + 1) * 10),
        };
      })
      .filter((item) => Boolean(item.attributeCode));

  const formatTemplateItemsText = (items) =>
    (Array.isArray(items) ? items : [])
      .map((item, index) =>
        [
          normalizeText(item.attributeCode).trim(),
          item.isRequired ? "1" : "0",
          item.isSale ? "1" : "0",
          item.isFilter ? "1" : "0",
          item.isSearch ? "1" : "0",
          item.isDisplay === false ? "0" : "1",
          normalizeText(item.sortNo, String((index + 1) * 10)),
        ].join("|"),
      )
      .filter(Boolean)
      .join("\n");

  const buildPresetTemplateItemsText = (promptProfile) => {
    const rows = TEMPLATE_PRESET_ROWS[normalizeText(promptProfile).trim()] || DEFAULT_TEMPLATE_PRESET;
    return formatTemplateItemsText(
      rows.map((row, index) => ({
        attributeCode: row.attributeCode,
        isRequired: Boolean(row.isRequired),
        isSale: false,
        isFilter: true,
        isSearch: true,
        isDisplay: true,
        sortNo: (index + 1) * 10,
      })),
    );
  };

  const formatEnumOptionsText = (options) =>
    (Array.isArray(options) ? options : [])
      .map((option) => `${normalizeText(option.optionCode).trim()}|${normalizeText(option.optionName).trim()}`)
      .filter((line) => line !== "|")
      .join("\n");

  const buildTemplateItemsFromAIDraftAttributes = (attributes) =>
    (Array.isArray(attributes) ? attributes : [])
      .map((attribute, index) => {
        const code = normalizeText(attribute.code).trim();
        return {
          attributeCode: code,
          isRequired: code === "brand_name" || code === "model_name",
          isSale: false,
          isFilter: true,
          isSearch: code === "brand_name" || code === "model_name" || code === "product_line",
          isDisplay: true,
          sortNo: (index + 1) * 10,
        };
      })
      .filter((row) => row.attributeCode);

  const setAIEditorVisibility = (visible) => {
    aiEditorVisible = Boolean(visible) && Boolean(aiDraftState);
    if (aiLayoutNode instanceof HTMLElement) {
      aiLayoutNode.hidden = !aiEditorVisible;
    }
    const toggleButton = root.querySelector('[data-category-ai-action="toggle-editor"]');
    if (toggleButton instanceof HTMLButtonElement) {
      toggleButton.textContent = aiEditorVisible ? "收起高级编辑" : "展开高级编辑";
    }
  };

  const ensureAIDraftSectionsVisible = (visible) => {
    if (aiDraftSummaryNode instanceof HTMLElement) {
      aiDraftSummaryNode.hidden = !visible;
    }
    setAIEditorVisibility(visible && aiEditorVisible);
    if (aiDraftFieldsNode instanceof HTMLElement) {
      aiDraftFieldsNode.hidden = !visible || !aiEditorVisible;
    }
    if (aiAttributesPanelNode instanceof HTMLElement) {
      aiAttributesPanelNode.hidden = !visible || !aiEditorVisible;
    }
    if (aiTemplatePanelNode instanceof HTMLElement) {
      aiTemplatePanelNode.hidden = !visible || !aiEditorVisible;
    }
  };

  const readAIDraftBaseFromForm = () => {
    if (!(aiForm instanceof HTMLFormElement)) {
      return null;
    }
    const fields = formDataObject(aiForm);
    return {
      category: {
        code: normalizeText(fields.categoryCode).trim(),
        name: normalizeText(fields.categoryName).trim(),
        path: normalizeText(fields.categoryPath).trim(),
        level: Number(fields.categoryLevel || 2),
        status: normalizeText(fields.categoryStatus, "ACTIVE").trim() || "ACTIVE",
      },
      runtime: {
        promptProfile: normalizeText(fields.promptProfile).trim(),
        extractorProfile: normalizeText(fields.extractorProfile).trim() || undefined,
        validatorProfile: normalizeText(fields.validatorProfile).trim() || undefined,
        llmProviderOverride: normalizeText(fields.llmProviderOverride).trim() || undefined,
        llmModelOverride: normalizeText(fields.llmModelOverride).trim() || undefined,
        runtimeStatus: normalizeText(fields.runtimeStatus, "ACTIVE").trim() || "ACTIVE",
        runtimeMetadata: {},
      },
      template: {
        version: Number(fields.templateVersion || 1),
        status: normalizeText(fields.templateStatus, "PUBLISHED").trim() || "PUBLISHED",
        bindAsActiveTemplate: true,
      },
    };
  };

  const writeAIDraftBaseToForm = (draft) => {
    if (!(aiForm instanceof HTMLFormElement) || !draft) {
      return;
    }
    aiForm.elements.categoryCode.value = normalizeText(draft.category?.code);
    aiForm.elements.categoryName.value = normalizeText(draft.category?.name);
    aiForm.elements.categoryPath.value = normalizeText(draft.category?.path);
    aiForm.elements.categoryLevel.value = normalizeText(draft.category?.level, "2");
    aiForm.elements.categoryStatus.value = normalizeText(draft.category?.status, "ACTIVE");
    aiForm.elements.promptProfile.value = normalizeText(draft.runtime?.promptProfile);
    aiForm.elements.extractorProfile.value = normalizeText(draft.runtime?.extractorProfile);
    aiForm.elements.validatorProfile.value = normalizeText(draft.runtime?.validatorProfile);
    aiForm.elements.llmProviderOverride.value = normalizeText(draft.runtime?.llmProviderOverride);
    aiForm.elements.llmModelOverride.value = normalizeText(draft.runtime?.llmModelOverride);
    aiForm.elements.runtimeStatus.value = normalizeText(draft.runtime?.runtimeStatus, "ACTIVE");
    aiForm.elements.templateVersion.value = normalizeText(draft.template?.version, "1");
    aiForm.elements.templateStatus.value = normalizeText(draft.template?.status, "PUBLISHED");
  };

  const normalizeAIDraftInClient = (draft) => {
    const safeDraft = draft && typeof draft === "object" ? draft : {};
    const category = safeDraft.category && typeof safeDraft.category === "object" ? safeDraft.category : {};
    const runtime = safeDraft.runtime && typeof safeDraft.runtime === "object" ? safeDraft.runtime : {};
    const governance = safeDraft.governance && typeof safeDraft.governance === "object" ? safeDraft.governance : {};
    const attributes = Array.isArray(safeDraft.attributes) ? safeDraft.attributes : [];
    const template = safeDraft.template && typeof safeDraft.template === "object" ? safeDraft.template : {};
    const templateItems = Array.isArray(template.items) ? template.items : [];
    const normalizedAttributes = attributes
      .map((row) => ({
        code: normalizeText(row.code).trim(),
        name: normalizeText(row.name).trim(),
        dataType: normalizeText(row.dataType, "TEXT").trim() || "TEXT",
        valueScope: normalizeText(row.valueScope, "SPU").trim() || "SPU",
        unit: normalizeText(row.unit).trim() || "",
        isMulti: Boolean(row.isMulti),
        status: normalizeText(row.status, "ACTIVE").trim() || "ACTIVE",
        options: Array.isArray(row.options) ? row.options : [],
      }))
      .filter((row) => row.code && row.name);
    let normalizedTemplateItems = templateItems
      .map((row, index) => ({
        attributeCode: normalizeText(row.attributeCode).trim(),
        isRequired: Boolean(row.isRequired),
        isSale: Boolean(row.isSale),
        isFilter: row.isFilter === undefined ? true : Boolean(row.isFilter),
        isSearch: Boolean(row.isSearch),
        isDisplay: row.isDisplay === undefined ? true : Boolean(row.isDisplay),
        sortNo: Number(row.sortNo || (index + 1) * 10),
      }))
      .filter((row) => row.attributeCode);
    if (!normalizedTemplateItems.length && normalizedAttributes.length) {
      normalizedTemplateItems = buildTemplateItemsFromAIDraftAttributes(normalizedAttributes);
    }
    return {
      category: {
        code: normalizeText(category.code).trim(),
        name: normalizeText(category.name).trim(),
        path: normalizeText(category.path).trim(),
        level: Number(category.level || 2),
        status: normalizeText(category.status, "ACTIVE").trim() || "ACTIVE",
      },
      runtime: {
        promptProfile: normalizeText(runtime.promptProfile).trim(),
        extractorProfile: normalizeText(runtime.extractorProfile).trim() || undefined,
        validatorProfile: normalizeText(runtime.validatorProfile).trim() || undefined,
        llmProviderOverride: normalizeText(runtime.llmProviderOverride).trim() || undefined,
        llmModelOverride: normalizeText(runtime.llmModelOverride).trim() || undefined,
        runtimeStatus: normalizeText(runtime.runtimeStatus, "ACTIVE").trim() || "ACTIVE",
        runtimeMetadata: runtime.runtimeMetadata && typeof runtime.runtimeMetadata === "object" ? runtime.runtimeMetadata : {},
      },
      attributes: normalizedAttributes,
      template: {
        version: Number(template.version || 1),
        status: normalizeText(template.status, "PUBLISHED").trim() || "PUBLISHED",
        bindAsActiveTemplate: true,
        items: normalizedTemplateItems,
      },
      governance: {
        policyVersion: normalizeText(governance.policyVersion).trim(),
        policyApplied: Boolean(governance.policyApplied),
        policyCode: normalizeText(governance.policyCode).trim(),
        matchedAlias: normalizeText(governance.matchedAlias).trim(),
        inputCategoryCode: normalizeText(governance.inputCategoryCode).trim(),
        canonicalCategoryCode: normalizeText(governance.canonicalCategoryCode).trim(),
        categoryCodeAdjusted: Boolean(governance.categoryCodeAdjusted),
        sanitizationApplied: Boolean(governance.sanitizationApplied),
        removedAttributeCodes: Array.isArray(governance.removedAttributeCodes)
          ? governance.removedAttributeCodes.map((code) => normalizeText(code).trim()).filter(Boolean)
          : [],
        removedTemplateItemCodes: Array.isArray(governance.removedTemplateItemCodes)
          ? governance.removedTemplateItemCodes.map((code) => normalizeText(code).trim()).filter(Boolean)
          : [],
        removedAttributes: Array.isArray(governance.removedAttributes)
          ? governance.removedAttributes
              .map((row) => ({
                code: normalizeText(row?.code).trim(),
                name: normalizeText(row?.name).trim(),
                reason: normalizeText(row?.reason).trim(),
              }))
              .filter((row) => row.code)
          : [],
        decisionLog: Array.isArray(governance.decisionLog)
          ? governance.decisionLog.map((line) => normalizeText(line).trim()).filter(Boolean)
          : [],
        variantSignals: Array.isArray(governance.variantSignals)
          ? governance.variantSignals
              .map((row) => ({
                attributeCode: normalizeText(row.attributeCode).trim(),
                dimensionName: normalizeText(row.dimensionName).trim(),
                optionCodes: Array.isArray(row.optionCodes)
                  ? row.optionCodes.map((code) => normalizeText(code).trim()).filter(Boolean)
                  : [],
              }))
              .filter((row) => row.attributeCode)
          : [],
      },
    };
  };

  const renderAIDraftGovernance = () => {
    if (!(aiGovernanceNode instanceof HTMLElement)) {
      return;
    }
    const governance = aiDraftState?.governance || {};
    const hasPolicy = Boolean(governance && governance.policyApplied);
    const decisionText = (Array.isArray(governance.decisionLog) ? governance.decisionLog : [])
      .map((line) => normalizeText(line).trim())
      .filter(Boolean)
      .join(" / ");
    const variantText = (Array.isArray(governance.variantSignals) ? governance.variantSignals : [])
      .map((row) => `${normalizeText(row.attributeCode)}: ${(Array.isArray(row.optionCodes) ? row.optionCodes : []).join(",") || "-"}`)
      .join(" ; ");
    const removedCodes = Array.isArray(governance?.removedAttributeCodes) ? governance.removedAttributeCodes : [];
    const removedTemplateCodes = Array.isArray(governance?.removedTemplateItemCodes) ? governance.removedTemplateItemCodes : [];
    aiGovernanceNode.innerHTML = `
      <div class="runtime-stat">
        <span>策略版本</span>
        <strong>${safeText(governance.policyVersion, "category_granularity_v1")}</strong>
      </div>
      <div class="runtime-stat">
        <span>Canonical 大类</span>
        <strong>${safeText(governance.canonicalCategoryCode || aiDraftState?.category?.code, "-")}</strong>
      </div>
      <div class="runtime-stat">
        <span>是否归并</span>
        <strong>${safeText(hasPolicy ? (governance.categoryCodeAdjusted ? "是" : "否") : "未命中策略")}</strong>
      </div>
      <div class="runtime-stat">
        <span>变体信号</span>
        <strong>${safeText(variantText || "未识别")}</strong>
      </div>
      <div class="runtime-stat">
        <span>自动净化属性</span>
        <strong>${safeText(removedCodes.length ? removedCodes.join(", ") : "无")}</strong>
      </div>
      <div class="runtime-stat">
        <span>净化模板项</span>
        <strong>${safeText(removedTemplateCodes.length ? removedTemplateCodes.join(", ") : "无")}</strong>
      </div>
      <div class="runtime-stat">
        <span>策略说明</span>
        <strong>${safeText(decisionText || "已命中策略")}</strong>
      </div>
    `;
  };

  const renderAIDraftOverview = () => {
    if (!(aiDraftOverviewNode instanceof HTMLElement)) {
      return;
    }
    if (!aiDraftState) {
      aiDraftOverviewNode.textContent = "";
      return;
    }
    const attributes = Array.isArray(aiDraftState.attributes) ? aiDraftState.attributes : [];
    const templateItems = Array.isArray(aiDraftState.template?.items) ? aiDraftState.template.items : [];
    const governance = aiDraftState.governance || {};
    const removedCodes = Array.isArray(governance.removedAttributeCodes) ? governance.removedAttributeCodes : [];
    const attributePreview = attributes.slice(0, 6).map((row) => normalizeText(row.name || row.code).trim()).filter(Boolean);
    const infoParts = [
      `大类：${normalizeText(aiDraftState.category?.name, aiDraftState.category?.code || "-")}`,
      `属性 ${attributes.length} 个`,
      `模板项 ${templateItems.length} 个`,
      governance.categoryCodeAdjusted ? `已归并到 ${normalizeText(governance.canonicalCategoryCode, "-")}` : null,
      removedCodes.length ? `已自动剔除 ${removedCodes.length} 个跨品类属性` : null,
      attributePreview.length ? `核心字段：${attributePreview.join(" / ")}` : null,
    ].filter(Boolean);
    aiDraftOverviewNode.textContent = infoParts.join(" · ");
  };

  const renderAIDraftAttributes = () => {
    if (!(aiAttributesListNode instanceof HTMLElement)) {
      return;
    }
    const attributes = Array.isArray(aiDraftState?.attributes) ? aiDraftState.attributes : [];
    if (!attributes.length) {
      aiAttributesListNode.innerHTML = '<p class="runtime-panel-text">暂无属性，点击“添加属性”。</p>';
      return;
    }
    aiAttributesListNode.innerHTML = attributes
      .map(
        (row, index) => `
          <details class="ai-draft-row ai-collapsible-row" data-ai-attribute-row="${index}">
            <summary class="ai-draft-row-header">
              <div class="ai-row-summary">
                <strong>${safeText(row.code || `attribute_${index + 1}`)}</strong>
                <span>${safeText(row.name || "未命名")} · ${safeText(row.dataType)} / ${safeText(row.valueScope)}</span>
              </div>
              <button type="button" class="ai-remove-button" data-category-ai-action="remove-attribute" data-index="${index}">移除</button>
            </summary>
            <div class="config-form-grid ai-compact-grid">
              <label class="filter-field">
                <span>Code</span>
                <input type="text" data-ai-attribute-field="code" value="${safeAttr(row.code)}" />
              </label>
              <label class="filter-field">
                <span>Name</span>
                <input type="text" data-ai-attribute-field="name" value="${safeAttr(row.name)}" />
              </label>
              <label class="filter-field">
                <span>Data Type</span>
                <select data-ai-attribute-field="dataType">
                  <option value="TEXT" ${selectedAttr("TEXT", row.dataType)}>TEXT</option>
                  <option value="NUMBER" ${selectedAttr("NUMBER", row.dataType)}>NUMBER</option>
                  <option value="BOOLEAN" ${selectedAttr("BOOLEAN", row.dataType)}>BOOLEAN</option>
                  <option value="ENUM" ${selectedAttr("ENUM", row.dataType)}>ENUM</option>
                  <option value="JSON" ${selectedAttr("JSON", row.dataType)}>JSON</option>
                </select>
              </label>
              <label class="filter-field">
                <span>Value Scope</span>
                <select data-ai-attribute-field="valueScope">
                  <option value="SPU" ${selectedAttr("SPU", row.valueScope)}>SPU</option>
                  <option value="SKU" ${selectedAttr("SKU", row.valueScope)}>SKU</option>
                  <option value="SALE" ${selectedAttr("SALE", row.valueScope)}>SALE</option>
                </select>
              </label>
            </div>
            <details class="ai-inline-advanced">
              <summary>更多字段</summary>
              <div class="config-form-grid ai-compact-grid">
                <label class="filter-field">
                  <span>Unit</span>
                  <input type="text" data-ai-attribute-field="unit" value="${safeAttr(row.unit || "")}" />
                </label>
                <label class="filter-field">
                  <span>Status</span>
                  <select data-ai-attribute-field="status">
                    <option value="ACTIVE" ${selectedAttr("ACTIVE", row.status)}>ACTIVE</option>
                    <option value="DRAFT" ${selectedAttr("DRAFT", row.status)}>DRAFT</option>
                    <option value="DISABLED" ${selectedAttr("DISABLED", row.status)}>DISABLED</option>
                    <option value="DEPRECATED" ${selectedAttr("DEPRECATED", row.status)}>DEPRECATED</option>
                  </select>
                </label>
                <label class="filter-field onboarding-checkbox-field">
                  <span>Is Multi</span>
                  <input type="checkbox" data-ai-attribute-field="isMulti" ${row.isMulti ? "checked" : ""} />
                </label>
              </div>
              <label class="filter-field wide-field">
                <span>Enum Options (每行 code|name)</span>
                <textarea data-ai-attribute-field="optionsText" rows="2">${safeText(formatEnumOptionsText(row.options), "")}</textarea>
              </label>
            </details>
          </details>
        `,
      )
      .join("");
  };

  const renderAIDraftTemplateItems = () => {
    if (!(aiTemplateItemsListNode instanceof HTMLElement)) {
      return;
    }
    const items = Array.isArray(aiDraftState?.template?.items) ? aiDraftState.template.items : [];
    if (!items.length) {
      aiTemplateItemsListNode.innerHTML = '<p class="runtime-panel-text">暂无模板属性，点击“添加模板属性”。</p>';
      return;
    }
    aiTemplateItemsListNode.innerHTML = items
      .map(
        (row, index) => `
          <details class="ai-draft-row ai-template-row ai-collapsible-row" data-ai-template-item-row="${index}">
            <summary class="ai-draft-row-header">
              <div class="ai-row-summary">
                <strong>${safeText(row.attributeCode || `item_${index + 1}`)}</strong>
                <span>required ${row.isRequired ? "yes" : "no"} · sort ${safeText(row.sortNo, (index + 1) * 10)}</span>
              </div>
              <button type="button" class="ai-remove-button" data-category-ai-action="remove-template-item" data-index="${index}">移除</button>
            </summary>
            <div class="config-form-grid ai-compact-grid">
              <label class="filter-field">
                <span>Attribute Code</span>
                <input type="text" data-ai-template-item-field="attributeCode" value="${safeAttr(row.attributeCode)}" />
              </label>
              <label class="filter-field narrow-field">
                <span>SortNo</span>
                <input type="number" min="1" data-ai-template-item-field="sortNo" value="${safeAttr(row.sortNo)}" />
              </label>
              <label class="filter-field onboarding-checkbox-field"><span>Required</span><input type="checkbox" data-ai-template-item-field="isRequired" ${row.isRequired ? "checked" : ""} /></label>
            </div>
            <details class="ai-inline-advanced">
              <summary>更多开关</summary>
              <div class="config-form-grid ai-compact-grid">
                <label class="filter-field onboarding-checkbox-field"><span>Sale</span><input type="checkbox" data-ai-template-item-field="isSale" ${row.isSale ? "checked" : ""} /></label>
                <label class="filter-field onboarding-checkbox-field"><span>Filter</span><input type="checkbox" data-ai-template-item-field="isFilter" ${row.isFilter ? "checked" : ""} /></label>
                <label class="filter-field onboarding-checkbox-field"><span>Search</span><input type="checkbox" data-ai-template-item-field="isSearch" ${row.isSearch ? "checked" : ""} /></label>
                <label class="filter-field onboarding-checkbox-field"><span>Display</span><input type="checkbox" data-ai-template-item-field="isDisplay" ${row.isDisplay ? "checked" : ""} /></label>
              </div>
            </details>
          </details>
        `,
      )
      .join("");
  };

  const renderAIDraft = () => {
    const hasDraft = Boolean(aiDraftState);
    ensureAIDraftSectionsVisible(hasDraft);
    if (!hasDraft) {
      if (aiDraftOverviewNode instanceof HTMLElement) {
        aiDraftOverviewNode.textContent = "";
      }
      if (aiGovernanceNode instanceof HTMLElement) {
        aiGovernanceNode.innerHTML = "";
      }
      if (aiAttributesListNode instanceof HTMLElement) {
        aiAttributesListNode.innerHTML = "";
      }
      if (aiTemplateItemsListNode instanceof HTMLElement) {
        aiTemplateItemsListNode.innerHTML = "";
      }
      return;
    }
    writeAIDraftBaseToForm(aiDraftState);
    renderAIDraftOverview();
    renderAIDraftGovernance();
    renderAIDraftAttributes();
    renderAIDraftTemplateItems();
  };

  const syncAIDraftFromForm = () => {
    if (!aiDraftState) {
      return;
    }
    const base = readAIDraftBaseFromForm();
    if (!base) {
      return;
    }
    aiDraftState.category = base.category;
    aiDraftState.runtime = {
      ...aiDraftState.runtime,
      ...base.runtime,
    };
    aiDraftState.template = {
      ...aiDraftState.template,
      version: base.template.version,
      status: base.template.status,
      bindAsActiveTemplate: true,
      items: Array.isArray(aiDraftState.template?.items) ? aiDraftState.template.items : [],
    };
  };

  const buildAIDraftPayloadForApply = () => {
    if (!aiDraftState) {
      throw new Error("请先点击“AI 生成草案”。");
    }
    syncAIDraftFromForm();
    const attributes = (Array.isArray(aiDraftState.attributes) ? aiDraftState.attributes : [])
      .map((row) => ({
        code: normalizeText(row.code).trim(),
        name: normalizeText(row.name).trim(),
        dataType: normalizeText(row.dataType, "TEXT").trim() || "TEXT",
        valueScope: normalizeText(row.valueScope, "SPU").trim() || "SPU",
        unit: normalizeText(row.unit).trim() || undefined,
        isMulti: Boolean(row.isMulti),
        status: normalizeText(row.status, "ACTIVE").trim() || "ACTIVE",
        options: parseEnumOptions(formatEnumOptionsText(row.options)),
      }))
      .filter((row) => row.code && row.name);
    const attributeCodes = new Set(attributes.map((row) => row.code));
    const items = (Array.isArray(aiDraftState.template?.items) ? aiDraftState.template.items : [])
      .map((row, index) => ({
        attributeCode: normalizeText(row.attributeCode).trim(),
        isRequired: Boolean(row.isRequired),
        isSale: Boolean(row.isSale),
        isFilter: Boolean(row.isFilter),
        isSearch: Boolean(row.isSearch),
        isDisplay: Boolean(row.isDisplay),
        sortNo: Number(row.sortNo || (index + 1) * 10),
      }))
      .filter((row) => row.attributeCode && attributeCodes.has(row.attributeCode));
    if (!items.length) {
      throw new Error("模板至少需要 1 个有效 attributeCode。");
    }
    return {
      category: { ...aiDraftState.category },
      runtime: { ...aiDraftState.runtime, runtimeMetadata: {} },
      attributes,
      governance: aiDraftState.governance || {},
      template: {
        version: Number(aiDraftState.template?.version || 1),
        status: normalizeText(aiDraftState.template?.status, "PUBLISHED").trim() || "PUBLISHED",
        bindAsActiveTemplate: true,
        items,
      },
    };
  };

  const renderWorkflowTemplateDiff = (diffPreview) => {
    if (!(workflowTemplateDiffNode instanceof HTMLElement)) {
      return;
    }
    if (!diffPreview) {
      workflowTemplateDiffNode.innerHTML = '<p class="runtime-panel-text">模板差异会显示在这里。</p>';
      return;
    }
    const changedItems = Array.isArray(diffPreview.changedItems) ? diffPreview.changedItems : [];
    workflowTemplateDiffNode.innerHTML = `
      <div class="config-summary-grid">
        <div class="runtime-stat">
          <span>对比模板</span>
          <strong>${safeText(diffPreview.compareToTemplateId || "active/latest")}</strong>
        </div>
        <div class="runtime-stat">
          <span>新增属性</span>
          <strong>${safeText((diffPreview.addedAttributeCodes || []).join(", "), "0")}</strong>
        </div>
        <div class="runtime-stat">
          <span>移除属性</span>
          <strong>${safeText((diffPreview.removedAttributeCodes || []).join(", "), "0")}</strong>
        </div>
        <div class="runtime-stat">
          <span>变更属性</span>
          <strong>${safeText(changedItems.map((item) => item.attributeCode).join(", "), "0")}</strong>
        </div>
      </div>
    `;
  };

  const renderTemplateOptions = (templates, currentValue = "") => {
    if (!(editForm instanceof HTMLFormElement)) {
      return;
    }
    const selectNode = editForm.elements.activeTemplateId;
    if (!(selectNode instanceof HTMLSelectElement)) {
      return;
    }
    const optionsHtml = [
      `<option value="" ${selectedAttr("", currentValue)}>未绑定</option>`,
      ...templates.map(
        (template) =>
          `<option value="${safeAttr(template.id)}" ${selectedAttr(template.id, currentValue)}>${safeText(
            `v${template.version} · ${template.status}`,
          )}</option>`,
      ),
    ];
    selectNode.innerHTML = optionsHtml.join("");
  };

  const renderWorkflowBindTemplateOptions = (templates, currentValue = "") => {
    if (!(workflowBindForm instanceof HTMLFormElement)) {
      return;
    }
    const selectNode = workflowBindForm.elements.templateId;
    if (!(selectNode instanceof HTMLSelectElement)) {
      return;
    }
    const optionsHtml = [
      `<option value="" ${selectedAttr("", currentValue)}>请选择模板</option>`,
      ...(Array.isArray(templates) ? templates : []).map(
        (template) =>
          `<option value="${safeAttr(template.id)}" ${selectedAttr(template.id, currentValue)}>${safeText(
            `${template.id} · v${template.version} · ${template.status}`,
          )}</option>`,
      ),
    ];
    selectNode.innerHTML = optionsHtml.join("");
  };

  const renderSummary = (item) => {
    if (!(summaryNode instanceof HTMLElement)) {
      return;
    }
    if (!item) {
      summaryNode.innerHTML = `
        <p class="runtime-panel-text">
          选择左侧大类后，这里会显示 legacy 业务域、已有模板和 runtime 绑定信息。属性不在本页直接创建，请先到
          <a href="/config/attributes">属性管理</a> 与
          <a href="/config/templates">模板配置</a> 完成属性与模板编排，再回到本页绑定 active template。
        </p>
      `;
      return;
    }
    const runtime = item.runtimeProfile || {};
    const legacyDomains = Array.isArray(item.legacyBusinessDomains) ? item.legacyBusinessDomains : [];
    summaryNode.innerHTML = `
      <div class="config-summary-grid">
        <div class="runtime-stat">
          <span>Legacy 业务域</span>
          <strong>${safeText(legacyDomains.join(" / "), "-")}</strong>
        </div>
        <div class="runtime-stat">
          <span>模板数</span>
          <strong>${safeText(item.templateCount, "0")}</strong>
        </div>
        <div class="runtime-stat">
          <span>当前模板</span>
          <strong>${safeText(runtime.activeTemplateId, "未绑定")}</strong>
        </div>
        <div class="runtime-stat">
          <span>推荐 Prompt</span>
          <strong>${safeText(item.recommendedPromptProfile, "-")}</strong>
        </div>
        <div class="runtime-stat">
          <span>具体品类 / 型号数</span>
          <strong>${safeText(item.modelCount, "0")}</strong>
        </div>
      </div>
      <p class="runtime-panel-text">
        当前大类下的具体品类/型号词典在
        <a href="${safeAttr(modelConfigHref(item.code))}">型号库页</a>
        维护；specs 会用这层 alias 词典去识别真实型号。
      </p>
    `;
  };

  const renderStudioContext = (item) => {
    if (studioTitleNode instanceof HTMLElement) {
      studioTitleNode.textContent = item
        ? `${normalizeText(item.name)} 的配置工作台`
        : "先在左侧选择一个大类";
    }
    if (studioDescriptionNode instanceof HTMLElement) {
      studioDescriptionNode.textContent = item
        ? `当前正在维护 ${normalizeText(item.name)}（${normalizeText(item.code)}）的 runtime、模板和型号上下文。进入模板页或型号库时，会自动带上这个大类过滤。`
        : "选中大类后，右侧所有动作都会围绕这个大类展开。这样你随时都知道是在改全局能力，还是在改当前大类的运行配置。";
    }
    categoryContextLinkNodes.forEach((node) => {
      if (!(node instanceof HTMLAnchorElement)) {
        return;
      }
      const kind = normalizeText(node.dataset.categoryContextLink).trim();
      if (kind === "templates") {
        node.href = templateConfigHref(item?.code);
        return;
      }
      if (kind === "models") {
        node.href = modelConfigHref(item?.code);
      }
    });
    if (categoryEditorHintNode instanceof HTMLElement) {
      categoryEditorHintNode.textContent = item
        ? `当前编辑对象是 ${normalizeText(item.name)}。基础档案只维护 runtime / prompt / active template，属性和模板的增删统一走上方工作流。`
        : "这里专门维护当前大类的 runtime profile、prompt profile 和 active template。属性与模板的创建，统一从上面的工作流入口进入。";
    }
  };

  const renderModelLinks = (item) => {
    const href = modelConfigHref(item?.code);
    categoryModelLinkNodes.forEach((node) => {
      if (node instanceof HTMLAnchorElement) {
        node.href = href;
      }
    });
    if (categoryModelCountBadge instanceof HTMLElement) {
      categoryModelCountBadge.textContent = item
        ? `已维护 ${normalizeText(item.modelCount, "0")} 个型号`
        : "未选择大类";
    }
  };

  const renderWorkflow = (item) => {
    renderStudioContext(item);
    if (workflowContextNode instanceof HTMLElement) {
      workflowContextNode.textContent = item ? `${normalizeText(item.name)} (${normalizeText(item.code)})` : "未选择大类";
    }

    if (!(workflowSummaryNode instanceof HTMLElement)) {
      return;
    }
    if (!item) {
      workflowSummaryNode.innerHTML = `
        <p class="runtime-panel-text">
          先在左侧列表选择一个大类。然后依次完成：创建属性 -> 创建模板并绑定属性 -> 绑定模板到当前大类 runtime -> 补齐该大类下的具体品类/型号库。
        </p>
      `;
      if (workflowTemplateForm instanceof HTMLFormElement) {
        workflowTemplateForm.reset();
        workflowTemplateForm.elements.categoryId.value = "";
        workflowTemplateForm.elements.categoryCode.value = "";
        workflowTemplateForm.elements.version.value = "1";
        workflowTemplateForm.elements.status.value = "DRAFT";
      }
      if (workflowBindForm instanceof HTMLFormElement) {
        workflowBindForm.reset();
      }
      renderModelLinks(null);
      renderWorkflowBindTemplateOptions([]);
      renderWorkflowTemplateDiff(null);
      return;
    }

    const runtime = item.runtimeProfile || {};
    const promptProfile = normalizeText(runtime.promptProfile, item.recommendedPromptProfile || "");
    const hasTemplate = Number(item.templateCount || 0) > 0;
    const hasActiveTemplate = Boolean(runtime.activeTemplateId);
    workflowSummaryNode.innerHTML = `
      <div class="config-summary-grid">
        <div class="runtime-stat">
          <span>Step 1 属性字典</span>
          <strong>已开启（全局属性池）</strong>
        </div>
        <div class="runtime-stat">
          <span>Step 2 模板状态</span>
          <strong>${safeText(hasTemplate ? `已有 ${item.templateCount} 个模板` : "尚未创建模板")}</strong>
        </div>
        <div class="runtime-stat">
          <span>Step 3 Active 绑定</span>
          <strong>${safeText(hasActiveTemplate ? runtime.activeTemplateId : "未绑定")}</strong>
        </div>
        <div class="runtime-stat">
          <span>Prompt Profile</span>
          <strong>${safeText(promptProfile, "-")}</strong>
        </div>
        <div class="runtime-stat">
          <span>Step 4 型号库</span>
          <strong>${safeText(Number(item.modelCount || 0) > 0 ? `已维护 ${item.modelCount} 个型号` : "尚未维护型号库")}</strong>
        </div>
      </div>
      <p class="runtime-panel-text">
        这个大类下的“具体品类”当前是通过型号库表达的。点击
        <a href="${safeAttr(modelConfigHref(item.code))}">进入型号库</a>
        ，会自动按当前大类过滤。
      </p>
    `;

    if (workflowTemplateForm instanceof HTMLFormElement) {
      workflowTemplateForm.elements.categoryId.value = normalizeText(item.id);
      workflowTemplateForm.elements.categoryCode.value = normalizeText(item.code);
      workflowTemplateForm.elements.version.value = "1";
      workflowTemplateForm.elements.status.value = "DRAFT";
      workflowTemplateForm.elements.promptProfile.value = promptProfile;
      workflowTemplateForm.elements.bindAsActiveTemplate.checked = false;
      workflowTemplateForm.elements.itemsText.value = buildPresetTemplateItemsText(promptProfile);
    }
    renderWorkflowTemplateDiff(null);

    if (workflowBindForm instanceof HTMLFormElement) {
      workflowBindForm.elements.promptProfile.value = promptProfile;
      renderWorkflowBindTemplateOptions(item.templateOptions || [], runtime.activeTemplateId || "");
    }
    renderModelLinks(item);
  };

  const getSelectedCategory = () => categoryItems.find((item) => item.id === selectedCategoryId) || null;
  const resolveOperatorId = () => normalizeText(formDataObject(controlsForm).operatorId).trim();

  const requireSelectedCategory = (actionLabel) => {
    const selected = getSelectedCategory();
    if (!selected) {
      throw new Error(`请先在左侧选择大类，再执行“${actionLabel}”。`);
    }
    return selected;
  };

  const resetForm = () => {
    if (!(editForm instanceof HTMLFormElement)) {
      return;
    }
    editForm.reset();
    editForm.elements.categoryId.value = "";
    editForm.elements.level.value = "2";
    editForm.elements.status.value = "ACTIVE";
    editForm.elements.runtimeStatus.value = "ACTIVE";
    editForm.elements.runtimeMetadata.value = "{}";
    renderTemplateOptions([]);
    renderSummary(null);
    renderWorkflow(null);
    selectedCategoryId = null;
  };

  const loadCategoryIntoForm = (item) => {
    if (!(editForm instanceof HTMLFormElement) || !item) {
      return;
    }
    selectedCategoryId = item.id;
    editForm.elements.categoryId.value = normalizeText(item.id);
    editForm.elements.code.value = normalizeText(item.code);
    editForm.elements.name.value = normalizeText(item.name);
    editForm.elements.path.value = normalizeText(item.path);
    editForm.elements.level.value = normalizeText(item.level, "2");
    editForm.elements.status.value = normalizeText(item.status, "ACTIVE");
    editForm.elements.promptProfile.value = normalizeText(
      item.runtimeProfile?.promptProfile,
      item.recommendedPromptProfile || "",
    );
    editForm.elements.extractorProfile.value = normalizeText(item.runtimeProfile?.extractorProfile);
    editForm.elements.validatorProfile.value = normalizeText(item.runtimeProfile?.validatorProfile);
    editForm.elements.llmProviderOverride.value = normalizeText(item.runtimeProfile?.llmProviderOverride);
    editForm.elements.llmModelOverride.value = normalizeText(item.runtimeProfile?.llmModelOverride);
    editForm.elements.runtimeStatus.value = normalizeText(item.runtimeProfile?.status, "ACTIVE");
    editForm.elements.runtimeMetadata.value = JSON.stringify(item.runtimeProfile?.metadata || {}, null, 2);
    renderTemplateOptions(item.templateOptions || [], item.runtimeProfile?.activeTemplateId || "");
    renderSummary(item);
    renderWorkflow(item);
  };

  const renderList = () => {
    if (!(listNode instanceof HTMLElement)) {
      return;
    }
    if (!categoryItems.length) {
      listNode.innerHTML = `
        <article class="panel compact-panel">
          <p class="eyebrow">空列表</p>
          <h3>当前没有大类配置</h3>
          <p class="runtime-panel-text">点击上方“新建大类”，可以开始配置新的大类与 runtime profile。</p>
        </article>
      `;
      return;
    }
    listNode.innerHTML = categoryItems
      .map((item) => {
        const activeClass = item.id === selectedCategoryId ? "is-active" : "";
        const runtime = item.runtimeProfile || {};
        return `
          <button type="button" class="config-list-item ${activeClass}" data-category-select="${safeAttr(item.id)}">
            <div class="config-list-head">
              <div>
                <p class="eyebrow">${safeText(item.code)}</p>
                <h3>${safeText(item.name)}</h3>
              </div>
              <span class="status-pill">${safeText(item.status)}</span>
            </div>
            <p class="runtime-panel-text">${safeText(item.path)}</p>
            <div class="config-list-meta">
              <span>模板 ${safeText(item.templateCount, "0")}</span>
              <span>型号 ${safeText(item.modelCount, "0")}</span>
              <span>Prompt ${safeText(runtime.promptProfile || item.recommendedPromptProfile, "-")}</span>
            </div>
          </button>
        `;
      })
      .join("");
  };

  const loadList = async () => {
    const filters = formDataObject(controlsForm);
    const query = new URLSearchParams();
    if (normalizeText(filters.status).trim()) {
      query.set("status", normalizeText(filters.status).trim());
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    const payload = await fetchJson(`/api/config/categories${suffix}`);
    categoryItems = Array.isArray(payload.items) ? payload.items : [];
    if (totalNode instanceof HTMLElement) {
      totalNode.textContent = `${categoryItems.length} 个大类`;
    }
    let matched = null;
    if (selectedCategoryId) {
      matched = categoryItems.find((item) => item.id === selectedCategoryId) || null;
    } else if (!preferredCategoryCodeApplied && preferredCategoryCode) {
      matched = categoryItems.find((item) => normalizeText(item.code).trim() === preferredCategoryCode) || null;
      preferredCategoryCodeApplied = true;
    }
    if (matched) {
      loadCategoryIntoForm(matched);
    } else if (selectedCategoryId) {
      selectedCategoryId = null;
      renderSummary(null);
      renderWorkflow(null);
    }
    if (!matched && !selectedCategoryId) {
      renderModelLinks(null);
    }
    renderList();
  };

  const collectPayload = (overrides = null) => {
    if (!(controlsForm instanceof HTMLFormElement) || !(editForm instanceof HTMLFormElement)) {
      return null;
    }
    const operatorFields = formDataObject(controlsForm);
    const categoryFields = formDataObject(editForm);
    let runtimeMetadata = {};
    try {
      runtimeMetadata = JSON.parse(normalizeText(categoryFields.runtimeMetadata, "{}") || "{}");
    } catch (_error) {
      throw new Error("Runtime Metadata 必须是合法 JSON。");
    }
    const payload = {
      categoryId: normalizeText(categoryFields.categoryId).trim() || undefined,
      code: normalizeText(categoryFields.code).trim(),
      name: normalizeText(categoryFields.name).trim(),
      path: normalizeText(categoryFields.path).trim(),
      level: Number(categoryFields.level || 2),
      status: normalizeText(categoryFields.status, "ACTIVE").trim() || "ACTIVE",
      promptProfile: normalizeText(categoryFields.promptProfile).trim() || undefined,
      activeTemplateId: normalizeText(categoryFields.activeTemplateId).trim() || undefined,
      extractorProfile: normalizeText(categoryFields.extractorProfile).trim() || undefined,
      validatorProfile: normalizeText(categoryFields.validatorProfile).trim() || undefined,
      llmProviderOverride: normalizeText(categoryFields.llmProviderOverride).trim() || undefined,
      llmModelOverride: normalizeText(categoryFields.llmModelOverride).trim() || undefined,
      runtimeStatus: normalizeText(categoryFields.runtimeStatus, "ACTIVE").trim() || "ACTIVE",
      runtimeMetadata,
    };
    return {
      operatorId: normalizeText(operatorFields.operatorId).trim(),
      payload: {
        ...payload,
        ...(overrides || {}),
      },
    };
  };

  const savePayload = async (apply, overrides = null) => {
    const requestBody = collectPayload(overrides);
    if (!requestBody) {
      return;
    }
    if (!requestBody.operatorId) {
      throw new Error("Operator 不能为空。");
    }
    const payload = await fetchJson("/api/config/categories", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        operatorId: requestBody.operatorId,
        apply,
        payload: requestBody.payload,
      }),
    });
    setFeedback(
      apply
        ? `大类配置已保存：${normalizeText(payload?.category?.name, payload?.category?.code)}`
        : `预演成功：${normalizeText(payload?.category?.name, payload?.category?.code)}`,
      "success",
    );
    await loadList();
    if (payload?.category?.id) {
      selectedCategoryId = payload.category.id;
      const matched = categoryItems.find((item) => item.id === selectedCategoryId);
      if (matched) {
        loadCategoryIntoForm(matched);
      }
    }
  };

  const savePayloadFromCategorySnapshot = async (item, apply, overrides = null) => {
    const operatorId = resolveOperatorId();
    if (!operatorId) {
      throw new Error("Operator 不能为空。");
    }
    const runtime = item?.runtimeProfile || {};
    const basePayload = {
      categoryId: normalizeText(item?.id).trim() || undefined,
      code: normalizeText(item?.code).trim(),
      name: normalizeText(item?.name).trim(),
      path: normalizeText(item?.path).trim(),
      level: Number(item?.level || 2),
      status: normalizeText(item?.status, "ACTIVE").trim() || "ACTIVE",
      promptProfile:
        normalizeText(runtime.promptProfile, item?.recommendedPromptProfile || "").trim() || undefined,
      activeTemplateId: normalizeText(runtime.activeTemplateId).trim() || undefined,
      extractorProfile: normalizeText(runtime.extractorProfile).trim() || undefined,
      validatorProfile: normalizeText(runtime.validatorProfile).trim() || undefined,
      llmProviderOverride: normalizeText(runtime.llmProviderOverride).trim() || undefined,
      llmModelOverride: normalizeText(runtime.llmModelOverride).trim() || undefined,
      runtimeStatus: normalizeText(runtime.status, "ACTIVE").trim() || "ACTIVE",
      runtimeMetadata: runtime.metadata && typeof runtime.metadata === "object" ? runtime.metadata : {},
    };
    const result = await fetchJson("/api/config/categories", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        operatorId,
        apply,
        payload: {
          ...basePayload,
          ...(overrides || {}),
        },
      }),
    });
    await loadList();
    if (result?.category?.id) {
      selectedCategoryId = result.category.id;
      const matched = categoryItems.find((row) => row.id === selectedCategoryId);
      if (matched) {
        loadCategoryIntoForm(matched);
      }
    }
    return result;
  };

  const appendAttributeToWorkflowTemplate = (attributeCode) => {
    if (!(workflowTemplateForm instanceof HTMLFormElement)) {
      return;
    }
    const area = workflowTemplateForm.elements.itemsText;
    if (!(area instanceof HTMLTextAreaElement)) {
      return;
    }
    const currentItems = parseTemplateItemsText(area.value);
    if (currentItems.some((item) => item.attributeCode === attributeCode)) {
      return;
    }
    const maxSort = currentItems.reduce((max, item) => Math.max(max, Number(item.sortNo || 0)), 0);
    currentItems.push({
      attributeCode,
      isRequired: false,
      isSale: false,
      isFilter: true,
      isSearch: true,
      isDisplay: true,
      sortNo: maxSort > 0 ? maxSort + 10 : 10,
    });
    area.value = formatTemplateItemsText(currentItems);
  };

  const saveWorkflowAttribute = async (apply) => {
    if (!(workflowAttributeForm instanceof HTMLFormElement)) {
      return;
    }
    const operatorId = resolveOperatorId();
    if (!operatorId) {
      throw new Error("Operator 不能为空。");
    }
    const fields = formDataObject(workflowAttributeForm);
    const payload = {
      code: normalizeText(fields.code).trim(),
      name: normalizeText(fields.name).trim(),
      scopeType: "PLATFORM",
      scopeId: "platform",
      dataType: normalizeText(fields.dataType, "TEXT").trim() || "TEXT",
      valueScope: normalizeText(fields.valueScope, "SPU").trim() || "SPU",
      unit: normalizeText(fields.unit).trim() || undefined,
      status: normalizeText(fields.status, "ACTIVE").trim() || "ACTIVE",
      isMulti: workflowAttributeForm.elements.isMulti.checked,
      options: parseEnumOptions(fields.optionsText),
    };
    if (!payload.code || !payload.name) {
      throw new Error("Attribute Code 和 Attribute Name 不能为空。");
    }
    const result = await fetchJson("/api/config/attributes", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        operatorId,
        apply,
        payload,
      }),
    });
    if (apply) {
      appendAttributeToWorkflowTemplate(payload.code);
    }
    setFeedback(
      apply
        ? `属性已创建：${normalizeText(result?.attribute?.code, payload.code)}`
        : `属性预演成功：${normalizeText(result?.attribute?.code, payload.code)}`,
      "success",
    );
  };

  const collectWorkflowTemplatePayload = () => {
    if (!(workflowTemplateForm instanceof HTMLFormElement)) {
      return null;
    }
    const selected = requireSelectedCategory("创建模板");
    const fields = formDataObject(workflowTemplateForm);
    const items = parseTemplateItemsText(fields.itemsText);
    if (!items.length) {
      throw new Error("Template Items 不能为空，至少要有一个 attributeCode。");
    }
    return {
      categoryId: normalizeText(fields.categoryId).trim() || normalizeText(selected.id).trim(),
      categoryCode: normalizeText(fields.categoryCode).trim() || normalizeText(selected.code).trim(),
      version: Number(fields.version || 1),
      status: normalizeText(fields.status, "DRAFT").trim() || "DRAFT",
      promptProfile: normalizeText(fields.promptProfile).trim() || undefined,
      bindAsActiveTemplate: workflowTemplateForm.elements.bindAsActiveTemplate.checked,
      items,
    };
  };

  const previewWorkflowTemplateDiff = async () => {
    const payload = collectWorkflowTemplatePayload();
    if (!payload) {
      return;
    }
    const result = await fetchJson("/api/config/templates/diff-preview", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ payload }),
    });
    renderWorkflowTemplateDiff(result);
    setFeedback("模板差异已生成。", "success");
  };

  const saveWorkflowTemplate = async (apply) => {
    const payload = collectWorkflowTemplatePayload();
    if (!payload) {
      return;
    }
    const operatorId = resolveOperatorId();
    if (!operatorId) {
      throw new Error("Operator 不能为空。");
    }
    const result = await fetchJson("/api/config/templates", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        operatorId,
        apply,
        payload,
      }),
    });
    renderWorkflowTemplateDiff(result?.diffPreview || null);
    setFeedback(
      apply
        ? `模板已保存：${normalizeText(result?.template?.id)}`
        : `模板预演成功：${normalizeText(result?.template?.id)}`,
      "success",
    );
    await loadList();
    const selected = getSelectedCategory();
    if (selected) {
      loadCategoryIntoForm(selected);
      renderList();
    }
  };

  const bindWorkflowTemplate = async (apply) => {
    if (!(workflowBindForm instanceof HTMLFormElement)) {
      return;
    }
    const selected = requireSelectedCategory("绑定模板");
    const fields = formDataObject(workflowBindForm);
    const templateId = normalizeText(fields.templateId).trim();
    if (!templateId) {
      throw new Error("请选择要绑定的模板。");
    }
    const promptProfile = normalizeText(fields.promptProfile).trim();
    const overrides = {
      categoryId: normalizeText(selected.id).trim(),
      activeTemplateId: templateId,
      promptProfile: promptProfile || normalizeText(selected.runtimeProfile?.promptProfile, selected.recommendedPromptProfile || ""),
    };
    await savePayloadFromCategorySnapshot(selected, apply, overrides);
    setFeedback(apply ? "模板绑定已保存。" : "模板绑定预演成功。", "success");
  };

  root.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const workflowOpenButton = target.closest("[data-category-workflow-open]");
    if (workflowOpenButton instanceof HTMLElement) {
      const kind = normalizeText(workflowOpenButton.dataset.categoryWorkflowOpen).trim();
      try {
        if (kind === "template" || kind === "bind") {
          requireSelectedCategory(kind === "template" ? "创建模板" : "绑定模板");
        }
        openWorkflowModal(kind);
      } catch (error) {
        setFeedback(error instanceof Error ? error.message : "操作失败。", "error");
      }
      return;
    }

    const workflowModalCloseButton = target.closest("[data-category-workflow-modal-close]");
    if (workflowModalCloseButton instanceof HTMLElement) {
      const modal = workflowModalCloseButton.closest("[data-category-workflow-modal]");
      closeWorkflowModal(modal instanceof HTMLElement ? modal : null);
      return;
    }

    const aiActionButton = target.closest("[data-category-ai-action]");
    if (aiActionButton instanceof HTMLElement) {
      const action = normalizeText(aiActionButton.dataset.categoryAiAction).trim();
      if (
        (action === "remove-attribute" || action === "remove-template-item")
        && aiActionButton.closest("summary")
        && event instanceof MouseEvent
      ) {
        event.preventDefault();
      }
      try {
        if (action === "generate") {
          if (!(aiForm instanceof HTMLFormElement)) {
            return;
          }
          const description = normalizeText(aiForm.elements.description.value).trim();
          if (!description) {
            throw new Error("请先输入自然语言描述。");
          }
          setAIFeedback("AI 正在生成草案...", "info");
          const payload = await fetchJson("/api/config/categories/ai-draft", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              description,
            }),
          });
          aiDraftState = normalizeAIDraftInClient(payload?.draft || {});
          aiEditorVisible = false;
          renderAIDraft();
          setAIFeedback("草案已生成，可修改后确认创建。", "success");
          return;
        }
        if (action === "toggle-editor") {
          if (!aiDraftState) {
            throw new Error("请先生成 AI 草案。");
          }
          setAIEditorVisibility(!aiEditorVisible);
          return;
        }
        if (action === "add-attribute") {
          if (!aiDraftState) {
            throw new Error("请先生成 AI 草案。");
          }
          aiDraftState.attributes = Array.isArray(aiDraftState.attributes) ? aiDraftState.attributes : [];
          aiDraftState.attributes.push({
            code: "",
            name: "",
            dataType: "TEXT",
            valueScope: "SPU",
            unit: "",
            isMulti: false,
            status: "ACTIVE",
            options: [],
          });
          renderAIDraft();
          return;
        }
        if (action === "remove-attribute") {
          if (!aiDraftState) {
            return;
          }
          const index = Number(aiActionButton.dataset.index);
          if (!Number.isFinite(index) || index < 0) {
            return;
          }
          aiDraftState.attributes = (Array.isArray(aiDraftState.attributes) ? aiDraftState.attributes : []).filter(
            (_row, rowIndex) => rowIndex !== index,
          );
          const remainingCodes = new Set(aiDraftState.attributes.map((row) => normalizeText(row.code).trim()));
          aiDraftState.template.items = (Array.isArray(aiDraftState.template?.items) ? aiDraftState.template.items : []).filter(
            (row) => remainingCodes.has(normalizeText(row.attributeCode).trim()),
          );
          renderAIDraft();
          return;
        }
        if (action === "add-template-item") {
          if (!aiDraftState) {
            throw new Error("请先生成 AI 草案。");
          }
          aiDraftState.template.items = Array.isArray(aiDraftState.template?.items) ? aiDraftState.template.items : [];
          aiDraftState.template.items.push({
            attributeCode: "",
            isRequired: false,
            isSale: false,
            isFilter: true,
            isSearch: false,
            isDisplay: true,
            sortNo: (aiDraftState.template.items.length + 1) * 10,
          });
          renderAIDraft();
          return;
        }
        if (action === "remove-template-item") {
          if (!aiDraftState) {
            return;
          }
          const index = Number(aiActionButton.dataset.index);
          if (!Number.isFinite(index) || index < 0) {
            return;
          }
          aiDraftState.template.items = (
            Array.isArray(aiDraftState.template?.items) ? aiDraftState.template.items : []
          ).filter((_row, rowIndex) => rowIndex !== index);
          renderAIDraft();
          return;
        }
        if (action === "sync-template-items") {
          if (!aiDraftState) {
            throw new Error("请先生成 AI 草案。");
          }
          aiDraftState.template.items = buildTemplateItemsFromAIDraftAttributes(aiDraftState.attributes);
          renderAIDraft();
          setAIFeedback("模板属性已按属性列表重建。", "success");
          return;
        }
        if (action === "apply-dry-run" || action === "apply") {
          const operatorId = resolveOperatorId();
          if (!operatorId) {
            throw new Error("Operator 不能为空。");
          }
          const draftPayload = buildAIDraftPayloadForApply();
          const aiFields = formDataObject(aiForm);
          const allowExistingCategoryUpdate = Boolean(aiFields.allowExistingCategoryUpdate);
          const allowActiveTemplateRebind = Boolean(aiFields.allowActiveTemplateRebind);
          setAIFeedback(action === "apply" ? "正在创建并绑定模板..." : "正在预演创建...", "info");
          const result = await fetchJson("/api/config/categories/ai-apply", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              operatorId,
              apply: action === "apply",
              allowExistingCategoryUpdate,
              allowActiveTemplateRebind,
              draft: draftPayload,
            }),
          });
          if (action === "apply") {
            const bindTip = result?.bindRequested && !result?.bindApplied ? "（已创建模板，但未切 Active）" : "";
            setAIFeedback(
              `创建完成：${normalizeText(result?.category?.name, result?.category?.code)}，模板 ${normalizeText(
                result?.template?.id,
                "-",
              )}${bindTip}`,
              "success",
            );
            selectedCategoryId = normalizeText(result?.category?.id).trim() || selectedCategoryId;
            await loadList();
            renderList();
            closeWorkflowModal(getWorkflowModal("ai"));
            setFeedback(
              result?.bindRequested && !result?.bindApplied
                ? "AI 建类已完成：属性和模板已创建，Active 模板保持不变。"
                : "AI 建类已完成：属性已创建，模板已绑定。",
              "success",
            );
          } else {
            setAIFeedback("预演通过，可点击一键确认创建。", "success");
          }
          return;
        }
      } catch (error) {
        setAIFeedback(error instanceof Error ? error.message : "AI 操作失败。", "error");
      }
      return;
    }

    const selectButton = target.closest("[data-category-select]");
    if (selectButton instanceof HTMLElement) {
      const categoryId = normalizeText(selectButton.dataset.categorySelect).trim();
      const matched = categoryItems.find((item) => item.id === categoryId);
      if (matched) {
        loadCategoryIntoForm(matched);
        renderList();
      }
      return;
    }

    const workflowActionButton = target.closest("[data-category-workflow-action]");
    if (workflowActionButton instanceof HTMLElement) {
      const action = normalizeText(workflowActionButton.dataset.categoryWorkflowAction).trim();
      try {
        if (action === "attribute-dry-run") {
          setFeedback("正在预演创建属性...", "info");
          await saveWorkflowAttribute(false);
          return;
        }
        if (action === "attribute-apply") {
          setFeedback("正在创建属性...", "info");
          await saveWorkflowAttribute(true);
          closeWorkflowModal(getWorkflowModal("attribute"));
          return;
        }
        if (action === "template-fill-preset") {
          const selected = requireSelectedCategory("填入推荐属性");
          if (workflowTemplateForm instanceof HTMLFormElement) {
            const promptProfile =
              normalizeText(workflowTemplateForm.elements.promptProfile.value).trim()
              || normalizeText(selected.runtimeProfile?.promptProfile, selected.recommendedPromptProfile || "");
            workflowTemplateForm.elements.itemsText.value = buildPresetTemplateItemsText(promptProfile);
          }
          setFeedback("已填入推荐模板属性。", "success");
          return;
        }
        if (action === "template-diff-preview") {
          setFeedback("正在生成模板差异...", "info");
          await previewWorkflowTemplateDiff();
          return;
        }
        if (action === "template-dry-run") {
          setFeedback("正在预演模板保存...", "info");
          await saveWorkflowTemplate(false);
          return;
        }
        if (action === "template-apply") {
          setFeedback("正在创建模板...", "info");
          await saveWorkflowTemplate(true);
          closeWorkflowModal(getWorkflowModal("template"));
          return;
        }
        if (action === "bind-dry-run") {
          setFeedback("正在预演模板绑定...", "info");
          await bindWorkflowTemplate(false);
          return;
        }
        if (action === "bind-apply") {
          setFeedback("正在绑定模板到当前大类...", "info");
          await bindWorkflowTemplate(true);
          closeWorkflowModal(getWorkflowModal("bind"));
        }
      } catch (error) {
        setFeedback(error instanceof Error ? error.message : "操作失败。", "error");
      }
      return;
    }

    const actionButton = target.closest("[data-category-config-action]");
    if (!(actionButton instanceof HTMLElement)) {
      return;
    }
    const action = normalizeText(actionButton.dataset.categoryConfigAction).trim();
    try {
      if (action === "new") {
        resetForm();
        renderList();
        openWorkflowModal("category-editor");
        if (editForm instanceof HTMLFormElement) {
          const codeInput = editForm.elements.code;
          if (codeInput instanceof HTMLInputElement) {
            window.setTimeout(() => codeInput.focus(), 60);
          }
        }
        setFeedback("已切到新建模式：请在弹窗里先保存大类，再继续 Step 1/2/3。", "info");
        return;
      }
      if (action === "refresh") {
        setFeedback("正在刷新大类列表...", "info");
        await loadList();
        setFeedback("大类列表已刷新。", "success");
        return;
      }
      if (action === "save-dry-run") {
        setFeedback("正在预演保存...", "info");
        await savePayload(false);
        return;
      }
      if (action === "save-apply") {
        setFeedback("正在正式保存...", "info");
        await savePayload(true);
        const inModal = target.closest("[data-category-workflow-modal]");
        if (inModal instanceof HTMLElement) {
          closeWorkflowModal(inModal);
        }
      }
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "操作失败。", "error");
    }
  });

  root.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement) || !aiDraftState) {
      return;
    }
    if (!(aiForm instanceof HTMLFormElement)) {
      return;
    }
    if (!aiForm.contains(target)) {
      return;
    }

    const attributeRow = target.closest("[data-ai-attribute-row]");
    if (attributeRow instanceof HTMLElement) {
      const index = Number(attributeRow.dataset.aiAttributeRow);
      if (!Number.isFinite(index) || index < 0 || index >= aiDraftState.attributes.length) {
        return;
      }
      const field = target.getAttribute("data-ai-attribute-field");
      if (!field) {
        return;
      }
      if (field === "isMulti" && target instanceof HTMLInputElement) {
        aiDraftState.attributes[index].isMulti = target.checked;
        renderAIDraftOverview();
        return;
      }
      if (field === "optionsText" && target instanceof HTMLTextAreaElement) {
        aiDraftState.attributes[index].options = parseEnumOptions(target.value);
        renderAIDraftOverview();
        return;
      }
      if ((target instanceof HTMLInputElement) || (target instanceof HTMLSelectElement)) {
        aiDraftState.attributes[index][field] = target.value;
      }
      renderAIDraftOverview();
      return;
    }

    const templateRow = target.closest("[data-ai-template-item-row]");
    if (templateRow instanceof HTMLElement) {
      const index = Number(templateRow.dataset.aiTemplateItemRow);
      const templateItems = Array.isArray(aiDraftState.template?.items) ? aiDraftState.template.items : [];
      if (!Number.isFinite(index) || index < 0 || index >= templateItems.length) {
        return;
      }
      const field = target.getAttribute("data-ai-template-item-field");
      if (!field) {
        return;
      }
      if (target instanceof HTMLInputElement && target.type === "checkbox") {
        templateItems[index][field] = target.checked;
        renderAIDraftOverview();
        return;
      }
      if (field === "sortNo" && target instanceof HTMLInputElement) {
        templateItems[index].sortNo = Number(target.value || (index + 1) * 10);
        renderAIDraftOverview();
        return;
      }
      if (target instanceof HTMLInputElement) {
        templateItems[index][field] = target.value;
      }
      renderAIDraftOverview();
      return;
    }

    syncAIDraftFromForm();
    renderAIDraftOverview();
  });

  root.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement) || !aiDraftState) {
      return;
    }
    if (!(aiForm instanceof HTMLFormElement)) {
      return;
    }
    if (!aiForm.contains(target)) {
      return;
    }
    syncAIDraftFromForm();
    renderAIDraftOverview();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    if (!(activeWorkflowModal instanceof HTMLElement)) {
      return;
    }
    closeWorkflowModal(activeWorkflowModal);
  });

  ensureAIDraftSectionsVisible(false);
  setAIFeedback("输入自然语言后点击“AI 生成草案”。", "info");
  resetForm();
  loadList()
    .then(() => {
      setFeedback("大类配置已加载。", "success");
    })
    .catch((error) => {
      setFeedback(error instanceof Error ? error.message : "加载失败。", "error");
    });
})();
