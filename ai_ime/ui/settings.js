const fieldIds = [
  "listener_enabled",
  "auto_learn_enabled",
  "auto_analyze_with_ai",
  "auto_deploy_rime",
  "record_full_keylog",
  "send_full_keylog",
  "start_on_login",
  "provider",
  "openai_base_url",
  "openai_model",
  "ollama_base_url",
  "ollama_model",
  "rime_dir",
  "rime_schema",
  "rime_dictionary",
  "rime_base_dictionary",
  "keylog_file",
];

const providerLabels = {
  "openai-compatible": "OpenAI 兼容",
  ollama: "Ollama",
  mock: "本地模拟",
};

let lastState = null;
let bridgeReady = false;
let providerPresets = [];
let activeRecordKind = "rules";

window.addEventListener("pywebviewready", () => {
  handleBridgeReady();
});

window.addEventListener("DOMContentLoaded", () => {
  bindUi();
  applyInitialState();
  waitForBridge();
});

function bindUi() {
  if (document.body.dataset.bound === "true") {
    return;
  }
  document.body.dataset.bound = "true";

  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => showPage(button.dataset.page));
  });
  document.querySelectorAll("[data-browse]").forEach((button) => {
    button.addEventListener("click", () => browsePath(button.dataset.browse, button.dataset.target));
  });
  document.getElementById("saveSettings").addEventListener("click", saveSettings);
  document.getElementById("reloadState").addEventListener("click", loadState);
  document.getElementById("detectRime").addEventListener("click", detectRime);
  document.getElementById("deployRime").addEventListener("click", deployRime);
  document.getElementById("openRimeDir").addEventListener("click", openRimeDir);
  document.getElementById("testProvider").addEventListener("click", testProvider);
  document.getElementById("model_select").addEventListener("change", applySelectedModel);
  document.getElementById("addManualCorrection").addEventListener("click", addManualCorrection);
  document.getElementById("openKeylogFile").addEventListener("click", () => openRecordFile("keylog"));
  document.getElementById("openLearningLog").addEventListener("click", () => openRecordFile("learning"));
  document.querySelectorAll("[data-record-kind]").forEach((button) => {
    button.addEventListener("click", () => openRecords(button.dataset.recordKind));
  });
  document.querySelectorAll("[data-record-tab]").forEach((button) => {
    button.addEventListener("click", () => setRecordKind(button.dataset.recordTab, true));
  });
  document.getElementById("recordSort").addEventListener("change", loadRecords);
  document.getElementById("refreshRecords").addEventListener("click", loadRecords);
  document.getElementById("provider_preset").addEventListener("change", applyProviderPreset);
  document.getElementById("provider").addEventListener("change", handleProviderTypeChange);
  document.getElementById("listener_enabled").addEventListener("change", syncTopbar);
  ["openai_base_url", "openai_model", "ollama_base_url"].forEach((id) => {
    document.getElementById(id).addEventListener("input", renderModelSummary);
  });
  syncActionState();
}

async function loadState() {
  if (!apiReady()) {
    return;
  }
  setStatus("正在读取配置");
  const response = await window.pywebview.api.load_state();
  if (!response.ok) {
    setStatus(response.message || "读取配置失败", "error");
    return;
  }
  lastState = response;
  fillForm(response.settings);
  renderMeta(response.meta);
  populateProviderPresets(response.meta.providerPresets || []);
  syncModelPage();
  renderModelSummary();
  syncTopbar();
  if (document.getElementById("records").classList.contains("active")) {
    await loadRecords();
  }
  renderStoragePaths(response.meta.storagePaths || []);
  renderModelSummary();
  setStatus("配置已读取", "ok");
}

async function saveSettings() {
  if (!apiReady()) {
    return;
  }
  setStatus("正在保存设置");
  const response = await window.pywebview.api.save_settings(collectPayload());
  if (!response.ok) {
    setStatus(response.message || "保存失败", "error");
    return;
  }
  document.getElementById("apiKey").value = "";
  setStatus(response.message || "设置已保存", "ok");
  await loadState();
}

async function detectRime() {
  if (!apiReady()) {
    return;
  }
  setStatus("正在检测 Rime");
  const response = await window.pywebview.api.detect_rime();
  if (!response.ok) {
    setStatus(response.message || "检测失败", "error");
    return;
  }
  document.getElementById("rime_dir").value = response.rimeDir || "";
  if (response.rimeSchema) {
    document.getElementById("rime_schema").value = response.rimeSchema;
  }
  setStatus(response.message || "Rime 已检测", "ok");
}

