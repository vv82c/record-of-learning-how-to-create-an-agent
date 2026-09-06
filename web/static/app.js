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
  const decreeCode = $("decree-code"), decreeTimer = $("decree-timer"), decreeBar = $("decree-bar");
  const starter = $("starter");   // E1.4：空状态示例圣旨卡
  const ledgerCtx = $("ledger-ctx"), ledgerCtxBar = $("ledger-ctx-bar"),
        ledgerCache = $("ledger-cache"), ledgerTurn = $("ledger-turn"),
        ledgerTotal = $("ledger-total");   // E5：内库账房

  /* ---- J2：昼/夜主题切换 ----
     内联自举脚本已在样式表解析前定好 data-theme（显式选择 > 跟随系统）；
     这里只管按钮文案与切换：一旦点过，localStorage 记下显式选择，不再跟系统漂移。 */
  const btnTheme = $("btn-theme");
  const THEME_KEY = "emperor-theme";

  function themeLabel() {
    return document.documentElement.dataset.theme === "light" ? "夜" : "昼";
  }
  function refreshThemeBtn() {
    btnTheme.textContent = themeLabel();
    btnTheme.title = `切换到${themeLabel() === "昼" ? "昼间" : "夜间"}主题`;
  }
  function applyTheme(t) {
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem(THEME_KEY, t); } catch { /* 内存态兜底 */ }
    refreshThemeBtn();
  }
  btnTheme.addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");
  });
  refreshThemeBtn();
  // 从未显式选过主题时，跟随系统实时切换；选过则以用户为准
  if (!localStorage.getItem(THEME_KEY)) {
    matchMedia("(prefers-color-scheme: light)").addEventListener?.("change", (e) => {
      document.documentElement.dataset.theme = e.matches ? "light" : "dark";
      refreshThemeBtn();
    });
  }

  /* ---- C1：圣旨待批弹窗 ----
     hook_ask → 弹窗 + 倒计时。I3 起时限从 /api/settings 现读（内务府颁行后即时联动）；
     即使倒计时与服务器有偏差，服务端超时仍 fail-closed，前端只是尽力同步观感。 */
  let countdownTimer = null;
  let askTimeoutMs = 120000;   // 初值与内核缺省一致，refreshSettings 后以设置为准

  function openDecree(reason, tool, inputObj, level) {
    decreeText.textContent = `皇上，此令需您朱批：${reason}`;
    // E4.1：完整工具与参数走结构化字段（reason 内命令被截断至 120 字符），等宽展示"看清再批"
    if (tool) {
      decreeCode.hidden = false;
      decreeCode.textContent = tool + (inputObj && Object.keys(inputObj).length
        ? "\n" + JSON.stringify(inputObj, null, 2) : "");
    } else {
      decreeCode.hidden = true;
      decreeCode.textContent = "";
    }
    // E4.2：两档危险视觉（high=外发/发布/部署类高危）
    veil.classList.toggle("high", level === "high");
    veil.hidden = false;
    startCountdown();
  }

  function closeDecree() {
    veil.hidden = true;
    veil.classList.remove("high");
    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
    decreeCount.hidden = true;
    decreeTimer.hidden = true;
  }

  function startCountdown() {
    const total = askTimeoutMs / 1000;
    const deadline = Date.now() + askTimeoutMs;
    decreeCount.hidden = false;
    decreeTimer.hidden = false;
    decreeBar.style.width = "100%";
    const tick = () => {
      const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      decreeCount.textContent = `（${left} 秒内未批，将按驳回处置）`;
      decreeBar.style.width = Math.max(0, (left / total) * 100) + "%";   // E4.3：可视进度
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

  /* E4.3：决策快捷键——弹窗开着时 Enter=准奏、Esc=驳回。
     焦点在传旨栏时其自身的 Enter 处理器会先跑（busy 中 send() 自行拒绝），随后冒泡到此仍会批阅。 */
  document.addEventListener("keydown", (e) => {
    if (veil.hidden) return;
    if (e.key === "Enter") { e.preventDefault(); resolveDecree(true); }
    else if (e.key === "Escape") { e.preventDefault(); resolveDecree(false); }
  });

  let ws = null;
  let activeMemorial = null;   // 正在流式渲染的奏折正文
  let lastMemorialSign = null; // E2.3：最近一份奏折的落款（done 时补耗时/tokens）
  let activeThinkBox = null;   // G4：圣思折叠段（思维链）
  let activeThinkBody = null;
  let lastMemorialRegen = null;// G3：最近一份奏折的"另拟"钮（finishTurn 时只留最后一份）
  let regenButtons = [];
  let editMode = false;        // G3：改旨模式（下一次传旨按 edit_send 送出）
  let lastZhuPi = null;        // G3：只有最后一条朱批可点改旨
  let turnHasMemorial = false; // 本轮是否产生过奏折（防 error 收场时把落款写到旧奏折）
  let pendingTools = [];       // 已 tool_start 未 tool_end 的卡片（内核顺序执行，按名配对）
  let busy = false;
  let queuedText = null;       // H3：busy 时暂存的传旨（当差办结自动传出，Esc 撤回）

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
    el.className = "zhu-pi editable";
    el.title = "点击改旨（替换上一问重新办理）";
    el.textContent = text;
    if (lastZhuPi) { lastZhuPi.classList.remove("editable"); lastZhuPi.title = ""; }
    const mine = el;
    el.addEventListener("click", () => {
      if (busy || mine !== lastZhuPi) return;
      editMode = true;
      input.value = text;
      autoGrow();
      input.placeholder = "改旨中……送出将替换上一问（Esc 取消）";
      input.focus();
    });
    lastZhuPi = el;
    addNode(el);
  }

  function renderMemorialStart() {
    if (activeMemorial) return;   // G4：reasoning_start 已先建好奏折，防重入
    hideThinking();
    turnHasMemorial = true;
    const art = document.createElement("article");
    art.className = "memorial";
    // G4：圣思折叠段——思维链流式写入，答完自动收起
    const think = document.createElement("details");
    think.className = "think-box";
    think.hidden = true;
    const thinkSum = document.createElement("summary");
    thinkSum.textContent = "圣思（思维链，点开可阅）";
    const thinkBody = document.createElement("div");
    thinkBody.className = "think-body";
    think.append(thinkSum, thinkBody);
    const body = document.createElement("div");
    body.className = "memorial-body";
    const foot = document.createElement("div");
    foot.className = "memorial-foot";
    const sign = document.createElement("span");
    sign.textContent = "老奴叩禀";
    lastMemorialSign = sign;
    const regenBtn = document.createElement("button");   // G3：另拟
    regenBtn.type = "button";
    regenBtn.className = "btn-copy";
    regenBtn.textContent = "另拟";
    regenBtn.hidden = true;
    regenBtn.addEventListener("click", requestRegen);
    regenButtons.push(regenBtn);
    lastMemorialRegen = regenBtn;
    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "btn-copy";
    copyBtn.textContent = "誊抄";
    foot.append(sign, regenBtn, copyBtn);
    art.append(think, body, foot);
    activeMemorial = body;
    activeThinkBox = think;
    activeThinkBody = thinkBody;
    mdBuffer = "";
    addNode(art);
  }

  /* G3：显示与历史对齐——回滚后把屏幕上对应的旧内容收走 */
  function clearFromLastZhuPi(includeZhuPi) {
    const children = [...chat.children];
    const idx = children.indexOf(lastZhuPi);
    if (idx < 0) return;
    children.slice(includeZhuPi ? idx : idx + 1).forEach(el => el.remove());
  }

  /* G3：另拟——原问重跑，服务端先回滚历史 */
  function requestRegen() {
    if (busy || !ws || ws.readyState !== WebSocket.OPEN) return;
    clearFromLastZhuPi(false);   // 收走上一份回答（朱批保留）
    ws.send(JSON.stringify({ type: "regen" }));
    busy = true;
    setLamp("busy", "● 行走中");
    btnStop.hidden = false;
    refreshSend();
    renderNotice("（请旨另拟，重办此差——）");
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

  /* ---- E3.3：极简 Markdown 渲染（DOM 构建式） ----
     五类支持：标题/列表/围栏代码块/加粗斜体/行内 code；其余一律纯文本节点。
     安全性由构造保证：全程 createElement/createTextNode，从不拼 HTML、不用 innerHTML，
     <script>、<img onerror>、[链接](javascript:) 等统统是普通文本的原料。
     流式策略：token 增量累加缓冲，rAF 节流全量重渲（回复 KB 级，成本可忽略）。 */
  function mdInline(parent, text) {
    const re = /(`([^`]+)`)|(\*\*([^*]+)\*\*)|(\*([^*\s][^*]*?)\*)/g;
    let last = 0, m;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) parent.appendChild(document.createTextNode(text.slice(last, m.index)));
      if (m[2] !== undefined) {
        const code = document.createElement("code");
        code.textContent = m[2];
        parent.appendChild(code);
      } else if (m[4] !== undefined) {
        const strong = document.createElement("strong");
        strong.textContent = m[4];
        parent.appendChild(strong);
      } else {
        const em = document.createElement("em");
        em.textContent = m[6];
        parent.appendChild(em);
      }
      last = re.lastIndex;
    }
    if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
  }

  function mdInlineBlock(tag, text) {
    const el = document.createElement(tag);
    mdInline(el, text);
    return el;
  }

  function renderMarkdown(root, raw) {
    root.classList.add("md");
    root.replaceChildren();
    const lines = String(raw).replace(/\r\n/g, "\n").split("\n");
    let i = 0;
    let para = null;
    while (i < lines.length) {
      const line = lines[i];

      // 围栏代码块 ```：收至闭合围栏；未闭合则吃到结尾（流式中间态）
      if (/^\s*```/.test(line)) {
        para = null;
        const body = [];
        i++;
        while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) {
          body.push(lines[i]); i++;
        }
        i++;                                   // 跳过闭合围栏；越界则循环自然结束
        const pre = document.createElement("pre");
        const code = document.createElement("code");
        code.textContent = body.join("\n");
        pre.appendChild(code);
        root.appendChild(pre);
        continue;
      }

      // 标题 #~######：映射为 h3 起步，避免盖过奏折卡片的视觉层级
      const head = /^(#{1,6})\s+(.*)$/.exec(line);
      if (head) {
        para = null;
        const level = Math.min(head[1].length + 2, 6);
        root.appendChild(mdInlineBlock("h" + level, head[2]));
        i++;
        continue;
      }

      // 列表：连续项归入同一个 ul/ol（`-`/`*` 无序，`1.`/`1、` 有序）
      const item = /^(\s*)([-*]|\d+[.、])\s+(.*)$/.exec(line);
      if (item) {
        para = null;
        const tag = /\d/.test(item[2]) ? "ol" : "ul";
        let list = root.lastElementChild;
        if (!(list && list.tagName === tag.toUpperCase())) {
          list = document.createElement(tag);
          root.appendChild(list);
        }
        const li = document.createElement("li");
        mdInline(li, item[3]);
        list.appendChild(li);
        i++;
        continue;
      }

      // 空行：段落收束
      if (!line.trim()) {
        para = null;
        i++;
        continue;
      }

      // 普通文本：归入段落（段内换行由 CSS pre-wrap 保留）
      if (!para) {
        para = document.createElement("p");
        root.appendChild(para);
      }
      if (para.childNodes.length) para.appendChild(document.createTextNode("\n"));
      mdInline(para, line);
      i++;
    }
  }

  let mdBuffer = "";           // 当前奏折的原始文本缓冲（流式增量累加）
  let mdScheduled = false;     // rAF 节流：一帧至多重渲一次

  function renderToken(text) {
    if (!activeMemorial) renderMemorialStart();
    mdBuffer += text;
    if (!mdScheduled) {
      mdScheduled = true;
      requestAnimationFrame(() => {
        mdScheduled = false;
        if (!activeMemorial) return;
        renderMarkdown(activeMemorial, mdBuffer);
        scrollBottom();
      });
    }
    scrollBottom();
  }

  /* ---- E2.1：拟旨占位（turn_start → 首个 token/turn_end/error/断线 收起） ---- */
  let thinkEl = null;
  function showThinking() {
    if (thinkEl) return;
    turnHasMemorial = false;                 // 本轮若以 error 收场，落款信息不得写到旧奏折上
    thinkEl = document.createElement("div");
    thinkEl.className = "memorial-think";
    thinkEl.textContent = "老奴正在拟旨";
    addNode(thinkEl);
  }
  function hideThinking() {
    if (thinkEl) { thinkEl.remove(); thinkEl = null; }
  }

  function renderReply(text) {            // 非流式整段回复（Hook 短路/拦截文案）
    renderMemorialStart();
    mdBuffer = text;
    renderMarkdown(activeMemorial, mdBuffer);
    activeMemorial = null;
  }

  /* E2.2：输入摘要——取第一个参数值压成一行（run_command 是命令本身，read/write 是路径） */
  function digestInput(obj) {
    if (!obj) return "";
    const v = Object.values(obj)[0];
    if (v === undefined || v === null || v === "") return "";
    return String(v).replace(/\s+/g, " ").slice(0, 36);
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
    pendingTools.push({ name, title, pre, state, digest: digestInput(inputObj) });
  }

  function renderToolEnd(name, output, blocked, ok, durationMs) {
    for (let i = pendingTools.length - 1; i >= 0; i--) {   // 顺序配对最近同名卡
      if (pendingTools[i].name === name) {
        const t = pendingTools.splice(i, 1)[0];
        const dur = typeof durationMs === "number" ? ` · ${(durationMs / 1000).toFixed(1)}s` : "";
        if (blocked) { t.state.textContent = `✗ 已拦截${dur}`; t.state.className = "state blocked"; }
        else if (ok === false) { t.state.textContent = `✗${dur}`; t.state.className = "state blocked"; }
        else { t.state.textContent = `✓${dur}`; t.state.className = "state ok"; }
        t.title.textContent = ` 内务府 · ${t.name}${t.digest ? " · " + t.digest : ""} `;
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

  /* H1：要务驻留条——重试/门禁/报错固定在输入栏上方，不随流式内容滚走；
     用户点 ×、发新一轮（user_echo）或换殿时才收起。 */
  function renderSticky(text) {
    $("sticky-notice-text").textContent = text;
    $("sticky-notice").hidden = false;
  }

  function clearSticky() { $("sticky-notice").hidden = true; }

  $("btn-notice-close").addEventListener("click", clearSticky);

  function setLamp(mode, text) {
    lamp.className = "lamp" + (mode ? " " + mode : "");
    lamp.textContent = text;
  }

  /* ---- 事件分发 ---- */
  function onEvent(ev) {
    switch (ev.type) {
      case "user_echo":       clearSticky(); hasConversation = true; starter.hidden = true; renderZhuPi(ev.text); break;
      case "reasoning_start": // G4：思维链先于正文，奏折带圣思段
        renderMemorialStart();
        activeThinkBox.hidden = false;
        activeThinkBox.open = true;
        break;
      case "reasoning":       activeThinkBody.textContent += ev.text; scrollBottom(); break;
      case "reply_start":
        renderMemorialStart();
        if (activeThinkBox) activeThinkBox.open = false;   // 正文开写，圣思收起
        break;
      case "token":           renderToken(ev.text); break;
      case "reply_end":
        // 冲刷未决的 rAF 帧：流结束时的最终 Markdown 状态必须落定
        if (activeMemorial && mdScheduled) {
          mdScheduled = false;
          renderMarkdown(activeMemorial, mdBuffer);
        }
        activeMemorial = null;
        break;
      case "reply":           hasConversation = true; starter.hidden = true; renderReply(ev.text); break;
      case "tool_start":      renderToolStart(ev.name, ev.input); break;
      case "tool_end":        renderToolEnd(ev.name, ev.output, ev.blocked, ev.ok, ev.duration_ms); break;
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
      case "stop_gate":       renderSticky(`[质量门禁] ${ev.reason}`); break;
      case "retry":           renderSticky(String(ev.message || "").trim()); break;  // H1：驻留不被流式刷走
      case "error":           hideThinking(); renderSticky(String(ev.message || "").trim()); break;
      case "hook_ask":        openDecree(ev.reason, ev.tool, ev.input, ev.level); break;   // C1/E4：圣旨弹窗
      case "hook_decision":
        if (ev.action === "deny") {
          // 弹窗开着收到 deny = 服务端超时驳回（fail-closed）：前端同步关窗对齐观感（E4）
          if (!veil.hidden) closeDecree();
          renderSticky(`[门禁·驳回] ${ev.reason}`);
        } else if (!veil.hidden) {
          closeDecree();
        }
        break;
      case "session":
        hideThinking();          // 换殿/重连不残留上一殿的拟旨占位
        clearSticky();           // H1：换殿清掉上一殿的驻留警告
        resetLedger();           // E5：换殿账本归零（内核已重置，前端观感对齐）
        editMode = false;        // G3：换殿退出改旨模式
        currentSessionId = ev.id;
        if (ev.resumed) {
          hasConversation = ev.messages > 0;
          renderNotice(`（已入偏殿 ${ev.id}，共 ${ev.messages} 条旧话，可续谈）`);
        } else {
          hasConversation = false;   // 新会话/首次连接/断线重连：空殿重新开谈
        }
        starter.hidden = hasConversation;
        if (ev.fresh) refreshSessions();
        refreshSessions();
        break;
      case "persona":
        currentPersona = ev.name;
        renderNotice(`（已换装：${ev.name}，下轮生效——）`);
        refreshPersonas();
        break;
      case "memory_compacted":// G1：压缩对用户可见
        renderNotice(`（老奴已将前事 ${ev.removed} 条沉淀入记忆卷宗——）`);
        refreshMemory();
        break;
      case "session_title":   // G2：本殿题名
        renderNotice(`（此殿题名：「${ev.title}」）`);
        refreshSessions();
        break;
      case "todos":           renderTodos(ev.todos); break;   // B3：差事灯笼
      case "turn_start":      showThinking(); break;          // E2.1：拟旨占位
      case "turn_end":        hideThinking(); break;          // 成败都收，防残留
      case "done":
        hideThinking();
        // E2.3：本轮确实产生过奏折才补落款（error 收场时历史落款不得被改写）
        if (turnHasMemorial && lastMemorialSign && typeof ev.duration_ms === "number") {
          let meta = ` · ${(ev.duration_ms / 1000).toFixed(1)}s`;
          if (ev.tokens) meta += ` · ${ev.tokens} tokens`;
          lastMemorialSign.textContent += meta;
        }
        renderLedger(ev.usage, ev.context_window);   // E5：账房入账
        // H1：done 只记账不收工——busy 保持到 idle（服务端 busy.clear 之后），
        // 消除 done→idle 窗口里发送必撞"仍在办理中"的竞态
        break;
      case "idle":            finishTurn(); flushQueued(); break;
      case "pong":            break;
    }
  }

  function refreshSend() {
    const ready = ws && ws.readyState === WebSocket.OPEN;
    btnSend.disabled = !ready;   // H3：busy 不再禁用——行走中也能拟旨，Enter 暂存排队
    btnSend.textContent = queuedText ? "已暂存" : "传 旨";
    input.placeholder = busy
      ? (queuedText ? "行走中……（排队之旨已录，Enter 可改暂存，Esc 撤回）"
                    : "行走中……（可先拟旨，Enter 暂存待传）")
      : ready ? "传旨……（Enter 传旨，Shift+Enter 换行）" : "未接驾……";
  }

  function finishTurn() {
    setLamp("on", "● 当值"); busy = false; refreshSend(); btnStop.hidden = true;
    regenButtons.forEach(b => { b.hidden = true; });   // G3：只保留最新奏折的另拟钮
    if (lastMemorialRegen) lastMemorialRegen.hidden = false;
  }

  /* H3：把暂存的传旨正式送出（idle 时服务端已清 busy，此刻发送必不落空） */
  function flushQueued() {
    if (!queuedText) return;
    const text = queuedText;
    queuedText = null;
    sendText(text, "send");
  }

  /* ---- E5：内库账房——用度计数板 ----
     数据全部来自 done 事件的 usage（内核按连接累加，new/resume 归零）。
     上下文占用 = 上一轮 prompt_tokens / 窗口（精确值，非估算）；
     缓存命中 = cache_hit / prompt（头两轮冷缓存属正常，不做报警暗示）。 */
  function fmtTok(v) {
    if (typeof v !== "number" || isNaN(v)) return "—";
    return v >= 1000 ? (v / 1000).toFixed(1) + "k" : String(v);
  }

  function renderLedger(usage, contextWindow) {
    if (!usage || typeof usage !== "object") return;
    const ctxWin = typeof contextWindow === "number" && contextWindow > 0 ? contextWindow : null;
    if (usage.last_prompt != null && ctxWin) {
      const pct = Math.min(100, (usage.last_prompt / ctxWin) * 100);
      ledgerCtxBar.style.width = pct.toFixed(1) + "%";
      ledgerCtx.textContent = `${pct.toFixed(0)}% · ${fmtTok(usage.last_prompt)}/${fmtTok(ctxWin)}`;
    } else {
      ledgerCtxBar.style.width = "0%";
      ledgerCtx.textContent = "—";
    }
    ledgerCache.textContent = usage.prompt > 0
      ? Math.round((usage.cache_hit / usage.prompt) * 100) + "%" : "—";
    ledgerTurn.textContent = fmtTok(usage.last_total);
    ledgerTotal.textContent = fmtTok(usage.prompt + usage.completion);
  }

  function resetLedger() {
    ledgerCtxBar.style.width = "0%";
    ledgerCtx.textContent = "—";
    ledgerCache.textContent = "—";
    ledgerTurn.textContent = "—";
    ledgerTotal.textContent = "—";
  }

  /* ---- E1.1：输入框随内容自动撑高（上限 140px 由 CSS max-height 把守） ---- */
  function autoGrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
  }
  input.addEventListener("input", autoGrow);

  /* ---- E1.2：传旨历史回溯（↑/↓ 循环，localStorage 持久） ----
     只在光标位于首行时 ↑ 才回溯、末行时 ↓ 才返回——不干扰多行编辑的光标移动。 */
  const HISTORY_KEY = "emperor-input-history";
  const HISTORY_MAX = 50;
  let inputHistory = [];
  try { inputHistory = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); }
  catch { inputHistory = []; }          // localStorage 不可用/损坏时静默降级为无历史
  let histIndex = -1;                    // -1 = 正在编辑当前草稿
  let histDraft = "";

  function rememberInput(text) {
    if (!text) return;
    inputHistory = inputHistory.filter(t => t !== text);   // 去重，最近使用的排末尾
    inputHistory.push(text);
    if (inputHistory.length > HISTORY_MAX) inputHistory = inputHistory.slice(-HISTORY_MAX);
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(inputHistory)); } catch { /* 内存态兜底 */ }
    histIndex = -1;
    histDraft = "";
  }

  function caretOnFirstLine() {
    const pos = input.selectionStart;
    return pos === null || input.value.slice(0, pos).indexOf("\n") === -1;
  }
  function caretOnLastLine() {
    const pos = input.selectionEnd;
    return pos === null || input.value.slice(pos).indexOf("\n") === -1;
  }

  /* 发送动作本体：守卫 + 入队 + 忙置位。传旨栏与 E1.4 示例圣旨卡共用。
     H3：busy 且是普通传旨 → 暂存排队（改旨/另拟只在闲时可发起，不排队）；idle 时冲队。 */
  function sendText(text, kind = "send") {
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return false;
    if (busy) {
      if (kind !== "send") return false;
      queuedText = text;
      refreshSend();
      renderNotice(`（行走中，此旨暂存待传：「${text.slice(0, 24)}」——）`);
      return true;
    }
    ws.send(JSON.stringify({ type: kind, text }));
    rememberInput(text);
    busy = true;
    setLamp("busy", "● 行走中");
    btnStop.hidden = false;
    refreshSend();
    return true;
  }

  function send() {
    const text = input.value.trim();
    if (!sendText(text, editMode ? "edit_send" : "send")) return;
    if (editMode) { clearFromLastZhuPi(true); lastZhuPi = null; }   // 改旨：旧问旧答一起收走
    editMode = false;
    refreshSend();   // 恢复常规占位提示（退出改旨模式）
    input.value = "";
    autoGrow();
  }

  /* ---- B3：请旨叫停（在途流断流返回部分内容，工具批后收束） ---- */
  btnStop.addEventListener("click", () => {
    if (!busy || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "stop" }));
    renderNotice("（已请旨叫停，待总管收束……）");
  });

  /* ---- F3：模型阁——多模型配置管理（REST：配置是进程级全局） ---- */
  let editingModel = null;          // 正在修改的档案名；null = 新增
  let deleteArm = null;             // 两步确认删除：已点一次删除的档案名

  async function refreshModels() {
    const data = await fetchJSON("/api/models");
    if (!data || !Array.isArray(data.profiles)) return;
    const ul = $("model-list");
    ul.replaceChildren();
    if (data.profiles.length === 0) {
      const li = document.createElement("li");
      li.className = "hint";
      li.textContent = "（尚无模型——展开下方表单，填接口地址 / Key / 模型名）";
      ul.appendChild(li);
      $("model-form-box").open = true;            // F4：首启无配置自动展开表单
      return;
    }
    for (const p of data.profiles) {
      const li = document.createElement("li");
      if (p.name === data.active) li.className = "active";
      const name = document.createElement("span");
      name.className = "hall-name";
      name.textContent = p.name + (p.key_hint ? ` · ${p.key_hint}` : "");
      const hint = document.createElement("span");
      hint.className = "hint";
      hint.textContent = p.name === data.active ? "当前" : "切换";
      const btnEdit = document.createElement("button");
      btnEdit.type = "button"; btnEdit.className = "btn-mini-inline"; btnEdit.textContent = "改";
      btnEdit.addEventListener("click", (e) => { e.stopPropagation(); fillModelForm(p); });
      const btnDel = document.createElement("button");
      btnDel.type = "button"; btnDel.className = "btn-mini-inline"; btnDel.textContent = "删";
      btnDel.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (deleteArm !== p.name) {               // 两步确认（pywebview 无原生 confirm）
          deleteArm = p.name;
          btnDel.textContent = "确认删?";
          setTimeout(() => { btnDel.textContent = "删"; deleteArm = null; }, 3000);
          return;
        }
        deleteArm = null;
        const r = await fetch("/api/models/delete", { method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: p.name }) });
        renderNotice(r.ok ? `（模型「${p.name}」已撤下——）` : "（撤下失败……）", r.ok ? "" : "warn");
        if (editingModel === p.name) cancelModelForm();
        refreshModels();
      });
      li.addEventListener("click", async () => {
        if (p.name === data.active) return;
        const r = await fetch("/api/models/switch", { method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: p.name }) });
        if (r.ok) renderNotice(`（已换用模型「${p.name}」——下轮生效）`);
        refreshModels();
      });
      li.append(name, btnEdit, btnDel, hint);
      ul.appendChild(li);
    }
  }

  function fillModelForm(p) {
    editingModel = p.name;
    $("model-name").value = p.name;
    $("model-url").value = p.base_url;
    $("model-id").value = p.model;
    $("model-key").value = "";                    // 空 = 沿用原 key
    $("model-window").value = p.context_window || "";
    $("model-form-title").textContent = `修改「${p.name}」`;
    $("btn-model-cancel").hidden = false;
    $("model-form-box").open = true;
  }

  function cancelModelForm() {
    editingModel = null;
    ["model-name", "model-url", "model-id", "model-key", "model-window"].forEach(id => { $(id).value = ""; });
    $("model-form-title").textContent = "＋ 添加 / 修改模型";
    $("btn-model-cancel").hidden = true;
  }

  $("btn-model-cancel").addEventListener("click", cancelModelForm);
  $("btn-model-save").addEventListener("click", async () => {
    const body = {
      name: $("model-name").value.trim(),
      base_url: $("model-url").value.trim(),
      model: $("model-id").value.trim(),
      api_key: $("model-key").value.trim(),
      context_window: parseInt($("model-window").value, 10) || null,
    };
    if (!body.name || !body.base_url || !body.model) {
      renderNotice("（名称、接口地址、模型名都不能空——）", "warn");
      return;
    }
    const r = await fetch("/api/models", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) { renderNotice("（保存失败——请检查各项填写）", "warn"); return; }
    renderNotice(editingModel ? `（模型「${body.name}」已更新并启用——）`
                              : `（模型「${body.name}」已入阁并启用——）`);
    cancelModelForm();
    refreshModels();
  });

  /* ---- I3：内务府——行为设置（REST：进程级全局，与模型阁同理） ----
     只在接驾时拉取回填（不进轮询——避免把用户改到一半的表单冲掉）；
     保存成功即同步本地的批阅倒计时时长，下个圣旨弹窗立即按新规计时。 */
  async function refreshSettings() {
    const [data, personaData] = await Promise.all([
      fetchJSON("/api/settings"), fetchJSON("/api/personas"),
    ]);
    if (!data || typeof data.settings !== "object") return;
    const s = data.settings;
    askTimeoutMs = (Number(s.ask_timeout) || 120) * 1000;
    $("set-ask-timeout").value = s.ask_timeout;
    $("set-fail-budget").value = s.subagent_fail_budget;
    const sel = $("set-persona");
    sel.replaceChildren();
    const optEmpty = document.createElement("option");
    optEmpty.value = "";
    optEmpty.textContent = "（未指定——用内核默认）";
    sel.appendChild(optEmpty);
    for (const n of (personaData?.personas) || []) {
      const o = document.createElement("option");
      o.value = n;
      o.textContent = n === "taijian" ? "太监总管" : n === "guanjia" ? "英式管家" : n;
      if (n === s.default_persona) o.selected = true;
      sel.appendChild(o);
    }
  }

  $("btn-settings-save").addEventListener("click", async () => {
    const body = {
      ask_timeout: parseFloat($("set-ask-timeout").value),
      default_persona: $("set-persona").value,
      subagent_fail_budget: parseInt($("set-fail-budget").value, 10),
    };
    if (isNaN(body.ask_timeout) || isNaN(body.subagent_fail_budget)) {
      renderNotice("（批阅时限与熔断预算都必须是数字——）", "warn");
      return;
    }
    const r = await fetch("/api/settings", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) {
      const err = await r.json().catch(() => null);
      renderNotice(`（颁行失败：${err?.detail || "未知原因"}）`, "warn");
      return;
    }
    const data = await r.json();
    askTimeoutMs = (Number(data.settings.ask_timeout) || 120) * 1000;
    renderNotice("（内务府新规已颁行——）");
  });

  /* ---- C2：面板数据（REST 拉取） ---- */
  let currentSessionId = null;
  let currentPersona = null;

  /* ---- E1.4：空状态引导——只在"全新且还没开谈"的会话展示示例卡 ----
     新会话（fresh/断线重连/首次连接）与 0 条旧话的恢复会话显示；
     一旦发出传旨或收到回复即收起，恢复有内容的旧殿直接不显示。 */
  let hasConversation = false;

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
    const q = ($("session-search").value || "").trim();   // H1：检索框有词即走服务端全文检索
    const data = await fetchJSON(q ? `/api/sessions?q=${encodeURIComponent(q)}` : "/api/sessions");
    if (!data || !Array.isArray(data.sessions)) return;
    const ul = $("session-list");
    ul.replaceChildren();
    if (data.sessions.length === 0) {
      const li = document.createElement("li");
      li.className = "hint";
      li.textContent = q ? "（未检索到相配的偏殿）" : "（尚无偏殿）";
      ul.appendChild(li);
      return;
    }
    for (const s of data.sessions.slice(0, 15)) {
      const li = document.createElement("li");
      if (s.id === currentSessionId) li.className = "active";
      const name = document.createElement("span");
      name.className = "hall-name";
      name.textContent = fmtHallName(s);
      // H1：改题名（当场行内编辑，Enter 存 / Esc 罢）
      const btnRename = document.createElement("button");
      btnRename.type = "button"; btnRename.className = "btn-mini-inline"; btnRename.textContent = "改";
      btnRename.addEventListener("click", (e) => { e.stopPropagation(); startRename(li, s, name); });
      li.append(name, btnRename);
      if (s.id !== currentSessionId) {   // 当值偏殿不可拆（服务端 ACTIVE_SESSIONS 也会拒）
        const btnDel = document.createElement("button");
        btnDel.type = "button"; btnDel.className = "btn-mini-inline"; btnDel.textContent = "拆";
        btnDel.addEventListener("click", (e) => { e.stopPropagation(); deleteSession(s.id, btnDel); });
        li.append(btnDel);
      }
      const hint = document.createElement("span");
      hint.className = "hint";
      hint.textContent = s.id === currentSessionId ? "当前" : `${s.messages}条`;
      li.append(hint);
      li.addEventListener("click", () => {
        if (s.id !== currentSessionId && !busy) resumeSession(s.id);
      });
      ul.appendChild(li);
    }
  }

  /* H1：行内改题名——输入框顶掉名字，Enter 存 / Esc 罢 / 点别处 blur 罢 */
  function startRename(li, s, nameSpan) {
    if (li.querySelector(".rename-input")) return;
    const inp = document.createElement("input");
    inp.className = "rename-input";
    inp.value = s.preview || "";
    li.replaceChild(inp, nameSpan);
    inp.focus();
    inp.select();
    let settled = false;
    const done = async (save) => {
      if (settled) return;
      settled = true;
      const t = inp.value.trim();
      if (save && t && t !== (s.preview || "")) {
        const r = await fetch("/api/sessions/rename", { method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: s.id, title: t }) });
        const err = r.ok ? null : await r.json().catch(() => null);
        renderNotice(r.ok ? `（偏殿已改题名：「${t}」——）`
                          : `（改题名失败：${err?.detail || "未知原因"}）`, r.ok ? "" : "warn");
        refreshSessions();
      } else {
        li.replaceChild(nameSpan, inp);   // 没改动就不惊动名册
      }
    };
    inp.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); done(true); }
      else if (e.key === "Escape") { e.preventDefault(); done(false); }
    });
    inp.addEventListener("blur", () => done(false));
  }

  /* H1：拆殿（两步确认，与模型阁撤下同款交互） */
  let deleteArmSession = null;
  async function deleteSession(id, btn) {
    if (deleteArmSession !== id) {
      deleteArmSession = id;
      btn.textContent = "确认拆?";
      setTimeout(() => {
        btn.textContent = "拆";
        if (deleteArmSession === id) deleteArmSession = null;
      }, 3000);
      return;
    }
    deleteArmSession = null;
    const r = await fetch("/api/sessions/delete", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }) });
    const err = r.ok ? null : await r.json().catch(() => null);
    renderNotice(r.ok ? `（偏殿 ${id} 已拆，名册除名——）`
                      : `（拆殿失败：${err?.detail || "未知原因"}）`, r.ok ? "" : "warn");
    refreshSessions();
  }

  /* H1：检索框防抖 → refreshSessions 自取框中关键词 */
  let searchTimer = null;
  $("session-search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(refreshSessions, 300);
  });

  /* H2：誊出话本——当前偏殿导出为 Markdown 下载 */
  $("btn-export").addEventListener("click", async () => {
    if (!currentSessionId) { renderNotice("（本殿尚未开口传旨，无话本可誊——）", "warn"); return; }
    const r = await fetch(`/api/sessions/export?id=${encodeURIComponent(currentSessionId)}`);
    if (!r.ok) {
      const err = await r.json().catch(() => null);
      renderNotice(`（誊抄失败：${err?.detail || "未知原因"}）`, "warn");
      return;
    }
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `emperor-${currentSessionId}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    renderNotice("（话本已誊出，请查收下载——）");
  });

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

  // E1.4：示例圣旨卡——点击即按正常传旨流程发出（sendText 成功才收起，失败保留）
  starter.querySelectorAll(".starter-card").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (sendText(btn.dataset.text || "")) starter.hidden = true;
    });
  });

  // 面板轮询：会话列表高频些（动作后要刷新），其余低频
  setInterval(refreshSessions, 8000);
  setInterval(() => { refreshTeam(); refreshMemory(); refreshSubagentLogs(); refreshModels(); }, 30000);

  /* ---- 连接与断线（B2：提示 + 每 3 秒自动重连；B3：断线提示去重） ---- */
  let offlineNotified = false;
  function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => {
      offlineNotified = false;
      busy = false;              // 服务端每条连接都是全新 runner：重连后必无在途差事，防 busy 卡死
      refreshSend();
      renderNotice("（已接驾，老奴候旨——）");
      setLamp("on", "● 当值");
      flushQueued();             // H3：断线前暂存之旨，接驾后即刻代传
      refreshSessions(); refreshPersonas(); refreshTeam(); refreshMemory();
      refreshSubagentLogs(); refreshMcp(); refreshModels(); refreshSettings();
    };
    ws.onmessage = (m) => {
      try { onEvent(JSON.parse(m.data)); } catch { /* 坏消息直接丢弃 */ }
    };
    ws.onclose = () => {
      hideThinking();          // 断线不残留拟旨占位（E2.1 验收项）
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
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); return; }
    if (e.key === "Escape" && editMode) {   // G3：改旨可反悔
      editMode = false;
      refreshSend();
    } else if (e.key === "Escape" && queuedText) {   // H3：暂存之旨可撤回
      queuedText = null;
      renderNotice("（已撤回暂存之旨——）");
      refreshSend();
    }
    if (e.key === "ArrowUp" && caretOnFirstLine() && inputHistory.length) {
      e.preventDefault();
      if (histIndex === -1) { histDraft = input.value; histIndex = inputHistory.length - 1; }
      else if (histIndex > 0) histIndex--;
      input.value = inputHistory[histIndex];
      autoGrow();
      input.setSelectionRange(input.value.length, input.value.length);
    } else if (e.key === "ArrowDown" && caretOnLastLine() && histIndex !== -1) {
      e.preventDefault();
      histIndex++;
      input.value = histIndex >= inputHistory.length ? histDraft : inputHistory[histIndex];
      if (histIndex >= inputHistory.length) histIndex = -1;
      autoGrow();
      input.setSelectionRange(input.value.length, input.value.length);
    }
  });

  connect();

  /* E3.3 验证钩子：把渲染器导出给自动化测试直接调用（生产路径不引用）。
     注入样本测试依赖它做确定性验证——模型会拒绝原样回显攻击串，走对话流测不到渲染器本身。
     H1 同款导出驻留条：自动化可直接驱动 renderSticky/clearSticky 验证显隐与关闭钮。 */
  window.__emperor_md = { render: renderMarkdown, inline: mdInline };
  window.__emperor_notice = { sticky: renderSticky, clear: clearSticky };
})();
