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
  syncTopbar();
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

function showPage(pageId) {
  document.querySelectorAll(".page").forEach((page) => {
    page.classList.toggle("active", page.id === pageId);
  });
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.page === pageId);
  });
  const page = document.getElementById(pageId);
  document.getElementById("pageTitle").textContent = page.dataset.title || "设置";
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

function syncTopbar() {
  const listener = document.getElementById("listener_enabled").checked;
  const provider = document.getElementById("provider").value;
  document.getElementById("listenerPill").textContent = listener ? "监听中" : "已暂停";
  document.getElementById("providerPill").textContent = providerLabels[provider] || provider;
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
    syncTopbar();
    setStatus("配置已预载，正在连接本地后端");
  } catch {
    setStatus("初始配置解析失败", "error");
  }
}

function syncActionState() {
  const pending = !bridgeReady && !(window.pywebview && window.pywebview.api);
  document.querySelectorAll("#saveSettings, #reloadState, #detectRime, #deployRime, #openRimeDir, #testProvider, [data-browse]").forEach((button) => {
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