async function deployRime() {
  if (!apiReady()) {
    return;
  }
  setStatus("正在部署纠错词典");
  const saveResponse = await window.pywebview.api.save_settings(collectPayload());
  if (!saveResponse.ok) {
    setStatus(saveResponse.message || "保存失败，未部署", "error");
    return;
  }
  const response = await window.pywebview.api.deploy_rime(collectPayload());
  if (!response.ok) {
    setStatus(response.message || "部署失败", "error");
    return;
  }
  setStatus(response.message || "部署完成", "ok");
  await loadState();
}

async function testProvider() {
  if (!apiReady()) {
    return;
  }
  resetModelSelect("正在获取模型列表");
  setProviderTestState("testing", "正在测试连接");
  setStatus("正在测试模型连接");
  const response = await window.pywebview.api.test_provider(collectPayload());
  if (!response.ok) {
    setProviderTestState("error", response.message || "模型连接失败");
    setStatus(response.message || "模型连接失败", "error");
    return;
  }
  renderModelOptions(response.models || []);
  setProviderTestState("ok", response.message || "模型连接正常");
  setStatus(response.message || "模型连接正常", "ok");
}

async function addManualCorrection() {
  if (!apiReady()) {
    return;
  }
  setStatus("正在记录手动纠错");
  const response = await window.pywebview.api.add_manual_correction({
    ...collectPayload(),
    correction: {
      wrongPinyin: document.getElementById("manualWrongPinyin").value.trim(),
      correctPinyin: document.getElementById("manualCorrectPinyin").value.trim(),
      committedText: document.getElementById("manualCommittedText").value.trim(),
    },
  });
  if (!response.ok) {
    setStatus(response.message || "记录失败", "error");
    return;
  }
  document.getElementById("manualWrongPinyin").value = "";
  document.getElementById("manualCorrectPinyin").value = "";
  document.getElementById("manualCommittedText").value = "";
  setStatus(response.message || "纠错已记录", "ok");
  await loadState();
  await openRecords("rules");
}

async function openRimeDir() {
  if (!apiReady()) {
    return;
  }
  const value = document.getElementById("rime_dir").value;
  const response = await window.pywebview.api.open_path(value);
  if (!response.ok) {
    setStatus(response.message || "打开目录失败", "error");
  }
}

async function openRecordFile(kind) {
  if (!apiReady()) {
    return;
  }
  const response = await window.pywebview.api.open_record_file(kind, collectPayload());
  if (!response.ok) {
    setStatus(response.message || "打开记录失败", "error");
  }
}

async function openRecords(kind = "rules") {
  await setRecordKind(kind, false);
  showPage("records", true);
  await loadRecords();
}

async function setRecordKind(kind = "rules", shouldLoad = true) {
  activeRecordKind = kind === "events" ? "events" : "rules";
  document.querySelectorAll("[data-record-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.recordTab === activeRecordKind);
  });
  if (shouldLoad) {
    await loadRecords();
  }
}

async function loadRecords() {
  if (!apiReady()) {
    return;
  }
  const sort = document.getElementById("recordSort").value;
  setStatus("正在读取纠错记录");
  const response = await window.pywebview.api.list_correction_records(sort);
  if (!response.ok) {
    setStatus(response.message || "读取纠错记录失败", "error");
    return;
  }
  renderRecords(activeRecordKind === "events" ? response.events : response.rules);
  setStatus("纠错记录已读取", "ok");
}

async function browsePath(kind, targetId) {
  if (!apiReady()) {
    return;
  }
  const target = document.getElementById(targetId);
  const response = await window.pywebview.api.choose_path(kind, target.value || "");
  if (response.ok && response.path) {
    target.value = response.path;
    setStatus("路径已更新", "ok");
  }
}

function showPage(pageId, skipRecordLoad = false) {
  document.querySelectorAll(".page").forEach((page) => {
    page.classList.toggle("active", page.id === pageId);
  });
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.page === pageId);
  });
  const page = document.getElementById(pageId);
  document.getElementById("pageTitle").textContent = page.dataset.title || "设置";
  if (pageId === "records" && !skipRecordLoad) {
    loadRecords();
  }
  if (pageId === "files" && lastState) {
    renderStoragePaths(lastState.meta.storagePaths || []);
  }
}

function fillForm(settings) {
  fieldIds.forEach((id) => {
    const element = document.getElementById(id);
    if (!element) {
      return;
    }
    if (element.type === "checkbox") {
      element.checked = Boolean(settings[id]);
    } else {
      element.value = settings[id] ?? "";
    }
  });
}

