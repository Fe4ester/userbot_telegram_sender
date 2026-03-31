const state = {
  settings: null,
  runtime: null,
  accounts: [],
  activeAccountId: null,
  targets: [],
  targetsPage: { page: 1, size: 5 },
  accountChats: [],
  accountChatsPage: { offset: 0, limit: 12, total: 0 },
  logsPage: { offset: 0, limit: 300, total: 0 },
};
let uiHeartbeatTimer = null;

const qs = (selector) => document.querySelector(selector);

function bindTabs() {
  const tabs = document.querySelectorAll(".tab");
  const panels = document.querySelectorAll(".panel");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((item) => item.classList.remove("active"));
      panels.forEach((item) => item.classList.remove("active"));
      tab.classList.add("active");
      qs(`.panel[data-panel="${tab.dataset.tab}"]`).classList.add("active");
    });
  });
}

function ensureAccountShape(account) {
  if (!account.broadcast) {
    account.broadcast = {
      message: "Test message",
      parse_mode: "html",
      targets: [],
      dispatch: {
        default_interval_seconds: 0,
        default_repeat: 0,
        retry_attempts: 3,
        retry_delay_seconds: 3,
        continue_on_error: true,
      },
      logging: { level: "INFO", file: "logs/broadcast.log" },
    };
  }
  account.broadcast.targets = account.broadcast.targets || [];
}

function fillFromState(settings, runtime) {
  state.settings = settings;
  state.runtime = runtime;
  state.accounts = [...(settings.userbots || [])];
  state.accounts.forEach(ensureAccountShape);
  state.activeAccountId = settings.active_userbot_id || state.accounts[0]?.id || null;

  renderAccounts();
  loadActiveAccountCampaign();
  setRuntime(runtime);
}

function renderAccounts() {
  const select = qs("#account-select");
  select.innerHTML = "";
  state.accounts.forEach((account) => {
    const option = document.createElement("option");
    option.value = account.id;
    option.textContent = account.name || account.session || account.id;
    select.appendChild(option);
  });
  if (!state.activeAccountId && state.accounts.length) {
    state.activeAccountId = state.accounts[0].id;
  }
  select.value = state.activeAccountId || "";
  fillActiveAccountFields();
}

function getActiveAccount() {
  return state.accounts.find((item) => item.id === state.activeAccountId) || null;
}

function fillActiveAccountFields() {
  const account = getActiveAccount();
  if (!account) return;
  qs("#account-name").value = account.name || "";
  qs("#api-id").value = account.api_id || "";
  qs("#api-hash").value = account.api_hash || "";
  qs("#session").value = account.session || "userbot";
}

function loadActiveAccountCampaign() {
  const account = getActiveAccount();
  if (!account) return;
  ensureAccountShape(account);
  qs("#message").value = account.broadcast.message || "";
  qs("#parse-mode").value = account.broadcast.parse_mode || "html";
  updateFormatHint();
  updatePreview();

  state.targets = [...(account.broadcast.targets || [])];
  state.targetsPage.page = 1;
  renderTargetsPage();
}

function persistActiveAccountFields() {
  const account = getActiveAccount();
  if (!account) return;
  account.name = qs("#account-name").value.trim() || account.name || "Userbot";
  account.api_id = qs("#api-id").value.trim();
  account.api_hash = qs("#api-hash").value.trim();
  account.session = qs("#session").value.trim() || "userbot";
}

function persistActiveAccountCampaign() {
  const account = getActiveAccount();
  if (!account) return;
  ensureAccountShape(account);
  account.broadcast.message = qs("#message").value;
  account.broadcast.parse_mode = qs("#parse-mode").value;
  account.broadcast.targets = state.targets
    .filter((item) => item.ref !== "" && item.ref != null)
    .map((item) => ({
      ref: item.ref,
      enabled: Boolean(item.enabled),
      interval_seconds: item.interval_seconds ?? null,
      initial_delay_seconds: Number(item.initial_delay_seconds || 0),
      repeat: Number(item.repeat ?? 0),
    }));
}

