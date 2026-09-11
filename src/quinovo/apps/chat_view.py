"""Cursor-style workspace chat. No raw JSON on the page."""

from __future__ import annotations

from quinovo.apps.chrome import wrap

_CHAT_SCRIPT = r"""
<script>
(function () {
  const thread = document.getElementById("chat-thread");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send");
  const stopBtn = document.getElementById("chat-stop");
  const listEl = document.getElementById("chat-list");
  const empty = document.getElementById("chat-empty");
  const modelEl = document.getElementById("chat-model");
  const newBtn = document.getElementById("chat-new");
  const params = new URLSearchParams(location.search);
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let sessionId = params.get("c") || "";
  let abort = null;
  let streaming = false;

  const ICONS = {
    read: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="3" y="2" width="10" height="12" stroke="currentColor" stroke-width="1.4"/><path d="M5.5 5h5M5.5 8h5M5.5 11h3" stroke="currentColor" stroke-width="1.4"/></svg>',
    search: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="4.2" stroke="currentColor" stroke-width="1.4"/><path d="M10.2 10.2 14 14" stroke="currentColor" stroke-width="1.4" stroke-linecap="square"/></svg>',
    write: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M9 3.5 12.5 7 6 13.5H2.5V10L9 3.5z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="miter"/></svg>',
    run: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M4 3.5 13 8 4 12.5V3.5z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="miter"/></svg>',
    list: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 4h10M3 8h10M3 12h7" stroke="currentColor" stroke-width="1.4" stroke-linecap="square"/></svg>',
    link: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M6.5 9.5 9.5 6.5M4 8.5 2.5 10a2.4 2.4 0 1 0 3.4 3.4L7.5 12M12 7.5 13.5 6A2.4 2.4 0 1 0 10.1 2.6L8.5 4" stroke="currentColor" stroke-width="1.4"/></svg>',
    approve: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3.5 8.5 6.5 11.5 12.5 4.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="square" stroke-linejoin="miter"/></svg>',
    reject: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="square"/></svg>',
    delete: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 5h10M6 5V3.5h4V5M5.5 5v8h5V5" stroke="currentColor" stroke-width="1.4"/></svg>',
    call: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="3" y="3" width="4" height="4" stroke="currentColor" stroke-width="1.4"/><rect x="9" y="9" width="4" height="4" stroke="currentColor" stroke-width="1.4"/><path d="M7 5h2v6" stroke="currentColor" stroke-width="1.4"/></svg>'
  };

  function resize() {
    input.style.height = "24px";
    input.style.height = Math.min(input.scrollHeight, 200) + "px";
  }
  input.addEventListener("input", resize);
  resize();

  function md(text) {
    const raw = String(text || "");
    const escaped = raw
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    const noJsonFence = escaped.replace(/```(?:json|ya?ml)[\s\S]*?```/gi, "");
    const withCode = noJsonFence.replace(/`([^`]+)`/g, "<code>$1</code>");
    const withBold = withCode.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    const withLinks = withBold.replace(
      /\[([^\]]+)\]\((\/[^)\s]+|https?:\/\/[^)\s]+)\)/g,
      '<a href="$2">$1</a>'
    );
    return withLinks.split(/\n{2,}/).map((block) => {
      const lines = block.split("\n");
      const items = lines.filter((l) => /^\s*[-*]\s+/.test(l));
      if (items.length && items.length === lines.filter((l) => l.trim()).length) {
        return "<ul>" + items.map((l) => "<li>" + l.replace(/^\s*[-*]\s+/, "") + "</li>").join("") + "</ul>";
      }
      return "<p>" + lines.join("<br/>") + "</p>";
    }).join("");
  }

  function scrollBottom() {
    thread.parentElement.scrollTop = thread.parentElement.scrollHeight;
  }

  function setBusy(on) {
    streaming = on;
    sendBtn.hidden = on;
    stopBtn.hidden = !on;
    input.disabled = on;
  }

  function showEmpty(on) {
    empty.hidden = !on;
    thread.hidden = on;
  }

  function toolCard(row) {
    const art = document.createElement("article");
    const running = row.status === "running";
    art.className = "chat-step" + (running ? " running" : " done");
    art.dataset.id = row.id || "";
    const icon = ICONS[row.icon] || ICONS.call;
    const verb = running
      ? (row.calling || ("Calling " + (row.verb || row.name || "tool")))
      : (row.verb || row.name || "Call");
    const target = row.target || "";
    art.innerHTML =
      '<div class="chat-step-row">' +
        '<span class="chat-step-icon">' + icon + "</span>" +
        '<span class="chat-step-copy">' +
          '<span class="chat-step-line">' +
            '<span class="chat-step-verb"></span>' +
            (target ? '<span class="chat-step-target"></span>' : "") +
          "</span>" +
          (row.summary && !running ? '<span class="chat-step-sum"></span>' : "") +
        "</span>" +
        (running ? '<span class="chat-spin" aria-hidden="true"></span>' : "") +
      "</div>";
    art.querySelector(".chat-step-verb").textContent = verb;
    const targetEl = art.querySelector(".chat-step-target");
    if (targetEl) targetEl.textContent = target;
    const sumEl = art.querySelector(".chat-step-sum");
    if (sumEl) sumEl.textContent = row.summary || "";
    return art;
  }

  function addUser(text) {
    showEmpty(false);
    const wrap = document.createElement("article");
    wrap.className = "chat-turn user";
    wrap.innerHTML = '<div class="chat-bubble">' + md(text) + "</div>";
    thread.appendChild(wrap);
    scrollBottom();
  }

  function addAssistant() {
    const wrap = document.createElement("article");
    wrap.className = "chat-turn assistant";
    wrap.innerHTML =
      '<div class="chat-pending"><span class="chat-spin" aria-hidden="true"></span><span>Working</span></div>' +
      '<div class="chat-tools"></div>' +
      '<div class="chat-prose"></div>';
    thread.appendChild(wrap);
    return wrap;
  }

  function hidePending(box) {
    const pending = box.querySelector(".chat-pending");
    if (pending) pending.remove();
  }

  function Typewriter(prose) {
    this.prose = prose;
    this.shown = "";
    this.queue = "";
    this.raf = 0;
    this.live = true;
  }
  Typewriter.prototype.push = function (text) {
    if (!text) return;
    if (reduceMotion) {
      this.shown += text;
      this.paint(true);
      return;
    }
    this.queue += text;
    this.kick();
  };
  Typewriter.prototype.flush = function () {
    if (this.raf) {
      cancelAnimationFrame(this.raf);
      this.raf = 0;
    }
    this.shown += this.queue;
    this.queue = "";
    this.paint(this.live);
  };
  Typewriter.prototype.finish = function (finalText) {
    this.live = false;
    if (finalText != null) this.shown = String(finalText);
    else this.shown += this.queue;
    this.queue = "";
    if (this.raf) {
      cancelAnimationFrame(this.raf);
      this.raf = 0;
    }
    this.paint(false);
  };
  Typewriter.prototype.kick = function () {
    if (this.raf) return;
    const step = () => {
      this.raf = 0;
      if (!this.queue) {
        this.paint(true);
        return;
      }
      const n = this.queue.length > 120 ? 16 : this.queue.length > 40 ? 7 : 3;
      this.shown += this.queue.slice(0, n);
      this.queue = this.queue.slice(n);
      this.paint(true);
      this.raf = requestAnimationFrame(step);
    };
    this.raf = requestAnimationFrame(step);
  };
  Typewriter.prototype.paint = function (caret) {
    const waiting = caret && !this.queue;
    this.prose.innerHTML = md(this.shown) + (caret
      ? '<span class="chat-caret' + (waiting ? " idle" : "") + '"></span>'
      : "");
    this.prose.classList.toggle("typing", !!(caret && this.queue));
    scrollBottom();
  };

  function renderHistory(messages) {
    thread.innerHTML = "";
    if (!messages || !messages.length) {
      showEmpty(true);
      return;
    }
    showEmpty(false);
    messages.forEach((msg) => {
      if (msg.role === "user") addUser(msg.text || "");
      else {
        const box = addAssistant();
        hidePending(box);
        (msg.tools || []).forEach((t) => box.querySelector(".chat-tools").appendChild(toolCard(t)));
        box.querySelector(".chat-prose").innerHTML = md(msg.text || "");
      }
    });
    scrollBottom();
  }

  function setSession(id, title) {
    sessionId = id || "";
    const url = new URL(location.href);
    if (sessionId) url.searchParams.set("c", sessionId);
    else url.searchParams.delete("c");
    url.searchParams.delete("q");
    history.replaceState(null, "", url.pathname + url.search);
    document.querySelectorAll(".chat-item").forEach((el) => {
      el.classList.toggle("on", el.dataset.id === sessionId);
    });
    if (title) {
      const item = document.querySelector('.chat-item[data-id="' + sessionId + '"]');
      if (item) item.querySelector(".chat-item-title").textContent = title;
    }
  }

  function itemHtml(row) {
    const a = document.createElement("a");
    a.className = "chat-item" + (row.id === sessionId ? " on" : "");
    a.href = "/chat?c=" + encodeURIComponent(row.id);
    a.dataset.id = row.id;
    a.innerHTML = '<span class="chat-item-title"></span>';
    a.querySelector(".chat-item-title").textContent = row.title || "Chat";
    a.addEventListener("click", (ev) => {
      ev.preventDefault();
      if (streaming) return;
      loadSession(row.id);
    });
    return a;
  }

  async function refreshList() {
    const res = await fetch("/chat/sessions");
    if (!res.ok) return;
    const data = await res.json();
    listEl.innerHTML = "";
    (data.sessions || []).forEach((row) => listEl.appendChild(itemHtml(row)));
    if (!(data.sessions || []).length) {
      listEl.innerHTML = '<p class="chat-list-empty">No chats yet</p>';
    }
  }

  async function loadSession(id) {
    const res = await fetch("/chat/sessions/" + encodeURIComponent(id));
    if (!res.ok) {
      setSession("", "");
      renderHistory([]);
      return;
    }
    const data = await res.json();
    setSession(data.id, data.title);
    renderHistory(data.messages || []);
    refreshList();
  }

  async function loadModel() {
    try {
      const res = await fetch("/settings.json");
      if (!res.ok) return;
      const data = await res.json();
      if (data.ready && data.model) modelEl.textContent = data.model;
      else {
        modelEl.innerHTML = '<a href="/settings">Set the model in Settings</a>';
      }
    } catch (e) {}
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text || streaming) return;
    input.value = "";
    resize();
    addUser(text);
    const box = addAssistant();
    const toolsEl = box.querySelector(".chat-tools");
    const prose = box.querySelector(".chat-prose");
    const writer = new Typewriter(prose);
    setBusy(true);
    abort = new AbortController();
    const cards = {};
    try {
      const res = await fetch("/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text, session_id: sessionId }),
        signal: abort.signal,
      });
      if (!res.ok || !res.body) {
        hidePending(box);
        writer.finish("Could not reach Quinovo. Try again.");
        setBusy(false);
        return;
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      let acc = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop();
        for (const chunk of parts) {
          const line = chunk.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).join("");
          if (!line) continue;
          let evnt;
          try { evnt = JSON.parse(line); } catch (e) { continue; }
          if (evnt.type === "session") {
            setSession(evnt.id, evnt.title);
            refreshList();
          } else if (evnt.type === "text") {
            hidePending(box);
            acc += evnt.text || "";
            writer.push(evnt.text || "");
          } else if (evnt.type === "tool") {
            hidePending(box);
            writer.flush();
            const id = evnt.id || evnt.name;
            let card = cards[id];
            if (!card) {
              card = toolCard(evnt);
              cards[id] = card;
              toolsEl.appendChild(card);
            } else {
              const next = toolCard(evnt);
              card.replaceWith(next);
              cards[id] = next;
            }
            scrollBottom();
          } else if (evnt.type === "error") {
            hidePending(box);
            acc = evnt.message || "Something went wrong.";
            writer.finish(acc);
          } else if (evnt.type === "done") {
            hidePending(box);
            acc = evnt.text || acc;
            writer.finish(acc);
          }
        }
      }
      if (writer.live) writer.finish(acc);
    } catch (err) {
      hidePending(box);
      if (err.name !== "AbortError") {
        writer.finish("The run stopped unexpectedly.");
      } else {
        writer.finish(writer.shown + writer.queue);
      }
    }
    setBusy(false);
    abort = null;
    refreshList();
    input.focus();
  });

  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      form.requestSubmit();
    }
  });

  stopBtn.addEventListener("click", () => {
    if (abort) abort.abort();
  });

  newBtn.addEventListener("click", () => {
    if (streaming) return;
    setSession("", "");
    renderHistory([]);
    input.focus();
  });

  document.querySelectorAll("[data-suggest]").forEach((btn) => {
    btn.addEventListener("click", () => {
      input.value = btn.dataset.suggest;
      resize();
      form.requestSubmit();
    });
  });

  loadModel();
  refreshList();
  const q = params.get("q");
  if (sessionId) loadSession(sessionId);
  else if (q) {
    input.value = q;
    resize();
    form.requestSubmit();
  } else {
    showEmpty(true);
  }
})();
</script>
"""