function collectPayload() {
  syncActiveModelInput();
  const settings = {};
  fieldIds.forEach((id) => {
    const element = document.getElementById(id);
    settings[id] = element.type === "checkbox" ? element.checked : element.value.trim();
  });
  settings.openai_api_key_env = "AI_IME_OPENAI_API_KEY";
  return {
    settings,
    apiKey: document.getElementById("apiKey").value.trim(),
  };
}

function renderMeta(meta) {
  document.getElementById("settingsPath").textContent = meta.settingsPath || "";
  document.getElementById("eventsCount").textContent = meta.eventsCount ?? 0;
  document.getElementById("enabledRulesCount").textContent = meta.enabledRulesCount ?? 0;
  document.getElementById("rulesCount").textContent = meta.rulesCount ?? 0;
  document.getElementById("apiKeyState").textContent = meta.apiKeySaved ? `已保存 ${meta.apiKeyMask}` : "未保存密钥";
}

function populateProviderPresets(presets) {
  providerPresets = Array.isArray(presets) ? presets : [];
  renderProviderPresetOptions();
}

function renderProviderPresetOptions() {
  const select = document.getElementById("provider_preset");
  const provider = document.getElementById("provider").value;
  const current = detectProviderPreset();
  select.innerHTML = "";
  select.appendChild(new Option(provider === "openai-compatible" ? "自定义中转商" : "自定义", "custom"));
  providerPresets.filter((preset) => preset.provider === provider).forEach((preset) => {
    const option = new Option(preset.label, preset.id);
    option.title = preset.description || "";
    select.appendChild(option);
  });
  select.value = current || "custom";
  if (!select.value) {
    select.value = "custom";
  }
}

function applyProviderPreset() {
  const presetId = document.getElementById("provider_preset").value;
  if (!presetId || presetId === "custom") {
    if (document.getElementById("provider").value === "openai-compatible") {
      document.getElementById("openai_base_url").value = "";
      document.getElementById("openai_model").value = "";
    }
    resetModelSelect("请先测试连接");
    setProviderTestState("", "等待测试");
    syncModelPage();
    renderModelSummary();
    syncTopbar();
    return;
  }
  const preset = providerPresets.find((item) => item.id === presetId);
  if (!preset) {
    return;
  }
  document.getElementById("provider").value = preset.provider;
  if (preset.provider === "ollama") {
    document.getElementById("ollama_base_url").value = preset.base_url || "http://localhost:11434";
    document.getElementById("ollama_model").value = preset.model || "";
  } else if (preset.provider === "openai-compatible") {
    document.getElementById("openai_base_url").value = preset.base_url || "";
    document.getElementById("openai_model").value = preset.model || "";
  } else if (preset.provider === "mock") {
    document.getElementById("openai_model").value = preset.model || "mock-model";
    document.getElementById("ollama_model").value = "";
  }
  resetModelSelect("请先测试连接");
  if (preset.provider !== "mock") {
    setProviderTestState("", "等待测试");
  }
  syncModelPage();
  renderModelSummary();
  syncTopbar();
  setStatus(`已应用接口预设：${preset.label}`, "ok");
}

function handleProviderTypeChange() {
  renderProviderPresetOptions();
  const provider = document.getElementById("provider").value;
  const defaultPreset = providerPresets.find((preset) => preset.provider === provider);
  if (defaultPreset) {
    document.getElementById("provider_preset").value = defaultPreset.id;
    applyProviderPreset();
  } else {
    document.getElementById("provider_preset").value = "custom";
    applyProviderPreset();
  }
  resetModelSelect("请先测试连接");
  syncModelPage();
  renderModelSummary();
  syncTopbar();
}

function detectProviderPreset() {
  const provider = document.getElementById("provider").value;
  const openaiBase = document.getElementById("openai_base_url").value.trim();
  const openaiModel = document.getElementById("openai_model").value.trim();
  const ollamaBase = document.getElementById("ollama_base_url").value.trim();
  const ollamaModel = document.getElementById("ollama_model").value.trim();
  const matched = providerPresets.find((preset) => {
    if (preset.provider !== provider) {
      return false;
    }
    if (provider === "openai-compatible") {
      return preset.base_url === openaiBase && preset.model === openaiModel;
    }
    if (provider === "ollama") {
      return preset.base_url === ollamaBase && preset.model === ollamaModel;
    }
    return provider === "mock";
  });
  return matched ? matched.id : "custom";
}