function addAccount() {
  persistActiveAccountFields();
  persistActiveAccountCampaign();
  const next = state.accounts.length + 1;
  const id = randomId();
  const template = state.accounts[0]?.broadcast || {};
  state.accounts.push({
    id,
    name: `Userbot ${next}`,
    api_id: "",
    api_hash: "",
    session: `userbot_${next}`,
    broadcast: {
      message: "Test message",
      parse_mode: "html",
      targets: [],
      dispatch: {
        default_interval_seconds: template.dispatch?.default_interval_seconds ?? 0,
        default_repeat: template.dispatch?.default_repeat ?? 0,
        retry_attempts: template.dispatch?.retry_attempts ?? 3,
        retry_delay_seconds: template.dispatch?.retry_delay_seconds ?? 3,
        continue_on_error: template.dispatch?.continue_on_error ?? true,
      },
      logging: {
        level: template.logging?.level ?? "INFO",
        file: template.logging?.file ?? "logs/broadcast.log",
      },
    },
  });
  state.activeAccountId = id;
  renderAccounts();
  loadActiveAccountCampaign();
}

function removeActiveAccount() {
  if (state.accounts.length <= 1) {
    alert("Нужно оставить минимум один аккаунт.");
    return;
  }
  state.accounts = state.accounts.filter((item) => item.id !== state.activeAccountId);
  state.activeAccountId = state.accounts[0]?.id || null;
  renderAccounts();
  loadActiveAccountCampaign();
}

function onAccountSwitch(newId) {
  persistActiveAccountFields();
  persistActiveAccountCampaign();
  state.activeAccountId = newId;
  fillActiveAccountFields();
  loadActiveAccountCampaign();
}

function renderTargetsPage() {
  const node = qs("#chat-list");
  node.innerHTML = "";
  const total = state.targets.length;
  const maxPage = Math.max(1, Math.ceil(total / state.targetsPage.size));
  state.targetsPage.page = Math.max(1, Math.min(state.targetsPage.page, maxPage));
  const from = (state.targetsPage.page - 1) * state.targetsPage.size;
  const to = Math.min(total, from + state.targetsPage.size);

  for (let i = from; i < to; i += 1) {
    node.appendChild(createTargetItem(state.targets[i], i));
  }
  qs("#targets-page-info").textContent = `${state.targetsPage.page} / ${maxPage}`;
}

function createTargetItem(target, index) {
  const wrapper = document.createElement("div");
  wrapper.className = "chat-item";
  wrapper.innerHTML = `
    <div class="chat-item-grid">
      <label class="field">
        <span>Группа</span>
        <input data-key="ref" data-idx="${index}" placeholder="id / ссылка / @username" />
        <small>Куда отправлять сообщение</small>
      </label>
      <label class="field">
        <span>Интервал (сек)</span>
        <input data-key="interval_seconds" data-idx="${index}" type="number" min="0" step="0.1" placeholder="например 10" />
        <small>Пауза между отправками в эту группу</small>
      </label>
      <label class="field">
        <span>Повторы</span>
        <input data-key="repeat" data-idx="${index}" type="number" min="0" step="1" placeholder="0 = бесконечно" />
        <small>Сколько отправок сделать в эту группу</small>
      </label>
      <label class="field">
        <span>Стартовая задержка</span>
        <input data-key="initial_delay_seconds" data-idx="${index}" type="number" min="0" step="0.1" placeholder="0" />
        <small>Пауза перед первой отправкой</small>
      </label>
      <label class="field">
        <span>Статус</span>
        <select data-key="enabled" data-idx="${index}">
          <option value="true">включено</option>
          <option value="false">выключено</option>
        </select>
        <small>Отключенные группы не участвуют</small>
      </label>
      <button class="remove" data-idx="${index}">Удалить</button>
    </div>
  `;

  wrapper.querySelector('[data-key="ref"]').value = target.ref ?? "";
  wrapper.querySelector('[data-key="interval_seconds"]').value = target.interval_seconds ?? "";
  wrapper.querySelector('[data-key="repeat"]').value = target.repeat ?? "";
  wrapper.querySelector('[data-key="initial_delay_seconds"]').value = target.initial_delay_seconds ?? 0;
  wrapper.querySelector('[data-key="enabled"]').value = String(target.enabled ?? true);

  wrapper.querySelectorAll("input,select").forEach((el) => {
    el.addEventListener("change", (event) => onTargetFieldChange(event.currentTarget));
  });
  wrapper.querySelector(".remove").addEventListener("click", (event) => {
    const idx = Number(event.currentTarget.dataset.idx);
    state.targets.splice(idx, 1);
    renderTargetsPage();
  });

  return wrapper;
}

