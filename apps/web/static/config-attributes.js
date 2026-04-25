(() => {
  const root = document.querySelector("[data-attribute-config-page]");
  if (!(root instanceof HTMLElement)) {
    return;
  }

  const controlsForm = root.querySelector("[data-attribute-config-controls]");
  const editForm = root.querySelector("[data-attribute-config-form]");
  const feedbackNode = root.querySelector("[data-attribute-config-feedback]");
  const totalNode = root.querySelector("[data-attribute-config-total]");
  const listNode = root.querySelector("[data-attribute-config-list]");
  const summaryNode = root.querySelector("[data-attribute-config-summary]");
  const modalNode = root.querySelector("[data-attribute-config-modal]");

  let attributeItems = [];
  let selectedAttributeId = null;

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
    const data = new FormData(form);
    return Object.fromEntries(data.entries());
  };

  const openEditor = () => {
    if (!(modalNode instanceof HTMLElement)) {
      return;
    }
    modalNode.hidden = false;
    document.body.style.overflow = "hidden";
    const focusTarget =
      modalNode.querySelector("input:not([type='hidden'])")
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

  const formatOptionsText = (options) =>
    (Array.isArray(options) ? options : [])
      .map((option) => `${normalizeText(option.optionCode).trim()}|${normalizeText(option.optionName).trim()}`)
      .filter((line) => line !== "|")
      .join("\n");

  const parseOptionsText = (value) =>
    normalizeText(value)
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line, index) => {
        const [code, name] = line.split("|").map((part) => part.trim());
        return {
          optionCode: code || name,
          optionName: name || code,
          sortNo: (index + 1) * 10,
          status: "ACTIVE",
        };
      });

  const renderSummary = (item) => {
    if (!(summaryNode instanceof HTMLElement)) {
      return;
    }
    if (!item) {
      summaryNode.innerHTML =
        '<p class="runtime-panel-text">选择左侧属性后，这里会显示它被多少模板引用，以及当前枚举值数量。</p>';
      return;
    }
    summaryNode.innerHTML = `
      <div class="config-summary-grid">
        <div class="runtime-stat">
          <span>模板引用数</span>
          <strong>${safeText(item.templateReferenceCount, "0")}</strong>
        </div>
        <div class="runtime-stat">
          <span>枚举值数</span>
          <strong>${safeText(item.optionCount, "0")}</strong>
        </div>
        <div class="runtime-stat">
          <span>Scope</span>
          <strong>${safeText(`${item.scopeType}/${item.scopeId}`)}</strong>
        </div>
        <div class="runtime-stat">
          <span>Value Scope</span>
          <strong>${safeText(item.valueScope)}</strong>
        </div>
        <div class="runtime-stat">
          <span>通用属性</span>
          <strong>${safeText(item.isCommon ? "是" : "否")}</strong>
        </div>
      </div>
    `;
  };

  const resetForm = () => {
    if (!(editForm instanceof HTMLFormElement)) {
      return;
    }
    editForm.reset();
    editForm.elements.attributeId.value = "";
    editForm.elements.scopeType.value = "PLATFORM";
    editForm.elements.scopeId.value = "platform";
    editForm.elements.dataType.value = "TEXT";
    editForm.elements.valueScope.value = "SPU";
    editForm.elements.status.value = "ACTIVE";
    editForm.elements.isCommon.checked = false;
    editForm.elements.optionsText.value = "";
    renderSummary(null);
    selectedAttributeId = null;
  };

  const loadAttributeIntoForm = (item) => {
    if (!(editForm instanceof HTMLFormElement) || !item) {
      return;
    }
    selectedAttributeId = item.id;
    editForm.elements.attributeId.value = normalizeText(item.id);
    editForm.elements.code.value = normalizeText(item.code);
    editForm.elements.name.value = normalizeText(item.name);
    editForm.elements.scopeType.value = normalizeText(item.scopeType, "PLATFORM");
    editForm.elements.scopeId.value = normalizeText(item.scopeId, "platform");
    editForm.elements.dataType.value = normalizeText(item.dataType, "TEXT");
    editForm.elements.valueScope.value = normalizeText(item.valueScope, "SPU");
    editForm.elements.unit.value = normalizeText(item.unit);
    editForm.elements.status.value = normalizeText(item.status, "ACTIVE");
    editForm.elements.isMulti.checked = Boolean(item.isMulti);
    editForm.elements.isCommon.checked = Boolean(item.isCommon);
    editForm.elements.optionsText.value = formatOptionsText(item.options);
    renderSummary(item);
  };

  const renderList = () => {
    if (!(listNode instanceof HTMLElement)) {
      return;
    }
    if (!attributeItems.length) {
      listNode.innerHTML = `
        <article class="panel compact-panel">
          <p class="eyebrow">空列表</p>
          <h3>当前没有属性配置</h3>
          <p class="runtime-panel-text">点击上方“新建属性”，可以开始维护属性字典。</p>
        </article>
      `;
      return;
    }
    listNode.innerHTML = attributeItems
      .map((item) => {
        const activeClass = item.id === selectedAttributeId ? "is-active" : "";
        return `
          <button type="button" class="config-list-item ${activeClass}" data-attribute-select="${safeAttr(item.id)}">
            <div class="config-list-head">
              <div>
                <p class="eyebrow">${safeText(item.code)}</p>
                <h3>${safeText(item.name)}</h3>
              </div>
              <span class="status-pill">${safeText(item.status)}</span>
            </div>
            <p class="runtime-panel-text">${safeText(`${item.dataType} · ${item.valueScope} · ${item.scopeType}/${item.scopeId}`)}</p>
            <div class="config-list-meta">
              <span>引用 ${safeText(item.templateReferenceCount, "0")}</span>
              <span>枚举 ${safeText(item.optionCount, "0")}</span>
              <span>${safeText(item.isCommon ? "通用属性" : "模板属性")}</span>
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
    if (normalizeText(filters.scopeType).trim()) {
      query.set("scope_type", normalizeText(filters.scopeType).trim());
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    const payload = await fetchJson(`/api/config/attributes${suffix}`);
    attributeItems = Array.isArray(payload.items) ? payload.items : [];
    if (totalNode instanceof HTMLElement) {
      totalNode.textContent = `${attributeItems.length} 个属性`;
    }
    if (selectedAttributeId) {
      const matched = attributeItems.find((item) => item.id === selectedAttributeId);
      if (matched) {
        loadAttributeIntoForm(matched);
      }
    }
    renderList();
  };

  const collectPayload = () => {
    if (!(controlsForm instanceof HTMLFormElement) || !(editForm instanceof HTMLFormElement)) {
      return null;
    }
    const operatorFields = formDataObject(controlsForm);
    const attributeFields = formDataObject(editForm);
    return {
      operatorId: normalizeText(operatorFields.operatorId).trim(),
      payload: {
        attributeId: normalizeText(attributeFields.attributeId).trim() || undefined,
        code: normalizeText(attributeFields.code).trim(),
        name: normalizeText(attributeFields.name).trim(),
        scopeType: normalizeText(attributeFields.scopeType, "PLATFORM").trim() || "PLATFORM",
        scopeId: normalizeText(attributeFields.scopeId, "platform").trim() || "platform",
        dataType: normalizeText(attributeFields.dataType, "TEXT").trim() || "TEXT",
        valueScope: normalizeText(attributeFields.valueScope, "SPU").trim() || "SPU",
        unit: normalizeText(attributeFields.unit).trim() || undefined,
        status: normalizeText(attributeFields.status, "ACTIVE").trim() || "ACTIVE",
        isMulti: editForm.elements.isMulti.checked,
        isCommon: editForm.elements.isCommon.checked,
        options: parseOptionsText(attributeFields.optionsText),
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
    const payload = await fetchJson("/api/config/attributes", {
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
        ? `属性已保存：${normalizeText(payload?.attribute?.name, payload?.attribute?.code)}`
        : `预演成功：${normalizeText(payload?.attribute?.name, payload?.attribute?.code)}`,
      "success",
    );
    await loadList();
    if (payload?.attribute?.id) {
      selectedAttributeId = payload.attribute.id;
      const matched = attributeItems.find((item) => item.id === selectedAttributeId);
      if (matched) {
        loadAttributeIntoForm(matched);
      }
    }
  };

  root.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const selectButton = target.closest("[data-attribute-select]");
    if (selectButton instanceof HTMLElement) {
      const attributeId = normalizeText(selectButton.dataset.attributeSelect).trim();
      const matched = attributeItems.find((item) => item.id === attributeId);
      if (matched) {
        loadAttributeIntoForm(matched);
        renderList();
        openEditor();
      }
      return;
    }

    if (target.closest("[data-attribute-config-modal-close]")) {
      closeEditor();
      return;
    }

    const actionButton = target.closest("[data-attribute-config-action]");
    if (!(actionButton instanceof HTMLElement)) {
      return;
    }
    const action = normalizeText(actionButton.dataset.attributeConfigAction).trim();
    try {
      if (action === "new") {
        resetForm();
        renderList();
        setFeedback("已切到新建属性模式。", "info");
        openEditor();
        return;
      }
      if (action === "open-editor") {
        openEditor();
        return;
      }
      if (action === "refresh") {
        setFeedback("正在刷新属性列表...", "info");
        await loadList();
        setFeedback("属性列表已刷新。", "success");
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

  resetForm();
  loadList()
    .then(() => {
      setFeedback("属性配置已加载。", "success");
    })
    .catch((error) => {
      setFeedback(error instanceof Error ? error.message : "加载失败。", "error");
    });
})();
