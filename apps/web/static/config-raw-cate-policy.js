(() => {
  const root = document.querySelector("[data-raw-cate-policy-page]");
  if (!(root instanceof HTMLElement)) {
    return;
  }

  const controlsForm = root.querySelector("[data-raw-cate-policy-controls]");
  const editForm = root.querySelector("[data-raw-cate-policy-form]");
  const feedbackNode = root.querySelector("[data-raw-cate-policy-feedback]");
  const totalNode = root.querySelector("[data-raw-cate-policy-total]");
  const listNode = root.querySelector("[data-raw-cate-policy-list]");
  const summaryNode = root.querySelector("[data-raw-cate-policy-summary]");

  let policyItems = [];
  let selectedPolicyId = null;

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
    return Object.fromEntries(new FormData(form).entries());
  };

  const renderSummary = (item) => {
    if (!(summaryNode instanceof HTMLElement)) {
      return;
    }
    if (!item) {
      summaryNode.innerHTML =
        '<p class="runtime-panel-text">选择左侧 policy 后，这里会显示 queue 样本、命中的 category/template，以及当前 policy 语义。</p>';
      return;
    }
    const queueSnapshot = item.queueSnapshot || {};
    summaryNode.innerHTML = `
      <div class="config-summary-grid">
        <div class="runtime-stat">
          <span>Policy Mode</span>
          <strong>${safeText(item.policyMode || "-")}</strong>
        </div>
        <div class="runtime-stat">
          <span>Category</span>
          <strong>${safeText(item.categoryCode || item.categoryId || "-")}</strong>
        </div>
        <div class="runtime-stat">
          <span>Template</span>
          <strong>${safeText(item.templateOverrideId || item.templateId || "-")}</strong>
        </div>
        <div class="runtime-stat">
          <span>Queue Samples</span>
          <strong>${safeText(queueSnapshot.itemCountSnapshot, "0")}</strong>
        </div>
      </div>
      <p class="runtime-panel-text">${safeText((queueSnapshot.sampleTitles || []).join(" / "), "无样本标题")}</p>
    `;
  };

  const resetForm = () => {
    if (!(editForm instanceof HTMLFormElement)) {
      return;
    }
    editForm.reset();
    editForm.elements.mappingId.value = "";
    editForm.elements.matchScope.value = "C_CAT";
    editForm.elements.policyMode.value = "FORCE_TEMPLATE";
    editForm.elements.status.value = "ACTIVE";
    editForm.elements.resolutionSource.value = "manual";
    selectedPolicyId = null;
    renderSummary(null);
  };

  const loadPolicyIntoForm = (item) => {
    if (!(editForm instanceof HTMLFormElement) || !item) {
      return;
    }
    selectedPolicyId = item.id;
    editForm.elements.mappingId.value = normalizeText(item.id);
    editForm.elements.matchScope.value = normalizeText(item.matchScope, "C_CAT");
    editForm.elements.xianyuCCatId.value = normalizeText(item.xianyuCCatId);
    editForm.elements.xianyuCatId.value = normalizeText(item.xianyuCatId);
    editForm.elements.xianyuTbCatId.value = normalizeText(item.xianyuTbCatId);
    editForm.elements.rawCategoryName.value = normalizeText(item.rawCategoryName);
    editForm.elements.policyMode.value = normalizeText(item.policyMode, "FORCE_TEMPLATE");
    editForm.elements.categoryId.value = normalizeText(item.categoryId);
    editForm.elements.categoryCode.value = normalizeText(item.categoryCode);
    editForm.elements.templateId.value = normalizeText(item.templateId);
    editForm.elements.templateOverrideId.value = normalizeText(item.templateOverrideId);
    editForm.elements.status.value = normalizeText(item.status, "ACTIVE");
    editForm.elements.resolutionSource.value = normalizeText(item.resolutionSource, "manual");
    renderSummary(item);
  };

  const renderList = () => {
    if (!(listNode instanceof HTMLElement)) {
      return;
    }
    if (!policyItems.length) {
      listNode.innerHTML = `
        <article class="panel compact-panel">
          <p class="eyebrow">空列表</p>
          <h3>当前没有 raw cate policy</h3>
          <p class="runtime-panel-text">这里会逐步替代“raw cate 直连模板”的旧语义，收敛为治理和 override 配置。</p>
        </article>
      `;
      return;
    }
    listNode.innerHTML = policyItems
      .map((item) => {
        const activeClass = item.id === selectedPolicyId ? "is-active" : "";
        return `
          <button type="button" class="config-list-item ${activeClass}" data-raw-cate-policy-select="${safeAttr(item.id)}">
            <div class="config-list-head">
              <div>
                <p class="eyebrow">${safeText(item.matchKey)}</p>
                <h3>${safeText(item.policyMode || "FORCE_TEMPLATE")}</h3>
              </div>
              <span class="status-pill">${safeText(item.status)}</span>
            </div>
            <p class="runtime-panel-text">${safeText(item.rawCategoryName || item.matchScope)}</p>
            <div class="config-list-meta">
              <span>${safeText(item.categoryCode || "-")}</span>
              <span>${safeText(item.templateOverrideId || item.templateId || "-")}</span>
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
    if (normalizeText(filters.policyModeFilter).trim()) {
      query.set("policy_mode", normalizeText(filters.policyModeFilter).trim());
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    const payload = await fetchJson(`/api/config/raw-cate-policy${suffix}`);
    policyItems = Array.isArray(payload.items) ? payload.items : [];
    if (totalNode instanceof HTMLElement) {
      totalNode.textContent = `${policyItems.length} 条策略`;
    }
    renderList();
  };

  const collectPayload = () => {
    if (!(controlsForm instanceof HTMLFormElement) || !(editForm instanceof HTMLFormElement)) {
      return null;
    }
    const operatorFields = formDataObject(controlsForm);
    const policyFields = formDataObject(editForm);
    return {
      operatorId: normalizeText(operatorFields.operatorId).trim(),
      payload: {
        mappingId: normalizeText(policyFields.mappingId).trim() || undefined,
        matchScope: normalizeText(policyFields.matchScope, "C_CAT").trim() || "C_CAT",
        xianyuCCatId: normalizeText(policyFields.xianyuCCatId).trim() || undefined,
        xianyuCatId: normalizeText(policyFields.xianyuCatId).trim() || undefined,
        xianyuTbCatId: normalizeText(policyFields.xianyuTbCatId).trim() || undefined,
        rawCategoryName: normalizeText(policyFields.rawCategoryName).trim() || undefined,
        policyMode: normalizeText(policyFields.policyMode, "FORCE_TEMPLATE").trim() || "FORCE_TEMPLATE",
        categoryId: normalizeText(policyFields.categoryId).trim() || undefined,
        categoryCode: normalizeText(policyFields.categoryCode).trim() || undefined,
        templateId: normalizeText(policyFields.templateId).trim() || undefined,
        templateOverrideId: normalizeText(policyFields.templateOverrideId).trim() || undefined,
        status: normalizeText(policyFields.status, "ACTIVE").trim() || "ACTIVE",
        resolutionSource: normalizeText(policyFields.resolutionSource, "manual").trim() || "manual",
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
    const payload = await fetchJson("/api/config/raw-cate-policy", {
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
        ? `raw cate policy 已保存：${normalizeText(payload?.policy?.matchKey)}`
        : `raw cate policy 预演成功：${normalizeText(payload?.policy?.matchKey)}`,
      "success",
    );
    await loadList();
    if (payload?.policy?.id) {
      const matched = policyItems.find((item) => item.id === payload.policy.id);
      if (matched) {
        loadPolicyIntoForm(matched);
        renderList();
      }
    }
  };

  root.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const selectButton = target.closest("[data-raw-cate-policy-select]");
    if (selectButton instanceof HTMLElement) {
      const policyId = normalizeText(selectButton.dataset.rawCatePolicySelect).trim();
      const matched = policyItems.find((item) => item.id === policyId);
      if (matched) {
        loadPolicyIntoForm(matched);
        renderList();
      }
      return;
    }

    const actionButton = target.closest("[data-raw-cate-policy-action]");
    if (!(actionButton instanceof HTMLElement)) {
      return;
    }
    const action = normalizeText(actionButton.dataset.rawCatePolicyAction).trim();
    try {
      if (action === "new") {
        resetForm();
        renderList();
        setFeedback("已切到新建 raw cate policy 模式。", "info");
        return;
      }
      if (action === "refresh") {
        setFeedback("正在刷新 raw cate policy 列表...", "info");
        await loadList();
        setFeedback("raw cate policy 列表已刷新。", "success");
        return;
      }
      if (action === "save-dry-run") {
        setFeedback("正在预演保存 raw cate policy...", "info");
        await savePayload(false);
        return;
      }
      if (action === "save-apply") {
        setFeedback("正在正式保存 raw cate policy...", "info");
        await savePayload(true);
      }
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "操作失败。", "error");
    }
  });

  resetForm();
  loadList()
    .then(() => {
      setFeedback("raw cate policy 已加载。", "success");
    })
    .catch((error) => {
      setFeedback(error instanceof Error ? error.message : "加载失败。", "error");
    });
})();
