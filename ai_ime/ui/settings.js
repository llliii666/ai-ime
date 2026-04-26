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
  document.getElementById("provider").addEventListener("change", syncTopbar);
  document.getElementById("listener_enabled").addEventListener("change", syncTopbar);
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
  syncTopbar();
  if (document.getElementById("records").classList.contains("active")) {
    await loadRecords();
  }
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
  setStatus("正在测试模型连接");
  const response = await window.pywebview.api.test_provider(collectPayload());
  setStatus(response.message || (response.ok ? "模型连接正常" : "模型连接失败"), response.ok ? "ok" : "error");
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
  const select = document.getElementById("provider_preset");
  const current = select.value || "custom";
  select.innerHTML = "";
  select.appendChild(new Option("自定义", "custom"));
  providerPresets.forEach((preset) => {
    const option = new Option(preset.label, preset.id);
    option.title = preset.description || "";
    select.appendChild(option);
  });
  select.value = detectProviderPreset() || current;
  if (!select.value) {
    select.value = "custom";
  }
}

function applyProviderPreset() {
  const presetId = document.getElementById("provider_preset").value;
  if (!presetId || presetId === "custom") {
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
  }
  syncTopbar();
  setStatus(`已应用接口预设：${preset.label}`, "ok");
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
    list.appendChild(row);
  });
}

function renderRecordTriple(record) {
  const triple = document.createElement("div");
  triple.className = "record-triple";
  triple.appendChild(recordToken(record.wrongPinyin || "", "record-code"));
  triple.appendChild(recordArrow());
  triple.appendChild(recordToken(record.correctPinyin || "", "record-code"));
  triple.appendChild(recordArrow());
  triple.appendChild(recordToken(record.committedText || "", "record-text"));
  return triple;
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