function syncModelPage() {
  const provider = document.getElementById("provider").value;
  document.getElementById("openaiProviderConfig").classList.toggle("active", provider === "openai-compatible");
  document.getElementById("ollamaProviderConfig").classList.toggle("active", provider === "ollama");
  document.getElementById("mockProviderConfig").classList.toggle("active", provider === "mock");
  if (provider === "ollama" && !document.getElementById("openai_model").value.trim()) {
    document.getElementById("openai_model").value = document.getElementById("ollama_model").value.trim();
  }
  if (provider === "mock") {
    renderModelOptions(["mock-model"]);
    setProviderTestState("ok", "本地模拟无需连接测试");
  }
  renderModelSummary();
}

function resetModelSelect(label) {
  const select = document.getElementById("model_select");
  select.innerHTML = "";
  select.appendChild(new Option(label, ""));
  select.disabled = true;
}

function renderModelOptions(models) {
  const select = document.getElementById("model_select");
  const items = Array.isArray(models) ? models.filter(Boolean) : [];
  select.innerHTML = "";
  if (items.length === 0) {
    select.appendChild(new Option("没有返回模型列表，可手动填写", ""));
    select.disabled = true;
    return;
  }
  select.disabled = false;
  items.forEach((model) => {
    select.appendChild(new Option(model, model));
  });
  const current = activeModelValue();
  if (current && items.includes(current)) {
    select.value = current;
  } else {
    select.value = items[0];
    applySelectedModel();
  }
}

function applySelectedModel() {
  const value = document.getElementById("model_select").value;
  if (!value) {
    return;
  }
  document.getElementById("openai_model").value = value;
  syncActiveModelInput();
  renderModelSummary();
}

function activeModelValue() {
  const provider = document.getElementById("provider").value;
  if (provider === "ollama") {
    return document.getElementById("ollama_model").value.trim() || document.getElementById("openai_model").value.trim();
  }
  return document.getElementById("openai_model").value.trim();
}

function syncActiveModelInput() {
  const provider = document.getElementById("provider").value;
  const model = document.getElementById("openai_model").value.trim() || document.getElementById("model_select").value;
  if (provider === "ollama") {
    document.getElementById("ollama_model").value = model;
  }
  renderModelSummary();
}

function renderModelSummary() {
  const provider = document.getElementById("provider")?.value || "";
  const summaryProvider = document.getElementById("summaryProvider");
  const summaryBaseUrl = document.getElementById("summaryBaseUrl");
  const summaryModel = document.getElementById("summaryModel");
  if (!summaryProvider || !summaryBaseUrl || !summaryModel) {
    return;
  }
  const presetSelect = document.getElementById("provider_preset");
  const presetLabel = presetSelect?.selectedOptions?.[0]?.textContent || "自定义";
  const baseUrl = provider === "ollama"
    ? document.getElementById("ollama_base_url").value.trim()
    : provider === "mock"
      ? "本地模拟"
      : document.getElementById("openai_base_url").value.trim();
  summaryProvider.textContent = `${providerLabels[provider] || provider || "未选择"} · ${presetLabel}`;
  summaryBaseUrl.textContent = baseUrl || "未填写";
  summaryModel.textContent = activeModelValue() || "未选择";
}

function setProviderTestState(type, message) {
  const node = document.getElementById("providerTestState");
  node.textContent = message;
  node.className = `connection-state ${type || ""}`.trim();
}

function renderRecords(records) {
  const list = document.getElementById("recordList");
  const empty = document.getElementById("recordEmpty");
  list.replaceChildren();
  const items = Array.isArray(records) ? records : [];
  empty.classList.toggle("active", items.length === 0);
  items.forEach((record, index) => {
    const row = document.createElement("div");
    row.className = "record-row";
    row.style.setProperty("--i", String(Math.min(index, 12)));
    row.appendChild(renderRecordTriple(record));
    row.appendChild(renderRecordMeta(record));
    row.appendChild(renderRecordActions(record));
    list.appendChild(row);
  });
}

function renderRecordTriple(record) {
  const wrapper = document.createElement("div");
  wrapper.className = "record-main";
  const triple = document.createElement("div");
  triple.className = "record-triple";
  triple.appendChild(recordToken(record.wrongPinyin || "", "record-code"));
  triple.appendChild(recordArrow());
  triple.appendChild(recordToken(record.correctPinyin || "", "record-code"));
  triple.appendChild(recordArrow());
  triple.appendChild(recordToken(record.committedText || "", "record-text"));
  wrapper.appendChild(triple);
  if (record.wrongCommittedText) {
    const wrongText = document.createElement("span");
    wrongText.className = "record-hint";
    wrongText.textContent = `错误候选：${record.wrongCommittedText}`;
    wrapper.appendChild(wrongText);
  }
  return wrapper;
}

