/* ═══════════════════════════════════════════════════════
   Emperor Agent · 对话核心流（任务 B2）
   职责：连 /ws，把内核事件流渲染成宫廷界面。
   B1 的静态示例已移除，本文件是唯一的动态渲染者。
   B3 补交互打磨（滚动锚定/停止/复制/差事灯笼），C 补面板与圣旨弹窗。
   安全约定：所有动态文本一律 textContent 写入，不经 innerHTML——
   工具输出与模型内容是不可信输入，防 XSS 从渲染层做起。
   ═══════════════════════════════════════════════════════ */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const chat = $("chat"), input = $("input"), btnSend = $("btn-send"),
        btnStop = $("btn-stop"), btnBack = $("btn-back"), lamp = $("lamp");
  const veil = $("decree-veil"), decreeText = $("decree-text"), decreeCount = $("decree-count");

  /* ---- C1：圣旨待批弹窗 ----
     hook_ask → 弹窗 + 倒计时（与服务端 ASK_TIMEOUT 同源配置，超时即驳回按钮自动按下；
     即使倒计时与服务器有偏差，服务端超时仍 fail-closed，前端只是尽力同步观感）。 */
  let countdownTimer = null;
  const ASK_TIMEOUT_MS = 120000;   // 与 web/server.py 的 EMPEROR_ASK_TIMEOUT 默认一致

  function openDecree(reason) {
    decreeText.textContent = `皇上，此令需您朱批：${reason}`;
    veil.hidden = false;
    startCountdown();
  }

  function closeDecree() {
    veil.hidden = true;
    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
    decreeCount.hidden = true;
  }

  function startCountdown() {
    const deadline = Date.now() + ASK_TIMEOUT_MS;
    decreeCount.hidden = false;
    const tick = () => {
      const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      decreeCount.textContent = `（${left} 秒内未批，将按驳回处置）`;
      if (left <= 0) { resolveDecree(false, true); }
    };
    tick();
    countdownTimer = setInterval(tick, 1000);
  }

  function resolveDecree(approved, byTimeout = false) {
    if (veil.hidden) return;                    // 无待批事项则忽略
    closeDecree();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "confirm", approved }));
    }
    renderNotice(approved ? "（皇上准奏——）" : byTimeout ? "（超时未批，按驳回处置）" : "（皇上驳回——）",
                 approved ? "" : "warn");
  }

  $("btn-approve").addEventListener("click", () => resolveDecree(true));
  $("btn-deny").addEventListener("click", () => resolveDecree(false));

  let ws = null;
  let activeMemorial = null;   // 正在流式渲染的奏折正文
  let pendingTools = [];       // 已 tool_start 未 tool_end 的卡片（内核顺序执行，按名配对）
  let busy = false;

  /* ---- B3：回看暂停——用户上翻即停跟随，回到底部自动恢复 ---- */
  let followTail = true;
  const NEAR_BOTTOM = 120;     // 距底不足该值视为"在跟最新"
  chat.addEventListener("scroll", () => {
    const near = chat.scrollHeight - chat.scrollTop - chat.clientHeight < NEAR_BOTTOM;
    followTail = near;
    btnBack.hidden = near;
  });
  btnBack.addEventListener("click", () => {
    chat.scrollTop = chat.scrollHeight;
  });

  /* ---- 渲染小件 ---- */
  function scrollBottom() { if (followTail) chat.scrollTop = chat.scrollHeight; }

  function addNode(el) { chat.appendChild(el); scrollBottom(); return el; }

  function renderZhuPi(text) {
    const el = document.createElement("div");
    el.className = "zhu-pi";
    el.textContent = text;
    addNode(el);
  }

  function renderMemorialStart() {
    const art = document.createElement("article");
    art.className = "memorial";
    const body = document.createElement("div");
    body.className = "memorial-body";
    const foot = document.createElement("div");
    foot.className = "memorial-foot";
    const sign = document.createElement("span");
    sign.textContent = "老奴叩禀";
    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "btn-copy";
    copyBtn.textContent = "誊抄";
    foot.append(sign, copyBtn);
    art.append(body, foot);
    activeMemorial = body;
    addNode(art);
  }

  /* ---- B3：誊抄（事件委托，动态卡片无需逐个绑） ---- */
  chat.addEventListener("click", (e) => {
    const btn = e.target.closest(".btn-copy");
    if (!btn) return;
    const text = btn.closest(".memorial").querySelector(".memorial-body").textContent;
    copyText(text).then((ok) => {
      btn.textContent = ok ? "已誊抄 ✓" : "誊抄失败";
      setTimeout(() => { btn.textContent = "誊抄"; }, 1600);
    });
  });

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; }
    catch {
      const ta = document.createElement("textarea");   // 兼容回退
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    }
  }

  /* ---- B3：差事灯笼实时联动 ---- */
  function renderTodos(list) {
    const ul = $("todo-list");
    ul.replaceChildren();
    if (!Array.isArray(list) || list.length === 0) {
      const li = document.createElement("li");
      li.className = "hint";
      li.textContent = "（暂无差事）";
      ul.appendChild(li);
      return;
    }
    const mark = { pending: ["○", "todo-pending"], in_progress: ["◐", "todo-doing"],
                   completed: ["◉", "todo-done"] };
    for (const t of list) {
      const li = document.createElement("li");
      const [icon, cls] = mark[t.status] || mark.pending;
      li.className = cls;
      li.textContent = `${icon} ${t.content}`;
      ul.appendChild(li);
    }
  }

  function renderToken(text) {
    if (!activeMemorial) renderMemorialStart();
    activeMemorial.textContent += text;
    scrollBottom();
  }

  function renderReply(text) {            // 非流式整段回复（Hook 短路/拦截文案）
    renderMemorialStart();
    activeMemorial.textContent = text;
    activeMemorial = null;
  }

  function renderToolStart(name, inputObj) {
    const det = document.createElement("details");
    det.className = "tool-card";
    const sum = document.createElement("summary");
    const arrow = document.createElement("span");
    arrow.className = "arrow"; arrow.textContent = "▸";
    const title = document.createElement("span");
    title.textContent = ` 内务府 · ${name} `;
    const state = document.createElement("span");
    state.className = "state"; state.textContent = "…";
    sum.append(arrow, title, state);
    const pre = document.createElement("pre");
    const args = inputObj ? JSON.stringify(inputObj, null, 2) : "";
    pre.textContent = args + (args ? "\n" : "") + "（执行中…）";
    det.append(sum, pre);
    addNode(det);
    pendingTools.push({ name, pre, state });
  }

  function renderToolEnd(name, output, blocked) {
    for (let i = pendingTools.length - 1; i >= 0; i--) {   // 顺序配对最近同名卡
      if (pendingTools[i].name === name) {
        const t = pendingTools.splice(i, 1)[0];
        t.state.textContent = blocked ? "✗ 已拦截" : "✓";
        t.state.className = "state " + (blocked ? "blocked" : "ok");
        t.pre.textContent = t.pre.textContent.split("\n（执行中…）")[0] + "\n" + (output ?? "");
        return;
      }
    }
  }

  function renderNotice(text, cls) {
    const el = document.createElement("div");
    el.className = "notice" + (cls ? " " + cls : "");
    el.textContent = text;
    addNode(el);
  }

  function setLamp(mode, text) {
    lamp.className = "lamp" + (mode ? " " + mode : "");
    lamp.textContent = text;
  }

  /* ---- 事件分发 ---- */
  function onEvent(ev) {
    switch (ev.type) {
      case "user_echo":       renderZhuPi(ev.text); break;
      case "reply_start":     renderMemorialStart(); break;
      case "token":           renderToken(ev.text); break;
      case "reply_end":       activeMemorial = null; break;
      case "reply":           renderReply(ev.text); break;
      case "tool_start":      renderToolStart(ev.name, ev.input); break;
      case "tool_end":        renderToolEnd(ev.name, ev.output, ev.blocked); break;
      case "subagents_start":
        renderNotice(`并发派遣 ${ev.count} 位小太监出巡…`);
        refreshSubagentLogs();
        break;
      case "subagent_summary": {        // C3：回禀升级为带内容的折叠卡
        const det = document.createElement("details");
        det.className = "tool-card subagent-card";
        const sum = document.createElement("summary");
        const arrow = document.createElement("span");
        arrow.className = "arrow"; arrow.textContent = "▸";
        const title = document.createElement("span");
        const breaker = (ev.summary || "").includes("提前收兵");
        title.textContent = breaker ? " 小太监回禀（已熔断收兵）" : ` 小太监回禀（${ev.length} 字）`;
        const state = document.createElement("span");
        state.className = "state " + (breaker ? "blocked" : "ok");
        state.textContent = breaker ? "⚡" : "✓";
        sum.append(arrow, title, state);
        const pre = document.createElement("pre");
        pre.textContent = ev.summary || "";
        det.append(sum, pre);
        addNode(det);
        refreshSubagentLogs();
        break;
      }
      case "stop_gate":       renderNotice(`[质量门禁] ${ev.reason}`, "warn"); break;
      case "retry":
      case "error":           renderNotice(String(ev.message || "").trim(), "warn"); break;
      case "hook_ask":        openDecree(ev.reason); break;   // C1：圣旨弹窗
      case "hook_decision":
        // 弹窗自己点的准奏/驳回已给过提示；服务器回传的 deny 意味着超时或其它否决路径
        if (ev.action === "deny" && veil.hidden) {
          renderNotice(`[门禁·驳回] ${ev.reason}`, "warn");
        } else if (!veil.hidden && ev.action !== "deny") {
          closeDecree();
        }
        break;
      case "hook_decision":   renderNotice(`[门禁] ${ev.action}：${ev.reason}`); break;
      case "session":
        currentSessionId = ev.id;
        if (ev.resumed) renderNotice(`（已入偏殿 ${ev.id}，共 ${ev.messages} 条旧话，可续谈）`);
        if (ev.fresh) refreshSessions();
        refreshSessions();
        break;
      case "persona":
        currentPersona = ev.name;
        renderNotice(`（已换装：${ev.name}，下轮生效——）`);
        refreshPersonas();
        break;
      case "todos":           renderTodos(ev.todos); break;   // B3：差事灯笼
      case "done":
      case "idle":            setLamp("on", "● 当值"); busy = false; refreshSend(); btnStop.hidden = true; break;
      case "pong":            break;
    }
  }

  function refreshSend() {
    const ready = ws && ws.readyState === WebSocket.OPEN;
    btnSend.disabled = busy || !ready;
    input.placeholder = busy ? "总管行走中……"
      : ready ? "传旨……（Enter 传旨，Shift+Enter 换行）" : "未接驾……";
  }

  function send() {
    const text = input.value.trim();
    if (!text || busy || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "send", text }));
    input.value = "";
    busy = true;
    setLamp("busy", "● 行走中");
    btnStop.hidden = false;
    refreshSend();
  }

  /* ---- B3：请旨叫停（在途流断流返回部分内容，工具批后收束） ---- */
  btnStop.addEventListener("click", () => {
    if (!busy || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "stop" }));
    renderNotice("（已请旨叫停，待总管收束……）");
  });

  /* ---- C2：面板数据（REST 拉取） ---- */
  let currentSessionId = null;
  let currentPersona = null;

  async function fetchJSON(url) {
    try {
      const r = await fetch(url);
      if (!r.ok) return null;
      return await r.json();
    } catch { return null; }
  }

  function fmtHallName(s) {
    // "20260824-011257" → "0824 · 01:12"（日期 · 时分）
    const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(s.id || "");
    const label = m ? `${m[2]}${m[3]} · ${m[4]}:${m[5]}` : (s.id || "?");
    const preview = (s.preview || "").slice(0, 12);
    return `${label}${preview ? " · " + preview : ""}`;
  }

  async function refreshSessions() {
    const data = await fetchJSON("/api/sessions");
    if (!data || !Array.isArray(data.sessions)) return;
    const ul = $("session-list");
    ul.replaceChildren();
    if (data.sessions.length === 0) {
      const li = document.createElement("li");
      li.className = "hint";
      li.textContent = "（尚无偏殿）";
      ul.appendChild(li);
      return;
    }
    for (const s of data.sessions.slice(0, 15)) {
      const li = document.createElement("li");
      if (s.id === currentSessionId) li.className = "active";
      const name = document.createElement("span");
      name.className = "hall-name";
      name.textContent = fmtHallName(s);
      const hint = document.createElement("span");
      hint.className = "hint";
      hint.textContent = s.id === currentSessionId ? "当前" : `${s.messages}条`;
      li.append(name, hint);
      li.addEventListener("click", () => {
        if (s.id !== currentSessionId && !busy) resumeSession(s.id);
      });
      ul.appendChild(li);
    }
  }

  function resumeSession(id) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "resume", id }));
    renderNotice(`（前往偏殿 ${id}……）`);
    refreshSessions();
  }

  async function refreshPersonas() {
    const data = await fetchJSON("/api/personas");
    if (!data || !Array.isArray(data.personas)) return;
    const box = $("persona-list");
    box.replaceChildren();
    for (const name of data.personas) {
      const span = document.createElement("span");
      span.className = "persona" + (name === currentPersona ? " active" : "");
      span.textContent = name === "taijian" ? "太监总管"
                       : name === "guanjia" ? "英式管家" : name;
      span.addEventListener("click", () => {
        if (ws && ws.readyState === WebSocket.OPEN && !busy) {
          ws.send(JSON.stringify({ type: "persona", name }));
        }
      });
      box.appendChild(span);
    }
  }

  async function refreshTeam() {
    const data = await fetchJSON("/api/team");
    if (!data || typeof data.team !== "string") return;
    const ul = $("team-list");
    ul.replaceChildren();
    const lines = data.team.split("\n").filter(l => l.trim().startsWith("-"));
    if (lines.length === 0) {
      const li = document.createElement("li");
      li.textContent = "暂无队友";
      ul.appendChild(li);
      return;
    }
    for (const line of lines) {
      const li = document.createElement("li");
      const m = /-\s*(.+?)（(.+?)）：(.+)/.exec(line);
      const name = document.createElement("span");
      const hint = document.createElement("span");
      hint.className = "hint";
      if (m) { name.textContent = `${m[1]} · ${m[2]}`; hint.textContent = m[3]; }
      else { name.textContent = line.replace(/^-\s*/, ""); }
      li.append(name, hint);
      ul.appendChild(li);
    }
  }

  async function refreshMemory() {
    const data = await fetchJSON("/api/memory");
    if (!data) return;
    $("memory-text").textContent =
      `【MEMORY.md · 长期记忆】\n${data.memory.trim()}\n\n【USER.md · 用户画像】\n${data.user.trim()}`;
  }

  /* ---- C3：出巡簿（子代理日志）与外务府（MCP 工具） ---- */
  async function refreshSubagentLogs() {
    const data = await fetchJSON("/api/subagent_logs");
    if (!data || !Array.isArray(data.logs)) return;
    const ul = $("subagent-log-list");
    if (!ul) return;
    ul.replaceChildren();
    if (data.logs.length === 0) {
      const li = document.createElement("li");
      li.className = "hint";
      li.textContent = "（尚无出巡记录）";
      ul.appendChild(li);
      return;
    }
    const outcomeText = { done: "办妥", circuit_breaker: "熔断", max_turns: "超轮", unknown: "?" };
    const outcomeCls = { done: "todo-done", circuit_breaker: "todo-doing", max_turns: "todo-doing" };
    for (const log of data.logs) {
      const li = document.createElement("li");
      li.className = outcomeCls[log.outcome] || "";
      const name = document.createElement("span");
      name.textContent = `${(log.agent_type || "?").slice(0, 8)} · ${(log.task || "").slice(0, 10)}`;
      const hint = document.createElement("span");
      hint.className = "hint";
      hint.textContent = `${outcomeText[log.outcome] || "?"} ${log.ok}✓/${log.fail}✗`;
      li.append(name, hint);
      li.title = log.summary || "";   // 悬停看回禀摘要
      ul.appendChild(li);
    }
  }

  async function refreshMcp() {
    const data = await fetchJSON("/api/mcp");
    if (!data || typeof data.mcp !== "string") return;
    const pre = $("mcp-text");
    if (!pre) return;
    pre.textContent = data.mcp;
  }

  // 开新殿按钮（B1 静态按钮在此接活）
  $("btn-new-hall").addEventListener("click", () => {
    if (busy || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "new_session" }));
    renderNotice("（已开新殿——）");
    refreshSessions();
  });

  // 面板轮询：会话列表高频些（动作后要刷新），其余低频
  setInterval(refreshSessions, 8000);
  setInterval(() => { refreshTeam(); refreshMemory(); refreshSubagentLogs(); }, 30000);

  /* ---- 连接与断线（B2：提示 + 每 3 秒自动重连；B3：断线提示去重） ---- */
  let offlineNotified = false;
  function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => {
      offlineNotified = false;
      renderNotice("（已接驾，老奴候旨——）");
      setLamp("on", "● 当值");
      refreshSend();
      refreshSessions(); refreshPersonas(); refreshTeam(); refreshMemory();
      refreshSubagentLogs(); refreshMcp();
    };
    ws.onmessage = (m) => {
      try { onEvent(JSON.parse(m.data)); } catch { /* 坏消息直接丢弃 */ }
    };
    ws.onclose = () => {
      setLamp("", "● 离线");
      if (!offlineNotified) {
        renderNotice("（连接断开，每 3 秒自动重连……重连后为新会话，旧对话可在偏殿名册找回）", "warn");
        offlineNotified = true;
      }
      refreshSend();
      setTimeout(connect, 3000);
    };
  }

  btnSend.addEventListener("click", send);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });

  connect();
})();