function onTargetFieldChange(element) {
  const idx = Number(element.dataset.idx);
  if (!Number.isInteger(idx) || !state.targets[idx]) return;
  const key = element.dataset.key;
  const target = state.targets[idx];

  if (key === "enabled") {
    target.enabled = element.value === "true";
  } else if (key === "ref") {
    const value = element.value.trim();
    target.ref = /^-?\d+$/.test(value) ? Number(value) : value;
  } else if (key === "interval_seconds" || key === "initial_delay_seconds") {
    const value = element.value.trim();
    target[key] = value === "" ? null : Number(value);
    if (key === "initial_delay_seconds" && target[key] == null) target[key] = 0;
  } else if (key === "repeat") {
    const value = element.value.trim();
    target.repeat = value === "" ? 0 : Number(value);
  }
}

function addTarget() {
  state.targets.push({
    ref: "",
    interval_seconds: 10,
    initial_delay_seconds: 0,
    repeat: 0,
    enabled: true,
  });
  state.targetsPage.page = Math.max(1, Math.ceil(state.targets.length / state.targetsPage.size));
  renderTargetsPage();
}

function renderAccountChats() {
  const node = qs("#account-chat-list");
  if (!state.accountChats.length) {
    node.innerHTML = '<div class="empty-note">Список пуст. Нажми "Обновить список".</div>';
  } else {
    node.innerHTML = "";
    state.accountChats.forEach((chat) => {
      const item = document.createElement("div");
      item.className = "account-chat-item";
      item.innerHTML = `
        <div class="account-chat-main">
          <div class="chat-title">${escapeHtml(chat.title)}</div>
          <div class="chat-meta">id=${chat.id} ${chat.username ? `| @${escapeHtml(chat.username)}` : ""}</div>
        </div>
        <button class="btn btn-ghost add-from-account">Добавить</button>
      `;
      item.querySelector(".add-from-account").addEventListener("click", () => {
        state.targets.push({
          ref: chat.username ? `@${chat.username}` : chat.id,
          enabled: true,
          interval_seconds: 10,
          initial_delay_seconds: 0,
          repeat: 0,
        });
        renderTargetsPage();
      });
      node.appendChild(item);
    });
  }
  const page = Math.floor(state.accountChatsPage.offset / state.accountChatsPage.limit) + 1;
  const maxPage = Math.max(1, Math.ceil(state.accountChatsPage.total / state.accountChatsPage.limit));
  qs("#account-chats-page-info").textContent = `${page} / ${maxPage}`;
}

function renderLogs(data) {
  qs("#log-output").textContent = data.items
    .map((item) => `${item.timestamp} [${item.level}] ${item.message}`)
    .join("\n");
  state.logsPage.total = data.total;
  state.logsPage.offset = data.offset;
  const page = Math.floor(data.offset / data.limit) + 1;
  const maxPage = Math.max(1, Math.ceil(data.total / data.limit));
  qs("#logs-page-info").textContent = `${page} / ${maxPage}`;
}

function collectSettings() {
  persistActiveAccountFields();
  persistActiveAccountCampaign();
  return {
    userbots: state.accounts,
    active_userbot_id: state.activeAccountId,
  };
}