def chat_html(pack_name: str = "") -> str:
    body = f"""
<div class="chat-shell">
  <aside class="chat-side">
    <button type="button" class="btn btn-ghost chat-new" id="chat-new">New chat</button>
    <nav class="chat-list" id="chat-list" aria-label="Chats"></nav>
  </aside>
  <div class="chat-stage">
    <div class="chat-scroll">
      <div class="chat-empty" id="chat-empty">
        <h1>Ask the graph</h1>
        <p>Quinovo looks things up, follows connections, and shows its work.</p>
        <div class="chat-suggests">
          <button type="button" class="chat-suggest" data-suggest="What kinds of things are in this workspace?">What kinds of things are here?</button>
          <button type="button" class="chat-suggest" data-suggest="What still needs a look?">What still needs a look?</button>
          <button type="button" class="chat-suggest" data-suggest="What did Quinovo recently notice?">What did Quinovo notice?</button>
        </div>
      </div>
      <div class="chat-thread" id="chat-thread" hidden></div>
    </div>
    <form class="chat-composer" id="chat-form">
      <label class="sr-only" for="chat-input">Message</label>
      <textarea id="chat-input" rows="1" placeholder="Ask anything about this workspace" autocomplete="off"></textarea>
      <button type="submit" class="chat-send" id="chat-send" aria-label="Send">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 19V5M5 12l7-7 7 7" stroke="currentColor" stroke-width="2" stroke-linecap="square" stroke-linejoin="miter"/>
        </svg>
      </button>
      <button type="button" class="chat-send chat-stop" id="chat-stop" hidden aria-label="Stop">
        <span class="chat-stop-sq"></span>
      </button>
      <p class="chat-model" id="chat-model">Agent</p>
    </form>
  </div>
</div>
{_CHAT_SCRIPT}
"""
    return wrap(
        "Chat",
        body,
        nav="chat",
        pack_name=pack_name,
        hide_search=True,
        body_class="chat-page",
    )
