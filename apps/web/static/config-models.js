(() => {
  const root = document.querySelector("[data-model-config-page]");
  if (!(root instanceof HTMLElement)) {
    return;
  }

  const controlsForm = root.querySelector("[data-model-config-controls]");
  const editForm = root.querySelector("[data-model-config-form]");
  const feedbackNode = root.querySelector("[data-model-config-feedback]");
  const totalNode = root.querySelector("[data-model-config-total]");
  const listNode = root.querySelector("[data-model-config-list]");
  const summaryNode = root.querySelector("[data-model-config-summary]");
  const contextTitleNode = root.querySelector("[data-model-context-title]");
  const contextDescriptionNode = root.querySelector("[data-model-context-description]");
  const contextLinkNodes = Array.from(root.querySelectorAll("[data-model-context-link]"));
  const modalNode = root.querySelector("[data-model-config-modal]");
  const filterCategoryNode = root.querySelector("[data-model-config-category-filter]");
  const bindingCategoryNode = root.querySelector("[data-model-config-category-binding]");
  const categoryLabelNode = root.querySelector("[data-model-config-category-label]");
  const categoryHintNode = root.querySelector("[data-model-config-category-hint]");
  const query = new URLSearchParams(window.location.search);
  const preferredCategoryCode = String(query.get("category_code") || "").trim();

  let categoryItems = [];
  let modelItems = [];
  let selectedModelId = null;

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
  const filteredConfigHref = (path, categoryCode) => {
    const normalized = normalizeText(categoryCode).trim();
    return normalized ? `${path}?category_code=${encodeURIComponent(normalized)}` : path;
  };
  const resolveCategoryByCode = (categoryCode) => {
    const normalized = normalizeText(categoryCode).trim();
    if (!normalized) {
      return null;
    }
    return categoryItems.find((item) => normalizeText(item.code).trim() === normalized) || null;
  };
  const resolveCategoryById = (categoryId) => {
    const normalized = normalizeText(categoryId).trim();
    if (!normalized) {
      return null;
    }
    return categoryItems.find((item) => normalizeText(item.id).trim() === normalized) || null;
  };
  const fillCategorySelect = (node, { placeholder, includeEmpty = true }) => {
    if (!(node instanceof HTMLSelectElement)) {
      return;
    }
    const currentValue = normalizeText(node.value).trim();
    const options = [];
    if (includeEmpty) {
      options.push(`<option value="">${escapeHtml(placeholder)}</option>`);
    }
    options.push(
      ...categoryItems.map((item) => {
        const label = `${normalizeText(item.name || item.code, "-")} · ${normalizeText(item.code, "-")}`;
        return `<option value="${safeAttr(item.code)}">${escapeHtml(label)}</option>`;
      }),
    );
    node.innerHTML = options.join("");
    node.value = currentValue;
  };
  const renderCategoryBinding = (item, fallbackCode = "") => {
    if (categoryLabelNode instanceof HTMLElement) {
      categoryLabelNode.textContent = item
        ? `${normalizeText(item.name || item.code, "-")} · ${normalizeText(item.code, "-")}`
        : normalizeText(fallbackCode, "未选择");
    }
    if (categoryHintNode instanceof HTMLElement) {
      categoryHintNode.textContent = item
        ? `${normalizeText(item.name || item.code)} 的型号将直接归到这个大类下，后续 query、型号词典、specs 标准化和看板汇总都会围绕这个大类生效。`
        : "请选择一个大类后再保存型号。这样型号、alias、batch collect 和看板汇总会始终属于同一个大类上下文。";
    }
  };
  const syncBoundCategory = (category) => {
    if (!(editForm instanceof HTMLFormElement)) {
      return;
    }
    const resolved = category || null;
    editForm.elements.categoryId.value = normalizeText(resolved?.id).trim();
    editForm.elements.categoryCode.value = normalizeText(resolved?.code).trim();
    if (bindingCategoryNode instanceof HTMLSelectElement) {
      bindingCategoryNode.value = normalizeText(resolved?.code).trim();
    }
    renderCategoryBinding(resolved, normalizeText(resolved?.code).trim());
    renderContext(
      resolved
        ? { categoryCode: resolved.code, categoryName: resolved.name }
        : null,
    );
  };
  const formatSyncSummary = (sync) => {
    if (!sync || typeof sync !== "object") {
      return "";
    }
    const taskCount = Number(sync.taskCount || 0);
    const queryCount = Number(sync.queryCount || 0);
    const brandCount = Number(sync.brandLexiconCount || 0);
    const modelCount = Number(sync.modelLexiconCount || 0);
    const autoTaskCount = Number(sync.autoCreatedTaskCount || 0);
    if (!taskCount && !queryCount && !brandCount && !modelCount && !autoTaskCount) {
      return "";
    }
    const parts = [`已同步 ${taskCount} 个任务`, `${queryCount} 条 query`, `${brandCount} 条 BRAND`, `${modelCount} 条 MODEL`];
    if (autoTaskCount) {
      parts.push(`自动创建 ${autoTaskCount} 个任务`);
    }
    return `；${parts.join(" / ")}`;
  };

  const setFeedback = (message, state = "info") => {
    if (!(feedbackNode instanceof HTMLElement)) {
      return;
    }
    feedbackNode.textContent = message;
    feedbackNode.dataset.state = state;
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
    return Object.fromEntries(new FormData(form).entries());
  };

  const openEditor = () => {
    if (!(modalNode instanceof HTMLElement)) {
      return;
    }
    modalNode.hidden = false;
    document.body.style.overflow = "hidden";
    const focusTarget =
      modalNode.querySelector("select[name='categoryBinding']")
      || modalNode.querySelector("input[name='brandName']")
      || modalNode.querySelector("textarea")
      || modalNode.querySelector("select");
    if (focusTarget instanceof HTMLElement) {
      window.setTimeout(() => focusTarget.focus(), 30);
    }
  };

  const closeEditor = () => {
    if (!(modalNode instanceof HTMLElement)) {
      return;
    }
    modalNode.hidden = true;
    document.body.style.overflow = "";
  };

  const formatAliasesText = (aliases) =>
    (Array.isArray(aliases) ? aliases : [])
      .map((alias) => `${normalizeText(alias.aliasText).trim()}|${normalizeText(alias.aliasType, "MANUAL").trim()}`)
      .filter(Boolean)
      .join("\n");

  const parseAliasesText = (value) =>
    normalizeText(value)
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [aliasText, aliasType] = line.split("|").map((part) => part.trim());
        return {
          aliasText,
          aliasType: aliasType || "MANUAL",
          status: "ACTIVE",
        };
      });

  const renderSummary = (item) => {
    if (!(summaryNode instanceof HTMLElement)) {
      return;
    }
    if (!item) {
      summaryNode.innerHTML =
        '<p class="runtime-panel-text">选择左侧型号后，这里会显示所属大类、品牌和 alias 数量。</p>';
      return;
    }
    summaryNode.innerHTML = `
      <div class="config-summary-grid">
        <div class="runtime-stat">
          <span>Category</span>
          <strong>${safeText(item.categoryCode || item.categoryId || "-")}</strong>
        </div>
        <div class="runtime-stat">
          <span>Brand</span>
          <strong>${safeText(item.brandName || "-")}</strong>
        </div>
        <div class="runtime-stat">
          <span>Series</span>
          <strong>${safeText(item.seriesName || "-")}</strong>
        </div>
        <div class="runtime-stat">
          <span>Aliases</span>
          <strong>${safeText(item.aliasCount, "0")}</strong>
        </div>
      </div>
    `;
  };

  const renderContext = (item = null) => {
    const contextCode = normalizeText(item?.categoryCode || editForm?.elements?.categoryCode?.value || preferredCategoryCode).trim();
    const contextName = normalizeText(item?.categoryName).trim();
    if (contextTitleNode instanceof HTMLElement) {
      contextTitleNode.textContent = contextCode
        ? `${contextName || contextCode} 的型号库`
        : "型号库工作台";
    }
    if (contextDescriptionNode instanceof HTMLElement) {
      contextDescriptionNode.textContent = contextCode
        ? `${contextName || contextCode} 的型号、系列与 alias 会在这里统一维护，并自动同步到 batch collect、specs 标准化和看板汇总。`
        : "型号库是“大类下的具体品类”表达层。标准型号、别名、品牌和系列会直接影响 specs 标准化与 batch collect 的 query 同步。";
    }
    contextLinkNodes.forEach((node) => {
      if (!(node instanceof HTMLAnchorElement)) {
        return;
      }
      const kind = normalizeText(node.dataset.modelContextLink).trim();
      if (kind === "categories") {
        node.href = filteredConfigHref("/config/categories", contextCode);
        return;
      }
      if (kind === "templates") {
        node.href = filteredConfigHref("/config/templates", contextCode);
      }
    });
  };

  const resetForm = () => {
    if (!(editForm instanceof HTMLFormElement)) {
      return;
    }
    editForm.reset();
    editForm.elements.modelId.value = "";
    editForm.elements.status.value = "ACTIVE";
    editForm.elements.aliasesText.value = "";
    selectedModelId = null;
    renderSummary(null);
    syncBoundCategory(resolveCategoryByCode(preferredCategoryCode));
  };

  const loadModelIntoForm = (item) => {
    if (!(editForm instanceof HTMLFormElement) || !item) {
      return;
    }
    selectedModelId = item.id;
    editForm.elements.modelId.value = normalizeText(item.id);
    editForm.elements.brandName.value = normalizeText(item.brandName);
    editForm.elements.seriesName.value = normalizeText(item.seriesName);
    editForm.elements.modelCode.value = normalizeText(item.modelCode);
    editForm.elements.modelName.value = normalizeText(item.modelName);
    editForm.elements.status.value = normalizeText(item.status, "ACTIVE");
    editForm.elements.aliasesText.value = formatAliasesText(item.aliases);
    syncBoundCategory(
      resolveCategoryById(item.categoryId) || resolveCategoryByCode(item.categoryCode) || {
        id: normalizeText(item.categoryId).trim(),
        code: normalizeText(item.categoryCode).trim(),
        name: normalizeText(item.categoryName).trim(),
      },
    );
    renderSummary(item);
  };

  const renderList = () => {
    if (!(listNode instanceof HTMLElement)) {
      return;
    }
    if (!modelItems.length) {
      listNode.innerHTML = `
        <article class="panel compact-panel">
          <p class="eyebrow">空列表</p>
          <h3>当前没有型号库配置</h3>
          <p class="runtime-panel-text">点击上方“新建型号”，可以开始维护 canonical model 和 alias。</p>
        </article>
      `;
      return;
    }
    listNode.innerHTML = modelItems
      .map((item) => {
        const activeClass = item.id === selectedModelId ? "is-active" : "";
        return `
          <button type="button" class="config-list-item ${activeClass}" data-model-select="${safeAttr(item.id)}">
            <div class="config-list-head">
              <div>
                <p class="eyebrow">${safeText(item.categoryCode || "-")}</p>
                <h3>${safeText(item.modelName)}</h3>
              </div>
              <span class="status-pill">${safeText(item.status)}</span>
            </div>
            <p class="runtime-panel-text">${safeText(`${item.brandName || "-"} · ${item.modelCode}`)}</p>
            <div class="config-list-meta">
              <span>Series ${safeText(item.seriesName || "-")}</span>
              <span>Aliases ${safeText(item.aliasCount, "0")}</span>
            </div>
          </button>
        `;
      })
      .join("");
  };

  const loadCategories = async () => {
    const payload = await fetchJson("/api/config/categories");
    categoryItems = Array.isArray(payload.items)
      ? [...payload.items].sort((left, right) => {
          return (
            Number(left.level || 0) - Number(right.level || 0)
            || normalizeText(left.name).localeCompare(normalizeText(right.name), "zh-Hans-CN")
            || normalizeText(left.code).localeCompare(normalizeText(right.code))
          );
        })
      : [];
    fillCategorySelect(filterCategoryNode, { placeholder: "全部大类", includeEmpty: true });
    fillCategorySelect(bindingCategoryNode, { placeholder: "请选择大类", includeEmpty: true });
    if (filterCategoryNode instanceof HTMLSelectElement && preferredCategoryCode) {
      filterCategoryNode.value = preferredCategoryCode;
    }
    syncBoundCategory(
      resolveCategoryById(editForm?.elements?.categoryId?.value)
      || resolveCategoryByCode(editForm?.elements?.categoryCode?.value)
      || resolveCategoryByCode(preferredCategoryCode),
    );
  };

  const loadList = async () => {
    const filters = formDataObject(controlsForm);
    const search = new URLSearchParams();
    if (normalizeText(filters.status).trim()) {
      search.set("status", normalizeText(filters.status).trim());
    }
    if (normalizeText(filters.categoryCodeFilter).trim()) {
      search.set("category_code", normalizeText(filters.categoryCodeFilter).trim());
    }
    if (normalizeText(filters.brandNameFilter).trim()) {
      search.set("brand_name", normalizeText(filters.brandNameFilter).trim());
    }
    const suffix = search.toString() ? `?${search.toString()}` : "";
    const payload = await fetchJson(`/api/config/models${suffix}`);
    modelItems = Array.isArray(payload.items) ? payload.items : [];
    if (totalNode instanceof HTMLElement) {
      totalNode.textContent = `${modelItems.length} 个型号`;
    }
    if (selectedModelId) {
      const matched = modelItems.find((item) => item.id === selectedModelId);
      if (matched) {
        loadModelIntoForm(matched);
      } else {
        selectedModelId = null;
        renderSummary(null);
        syncBoundCategory(resolveCategoryByCode(preferredCategoryCode));
      }
    } else {
      syncBoundCategory(
        resolveCategoryByCode(editForm?.elements?.categoryCode?.value || preferredCategoryCode),
      );
    }
    renderList();
  };

  const collectPayload = () => {
    if (!(controlsForm instanceof HTMLFormElement) || !(editForm instanceof HTMLFormElement)) {
      return null;
    }
    const operatorFields = formDataObject(controlsForm);
    const modelFields = formDataObject(editForm);
    return {
      operatorId: normalizeText(operatorFields.operatorId).trim(),
      payload: {
        modelId: normalizeText(modelFields.modelId).trim() || undefined,
        categoryId: normalizeText(modelFields.categoryId).trim() || undefined,
        categoryCode: normalizeText(modelFields.categoryCode).trim() || undefined,
        brandName: normalizeText(modelFields.brandName).trim() || undefined,
        seriesName: normalizeText(modelFields.seriesName).trim() || undefined,
        modelCode: normalizeText(modelFields.modelCode).trim(),
        modelName: normalizeText(modelFields.modelName).trim(),
        status: normalizeText(modelFields.status, "ACTIVE").trim() || "ACTIVE",
        aliases: parseAliasesText(modelFields.aliasesText),
      },
    };
  };

  const savePayload = async (apply) => {
    const requestBody = collectPayload();
    if (!requestBody) {
      return;
    }
    if (!requestBody.operatorId) {
      throw new Error("Operator 不能为空。");
    }
    if (!requestBody.payload.categoryCode) {
      throw new Error("请先选择大类。");
    }
    const payload = await fetchJson("/api/config/models", {
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
        ? `型号已保存：${normalizeText(payload?.model?.modelName, payload?.model?.modelCode)}${formatSyncSummary(payload?.sync)}`
        : `型号预演成功：${normalizeText(payload?.model?.modelName, payload?.model?.modelCode)}${formatSyncSummary(payload?.sync)}`,
      "success",
    );
    await loadList();
    if (payload?.model?.id) {
      const matched = modelItems.find((item) => item.id === payload.model.id);
      if (matched) {
        loadModelIntoForm(matched);
        renderList();
      }
    }
  };

  const exportJson = async () => {
    if (!(editForm instanceof HTMLFormElement)) {
      return;
    }
    const filters = formDataObject(controlsForm);
    const search = new URLSearchParams();
    if (normalizeText(filters.status).trim()) {
      search.set("status", normalizeText(filters.status).trim());
    }
    if (normalizeText(filters.categoryCodeFilter).trim()) {
      search.set("category_code", normalizeText(filters.categoryCodeFilter).trim());
    }
    if (normalizeText(filters.brandNameFilter).trim()) {
      search.set("brand_name", normalizeText(filters.brandNameFilter).trim());
    }
    const suffix = search.toString() ? `?${search.toString()}` : "";
    const payload = await fetchJson(`/api/config/models/export${suffix}`);
    editForm.elements.exchangeJson.value = JSON.stringify(payload, null, 2);
    setFeedback("型号库 JSON 已导出。", "success");
  };

  const importJson = async (apply) => {
    if (!(controlsForm instanceof HTMLFormElement) || !(editForm instanceof HTMLFormElement)) {
      return;
    }
    const operatorId = normalizeText(formDataObject(controlsForm).operatorId).trim();
    if (!operatorId) {
      throw new Error("Operator 不能为空。");
    }
    let exchangePayload = {};
    try {
      exchangePayload = JSON.parse(normalizeText(editForm.elements.exchangeJson.value, "{}") || "{}");
    } catch (_error) {
      throw new Error("Import / Export JSON 必须是合法 JSON。");
    }
    const payload = await fetchJson("/api/config/models/import", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        operatorId,
        apply,
        payload: exchangePayload,
      }),
    });
    setFeedback(
      apply
        ? `已导入 ${normalizeText(payload.importedCount, "0")} 条型号${formatSyncSummary(payload?.sync)}。`
        : `导入预演成功，共 ${normalizeText(payload.importedCount, "0")} 条${formatSyncSummary(payload?.sync)}。`,
      "success",
    );
    await loadList();
  };

  root.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const selectButton = target.closest("[data-model-select]");
    if (selectButton instanceof HTMLElement) {
      const modelId = normalizeText(selectButton.dataset.modelSelect).trim();
      const matched = modelItems.find((item) => item.id === modelId);
      if (matched) {
        loadModelIntoForm(matched);
        renderList();
        openEditor();
      }
      return;
    }

    if (target.closest("[data-model-config-modal-close]")) {
      closeEditor();
      return;
    }

    const actionButton = target.closest("[data-model-config-action]");
    if (!(actionButton instanceof HTMLElement)) {
      return;
    }
    const action = normalizeText(actionButton.dataset.modelConfigAction).trim();
    try {
      if (action === "new") {
        resetForm();
        renderList();
        setFeedback("已切到新建型号模式。", "info");
        openEditor();
        return;
      }
      if (action === "open-editor") {
        openEditor();
        return;
      }
      if (action === "refresh") {
        setFeedback("正在刷新型号列表...", "info");
        await loadList();
        setFeedback("型号列表已刷新。", "success");
        return;
      }
      if (action === "export-json") {
        setFeedback("正在导出型号 JSON...", "info");
        await exportJson();
        openEditor();
        return;
      }
      if (action === "import-json") {
        setFeedback("正在导入型号 JSON...", "info");
        await importJson(true);
        openEditor();
        return;
      }
      if (action === "save-dry-run") {
        setFeedback("正在预演保存型号...", "info");
        await savePayload(false);
        return;
      }
      if (action === "save-apply") {
        setFeedback("正在正式保存型号...", "info");
        await savePayload(true);
        closeEditor();
      }
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "操作失败。", "error");
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && modalNode instanceof HTMLElement && !modalNode.hidden) {
      closeEditor();
    }
  });

  if (bindingCategoryNode instanceof HTMLSelectElement) {
    bindingCategoryNode.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLSelectElement)) {
        return;
      }
      syncBoundCategory(resolveCategoryByCode(target.value));
    });
  }

  resetForm();
  loadCategories()
    .then(() => loadList())
    .then(() => {
      setFeedback(
        preferredCategoryCode
          ? `型号配置已加载，当前按大类 ${preferredCategoryCode} 过滤并预绑定到该大类。`
          : "型号配置已加载。",
        "success",
      );
    })
    .catch((error) => {
      setFeedback(error instanceof Error ? error.message : "加载失败。", "error");
    });
})();
