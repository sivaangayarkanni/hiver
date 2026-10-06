/* Hiver AppleSupport inbox — dependency-free SPA (hash routing). */
(() => {
  "use strict";

  const app = document.getElementById("app");
  const toastEl = document.getElementById("toast");
  const PAGE = 25;
  const VIEWS = {
    active: { label: "Active", params: { status: "active" } },
    mine: { label: "Assigned to me", params: { status: "active", assignee: "me" } },
    unassigned: { label: "Unassigned", params: { status: "active", assignee: "unassigned" } },
    escalated: { label: "Escalated", params: { status: "escalated" } },
    open: { label: "Open (auto-handle)", params: { status: "open" } },
    replied: { label: "Replied", params: { status: "replied" } },
    closed: { label: "Closed", params: { status: "closed" } },
    all: { label: "All tickets", params: {} },
  };
  const SAMPLES = [
    ["Apple ID locked", "I cannot sign in to my Apple ID — keeps saying locked for security reasons."],
    ["iCloud full", "iCloud storage full, can't backup photos anymore. What do I delete?"],
    ["Stolen iPhone", "My iPhone was stolen last night. I need to lock it and wipe it."],
    ["Unauthorized charge", "There's an unauthorized charge on my App Store receipt. I want a refund."],
    ["Battery drain", "Battery draining super fast after the iOS update — any tips?"],
  ];

  const state = {
    user: null, meta: null, users: [], stats: null,
    view: "active", intent: "", q: "", offset: 0,
    list: null, listLoading: false, selectedId: null, ticket: null, ticketLoading: false,
    sideOpen: false,
  };

  // ------------------------------------------------------------ utilities
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pretty = (s) => String(s || "").replaceAll("_", " ");
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function timeAgo(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    if (s < 86400 * 7) return Math.floor(s / 86400) + "d ago";
    return d.toLocaleDateString();
  }
  const fullTime = (iso) => (iso ? new Date(iso).toLocaleString() : "");

  let toastTimer;
  function toast(msg, isErr = false) {
    toastEl.textContent = msg;
    toastEl.className = "show" + (isErr ? " err" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toastEl.className = ""), isErr ? 5000 : 2600);
  }

  class ApiError extends Error {
    constructor(msg, status) { super(msg); this.status = status; }
  }

  async function api(method, path, body) {
    const opts = { method, credentials: "same-origin", headers: { Accept: "application/json" } };
    if (method !== "GET") {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body || {});
    }
    let res;
    try {
      res = await fetch(path, opts);
    } catch (e) {
      throw new ApiError("Network error — check your connection and retry.", 0);
    }
    let data = null;
    try { data = await res.json(); } catch (_) { /* non-JSON */ }
    if (!res.ok) {
      let msg = (data && data.detail) || res.statusText || "Request failed";
      if (Array.isArray(msg)) {
        msg = msg.map((d) => {
          const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : "";
          const m = String(d.msg || "").replace(/^Value error, /, "");
          return field && field !== "body" ? `${pretty(field)}: ${m}` : m;
        }).join(" · ");
      }
      if (res.status === 401 && !path.startsWith("/api/auth/")) {
        state.user = null;
        location.hash = "#/login";
      }
      throw new ApiError(msg, res.status);
    }
    return data;
  }

  function setBusy(btn, busy, label) {
    if (!btn) return;
    if (busy) {
      btn.dataset.label = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner sm"></span> ${esc(label || "Working…")}`;
    } else {
      btn.disabled = false;
      if (btn.dataset.label) btn.innerHTML = btn.dataset.label;
    }
  }

  const MARK = `<div class="mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M12 3c1.2 2.4.6 4.4-.6 5.6C9.8 6.8 8 6.2 6.6 6.8 8.2 4.4 10.2 3.2 12 3z" fill="#10210c"/><path d="M7 10.2c2.2-1.4 4.2-.8 5-0.2.8-.6 2.8-1.2 5 .2 1.6 1 2.6 2.8 2.6 4.8 0 3.6-3.1 6.2-7.6 6.2S4.4 18.6 4.4 15c0-2 .9-3.8 2.6-4.8z" fill="#10210c"/></svg></div>`;
  const BRAND = `<a class="brand" href="#/inbox/active">${MARK}<div><h1>AppleSupport inbox</h1><div class="sub">Hiver · classify → draft → escalate</div></div></a>`;

  // ------------------------------------------------------------ routing
  function parseHash() {
    const parts = (location.hash || "#/").replace(/^#\/?/, "").split("/").filter(Boolean);
    return parts;
  }

  async function route() {
    const [page, a, b] = parseHash();
    if (page === "playground") return renderPlayground();
    if (page === "login" || page === "signup") {
      if (state.user) { location.hash = "#/inbox/active"; return; }
      return renderAuth(page);
    }
    if (!state.user) { location.hash = "#/login"; return; }
    if (page === "new") return renderCompose();
    if (page === "inbox") {
      const view = VIEWS[a] ? a : "active";
      const id = b ? parseInt(b, 10) : null;
      return renderInbox(view, Number.isFinite(id) ? id : null);
    }
    location.hash = "#/inbox/active";
  }

  // ------------------------------------------------------------ auth pages
  function renderAuth(mode) {
    const isLogin = mode === "login";
    app.innerHTML = `
      <div class="auth-wrap"><div class="auth-card">
        ${BRAND.replace('href="#/inbox/active"', 'href="#/login"')}
        <div class="card">
          <h2>${isLogin ? "Sign in" : "Create your account"}</h2>
          <p class="lead">${isLogin ? "Welcome back. Your team's shared AppleSupport inbox is waiting." : "Join the shared inbox — every agent sees the same queue."}</p>
          <form id="authForm" novalidate>
            ${isLogin ? "" : `<label class="field"><span>Name</span><input type="text" name="name" autocomplete="name" required maxlength="80" /></label>`}
            <label class="field"><span>Email</span><input type="email" name="email" autocomplete="email" required /></label>
            <label class="field"><span>Password</span><input type="password" name="password" autocomplete="${isLogin ? "current-password" : "new-password"}" required minlength="${isLogin ? 1 : 8}" /></label>
            ${isLogin ? "" : `<div class="hint" style="margin:-6px 0 12px">At least 8 characters.</div>`}
            <p class="err-text" id="authErr"></p>
            <button class="btn primary" style="width:100%;justify-content:center" type="submit">${isLogin ? "Sign in" : "Create account"}</button>
          </form>
          ${isLogin ? `<div class="demo-box">Demo login: <b>demo@hiver.dev</b> / <b>hiver-demo-2026</b> <button class="btn sm" type="button" id="fillDemo" style="margin-left:6px">Use demo</button></div>` : ""}
        </div>
        <div class="auth-switch">${isLogin ? `New here? <a href="#/signup">Create an account</a>` : `Already have an account? <a href="#/login">Sign in</a>`}
          · <a href="#/playground">Try the agent without signing in</a></div>
      </div></div>`;
    const form = $("#authForm");
    const err = $("#authErr");
    const demo = $("#fillDemo");
    if (demo) demo.onclick = () => { form.email.value = "demo@hiver.dev"; form.password.value = "hiver-demo-2026"; form.requestSubmit(); };
    (form.name && !isLogin ? form.name : form.email).focus();
    form.onsubmit = async (e) => {
      e.preventDefault();
      err.textContent = "";
      const body = { email: form.email.value.trim(), password: form.password.value };
      if (!isLogin) body.name = form.name.value.trim();
      if (!body.email || !body.password || (!isLogin && !body.name)) { err.textContent = "Please fill in all fields."; return; }
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(body.email)) { err.textContent = "Enter a valid email address."; return; }
      if (!isLogin && body.password.length < 8) { err.textContent = "Password must be at least 8 characters."; return; }
      const btn = form.querySelector("button[type=submit]");
      setBusy(btn, true, isLogin ? "Signing in…" : "Creating account…");
      try {
        const data = await api("POST", `/api/auth/${isLogin ? "login" : "signup"}`, body);
        state.user = data.user;
        await loadShared();
        toast(isLogin ? `Welcome back, ${data.user.name}` : `Welcome, ${data.user.name}!`);
        location.hash = "#/inbox/active";
      } catch (ex) {
        err.textContent = ex.message;
        setBusy(btn, false);
      }
    };
  }

  async function loadShared() {
    const [meta, users] = await Promise.all([api("GET", "/api/meta"), api("GET", "/api/users")]);
    state.meta = meta;
    state.users = users.items;
  }

  // ------------------------------------------------------------ shell
  function shell(active) {
    if (!$(".shell")) {
      app.innerHTML = `
        <div class="shell">
          <aside class="side" id="side">
            ${BRAND}
            <a class="btn primary" href="#/new" style="justify-content:center">+ New ticket</a>
            <nav class="nav" id="nav"></nav>
            <div class="me">
              <div class="name">${esc(state.user.name)}</div>
              <div class="email">${esc(state.user.email)}</div>
              <button class="btn sm" id="logoutBtn" type="button">Sign out</button>
            </div>
          </aside>
          <div class="main">
            <div class="topbar">
              <button class="btn sm menu-btn" id="menuBtn" type="button" aria-label="Menu">☰</button>
              <input class="search" id="search" type="search" placeholder="Search messages, @handles or #id…" aria-label="Search tickets" />
              <div class="spacer"></div>
              <span class="badge-mode hint" id="modeHint"></span>
            </div>
            <div class="content" id="content"></div>
          </div>
        </div>`;
      $("#logoutBtn").onclick = async () => {
        try { await api("POST", "/api/auth/logout"); } catch (_) { /* ignore */ }
        state.user = null; state.list = null; state.ticket = null;
        location.hash = "#/login";
      };
      $("#menuBtn").onclick = () => $("#side").classList.toggle("open");
      const search = $("#search");
      let t;
      search.addEventListener("input", () => {
        clearTimeout(t);
        t = setTimeout(() => {
          state.q = search.value.trim();
          state.offset = 0;
          if (!location.hash.startsWith("#/inbox")) location.hash = "#/inbox/all";
          else loadList();
        }, 300);
      });
    }
    $("#side").classList.remove("open");
    $("#search").value = state.q;
    $("#modeHint").textContent = state.meta && state.meta.live_llm_available ? "Live LLM available" : "Dry-run drafts (no LLM key)";
    renderNav(active);
    return $("#content");
  }

  function renderNav(active) {
    const s = state.stats;
    const counts = s ? {
      active: s.active, mine: s.mine, escalated: s.by_status.escalated, open: s.by_status.open,
      replied: s.by_status.replied, closed: s.by_status.closed, all: s.total,
    } : {};
    const link = (key) => `<a href="#/inbox/${key}" class="${active === key ? "active" : ""}"><span>${esc(VIEWS[key].label)}</span><span class="count">${counts[key] ?? ""}</span></a>`;
    $("#nav").innerHTML =
      `<div class="section">Inbox</div>${["active", "mine", "unassigned", "escalated", "open"].map(link).join("")}` +
      `<div class="section">Done</div>${["replied", "closed", "all"].map(link).join("")}` +
      `<div class="section">Tools</div><a href="#/playground" class="${active === "playground" ? "active" : ""}"><span>Agent playground</span></a>`;
  }

  async function refreshStats() {
    try {
      state.stats = await api("GET", "/api/stats");
      if ($("#nav")) renderNav(state.view);
      const el = $("#stats");
      if (el) el.innerHTML = statsHtml();
    } catch (_) { /* non-fatal */ }
  }

  function statsHtml() {
    const s = state.stats;
    if (!s) return [1, 2, 3, 4].map(() => `<div class="stat"><div class="sk" style="width:40%;height:22px"></div><div class="sk" style="width:70%"></div></div>`).join("");
    return `
      <div class="stat"><div class="v">${s.active}</div><div class="l">Active</div></div>
      <div class="stat"><div class="v">${s.by_status.escalated}</div><div class="l">Escalated</div></div>
      <div class="stat"><div class="v">${s.mine}</div><div class="l">Assigned to me</div></div>
      <div class="stat"><div class="v">${Math.round(s.auto_handle_rate * 100)}%</div><div class="l">Agent auto-handle rate</div></div>`;
  }

  // ------------------------------------------------------------ inbox
  async function renderInbox(view, id) {
    const viewChanged = state.view !== view || !$("#list");
    if (state.view !== view) state.offset = 0;
    state.view = view;
    const content = shell(view);
    if (viewChanged) {
      const intents = (state.meta?.intents || []).map((i) => `<option value="${esc(i.name)}" ${state.intent === i.name ? "selected" : ""}>${esc(pretty(i.name))}</option>`).join("");
      content.innerHTML = `
        <div class="stats" id="stats">${statsHtml()}</div>
        <div class="split" id="split">
          <section class="list" aria-label="Tickets">
            <div class="list-head">
              <span id="listTitle">${esc(VIEWS[view].label)}</span>
              <select id="intentFilter" aria-label="Filter by intent"><option value="">All intents</option>${intents}</select>
            </div>
            <div id="list"></div>
            <div class="pager hidden" id="pager"></div>
          </section>
          <section class="detail" id="detail" aria-label="Ticket detail"></section>
        </div>`;
      $("#intentFilter").onchange = (e) => { state.intent = e.target.value; state.offset = 0; loadList(); };
      loadList();
      refreshStats();
    }
    state.selectedId = id;
    $("#split").classList.toggle("has-detail", !!id);
    markActiveRow();
    if (id) loadTicket(id);
    else $("#detail").innerHTML = `<div class="empty"><div class="big">Select a ticket</div>Pick a conversation from the list to review the agent's triage and reply.</div>`;
  }

  async function loadList() {
    const listEl = $("#list");
    if (!listEl) return;
    const params = new URLSearchParams({ ...VIEWS[state.view].params, limit: PAGE, offset: state.offset });
    if (state.intent) params.set("intent", state.intent);
    if (state.q) params.set("q", state.q);
    listEl.innerHTML = Array.from({ length: 5 }, () => `<div class="row"><div class="sk" style="width:45%"></div><div class="sk"></div><div class="sk" style="width:60%"></div></div>`).join("");
    const reqId = (loadList.seq = (loadList.seq || 0) + 1);
    try {
      const data = await api("GET", "/api/tickets?" + params.toString());
      if (reqId !== loadList.seq) return;
      state.list = data;
      renderList();
    } catch (e) {
      if (reqId !== loadList.seq) return;
      listEl.innerHTML = `<div class="empty"><div class="big">Couldn't load tickets</div>${esc(e.message)}<div style="margin-top:12px"><button class="btn sm" id="retryList">Retry</button></div></div>`;
      $("#retryList").onclick = loadList;
    }
  }

  function renderList() {
    const { items, total, offset } = state.list;
    const listEl = $("#list");
    $("#listTitle").textContent = `${VIEWS[state.view].label} · ${total}`;
    if (!items.length) {
      const filtered = state.q || state.intent;
      listEl.innerHTML = `<div class="empty"><div class="big">${filtered ? "No matches" : "Inbox zero 🎉"}</div>${filtered ? "Try clearing the search or intent filter." : "Nothing here right now."}
        <div style="margin-top:12px"><a class="btn sm" href="#/new">+ New ticket</a></div></div>`;
    } else {
      listEl.innerHTML = items.map((t) => `
        <a class="row" data-id="${t.id}" href="#/inbox/${state.view}/${t.id}">
          <div class="top"><span class="handle">${esc(t.customer_handle)} <span class="muted">#${t.id}</span></span><span class="time" title="${esc(fullTime(t.updated_at))}">${esc(timeAgo(t.updated_at))}</span></div>
          <div class="text">${esc(t.customer_text)}</div>
          <div class="tags">
            <span class="tag ${esc(t.status)}">${esc(t.status)}</span>
            ${t.priority === "urgent" || t.priority === "high" ? `<span class="tag ${esc(t.priority)}">${esc(t.priority)}</span>` : ""}
            ${t.intent ? `<span class="tag intent">${esc(pretty(t.intent))}</span>` : ""}
            ${t.assignee_name ? `<span class="tag intent">→ ${esc(t.assignee_name)}</span>` : ""}
          </div>
        </a>`).join("");
    }
    const pager = $("#pager");
    if (total > PAGE) {
      pager.classList.remove("hidden");
      pager.innerHTML = `<button class="btn sm" id="prevPg" ${offset === 0 ? "disabled" : ""}>← Prev</button>
        <span>${offset + 1}–${Math.min(offset + PAGE, total)} of ${total}</span>
        <button class="btn sm" id="nextPg" ${offset + PAGE >= total ? "disabled" : ""}>Next →</button>`;
      $("#prevPg").onclick = () => { state.offset = Math.max(0, offset - PAGE); loadList(); };
      $("#nextPg").onclick = () => { state.offset = offset + PAGE; loadList(); };
    } else pager.classList.add("hidden");
    markActiveRow();
  }

  function markActiveRow() {
    $$(".row[data-id]").forEach((r) => r.classList.toggle("active", Number(r.dataset.id) === state.selectedId));
  }

  async function loadTicket(id) {
    const el = $("#detail");
    if (!state.ticket || state.ticket.id !== id) {
      el.innerHTML = `<div class="sk" style="width:40%;height:20px"></div><div class="sk" style="width:25%"></div><div class="sk" style="height:80px;margin-top:18px"></div><div class="sk" style="height:60px"></div>`;
    }
    try {
      const data = await api("GET", `/api/tickets/${id}`);
      if (state.selectedId !== id) return;
      state.ticket = data.ticket;
      renderDetail();
    } catch (e) {
      el.innerHTML = `<a class="back-link" href="#/inbox/${state.view}">← Back to list</a><div class="empty"><div class="big">${e.status === 404 ? "Ticket not found" : "Couldn't load ticket"}</div>${esc(e.message)}</div>`;
    }
  }

  function applyTicket(t) {
    state.ticket = t;
    renderDetail();
    // update the row in place, then refresh list/stats in background
    loadList();
    refreshStats();
  }

  function renderDetail() {
    const t = state.ticket;
    const el = $("#detail");
    const conf = Math.round((t.confidence || 0) * 100);
    const users = state.users.map((u) => `<option value="${u.id}" ${t.assignee_id === u.id ? "selected" : ""}>${esc(u.name)}${u.id === state.user.id ? " (me)" : ""}</option>`).join("");
    const opt = (vals, cur) => vals.map((v) => `<option value="${v}" ${v === cur ? "selected" : ""}>${esc(pretty(v))}</option>`).join("");
    const done = t.status === "replied" || t.status === "closed";
    const sources = (t.draft_sources || []).join(", ");
    el.innerHTML = `
      <a class="back-link" href="#/inbox/${state.view}">← Back to list</a>
      <div class="detail-head">
        <div>
          <h2>${esc(t.customer_handle)} <span class="muted">#${t.id}</span></h2>
          <div class="meta">${esc(pretty(t.channel))} · received <span title="${esc(fullTime(t.created_at))}">${esc(timeAgo(t.created_at))}</span>${t.created_by_name ? ` · logged by ${esc(t.created_by_name)}` : ""}</div>
        </div>
        <div class="tags"><span class="tag ${esc(t.status)}">${esc(t.status)}</span><span class="tag ${esc(t.priority)}">${esc(t.priority)}</span></div>
      </div>
      <div class="controls">
        <label><span>Status</span><select id="fStatus">${opt(state.meta.statuses, t.status)}</select></label>
        <label><span>Priority</span><select id="fPriority">${opt(state.meta.priorities, t.priority)}</select></label>
        <label><span>Assignee</span><select id="fAssignee"><option value="">Unassigned</option>${users}</select></label>
      </div>
      <div class="k">Customer message</div>
      <div class="bubble">${esc(t.customer_text)}</div>
      <div class="panels">
        <div class="panel">
          <div class="k">Agent intent</div>
          <p class="intent-name">${esc(pretty(t.intent || "—"))}</p>
          <div class="conf-bar"><span style="width:${conf}%"></span></div>
          <div class="conf-num">${(t.confidence || 0).toFixed(2)} confidence · ${esc(t.classifier || "")}</div>
        </div>
        <div class="panel">
          <div class="k">Agent decision</div>
          <span class="tag ${esc(t.escalation_action)}">${esc(pretty(t.escalation_action || "—"))}</span>
          <p class="reason">${esc(t.escalation_reason || "")}</p>
          ${(t.rules_fired || []).length ? `<div class="rules">Rules: ${esc(t.rules_fired.join(", "))}</div>` : ""}
        </div>
      </div>
      ${t.reply_text ? `<div class="k">Reply sent ${t.replied_at ? `· <span title="${esc(fullTime(t.replied_at))}">${esc(timeAgo(t.replied_at))}</span>` : ""}</div><div class="sent">${esc(t.reply_text)}</div>` : ""}
      <div class="composer" style="margin-top:14px">
        <div class="k">${done ? "Follow-up reply" : "Reply (pre-filled with the agent's grounded draft)"}</div>
        <textarea id="replyText" maxlength="4000">${esc(done ? "" : (t.draft || "").replace(/^\[dry-run\] /, ""))}</textarea>
        <div class="actions">
          <span class="hint left">${t.dry_run ? "Dry-run draft" : "Live LLM draft"}${sources ? ` · grounded in ${esc(sources)}` : ""}</span>
          <button class="btn sm" id="rerunBtn" type="button" title="Re-run classify → draft → escalate">↻ Re-run agent</button>
          <button class="btn sm" id="saveDraftBtn" type="button">Save draft</button>
          <button class="btn sm" id="replyCloseBtn" type="button">Send &amp; close</button>
          <button class="btn primary sm" id="replyBtn" type="button">Send reply</button>
        </div>
        <p class="err-text" id="replyErr"></p>
      </div>
      <div class="timeline">
        <div class="k">Activity</div>
        ${(t.events || []).map((e) => `
          <div class="ev ${esc(e.kind)}"><span class="dot"></span><div>
            <span class="who">${esc(e.user_name || (e.kind === "agent" ? "AI agent" : "System"))}</span><span class="when" title="${esc(fullTime(e.created_at))}">${esc(timeAgo(e.created_at))}</span>
            <span class="muted"> · ${esc(e.kind)}</span>
            ${e.body ? `<div class="body">${esc(e.body)}</div>` : ""}
          </div></div>`).join("")}
        <form class="note-form" id="noteForm">
          <input type="text" id="noteText" maxlength="2000" placeholder="Add an internal note for your team…" aria-label="Internal note" />
          <button class="btn sm" type="submit">Add note</button>
        </form>
      </div>`;

    const patch = async (changes, msg) => {
      try {
        const data = await api("PATCH", `/api/tickets/${t.id}`, changes);
        applyTicket(data.ticket);
        toast(msg);
      } catch (e) { toast(e.message, true); renderDetail(); }
    };
    $("#fStatus").onchange = (e) => patch({ status: e.target.value }, `Status → ${pretty(e.target.value)}`);
    $("#fPriority").onchange = (e) => patch({ priority: e.target.value }, `Priority → ${e.target.value}`);
    $("#fAssignee").onchange = (e) => patch({ assignee_id: e.target.value ? Number(e.target.value) : null }, e.target.value ? "Assigned" : "Unassigned");

    const replyErr = $("#replyErr");
    const send = async (close, btn) => {
      const text = $("#replyText").value.trim();
      replyErr.textContent = "";
      if (!text) { replyErr.textContent = "Write a reply first."; return; }
      setBusy(btn, true, "Sending…");
      try {
        const data = await api("POST", `/api/tickets/${t.id}/reply`, { text, close });
        applyTicket(data.ticket);
        toast(close ? "Reply sent and ticket closed" : "Reply sent");
      } catch (e) { replyErr.textContent = e.message; setBusy(btn, false); }
    };
    $("#replyBtn").onclick = (e) => send(false, e.currentTarget);
    $("#replyCloseBtn").onclick = (e) => send(true, e.currentTarget);
    $("#saveDraftBtn").onclick = async (e) => {
      const btn = e.currentTarget;
      setBusy(btn, true, "Saving…");
      try {
        const data = await api("PATCH", `/api/tickets/${t.id}`, { draft: $("#replyText").value });
        applyTicket(data.ticket);
        toast("Draft saved");
      } catch (ex) { replyErr.textContent = ex.message; setBusy(btn, false); }
    };
    $("#rerunBtn").onclick = async (e) => {
      const btn = e.currentTarget;
      setBusy(btn, true, "Running…");
      try {
        const data = await api("POST", `/api/tickets/${t.id}/reanalyze`, { dry_run: !state.meta.live_llm_available });
        applyTicket(data.ticket);
        toast(data.llm_error ? "LLM unavailable — used dry-run draft" : "Agent re-run complete", !!data.llm_error);
      } catch (ex) { toast(ex.message, true); setBusy(btn, false); }
    };
    $("#noteForm").onsubmit = async (e) => {
      e.preventDefault();
      const input = $("#noteText");
      const body = input.value.trim();
      if (!body) { input.focus(); return; }
      const btn = e.currentTarget.querySelector("button");
      setBusy(btn, true, "Adding…");
      try {
        const data = await api("POST", `/api/tickets/${t.id}/notes`, { body });
        applyTicket(data.ticket);
        toast("Note added");
      } catch (ex) { toast(ex.message, true); setBusy(btn, false); }
    };
  }

  // ------------------------------------------------------------ compose
  function renderCompose() {
    state.view = "new";
    const content = shell("new");
    content.innerHTML = `
      <div class="narrow">
        <h2 class="page-title">New ticket</h2>
        <p class="page-sub">Log an incoming customer message. The agent classifies it, drafts a grounded reply and decides whether to escalate — then it lands in the shared inbox.</p>
        <form class="card" id="composeForm" novalidate>
          <div class="form-row">
            <label class="field"><span>Customer handle</span><input type="text" name="handle" placeholder="@customer" maxlength="80" required /></label>
            <label class="field"><span>Channel</span><select name="channel"><option value="twitter">Twitter / X</option><option value="email">Email</option><option value="chat">Chat</option></select></label>
          </div>
          <label class="field"><span>Customer message</span><textarea name="text" maxlength="4000" placeholder="e.g. Battery draining after the iOS update…" required></textarea></label>
          <div class="chips">${SAMPLES.map(([l, txt]) => `<button type="button" class="chip" data-text="${esc(txt)}">${esc(l)}</button>`).join("")}</div>
          ${state.meta.live_llm_available ? `<label class="toggle"><input type="checkbox" name="live" /> Draft with the live LLM</label>` : `<div class="hint">Drafts use the deterministic dry-run writer (no LLM key configured).</div>`}
          <p class="err-text" id="composeErr"></p>
          <div style="display:flex;justify-content:flex-end;gap:8px">
            <a class="btn" href="#/inbox/active">Cancel</a>
            <button class="btn primary" type="submit">Create &amp; triage</button>
          </div>
        </form>
      </div>`;
    const form = $("#composeForm");
    form.handle.focus();
    $$(".chip", form).forEach((c) => (c.onclick = () => { form.text.value = c.dataset.text; form.text.focus(); }));
    form.onsubmit = async (e) => {
      e.preventDefault();
      const err = $("#composeErr");
      err.textContent = "";
      const body = {
        customer_handle: form.handle.value.trim(),
        customer_text: form.text.value.trim(),
        channel: form.channel.value,
        dry_run: !(form.live && form.live.checked),
      };
      if (!body.customer_handle) { err.textContent = "Customer handle is required."; form.handle.focus(); return; }
      if (body.customer_text.length < 3) { err.textContent = "Customer message is too short."; form.text.focus(); return; }
      const btn = form.querySelector("button[type=submit]");
      setBusy(btn, true, "Triaging…");
      try {
        const data = await api("POST", "/api/tickets", body);
        if (data.llm_error) toast("LLM unavailable — used dry-run draft", true);
        else toast(`Ticket #${data.ticket.id} created → ${pretty(data.ticket.escalation_action)}`);
        state.ticket = data.ticket;
        state.q = ""; state.intent = "";
        location.hash = `#/inbox/all/${data.ticket.id}`;
      } catch (ex) { err.textContent = ex.message; setBusy(btn, false); }
    };
  }

  // ------------------------------------------------------------ playground
  function renderPlayground() {
    let content;
    if (state.user) {
      state.view = "playground";
      content = shell("playground");
    } else {
      app.innerHTML = `<div style="max-width:800px;margin:0 auto;padding:36px 20px 60px"><div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:22px">${BRAND.replace('href="#/inbox/active"', 'href="#/login"')}<a class="btn sm" href="#/login">Sign in</a></div><div id="content"></div></div>`;
      content = $("#content");
    }
    content.innerHTML = `
      <div class="narrow">
        <h2 class="page-title">Agent playground</h2>
        <p class="page-sub">Stateless: runs classify → draft → escalate on any message without saving it. Sign in to work the shared inbox.</p>
        <div class="card">
          <label class="field" style="margin:0"><span>Customer message</span>
          <textarea id="pgText" maxlength="4000">Battery draining after iOS update — any tips?</textarea></label>
          <div class="chips">${SAMPLES.map(([l, txt]) => `<button type="button" class="chip" data-text="${esc(txt)}">${esc(l)}</button>`).join("")}</div>
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px">
            <span class="hint">TF-IDF intent model + retrieval-grounded draft · ⌘/Ctrl+Enter to run</span>
            <button class="btn primary" id="pgRun" type="button">Run agent</button>
          </div>
          <p class="err-text" id="pgErr"></p>
        </div>
        <div id="pgOut"></div>
      </div>`;
    const text = $("#pgText");
    $$(".chip", content).forEach((c) => (c.onclick = () => { text.value = c.dataset.text; text.focus(); }));
    const run = async () => {
      const v = text.value.trim();
      const err = $("#pgErr");
      err.textContent = "";
      if (!v) { err.textContent = "Enter a customer message."; return; }
      const btn = $("#pgRun");
      setBusy(btn, true, "Running…");
      try {
        const d = await api("POST", "/api/analyze", { text: v, dry_run: true });
        const pct = Math.round((d.confidence || 0) * 100);
        $("#pgOut").innerHTML = `
          <div class="panels">
            <div class="panel"><div class="k">Intent + confidence</div><p class="intent-name">${esc(pretty(d.intent))}</p>
              <div class="conf-bar"><span style="width:${pct}%"></span></div><div class="conf-num">${d.confidence.toFixed(2)} · ${esc(d.method)}</div></div>
            <div class="panel"><div class="k">Escalation</div><span class="tag ${esc(d.escalation_action)}">${esc(pretty(d.escalation_action))}</span><p class="reason">${esc(d.escalation_reason)}</p></div>
          </div>
          <div class="panel"><div class="k">Drafted reply</div><p class="reason" style="white-space:pre-wrap">${esc(d.draft)}</p>
            ${d.draft_sources.length ? `<div class="rules">Grounded in: ${esc(d.draft_sources.join(", "))}</div>` : ""}</div>`;
      } catch (ex) { err.textContent = ex.message; }
      finally { setBusy(btn, false); }
    };
    $("#pgRun").onclick = run;
    text.addEventListener("keydown", (e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run(); });
  }

  // ------------------------------------------------------------ boot
  async function boot() {
    try {
      const data = await api("GET", "/api/auth/me");
      state.user = data.user;
      if (state.user) await loadShared();
    } catch (e) {
      state.user = null;
      if (e.status && e.status !== 401) toast(e.message, true);
    }
    window.addEventListener("hashchange", route);
    if (!location.hash || location.hash === "#/" || location.hash === "#") location.hash = state.user ? "#/inbox/active" : "#/login";
    else route();
  }
  boot();
})();