function setRuntime(runtime) {
  if (!runtime) return;
  qs("#runtime-state").textContent = runtime.running ? "Статус: работает" : "Статус: ожидание";
  qs("#runtime-meta").textContent = `результатов=${runtime.results_count ?? 0} старт=${runtime.started_at ?? "-"} финиш=${runtime.finished_at ?? "-"}`;
  qs("#btn-start").disabled = runtime.running;
  qs("#btn-stop").disabled = !runtime.running;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

async function saveSettings() {
  await api("/api/state", { method: "PUT", body: JSON.stringify(collectSettings()) });
}

async function startBroadcast() {
  await saveSettings();
  const data = await api("/api/start", { method: "POST" });
  setRuntime(data.runtime);
}

async function stopBroadcast() {
  const data = await api("/api/stop", { method: "POST" });
  setRuntime(data.runtime);
}

async function refreshLogs(offset = state.logsPage.offset) {
  const level = qs("#log-filter-level").value;
  const query = new URLSearchParams({
    limit: String(state.logsPage.limit),
    offset: String(Math.max(0, offset)),
  });
  if (level) query.set("level", level);
  const data = await api(`/api/logs?${query.toString()}`);
  renderLogs(data);
}

async function refreshState() {
  const data = await api("/api/state");
  fillFromState(data.settings, data.runtime);
}

function userbotPayloadFromFields() {
  return {
    api_id: qs("#api-id").value.trim(),
    api_hash: qs("#api-hash").value.trim(),
    session: qs("#session").value.trim() || "userbot",
  };
}

async function loadAccountChats(offset = state.accountChatsPage.offset) {
  const payload = {
    account_id: state.activeAccountId,
    userbot: userbotPayloadFromFields(),
    offset: Math.max(0, offset),
    limit: state.accountChatsPage.limit,
  };
  const data = await api("/api/chats/list", { method: "POST", body: JSON.stringify(payload) });
  state.accountChats = data.items || [];
  state.accountChatsPage.total = data.total || 0;
  state.accountChatsPage.offset = data.offset || 0;
  renderAccountChats();
}

async function authSendCode() {
  const payload = {
    account_id: state.activeAccountId,
    userbot: userbotPayloadFromFields(),
    phone: qs("#auth-phone").value.trim(),
  };
  const data = await api("/api/auth/send-code", { method: "POST", body: JSON.stringify(payload) });
  qs("#auth-status").textContent = data.status === "code_sent" ? "Код отправлен, проверь Telegram." : "Ожидание";
}

async function authVerifyCode() {
  const payload = {
    account_id: state.activeAccountId,
    userbot: userbotPayloadFromFields(),
    code: qs("#auth-code").value.trim(),
  };
  const data = await api("/api/auth/verify-code", { method: "POST", body: JSON.stringify(payload) });
  qs("#auth-status").textContent =
    data.status === "password_required"
      ? "Нужен пароль 2FA. Введи пароль ниже."
      : "Код подтвержден. Сессия создана.";
}

async function authVerifyPassword() {
  const payload = {
    account_id: state.activeAccountId,
    userbot: userbotPayloadFromFields(),
    password: qs("#auth-password").value.trim(),
  };
  await api("/api/auth/verify-password", { method: "POST", body: JSON.stringify(payload) });
  qs("#auth-status").textContent = "2FA подтвержден. Сессия готова.";
}

async function authCheckStatus() {
  const payload = { account_id: state.activeAccountId, userbot: userbotPayloadFromFields() };
  const data = await api("/api/auth/status", { method: "POST", body: JSON.stringify(payload) });
  qs("#auth-status").textContent = data.authorized
    ? "Статус авторизации: ВХОД ВЫПОЛНЕН"
    : "Статус авторизации: не авторизован";
}

async function checkStatusPage() {
  const payload = { account_id: state.activeAccountId, userbot: userbotPayloadFromFields() };
  const data = await api("/api/status/check", { method: "POST", body: JSON.stringify(payload) });
  const node = qs("#status-grid");
  const items = [
    ["Авторизован", boolToRu(data.authorized)],
    ["Аккаунт", data.account_name || "-"],
    ["Username", data.username ? `@${data.username}` : "-"],
    ["Телефон", data.phone || "-"],
    ["Premium", boolToRu(data.is_premium)],
    ["Количество групп", String(data.groups_count ?? 0)],
    ["SpamBlock", data.spam_block_state || "unknown"],
    ["Ответ @SpamBot", data.spam_block_message || "-"],
  ];
  node.innerHTML = items
    .map(([key, value]) => `<div class="status-item"><b>${escapeHtml(key)}:</b> ${escapeHtml(value)}</div>`)
    .join("");
}

function setupFormattingTools() {
  document.querySelectorAll(".fmt-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      wrapSelection(btn.dataset.wrap);
      updatePreview();
    });
  });
  qs("#insert-premium-emoji").addEventListener("click", () => {
    insertAtCursor("<tg-emoji emoji-id=\"5368324170671202286\">🔥</tg-emoji>");
    updatePreview();
  });
  qs("#parse-mode").addEventListener("change", () => {
    updateFormatHint();
    updatePreview();
  });
  qs("#message").addEventListener("input", updatePreview);
}

function wrapSelection(pattern) {
  const area = qs("#message");
  const [left, right] = pattern.split("|");
  const selected = area.value.slice(area.selectionStart, area.selectionEnd);
  area.setRangeText(`${left}${selected || "текст"}${right}`, area.selectionStart, area.selectionEnd, "end");
  area.focus();
}

function insertAtCursor(text) {
  const area = qs("#message");
  area.setRangeText(text, area.selectionStart, area.selectionEnd, "end");
  area.focus();
}

