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
  const chat = $("chat"), input = $("input"), btnSend = $("btn-send"), lamp = $("lamp");

  let ws = null;
  let activeMemorial = null;   // 正在流式渲染的奏折正文
  let pendingTools = [];       // 已 tool_start 未 tool_end 的卡片（内核顺序执行，按名配对）
  let busy = false;

  /* ---- 渲染小件 ---- */
  function scrollBottom() { chat.scrollTop = chat.scrollHeight; }

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
    foot.textContent = "老奴叩禀";
    art.append(body, foot);
    activeMemorial = body;
    addNode(art);
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
      case "subagents_start": renderNotice(`并发派遣 ${ev.count} 位小太监出巡…`); break;
      case "subagent_summary": renderNotice(`小太监已回禀（${ev.length} 字），详情见最终奏折`); break;
      case "stop_gate":       renderNotice(`[质量门禁] ${ev.reason}`, "warn"); break;
      case "retry":
      case "error":           renderNotice(String(ev.message || "").trim(), "warn"); break;
      case "hook_ask":        renderNotice(`[需朱批] ${ev.reason}（圣旨弹窗 C1 上线，未批将超时驳回）`, "warn"); break;
      case "hook_decision":   renderNotice(`[门禁] ${ev.action}：${ev.reason}`); break;
      case "session":         break;    // C2：偏殿名册
      case "todos":           break;    // B3：差事灯笼
      case "done":
      case "idle":            setLamp("on", "● 当值"); busy = false; refreshSend(); break;
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
    refreshSend();
  }

  /* ---- 连接与断线（B2：提示 + 每 3 秒自动重连） ---- */
  function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => {
      renderNotice("（已接驾，老奴候旨——）");
      setLamp("on", "● 当值");
      refreshSend();
    };
    ws.onmessage = (m) => {
      try { onEvent(JSON.parse(m.data)); } catch { /* 坏消息直接丢弃 */ }
    };
    ws.onclose = () => {
      setLamp("", "● 离线");
      renderNotice("（连接断开，每 3 秒自动重连……重连后为新会话，旧对话可在偏殿名册找回）", "warn");
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