function renderRecordMeta(record) {
  const meta = document.createElement("div");
  meta.className = "record-meta";
  if (activeRecordKind === "rules") {
    const confidence = Number(record.confidence || 0);
    meta.appendChild(recordMetaLine(`规则 #${record.id ?? "-"}`, `${record.provider || "rule"} · ${record.count || 0} 次 · ${(confidence * 100).toFixed(0)}%`));
    meta.appendChild(recordSmall(record.lastSeenAt || ""));
  } else {
    meta.appendChild(recordMetaLine(`事件 #${record.id ?? "-"}`, `${record.source || "unknown"} · ${record.commitKey || "unknown"}`));
    meta.appendChild(recordSmall(record.createdAt || ""));
  }
  return meta;
}

function renderRecordActions(record) {
  const actions = document.createElement("div");
  actions.className = "record-actions";
  const edit = document.createElement("button");
  edit.className = "icon-action";
  edit.textContent = "修改";
  edit.addEventListener("click", () => editRecord(record, actions.closest(".record-row")));
  const remove = document.createElement("button");
  remove.className = "icon-action danger";
  remove.textContent = "删除";
  remove.addEventListener("click", () => deleteRecord(record));
  actions.appendChild(edit);
  actions.appendChild(remove);
  return actions;
}

function editRecord(record, row) {
  if (!row) {
    return;
  }
  row.classList.add("editing");
  row.replaceChildren(renderRecordEditor(record));
}

function renderRecordEditor(record) {
  const form = document.createElement("div");
  form.className = "record-edit-form";
  form.appendChild(recordEditField("错误拼音", "wrongPinyin", record.wrongPinyin || ""));
  form.appendChild(recordEditField("正确拼音", "correctPinyin", record.correctPinyin || ""));
  if (activeRecordKind === "events") {
    form.appendChild(recordEditField("错误候选", "wrongCommittedText", record.wrongCommittedText || ""));
  }
  form.appendChild(recordEditField("正确汉字", "committedText", record.committedText || ""));
  const actions = document.createElement("div");
  actions.className = "record-edit-actions";
  const save = document.createElement("button");
  save.className = "primary compact-button";
  save.textContent = "保存";
  save.addEventListener("click", () => saveEditedRecord(record, form));
  const cancel = document.createElement("button");
  cancel.className = "secondary compact-button";
  cancel.textContent = "取消";
  cancel.addEventListener("click", loadRecords);
  actions.appendChild(save);
  actions.appendChild(cancel);
  form.appendChild(actions);
  return form;
}

function recordEditField(labelText, key, value) {
  const label = document.createElement("label");
  label.className = "record-edit-field";
  const span = document.createElement("span");
  span.textContent = labelText;
  const input = document.createElement("input");
  input.type = "text";
  input.value = value;
  input.dataset.edit = key;
  input.spellcheck = false;
  label.appendChild(span);
  label.appendChild(input);
  return label;
}

async function saveEditedRecord(record, form) {
  if (!apiReady()) {
    return;
  }
  const payload = {
    ...record,
    wrongPinyin: form.querySelector('[data-edit="wrongPinyin"]').value.trim(),
    correctPinyin: form.querySelector('[data-edit="correctPinyin"]').value.trim(),
    committedText: form.querySelector('[data-edit="committedText"]').value.trim(),
    wrongCommittedText: form.querySelector('[data-edit="wrongCommittedText"]')?.value.trim() || "",
  };
  const response = await window.pywebview.api.update_correction_record(activeRecordKind, record.id, {
    ...payload,
  });
  if (!response.ok) {
    setStatus(response.message || "更新失败", "error");
    return;
  }
  setStatus(response.message || "记录已更新", "ok");
  await loadState();
}

async function deleteRecord(record) {
  if (!apiReady()) {
    return;
  }
  const ok = window.confirm(`删除这条${activeRecordKind === "events" ? "纠错事件" : "启用规则"}？\n${record.wrongPinyin} -> ${record.correctPinyin} -> ${record.committedText}`);
  if (!ok) {
    return;
  }
  const response = await window.pywebview.api.delete_correction_record(activeRecordKind, record.id);
  if (!response.ok) {
    setStatus(response.message || "删除失败", "error");
    return;
  }
  setStatus(response.message || "记录已删除", "ok");
  await loadState();
}