function updateFormatHint() {
  const mode = qs("#parse-mode").value;
  qs("#format-help").value =
    mode === "html"
      ? "HTML: <b>жирный</b>, <i>курсив</i>, <u>подчерк.</u>, <a href='https://...'>ссылка</a>, <tg-emoji emoji-id='...'>🔥</tg-emoji>"
      : "Markdown: **жирный**, __курсив__, `код`, [ссылка](https://...)";
}

function updatePreview() {
  const mode = qs("#parse-mode").value;
  const raw = qs("#message").value || "";
  const node = qs("#message-preview");
  if (mode === "html") {
    node.innerHTML = raw || "<span class='preview-placeholder'>Здесь будет предпросмотр</span>";
  } else {
    node.innerHTML = renderMarkdownPreview(raw);
  }
}

function renderMarkdownPreview(text) {
  if (!text.trim()) return "<span class='preview-placeholder'>Здесь будет предпросмотр</span>";
  let html = escapeHtml(text);
  html = html.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  html = html.replace(/__(.+?)__/g, "<i>$1</i>");
  html = html.replace(/`(.+?)`/g, "<code>$1</code>");
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
  html = html.replace(/\n/g, "<br>");
  return html;
}

function boolToRu(v) {
  return v ? "Да" : "Нет";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function randomId() {
  return Math.random().toString(16).slice(2, 14);
}

function setupEvents() {
  qs("#add-chat").addEventListener("click", addTarget);
  qs("#targets-prev").addEventListener("click", () => {
    state.targetsPage.page -= 1;
    renderTargetsPage();
  });
  qs("#targets-next").addEventListener("click", () => {
    state.targetsPage.page += 1;
    renderTargetsPage();
  });

  qs("#account-select").addEventListener("change", (event) => onAccountSwitch(event.target.value));
  qs("#account-add").addEventListener("click", addAccount);
  qs("#account-remove").addEventListener("click", removeActiveAccount);

  qs("#btn-save").addEventListener("click", async () => {
    try {
      await saveSettings();
      await refreshState();
      alert("Настройки сохранены.");
    } catch (error) {
      alert(error.message);
    }
  });
  qs("#btn-start").addEventListener("click", async () => {
    try {
      await startBroadcast();
    } catch (error) {
      alert(error.message);
    }
  });
  qs("#btn-stop").addEventListener("click", async () => {
    try {
      await stopBroadcast();
    } catch (error) {
      alert(error.message);
    }
  });

  qs("#refresh-logs").addEventListener("click", () => refreshLogs(0));
  qs("#logs-prev").addEventListener("click", () => refreshLogs(state.logsPage.offset - state.logsPage.limit));
  qs("#logs-next").addEventListener("click", () => refreshLogs(state.logsPage.offset + state.logsPage.limit));
  qs("#log-filter-level").addEventListener("change", () => refreshLogs(0));

  qs("#load-account-chats").addEventListener("click", () => loadAccountChats(0));
  qs("#account-chats-prev").addEventListener("click", () => loadAccountChats(state.accountChatsPage.offset - state.accountChatsPage.limit));
  qs("#account-chats-next").addEventListener("click", () => loadAccountChats(state.accountChatsPage.offset + state.accountChatsPage.limit));

  qs("#auth-send-code").addEventListener("click", () => authSendCode().catch((e) => alert(e.message)));
  qs("#auth-verify-code").addEventListener("click", () => authVerifyCode().catch((e) => alert(e.message)));
  qs("#auth-verify-password").addEventListener("click", () => authVerifyPassword().catch((e) => alert(e.message)));
  qs("#auth-check-status").addEventListener("click", () => authCheckStatus().catch((e) => alert(e.message)));
  qs("#status-check").addEventListener("click", () => checkStatusPage().catch((e) => alert(e.message)));
}

async function init() {
  bindTabs();
  setupEvents();
  setupFormattingTools();
  await refreshState();
  await refreshLogs(0);
  startUiHeartbeat();
  renderAccountChats();
  setInterval(async () => {
    try {
      const data = await api("/api/state");
      setRuntime(data.runtime);
    } catch (_error) {}
  }, 2000);
}

init();

function startUiHeartbeat() {
  if (uiHeartbeatTimer) clearInterval(uiHeartbeatTimer);
  sendUiHeartbeat().catch(() => {});
  uiHeartbeatTimer = setInterval(() => {
    sendUiHeartbeat().catch(() => {});
  }, 2000);
}

async function sendUiHeartbeat() {
  await fetch("/api/runtime/heartbeat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
    keepalive: true,
  });
}
