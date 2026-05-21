/* Orchestration live updates: EventSource client with polling fallback.
   - On `snapshot` event: ignored (server-rendered initial state already in DOM).
   - On `message_added`: append a new message card and bump msg counter.
   - On `run_finished` / `done`: update status pill, stop the stream.
   - On EventSource error: switch to polling /refresh until reconnect succeeds. */
(function () {
  "use strict";

  const wrapper = document.getElementById("orch-detail");
  if (!wrapper) return;
  const slug = wrapper.dataset.slug;
  const runId = wrapper.dataset.runId;
  const initialStatus = wrapper.dataset.runStatus;
  const streamUrl = `/p/${slug}/orchestration/${runId}/stream`;
  const refreshUrl = `/p/${slug}/orchestration/${runId}/refresh`;
  const indicator = document.getElementById("sse-indicator");

  let es = null;
  let pollHandle = null;
  let lastMsgCount = parseInt(wrapper.dataset.msgCount || "0", 10);
  let lastNodeCount = parseInt(wrapper.dataset.nodeCount || "0", 10);
  let normalClose = false;

  function setIndicator(state) {
    if (!indicator) return;
    indicator.className = "sse-indicator " + state;
    indicator.textContent = state.toUpperCase();
  }

  function setStatus(status) {
    const el = document.getElementById("run-status");
    if (el) {
      el.textContent = status;
      el.className = "font-mono status-pill status-" + status;
    }
  }

  function bumpCounter(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = String(value);
  }

  function appendMessage(msg) {
    const list = document.getElementById("messages-list");
    if (!list) return;
    const card = document.createElement("div");
    card.className = "rounded p-3 msg-card";
    card.style.background = "var(--bg-elevated)";
    card.style.border = "1px solid var(--border-subtle)";
    if (msg.node_id) card.dataset.nodeId = msg.node_id;
    card.innerHTML = `
      <div class="text-xs mb-1" style="color: var(--text-faint);">
        <span class="font-mono">${msg.author || ""}</span> ·
        <span class="font-mono">${msg.kind || ""}</span> ·
        ${msg.ts || ""}
      </div>
      <pre class="whitespace-pre-wrap text-sm font-mono" style="color: var(--text-body);"></pre>`;
    card.querySelector("pre").textContent = msg.text || "";
    list.appendChild(card);
    lastMsgCount += 1;
    bumpCounter("msg-count", lastMsgCount);
  }

  function handleEvent(eventType, data) {
    switch (eventType) {
      case "snapshot":
        return;
      case "message_added":
        appendMessage({
          author: data.author || "",
          kind: data.kind || "",
          ts: data.ts || "",
          node_id: data.node_id || "",
          text: data.text || "",
        });
        return;
      case "node_created":
      case "node_status_changed":
        lastNodeCount = data.node_count || lastNodeCount + 1;
        bumpCounter("node-count", lastNodeCount);
        return;
      case "run_finished":
      case "run_resumed":
        if (data.status) setStatus(data.status);
        return;
      case "done":
        normalClose = true;
        setStatus(data.status || "completed");
        setIndicator("done");
        if (es) { es.close(); es = null; }
        return;
      default:
        return;
    }
  }

  function startStream() {
    try {
      es = new EventSource(streamUrl);
    } catch (e) {
      console.warn("EventSource init failed", e);
      startPolling();
      return;
    }
    es.onopen = () => setIndicator("connected");
    // No `onmessage` handler: our server always sets an `event:` field via
    // sse_starlette, so events arrive on named listeners below.
    const named = ["snapshot", "message_added", "node_created", "node_status_changed",
                   "run_finished", "run_resumed", "run_started", "done", "heartbeat"];
    named.forEach((name) => {
      es.addEventListener(name, (e) => {
        let payload = {};
        try { payload = JSON.parse(e.data || "{}"); } catch {}
        handleEvent(name, payload);
      });
    });
    es.onerror = () => {
      if (normalClose) return;
      setIndicator("disconnected");
      if (es) { es.close(); es = null; }
      startPolling();
      setTimeout(() => {
        if (!normalClose && !es) {
          stopPolling();
          startStream();
        }
      }, 10000);
    };
  }

  async function pollOnce() {
    try {
      const r = await fetch(refreshUrl);
      if (!r.ok) return;
      const data = await r.json();
      setStatus(data.status);
      bumpCounter("node-count", data.node_count);
      bumpCounter("msg-count", data.message_count);
      if (data.status !== "running") {
        normalClose = true;
        stopPolling();
        setIndicator("connected");
      }
    } catch (e) {}
  }

  function startPolling() {
    if (pollHandle) return;
    setIndicator("polling");
    pollOnce();
    pollHandle = setInterval(pollOnce, 3000);
  }

  function stopPolling() {
    if (pollHandle) {
      clearInterval(pollHandle);
      pollHandle = null;
    }
  }

  // create_run always inserts status='running'; non-running means terminal.
  if (initialStatus === "running") {
    startStream();
  } else {
    setIndicator("done");
  }

  window.addEventListener("beforeunload", () => {
    if (es) es.close();
    stopPolling();
  });
})();
