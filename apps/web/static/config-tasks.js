(() => {
  const root = document.querySelector("[data-task-config-page]");
  if (!(root instanceof HTMLElement)) {
    return;
  }

  const controlsForm = root.querySelector("[data-task-config-controls]");
  const editForm = root.querySelector("[data-task-config-form]");
  const feedbackNode = root.querySelector("[data-task-config-feedback]");
  const totalNode = root.querySelector("[data-task-config-total]");
  const listNode = root.querySelector("[data-task-config-list]");
  const summaryNode = root.querySelector("[data-task-config-summary]");
  const filterCategoryNode = root.querySelector("[data-task-config-category-filter]");
  const bindingCategoryNode = root.querySelector("[data-task-config-category-binding]");
  const categoryLabelNode = root.querySelector("[data-task-config-category-label]");
  const categoryHintNode = root.querySelector("[data-task-config-category-hint]");
  const domainLabelNode = root.querySelector("[data-task-config-domain-label]");
  const query = new URLSearchParams(window.location.search);
  const preferredCategoryCode = String(query.get("category_code") || "").trim();

  let categoryItems = [];
  let taskItems = [];
  let selectedTaskKey = null;

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
  const renderCategoryBinding = (item, domainOverride = "") => {
    const categoryCode = normalizeText(item?.code).trim();
    const domainValue = categoryCode || normalizeText(domainOverride).trim();
    if (categoryLabelNode instanceof HTMLElement) {
      categoryLabelNode.textContent = item
        ? `${normalizeText(item.name || item.code, "-")} · ${normalizeText(item.code, "-")}`
        : "未绑定";
    }
    if (domainLabelNode instanceof HTMLElement) {
      domainLabelNode.textContent = normalizeText(domainValue, "未设置");
    }
    if (categoryHintNode instanceof HTMLElement) {
      categoryHintNode.textContent = item
        ? `${normalizeText(item.name || item.code)} 已绑定为这条任务的唯一大类。保存时 business domain 会自动镜像成 ${normalizeText(item.code)}，避免 task/category 漂移。`
        : "如果这是生产任务，建议先绑定大类。只有系统型、过渡型任务才保留手工 business domain。";
    }
  };
  const syncBoundCategory = (category, options = {}) => {
    if (!(editForm instanceof HTMLFormElement)) {
      return;
    }
    const { overrideDomain = null } = options;
    const resolved = category || null;
    const businessDomainNode = editForm.elements.businessDomain;
    const previousCategoryCode = normalizeText(editForm.elements.categoryCode.value).trim();
    editForm.elements.categoryId.value = normalizeText(resolved?.id).trim();
    editForm.elements.categoryCode.value = normalizeText(resolved?.code).trim();
    if (bindingCategoryNode instanceof HTMLSelectElement) {
      bindingCategoryNode.value = normalizeText(resolved?.code).trim();
    }
    if (businessDomainNode instanceof HTMLInputElement) {
      if (resolved) {
        businessDomainNode.value = normalizeText(resolved.code).trim();
        businessDomainNode.readOnly = true;
        businessDomainNode.placeholder = "已由绑定大类自动镜像";
      } else {
        if (overrideDomain !== null) {
          businessDomainNode.value = normalizeText(overrideDomain).trim();
        } else if (normalizeText(businessDomainNode.value).trim() === previousCategoryCode) {
          businessDomainNode.value = "";
        }
        businessDomainNode.readOnly = false;
        businessDomainNode.placeholder = "仅在不绑定大类的系统任务中手填，例如：xianyu_onboarding";
      }
    }
    renderCategoryBinding(
      resolved,
      businessDomainNode instanceof HTMLInputElement ? businessDomainNode.value : overrideDomain,
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

  const formatQueriesText = (queries) =>
    (Array.isArray(queries) ? queries : [])
      .map((entry) => `${normalizeText(entry.query).trim()}|${normalizeText(entry.pages, "1")}|${normalizeText(entry.priority, "10")}`)
      .filter(Boolean)
      .join("\n");

  const parseQueriesText = (value) =>
    normalizeText(value)
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line, index) => {
        const [query, pages, priority] = line.split("|").map((part) => part.trim());
        return {
          query,
          pages: Number(pages || 1),
          priority: Number(priority || (index + 1) * 10),
          status: "ACTIVE",
        };
      });

  const formatLexiconText = (entries) =>
    (Array.isArray(entries) ? entries : [])
      .map((entry) => normalizeText(entry.term).trim())
      .filter(Boolean)
      .join("\n");

  const parseLexiconText = (value) =>
    normalizeText(value)
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((term, index) => ({
        term,
        priority: (index + 1) * 10,
        status: "ACTIVE",
      }));

  const renderSummary = (item) => {
    if (!(summaryNode instanceof HTMLElement)) {
      return;
    }
    if (!item) {
      summaryNode.innerHTML =
        '<p class="runtime-panel-text">选择左侧任务后，这里会显示 category 绑定、query 数量和 lexicon 数量。</p>';
      return;
    }
    const lexicons = item.lexicons || {};
    summaryNode.innerHTML = `
      <div class="config-summary-grid">
        <div class="runtime-stat">
          <span>Category</span>
          <strong>${safeText(item.categoryCode || item.categoryId || "-")}</strong>
        </div>
        <div class="runtime-stat">
          <span>Queries</span>
          <strong>${safeText((item.queries || []).length, "0")}</strong>
        </div>
        <div class="runtime-stat">
          <span>Brand Lexicon</span>
          <strong>${safeText((lexicons.BRAND || []).length, "0")}</strong>
        </div>
        <div class="runtime-stat">
          <span>Model Lexicon</span>
          <strong>${safeText((lexicons.MODEL || []).length, "0")}</strong>
        </div>
      </div>
    `;
  };

  const resetForm = () => {
    if (!(editForm instanceof HTMLFormElement)) {
      return;
    }
    editForm.reset();
    editForm.elements.taskType.value = "PRODUCTION";
    editForm.elements.profileKey.value = "chrome-attached";
    editForm.elements.parallelTabs.value = "1";
    editForm.elements.pagingLimit.value = "5";
    editForm.elements.status.value = "active";
    renderSummary(null);
    selectedTaskKey = null;
    syncBoundCategory(resolveCategoryByCode(preferredCategoryCode), { overrideDomain: "" });
  };

  const loadTaskIntoForm = (item) => {
    if (!(editForm instanceof HTMLFormElement) || !item) {
      return;
    }
    selectedTaskKey = item.taskKey;
    editForm.elements.taskKey.value = normalizeText(item.taskKey);
    editForm.elements.displayName.value = normalizeText(item.displayName);
    editForm.elements.categoryId.value = normalizeText(item.categoryId);
    editForm.elements.categoryCode.value = normalizeText(item.categoryCode);
    editForm.elements.businessDomain.value = normalizeText(item.businessDomain);
    editForm.elements.taskType.value = normalizeText(item.taskType, "PRODUCTION");
    editForm.elements.profileKey.value = normalizeText(item.profileKey, "chrome-attached");
    editForm.elements.parallelTabs.value = normalizeText(item.parallelTabs, "1");
    editForm.elements.pagingLimit.value = normalizeText(item.pagingLimit, "5");
    editForm.elements.status.value = normalizeText(item.status, "active");
    editForm.elements.queriesText.value = formatQueriesText(item.queries);
    editForm.elements.brandLexiconText.value = formatLexiconText(item.lexicons?.BRAND);
    editForm.elements.modelLexiconText.value = formatLexiconText(item.lexicons?.MODEL);
    editForm.elements.configLexiconText.value = formatLexiconText(item.lexicons?.CONFIG);
    syncBoundCategory(
      resolveCategoryById(item.categoryId) || resolveCategoryByCode(item.categoryCode) || {
        id: normalizeText(item.categoryId).trim(),
        code: normalizeText(item.categoryCode).trim(),
        name: normalizeText(item.categoryName).trim(),
      },
      { overrideDomain: item.businessDomain },
    );
    renderSummary(item);
  };

  const renderList = () => {
    if (!(listNode instanceof HTMLElement)) {
      return;
    }
    if (!taskItems.length) {
      listNode.innerHTML = `
        <article class="panel compact-panel">
          <p class="eyebrow">空列表</p>
          <h3>当前没有任务配置</h3>
          <p class="runtime-panel-text">点击上方“新建任务”，可以开始数据库驱动的 batch collect 配置。</p>
        </article>
      `;
      return;
    }
    listNode.innerHTML = taskItems
      .map((item) => {
        const activeClass = item.taskKey === selectedTaskKey ? "is-active" : "";
        return `
          <button type="button" class="config-list-item ${activeClass}" data-task-select="${safeAttr(item.taskKey)}">
            <div class="config-list-head">
              <div>
                <p class="eyebrow">${safeText(item.taskKey)}</p>
                <h3>${safeText(item.displayName)}</h3>
              </div>
              <span class="status-pill">${safeText(item.status)}</span>
            </div>
            <p class="runtime-panel-text">${safeText(`${normalizeText(item.businessDomain, "-")} · ${normalizeText(item.categoryCode, "-")}`)}</p>
            <div class="config-list-meta">
              <span>Queries ${safeText((item.queries || []).length, "0")}</span>
              <span>Tabs ${safeText(item.parallelTabs, "1")}</span>
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
    fillCategorySelect(bindingCategoryNode, { placeholder: "不绑定大类", includeEmpty: true });
    if (filterCategoryNode instanceof HTMLSelectElement && preferredCategoryCode) {
      filterCategoryNode.value = preferredCategoryCode;
    }
    syncBoundCategory(
      resolveCategoryById(editForm?.elements?.categoryId?.value)
      || resolveCategoryByCode(editForm?.elements?.categoryCode?.value)
      || (
        normalizeText(editForm?.elements?.categoryCode?.value).trim()
          ? {
              id: normalizeText(editForm?.elements?.categoryId?.value).trim(),
              code: normalizeText(editForm?.elements?.categoryCode?.value).trim(),
              name: "",
            }
          : null
      )
      || resolveCategoryByCode(preferredCategoryCode),
      {
        overrideDomain: editForm?.elements?.businessDomain?.value || "",
      },
    );
  };

  const loadList = async () => {
    const filters = formDataObject(controlsForm);
    const query = new URLSearchParams();
    if (normalizeText(filters.status).trim()) {
      query.set("status", normalizeText(filters.status).trim());
    }
    if (normalizeText(filters.categoryCodeFilter).trim()) {
      query.set("category_code", normalizeText(filters.categoryCodeFilter).trim());
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    const payload = await fetchJson(`/api/config/tasks${suffix}`);
    taskItems = Array.isArray(payload.items) ? payload.items : [];
    if (totalNode instanceof HTMLElement) {
      totalNode.textContent = `${taskItems.length} 个任务`;
    }
    if (selectedTaskKey) {
      const matched = taskItems.find((item) => item.taskKey === selectedTaskKey);
      if (matched) {
        loadTaskIntoForm(matched);
      } else {
        selectedTaskKey = null;
        renderSummary(null);
        syncBoundCategory(resolveCategoryByCode(preferredCategoryCode), { overrideDomain: "" });
      }
    } else if (preferredCategoryCode && taskItems.length) {
      loadTaskIntoForm(taskItems[0]);
    }
    renderList();
  };

  const collectPayload = () => {
    if (!(controlsForm instanceof HTMLFormElement) || !(editForm instanceof HTMLFormElement)) {
      return null;
    }
    const operatorFields = formDataObject(controlsForm);
    const taskFields = formDataObject(editForm);
    return {
      operatorId: normalizeText(operatorFields.operatorId).trim(),
      payload: {
        taskKey: normalizeText(taskFields.taskKey).trim(),
        displayName: normalizeText(taskFields.displayName).trim(),
        categoryId: normalizeText(taskFields.categoryId).trim() || undefined,
        categoryCode: normalizeText(taskFields.categoryCode).trim() || undefined,
        businessDomain: normalizeText(taskFields.businessDomain).trim() || undefined,
        taskType: normalizeText(taskFields.taskType, "PRODUCTION").trim() || "PRODUCTION",
        profileKey: normalizeText(taskFields.profileKey, "chrome-attached").trim() || "chrome-attached",
        parallelTabs: Number(taskFields.parallelTabs || 1),
        pagingLimit: Number(taskFields.pagingLimit || 5),
        status: normalizeText(taskFields.status, "active").trim() || "active",
        queries: parseQueriesText(taskFields.queriesText),
        lexicons: {
          BRAND: parseLexiconText(taskFields.brandLexiconText),
          MODEL: parseLexiconText(taskFields.modelLexiconText),
          CONFIG: parseLexiconText(taskFields.configLexiconText),
        },
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
    const payload = await fetchJson("/api/config/tasks", {
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
      apply ? `任务已保存：${normalizeText(payload?.task?.displayName, payload?.task?.taskKey)}` : `预演成功：${normalizeText(payload?.task?.displayName, payload?.task?.taskKey)}`,
      "success",
    );
    await loadList();
    if (payload?.task?.taskKey) {
      selectedTaskKey = payload.task.taskKey;
      const matched = taskItems.find((item) => item.taskKey === selectedTaskKey);
      if (matched) {
        loadTaskIntoForm(matched);
      }
    }
  };

  root.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const selectButton = target.closest("[data-task-select]");
    if (selectButton instanceof HTMLElement) {
      const taskKey = normalizeText(selectButton.dataset.taskSelect).trim();
      const matched = taskItems.find((item) => item.taskKey === taskKey);
      if (matched) {
        loadTaskIntoForm(matched);
        renderList();
      }
      return;
    }

    const actionButton = target.closest("[data-task-config-action]");
    if (!(actionButton instanceof HTMLElement)) {
      return;
    }
    const action = normalizeText(actionButton.dataset.taskConfigAction).trim();
    try {
      if (action === "new") {
        resetForm();
        renderList();
        setFeedback("已切到新建任务模式。", "info");
        return;
      }
      if (action === "refresh") {
        setFeedback("正在刷新任务列表...", "info");
        await loadList();
        setFeedback("任务列表已刷新。", "success");
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
      }
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "操作失败。", "error");
    }
  });

  if (bindingCategoryNode instanceof HTMLSelectElement) {
    bindingCategoryNode.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLSelectElement)) {
        return;
      }
      syncBoundCategory(resolveCategoryByCode(target.value), { overrideDomain: "" });
    });
  }

  if (editForm instanceof HTMLFormElement && editForm.elements.businessDomain instanceof HTMLInputElement) {
    editForm.elements.businessDomain.addEventListener("input", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) {
        return;
      }
      if (normalizeText(editForm.elements.categoryCode.value).trim()) {
        target.value = normalizeText(editForm.elements.categoryCode.value).trim();
      }
      renderCategoryBinding(
        resolveCategoryByCode(editForm.elements.categoryCode.value),
        target.value,
      );
    });
  }

  resetForm();
  loadCategories()
    .then(() => loadList())
    .then(() => {
      setFeedback(
        preferredCategoryCode
          ? `任务配置已加载，当前按大类 ${preferredCategoryCode} 过滤并预绑定到该大类。`
          : "任务配置已加载。",
        "success",
      );
    })
    .catch((error) => {
      setFeedback(error instanceof Error ? error.message : "加载失败。", "error");
    });
})();