function recordToken(text, className) {
  const token = document.createElement("span");
  token.className = className;
  token.textContent = text || "-";
  return token;
}

function recordArrow() {
  const arrow = document.createElement("span");
  arrow.className = "record-arrow";
  arrow.textContent = "→";
  return arrow;
}

function recordMetaLine(title, detail) {
  const wrapper = document.createElement("div");
  const strong = document.createElement("strong");
  strong.textContent = title;
  wrapper.appendChild(strong);
  wrapper.appendChild(document.createTextNode(` ${detail}`));
  return wrapper;
}

function recordSmall(text) {
  const small = document.createElement("span");
  small.textContent = text || "";
  return small;
}

function renderStoragePaths(paths) {
  const list = document.getElementById("fileList");
  if (!list) {
    return;
  }
  list.replaceChildren();
  (Array.isArray(paths) ? paths : []).forEach((item) => {
    const row = document.createElement("div");
    row.className = "file-row";
    const main = document.createElement("div");
    main.className = "file-main";
    const title = document.createElement("strong");
    title.textContent = item.label || item.id || "文件";
    const path = document.createElement("code");
    path.textContent = item.path || "";
    const desc = document.createElement("span");
    desc.textContent = item.description || "";
    main.appendChild(title);
    main.appendChild(path);
    main.appendChild(desc);
    const button = document.createElement("button");
    button.className = "secondary compact-button";
    button.textContent = "打开位置";
    button.addEventListener("click", () => openStoragePath(item.path));
    row.appendChild(main);
    row.appendChild(button);
    list.appendChild(row);
  });
}

async function openStoragePath(path) {
  if (!apiReady()) {
    return;
  }
  const response = await window.pywebview.api.open_location(path || "");
  if (!response.ok) {
    setStatus(response.message || "打开位置失败", "error");
  }
}

function syncTopbar() {
  const listener = document.getElementById("listener_enabled").checked;
  const provider = document.getElementById("provider").value;
  document.getElementById("listenerPill").textContent = listener ? "监听中" : "已暂停";
  document.getElementById("providerPill").textContent = providerLabels[provider] || provider;
  const preset = document.getElementById("provider_preset");
  if (preset) {
    preset.value = detectProviderPreset();
  }
}

function setStatus(message, type = "") {
  const status = document.getElementById("statusText");
  status.textContent = message;
  status.className = `status-text ${type}`.trim();
}

function apiReady() {
  if (window.pywebview && window.pywebview.api) {
    return true;
  }
  setStatus("本地后端正在连接，请稍候");
  return false;
}

function applyInitialState() {
  const node = document.getElementById("initial-state");
  if (!node || !node.textContent) {
    syncTopbar();
    return;
  }
  try {
    const state = JSON.parse(node.textContent);
    if (!state.ok) {
      setStatus(state.message || "初始配置读取失败", "error");
      return;
    }
    lastState = state;
    fillForm(state.settings);
    renderMeta(state.meta);
    populateProviderPresets(state.meta.providerPresets || []);
    renderStoragePaths(state.meta.storagePaths || []);
    syncModelPage();
    renderModelSummary();
    syncTopbar();
    setStatus("配置已预载，正在连接本地后端");
  } catch {
    setStatus("初始配置解析失败", "error");
  }
}

function syncActionState() {
  const pending = !bridgeReady && !(window.pywebview && window.pywebview.api);
  document.querySelectorAll("#saveSettings, #reloadState, #detectRime, #deployRime, #openRimeDir, #testProvider, #addManualCorrection, #openKeylogFile, #openLearningLog, #refreshRecords, [data-browse], [data-record-kind], [data-record-tab]").forEach((button) => {
    button.disabled = pending;
    button.classList.toggle("is-pending", pending);
  });
  if (pending) {
    window.setTimeout(syncActionState, 100);
  }
}

function handleBridgeReady() {
  if (bridgeReady) {
    return;
  }
  bridgeReady = true;
  bindUi();
  syncActionState();
  loadState();
}

function waitForBridge(attempt = 0) {
  if (window.pywebview && window.pywebview.api) {
    handleBridgeReady();
    return;
  }
  setStatus("正在连接本地后端");
  if (attempt < 80) {
    window.setTimeout(() => waitForBridge(attempt + 1), 50);
    return;
  }
  setStatus("本地后端连接超时，请关闭窗口后重试", "error");
}
