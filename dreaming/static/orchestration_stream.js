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

  function chipStateClass(status) {
    if (status === "running") return "state-active";
    if (status === "completed") return "state-done";
    if (status === "failed" || status === "cancelled") return "state-rejected";
    return "state-idle";
  }

  function ensureSwimCell(stageId) {
    // Locate the swim-cell for this stage, or fall back to creating one
    // (rare — happens if a node arrives for a stage that the page hasn't
    // server-rendered yet, e.g. when stages are created live).
    if (!stageId) return null;
    let cell = document.querySelector('.swim-cell[data-stage-id="' + stageId + '"]');
    if (cell) {
      // Drop any "no agents yet" placeholder so the new chip can land alongside.
      const placeholder = cell.querySelector("span.text-xs.muted");
      if (placeholder && !placeholder.classList.contains("chip-action")) placeholder.remove();
    }
    return cell;
  }

  function addNodeChip(data) {
    const cell = ensureSwimCell(data.stage_id);
    if (!cell) return;
    // Don't duplicate if the chip is already there (server-render + late event).
    if (cell.querySelector('.activity-chip[data-node-id="' + data.node_id + '"]')) return;
    const chip = document.createElement("div");
    chip.className = "activity-chip " + chipStateClass(data.status);
    chip.dataset.nodeId = data.node_id;
    const action = document.createElement("span");
    action.className = "chip-action";
    action.textContent = data.agent_name || "agent";
    chip.appendChild(action);
    const meta = document.createElement("span");
    meta.className = "text-xs muted";
    meta.textContent = (data.role || "") + " · " + (data.status || "");
    chip.appendChild(meta);
    // Bump the swim-row's agent counter ("N agents") if it's there.
    const row = cell.closest(".swim-row");
    if (row) {
      const counter = row.querySelector(".swim-agent-role");
      if (counter) {
        const n = row.querySelectorAll(".activity-chip").length + 1;
        counter.textContent = n + " agent" + (n === 1 ? "" : "s");
      }
    }
    // Wire the click-to-filter handler that the inline script in the template
    // attached to the server-rendered chips.
    chip.addEventListener("click", () => {
      const list = document.getElementById("messages-list");
      if (!list) return;
      const bar = document.getElementById("msg-filter-bar");
      const label = document.getElementById("msg-filter-label");
      const already = chip.classList.contains("selected");
      document.querySelectorAll(".activity-chip.selected").forEach(c => c.classList.remove("selected"));
      if (already) {
        list.querySelectorAll(".msg-card").forEach(c => c.style.display = "");
        if (bar) bar.classList.add("hidden");
        return;
      }
      chip.classList.add("selected");
      const nid = chip.dataset.nodeId;
      list.querySelectorAll(".msg-card").forEach(c => {
        c.style.display = (c.dataset.nodeId === nid) ? "" : "none";
      });
      if (label) label.textContent = (data.agent_name || nid.slice(0, 8));
      if (bar) bar.classList.remove("hidden");
    });
    cell.appendChild(chip);
  }

  function updateNodeChipStatus(nodeId, newStatus) {
    const chip = document.querySelector('.activity-chip[data-node-id="' + nodeId + '"]');
    if (!chip) return;
    chip.classList.remove("state-active", "state-done", "state-rejected", "state-idle");
    chip.classList.add(chipStateClass(newStatus));
    const meta = chip.querySelector(".text-xs.muted");
    if (meta) {
      const role = meta.textContent.split("·")[0].trim();
      meta.textContent = role + " · " + newStatus;
    }
  }

  function updateStageStatus(stageId, newStatus) {
    const tile = document.querySelector('.stage-tile[data-stage-id="' + stageId + '"]');
    if (!tile) return;
    tile.classList.remove("running", "completed", "failed", "cancelled", "pending");
    tile.classList.add(newStatus);
    const pill = tile.querySelector(".status-pill");
    if (pill) {
      pill.className = "status-pill status-" + newStatus;
      pill.textContent = newStatus;
    }
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
        addNodeChip(data);
        lastNodeCount += 1;
        bumpCounter("node-count", lastNodeCount);
        return;
      case "node_status_changed":
        if (data.node_id && data.status) updateNodeChipStatus(data.node_id, data.status);
        return;
      case "stage_status_changed":
        if (data.stage_id && data.status) updateStageStatus(data.stage_id, data.status);
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
