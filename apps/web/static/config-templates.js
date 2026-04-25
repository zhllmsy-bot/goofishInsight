(() => {
  const root = document.querySelector("[data-template-config-page]");
  if (!(root instanceof HTMLElement)) {
    return;
  }

  const controlsForm = root.querySelector("[data-template-config-controls]");
  const editForm = root.querySelector("[data-template-config-form]");
  const feedbackNode = root.querySelector("[data-template-config-feedback]");
  const totalNode = root.querySelector("[data-template-config-total]");
  const listNode = root.querySelector("[data-template-config-list]");
  const summaryNode = root.querySelector("[data-template-config-summary]");
  const diffNode = root.querySelector("[data-template-config-diff]");
  const contextTitleNode = root.querySelector("[data-template-context-title]");
  const contextDescriptionNode = root.querySelector("[data-template-context-description]");
  const contextLinkNodes = Array.from(root.querySelectorAll("[data-template-context-link]"));
  const modalNode = root.querySelector("[data-template-config-modal]");
  const filterCategoryNode = root.querySelector("[data-template-config-category-filter]");
  const bindingCategoryNode = root.querySelector("[data-template-config-category-binding]");
  const categoryLabelNode = root.querySelector("[data-template-config-category-label]");
  const categoryHintNode = root.querySelector("[data-template-config-category-hint]");
  const query = new URLSearchParams(window.location.search);
  const preferredCategoryCode = String(query.get("category_code") || "").trim();

  let categoryItems = [];
  let templateItems = [];
  let selectedTemplateId = null;

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
        ? `${normalizeText(item.name || item.code)} 的模板将作为这个大类的编排基线。active template、prompt profile 和 runtime 生效链路都会围绕这个大类展开。`
        : "请选择一个大类后再编辑模板。这样模板版本、差异预览和 runtime 绑定会始终处于同一个大类上下文里。";
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
      || modalNode.querySelector("input[name='version']")
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

  const formatItemsText = (items) =>
    (Array.isArray(items) ? items : [])
      .map((item) =>
        [
          normalizeText(item.attributeCode).trim(),
          item.isRequired ? "1" : "0",
          item.isSale ? "1" : "0",
          item.isFilter ? "1" : "0",
          item.isSearch ? "1" : "0",
          item.isDisplay === false ? "0" : "1",
          normalizeText(item.sortNo, "10"),
        ].join("|"),
      )
      .filter(Boolean)
      .join("\n");

  const parseItemsText = (value) =>
    normalizeText(value)
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line, index) => {
        const [attributeCode, required, sale, filter, search, display, sortNo] = line
          .split("|")
          .map((part) => part.trim());
        return {
          attributeCode,
          isRequired: required === "1" || /^true$/i.test(required || ""),
          isSale: sale === "1" || /^true$/i.test(sale || ""),
          isFilter: filter === "1" || /^true$/i.test(filter || ""),
          isSearch: search === "1" || /^true$/i.test(search || ""),
          isDisplay: !(display === "0" || /^false$/i.test(display || "")),
          sortNo: Number(sortNo || (index + 1) * 10),
        };
      });

  const renderSummary = (item) => {
    if (!(summaryNode instanceof HTMLElement)) {
      return;
    }
    if (!item) {
      summaryNode.innerHTML =
        '<p class="runtime-panel-text">选择左侧模板后，这里会显示所属大类、是否生效，以及与 active/latest 的差异。</p>';
      return;
    }
    summaryNode.innerHTML = `
      <div class="config-summary-grid">
        <div class="runtime-stat">
          <span>Category</span>
          <strong>${safeText(item.categoryCode || item.categoryId || "-")}</strong>
        </div>
        <div class="runtime-stat">
          <span>版本</span>
          <strong>${safeText(item.version, "-")}</strong>
        </div>
        <div class="runtime-stat">
          <span>模板状态</span>
          <strong>${safeText(item.status, "-")}</strong>
        </div>
        <div class="runtime-stat">
          <span>Runtime 生效</span>
          <strong>${safeText(item.isActiveTemplate ? "YES" : "NO")}</strong>
        </div>
      </div>
    `;
  };

  const renderContext = (item = null) => {
    const contextCode = normalizeText(item?.categoryCode || editForm?.elements?.categoryCode?.value || preferredCategoryCode).trim();
    const contextName = normalizeText(item?.categoryName).trim();
    if (contextTitleNode instanceof HTMLElement) {
      contextTitleNode.textContent = contextCode
        ? `${contextName || contextCode} 的模板编排`
        : "模板编排工作台";
    }
    if (contextDescriptionNode instanceof HTMLElement) {
      contextDescriptionNode.textContent = contextCode
        ? `当前模板工作区已绑定到 ${contextName || contextCode}。你在这里创建、发布或绑定 active template 时，都会围绕这个大类上下文展开。`
        : "建议始终带着当前大类进入模板页。这样模板发布、差异预览和 runtime 绑定都会围绕同一个大类上下文展开。";
    }
    contextLinkNodes.forEach((node) => {
      if (!(node instanceof HTMLAnchorElement)) {
        return;
      }
      const kind = normalizeText(node.dataset.templateContextLink).trim();
      if (kind === "categories") {
        node.href = filteredConfigHref("/config/categories", contextCode);
        return;
      }
      if (kind === "models") {
        node.href = filteredConfigHref("/config/models", contextCode);
      }
    });
  };

  const renderDiff = (diffPreview) => {
    if (!(diffNode instanceof HTMLElement)) {
      return;
    }
    if (!diffPreview) {
      diffNode.innerHTML = '<p class="runtime-panel-text">点击“预览差异”后，这里会显示模板变化摘要。</p>';
      return;
    }
    const changedItems = Array.isArray(diffPreview.changedItems) ? diffPreview.changedItems : [];
    diffNode.innerHTML = `
      <div class="config-summary-grid">
        <div class="runtime-stat">
          <span>对比模板</span>
          <strong>${safeText(diffPreview.compareToTemplateId || "无")}</strong>
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
          <strong>${safeText(changedItems.map((entry) => entry.attributeCode).join(", "), "0")}</strong>
        </div>
      </div>
    `;
  };

  const resetForm = () => {
    if (!(editForm instanceof HTMLFormElement)) {
      return;
    }
    editForm.reset();
    editForm.elements.templateId.value = "";
    editForm.elements.version.value = "1";
    editForm.elements.status.value = "DRAFT";
    editForm.elements.itemsText.value = "";
    editForm.elements.bindAsActiveTemplate.checked = false;
    selectedTemplateId = null;
    renderSummary(null);
    renderDiff(null);
    syncBoundCategory(resolveCategoryByCode(preferredCategoryCode));
  };

  const loadTemplateIntoForm = (item) => {
    if (!(editForm instanceof HTMLFormElement) || !item) {
      return;
    }
    selectedTemplateId = item.id;
    editForm.elements.templateId.value = normalizeText(item.id);
    editForm.elements.version.value = normalizeText(item.version, "1");
    editForm.elements.status.value = normalizeText(item.status, "DRAFT");
    editForm.elements.effectiveAt.value = normalizeText(item.effectiveAt).slice(0, 16);
    editForm.elements.publishedBy.value = normalizeText(item.publishedBy);
    editForm.elements.promptProfile.value = normalizeText(item.activePromptProfile);
    editForm.elements.compareToTemplateId.value = "";
    editForm.elements.itemsText.value = formatItemsText(item.items);
    editForm.elements.bindAsActiveTemplate.checked = Boolean(item.isActiveTemplate);
    syncBoundCategory(
      resolveCategoryById(item.categoryId) || resolveCategoryByCode(item.categoryCode) || {
        id: normalizeText(item.categoryId).trim(),
        code: normalizeText(item.categoryCode).trim(),
        name: normalizeText(item.categoryName).trim(),
      },
    );
    renderSummary(item);
    renderDiff(item.diffPreview || null);
  };

  const renderList = () => {
    if (!(listNode instanceof HTMLElement)) {
      return;
    }
    if (!templateItems.length) {
      listNode.innerHTML = `
        <article class="panel compact-panel">
          <p class="eyebrow">空列表</p>
          <h3>当前没有模板配置</h3>
          <p class="runtime-panel-text">点击上方“新建模板”，可以开始为大类编排模板版本。</p>
        </article>
      `;
      return;
    }
    listNode.innerHTML = templateItems
      .map((item) => {
        const activeClass = item.id === selectedTemplateId ? "is-active" : "";
        return `
          <button type="button" class="config-list-item ${activeClass}" data-template-select="${safeAttr(item.id)}">
            <div class="config-list-head">
              <div>
                <p class="eyebrow">${safeText(item.categoryCode || "-")}</p>
                <h3>${safeText(`v${item.version} · ${item.status}`)}</h3>
              </div>
              <span class="status-pill">${safeText(item.isActiveTemplate ? "ACTIVE" : "IDLE")}</span>
            </div>
            <p class="runtime-panel-text">${safeText(item.categoryName || item.categoryId || "-")}</p>
            <div class="config-list-meta">
              <span>Items ${safeText(item.itemCount, "0")}</span>
              <span>${safeText(item.publishedBy || "draft")}</span>
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
    const suffix = search.toString() ? `?${search.toString()}` : "";
    const payload = await fetchJson(`/api/config/templates${suffix}`);
    templateItems = Array.isArray(payload.items) ? payload.items : [];
    if (totalNode instanceof HTMLElement) {
      totalNode.textContent = `${templateItems.length} 个模板`;
    }
    const matched = selectedTemplateId ? templateItems.find((item) => item.id === selectedTemplateId) : null;
    if (matched) {
      loadTemplateIntoForm(matched);
    } else if (!selectedTemplateId && preferredCategoryCode && templateItems.length) {
      await loadTemplateDetail(templateItems[0].id);
    } else if (selectedTemplateId) {
      selectedTemplateId = null;
      renderSummary(null);
      renderDiff(null);
      syncBoundCategory(resolveCategoryByCode(preferredCategoryCode));
    } else {
      syncBoundCategory(
        resolveCategoryByCode(editForm?.elements?.categoryCode?.value || preferredCategoryCode),
      );
    }
    renderList();
  };

  const loadTemplateDetail = async (templateId) => {
    const compareToTemplateId = normalizeText(editForm?.elements.compareToTemplateId?.value).trim();
    const search = new URLSearchParams();
    if (compareToTemplateId) {
      search.set("compare_to_template_id", compareToTemplateId);
    }
    const suffix = search.toString() ? `?${search.toString()}` : "";
    const payload = await fetchJson(`/api/config/templates/${encodeURIComponent(templateId)}${suffix}`);
    loadTemplateIntoForm(payload);
    renderList();
  };

  const collectPayload = () => {
    if (!(controlsForm instanceof HTMLFormElement) || !(editForm instanceof HTMLFormElement)) {
      return null;
    }
    const operatorFields = formDataObject(controlsForm);
    const templateFields = formDataObject(editForm);
    return {
      operatorId: normalizeText(operatorFields.operatorId).trim(),
      payload: {
        templateId: normalizeText(templateFields.templateId).trim() || undefined,
        categoryId: normalizeText(templateFields.categoryId).trim() || undefined,
        categoryCode: normalizeText(templateFields.categoryCode).trim() || undefined,
        version: Number(templateFields.version || 1),
        status: normalizeText(templateFields.status, "DRAFT").trim() || "DRAFT",
        effectiveAt: normalizeText(templateFields.effectiveAt).trim() || undefined,
        publishedBy: normalizeText(templateFields.publishedBy).trim() || undefined,
        compareToTemplateId: normalizeText(templateFields.compareToTemplateId).trim() || undefined,
        promptProfile: normalizeText(templateFields.promptProfile).trim() || undefined,
        bindAsActiveTemplate: editForm.elements.bindAsActiveTemplate.checked,
        items: parseItemsText(templateFields.itemsText),
      },
    };
  };

  const previewDiff = async () => {
    const requestBody = collectPayload();
    if (!requestBody) {
      return;
    }
    if (!requestBody.payload.categoryCode) {
      throw new Error("请先选择大类。");
    }
    const payload = await fetchJson("/api/config/templates/diff-preview", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        payload: requestBody.payload,
      }),
    });
    renderDiff(payload);
    setFeedback("模板差异已生成。", "success");
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
    const payload = await fetchJson("/api/config/templates", {
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
        ? `模板已保存：${normalizeText(payload?.template?.categoryCode)} v${normalizeText(payload?.template?.version, "-")}`
        : `模板预演成功：${normalizeText(payload?.template?.categoryCode)} v${normalizeText(payload?.template?.version, "-")}`,
      "success",
    );
    await loadList();
    if (payload?.template?.id) {
      await loadTemplateDetail(payload.template.id);
    } else if (payload?.diffPreview) {
      renderDiff(payload.diffPreview);
    }
  };

  root.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const selectButton = target.closest("[data-template-select]");
    if (selectButton instanceof HTMLElement) {
      const templateId = normalizeText(selectButton.dataset.templateSelect).trim();
      if (templateId) {
        try {
          setFeedback("正在加载模板详情...", "info");
          await loadTemplateDetail(templateId);
          setFeedback("模板详情已加载。", "success");
          openEditor();
        } catch (error) {
          setFeedback(error instanceof Error ? error.message : "模板详情加载失败。", "error");
        }
      }
      return;
    }

    if (target.closest("[data-template-config-modal-close]")) {
      closeEditor();
      return;
    }

    const actionButton = target.closest("[data-template-config-action]");
    if (!(actionButton instanceof HTMLElement)) {
      return;
    }
    const action = normalizeText(actionButton.dataset.templateConfigAction).trim();
    try {
      if (action === "new") {
        resetForm();
        renderList();
        setFeedback("已切到新建模板模式。", "info");
        openEditor();
        return;
      }
      if (action === "open-editor") {
        openEditor();
        return;
      }
      if (action === "refresh") {
        setFeedback("正在刷新模板列表...", "info");
        await loadList();
        setFeedback("模板列表已刷新。", "success");
        return;
      }
      if (action === "preview-diff") {
        setFeedback("正在生成模板差异...", "info");
        await previewDiff();
        return;
      }
      if (action === "save-dry-run") {
        setFeedback("正在预演保存模板...", "info");
        await savePayload(false);
        return;
      }
      if (action === "save-apply") {
        setFeedback("正在正式保存模板...", "info");
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
          ? `模板配置已加载，当前按大类 ${preferredCategoryCode} 过滤并预绑定到该大类。`
          : "模板配置已加载。",
        "success",
      );
    })
    .catch((error) => {
      setFeedback(error instanceof Error ? error.message : "加载失败。", "error");
    });
})();
