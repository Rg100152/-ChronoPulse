/* ==========================================================================
   ChronoPulse — Live Chronograph Engine
   Timer state survives refreshes via localStorage. All data is persisted
   through the Flask JSON API.  By Raj Gautam
   ========================================================================== */

(function () {
  "use strict";

  const STORAGE_KEY = "chronopulse.timer.v1";
  const $ = (id) => document.getElementById(id);

  const el = {
    devPill: $("devPillBtn"),
    toastHost: $("toastHost"),
    dialTime: $("dialTime"),
    dialStatus: $("dialStatus"),
    dialMeta: $("dialMeta"),
    dialHint: $("dialHint"),
    dialTicks: $("dialTicks"),
    secondsRing: $("secondsRing"),
    minutesRing: $("minutesRing"),
    needle: $("dialNeedle"),
    liveDot: $("liveDot"),
    timerProject: $("timerProject"),
    timerTask: $("timerTask"),
    timerBillable: $("timerBillable"),
    startBtn: $("startBtn"),
    stopBtn: $("stopBtn"),
    ratePreview: $("ratePreview"),
    earningPreview: $("earningPreview"),
    statePreview: $("statePreview"),
    kpiToday: $("kpiToday"),
    kpiWeek: $("kpiWeek"),
    kpiBillable: $("kpiBillable"),
    kpiTop: $("kpiTop"),
    weekChart: $("weekChart"),
    chartUpdated: $("chartUpdated"),
    recentLogs: $("recentLogs"),
    manualEntryBtn: $("manualEntryBtn"),
    manualModal: $("manualModal"),
    manualForm: $("manualForm"),
    manualDate: $("manualDate"),
    manualProject: $("manualProject"),
    manualTask: $("manualTask"),
    manualHours: $("manualHours"),
    manualBillable: $("manualBillable"),
    manualSubmit: $("manualSubmit"),
  };

  let state = loadState();
  let tickHandle = null;
  const ringLengths = {};

  /* ---------------------------- utilities ------------------------------- */
  function loadState() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
      if (saved && saved.running && saved.startedAt) return saved;
    } catch (_) { /* ignore corrupt state */ }
    return {
      running: false, startedAt: null, accumulated: 0,
      projectId: "", task: "", billable: true, rate: 0,
    };
  }

  function saveState() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function clearState() {
    localStorage.removeItem(STORAGE_KEY);
    state = {
      running: false, startedAt: null, accumulated: 0,
      projectId: "", task: "", billable: true, rate: 0,
    };
  }

  function elapsedMs() {
    return (state.accumulated || 0) + (state.running ? Date.now() - state.startedAt : 0);
  }

  function formatHMS(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
  }

  function localISO(d) {
    return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, "0"),
      String(d.getDate()).padStart(2, "0")].join("-");
  }

  function timeString(d) {
    return [String(d.getHours()).padStart(2, "0"),
      String(d.getMinutes()).padStart(2, "0"),
      String(d.getSeconds()).padStart(2, "0")].join(":");
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function inr(value) {
    return "₹" + Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  }

  function toast(title, message, error) {
    if (!el.toastHost) return;
    const node = document.createElement("div");
    node.className = "toast" + (error ? " error" : "");
    node.innerHTML = `<strong>${escapeHtml(title)}</strong>${escapeHtml(message)}`;
    el.toastHost.appendChild(node);
    setTimeout(() => node.remove(), 5000);
  }

  async function postJSON(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    let data;
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || "Request failed. Please try again.");
    }
    return data;
  }

  /* --------------------------- dialog plumbing -------------------------- */
  function initDialogs() {
    document.querySelectorAll("dialog").forEach((dialog) => {
      dialog.addEventListener("click", (event) => {
        if (event.target === dialog) dialog.close();
      });
      dialog.querySelectorAll("[data-close-dialog]").forEach((btn) => {
        btn.addEventListener("click", () => dialog.close());
      });
    });
    if (el.devPill && $("devModal")) {
      el.devPill.addEventListener("click", () => $("devModal").showModal());
    }
  }

  /* ----------------------------- dial setup ----------------------------- */
  function setupDial() {
    if (!el.dialTicks) return;

    let ticks = "";
    for (let i = 0; i < 60; i++) {
      const angle = (i * 6 - 90) * Math.PI / 180;
      const major = i % 5 === 0;
      const inner = major ? 140 : 143;
      const outer = major ? 149 : 147;
      const x1 = (160 + inner * Math.cos(angle)).toFixed(2);
      const y1 = (160 + inner * Math.sin(angle)).toFixed(2);
      const x2 = (160 + outer * Math.cos(angle)).toFixed(2);
      const y2 = (160 + outer * Math.sin(angle)).toFixed(2);
      ticks += `<line class="${major ? "dial-tick-major" : "dial-tick"}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
    }
    el.dialTicks.innerHTML = ticks;

    [el.secondsRing, el.minutesRing].forEach((ring) => {
      if (!ring) return;
      const radius = parseFloat(ring.getAttribute("r"));
      ringLengths[ring.id] = 2 * Math.PI * radius;
      ring.style.strokeDasharray = String(ringLengths[ring.id]);
      ring.style.strokeDashoffset = String(ringLengths[ring.id]);
    });
  }

  function selectedRate() {
    if (state.running) return Number(state.rate || 0);
    const option = el.timerProject && el.timerProject.selectedOptions[0];
    return option ? Number(option.dataset.rate || 0) : 0;
  }

  function renderTimer() {
    if (!el.dialTime) return;
    const ms = elapsedMs();
    const seconds = ms / 1000;
    const secFraction = (seconds % 60) / 60;
    const minFraction = (seconds % 3600) / 3600;

    el.dialTime.textContent = formatHMS(ms);

    if (el.secondsRing && ringLengths.secondsRing) {
      el.secondsRing.style.strokeDashoffset =
        String(ringLengths.secondsRing * (1 - secFraction));
    }
    if (el.minutesRing && ringLengths.minutesRing) {
      el.minutesRing.style.strokeDashoffset =
        String(ringLengths.minutesRing * (1 - minFraction));
    }
    if (el.needle) {
      el.needle.setAttribute("transform", `rotate(${(secFraction * 360).toFixed(2)} 160 160)`);
    }

    const rate = selectedRate();
    const projected = rate * ms / 3600000;
    if (el.ratePreview) el.ratePreview.textContent = inr(rate) + "/h";
    if (el.earningPreview) el.earningPreview.textContent = inr(projected);

    const running = state.running;
    if (el.dialStatus) {
      el.dialStatus.textContent = running ? "● LIVE SESSION" : "● STANDBY";
      el.dialStatus.classList.toggle("is-live", running);
    }
    if (el.liveDot) el.liveDot.classList.toggle("is-live", running);
    if (el.dialMeta) {
      el.dialMeta.textContent = running
        ? (state.task || "Focus session").slice(0, 46)
        : "Ready when you are";
    }
    if (el.statePreview) el.statePreview.textContent = running ? "Running" : "Idle";
    if (el.startBtn) el.startBtn.disabled = running;
    if (el.stopBtn) el.stopBtn.disabled = !running || seconds < 1;
    if (el.dialHint) {
      el.dialHint.textContent = running
        ? "Session is saved locally — refreshing this page will not stop the clock."
        : "Tip: the timer keeps running even if you refresh this page.";
    }
  }

  function restoreTimerFields() {
    if (!state.running) return;
    if (el.timerProject && state.projectId) el.timerProject.value = state.projectId;
    if (el.timerTask && state.task) el.timerTask.value = state.task;
    if (el.timerBillable) el.timerBillable.checked = !!state.billable;
  }

  function startTimer() {
    if (state.running || !el.timerProject) return;
    const option = el.timerProject.selectedOptions[0];
    state = {
      running: true,
      startedAt: Date.now(),
      accumulated: 0,
      projectId: el.timerProject.value,
      task: (el.timerTask && el.timerTask.value.trim()) || "Untitled focus session",
      billable: !!(el.timerBillable && el.timerBillable.checked),
      rate: option ? Number(option.dataset.rate || 0) : 0,
      projectName: option ? option.textContent.trim() : "",
    };
    saveState();
    renderTimer();
    toast("Timer engaged", "Chronograph is live — log the session when you're done.");
  }

  async function stopTimer() {
    if (!state.running) return;
    const seconds = Math.round(elapsedMs() / 1000);
    if (seconds < 1) {
      toast("Too short", "Log at least one second before stopping.", true);
      return;
    }
    const started = new Date(state.startedAt);
    const ended = new Date(state.startedAt + seconds * 1000);
    const payload = {
      project_id: state.projectId,
      task_description: state.task,
      log_date: localISO(started),
      start_time: timeString(started),
      end_time: timeString(ended),
      duration_seconds: seconds,
      billable: state.billable ? 1 : 0,
    };
    try {
      const result = await postJSON("/api/log", payload);
      clearState();
      if (el.timerTask) el.timerTask.value = "";
      renderTimer();
      refreshDashboard();
      toast("Session logged", `${formatHMS(seconds * 1000)} saved · ${inr(result.earnings)} billed.`);
    } catch (error) {
      toast("Could not log session", error.message, true);
    }
  }

  /* --------------------------- dashboard data --------------------------- */
  function renderChart(chart) {
    if (!el.weekChart || !Array.isArray(chart)) return;
    const max = Math.max(1, ...chart.map((d) => Number(d.hours) || 0));
    el.weekChart.innerHTML = chart.map((d) => {
      const hours = Number(d.hours) || 0;
      const height = hours ? Math.max(6, (hours / max) * 100) : 2;
      return `
        <div class="chart-day ${d.is_today ? "is-today" : ""}"
             title="${escapeHtml(d.date)} · ${hours.toFixed(2)}h · ${inr(d.earnings)}">
          <span class="heat heat-${Number(d.heat) || 0}"></span>
          <div class="bar-track"><div class="bar" style="height:${height.toFixed(1)}%"></div></div>
          <strong class="bar-value">${hours.toFixed(1)}h</strong>
          <span class="day-label">${escapeHtml(String(d.day).toUpperCase())}</span>
          <span class="day-num">${String(d.day_num).padStart(2, "0")}</span>
        </div>`;
    }).join("");
  }

  function renderRecentLogs(logs) {
    if (!el.recentLogs || !Array.isArray(logs)) return;
    if (!logs.length) {
      el.recentLogs.innerHTML = '<tr><td colspan="7" class="empty-cell">No sessions yet — engage the timer to start your ledger.</td></tr>';
      return;
    }
    el.recentLogs.innerHTML = logs.map((log) => `
      <tr>
        <td class="mono">${escapeHtml(log.log_date)}</td>
        <td><span class="project-dot" style="--dot:${escapeHtml(log.color_tag)}"></span><strong>${escapeHtml(log.project_name)}</strong><small>${escapeHtml(log.client_name)}</small></td>
        <td>${escapeHtml(log.task_description)}</td>
        <td class="mono">${escapeHtml(log.start_time || "—")}–${escapeHtml(log.end_time || "—")}</td>
        <td class="mono">${Number(log.hours).toFixed(2)}</td>
        <td><span class="badge ${log.billable ? "badge-yes" : "badge-no"}">${log.billable ? "BILLABLE" : "INTERNAL"}</span></td>
        <td class="mono earnings">${inr(log.earnings)}</td>
      </tr>`).join("");
  }

  function applyDashboard(data) {
    if (data.stats) {
      if (el.kpiToday) el.kpiToday.innerHTML = Number(data.stats.today_hours).toFixed(2) + "<small>h</small>";
      if (el.kpiWeek) el.kpiWeek.innerHTML = Number(data.stats.week_hours).toFixed(2) + "<small>h</small>";
      if (el.kpiBillable) el.kpiBillable.textContent = inr(data.stats.billable_amount);
      if (el.kpiTop) el.kpiTop.textContent = data.stats.top_project || "No data yet";
    }
    renderChart(data.chart);
    renderRecentLogs(data.recent_logs);
    if (el.chartUpdated && data.generated_at) {
      el.chartUpdated.textContent = "Updated " + data.generated_at;
    }
  }

  async function refreshDashboard() {
    try {
      const response = await fetch("/api/dashboard", { cache: "no-store" });
      if (!response.ok) return;
      applyDashboard(await response.json());
    } catch (_) { /* offline — keep the last rendered values */ }
  }

  /* --------------------------- manual entry ----------------------------- */
  function initManualEntry() {
    if (!el.manualModal) return;
    if (el.manualDate) el.manualDate.value = localISO(new Date());

    if (el.manualEntryBtn) {
      el.manualEntryBtn.addEventListener("click", () => el.manualModal.showModal());
    }
    if (!el.manualForm) return;

    el.manualForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const hours = Number(el.manualHours.value);
      if (!hours || hours <= 0) {
        toast("Invalid hours", "Enter a duration greater than zero.", true);
        return;
      }
      if (el.manualSubmit) el.manualSubmit.disabled = true;
      try {
        await postJSON("/api/log", {
          project_id: el.manualProject.value,
          task_description: el.manualTask.value.trim(),
          log_date: el.manualDate.value,
          duration_seconds: Math.round(hours * 3600),
          billable: el.manualBillable.checked ? 1 : 0,
        });
        el.manualModal.close();
        el.manualForm.reset();
        el.manualDate.value = localISO(new Date());
        refreshDashboard();
        toast("Session logged", `${hours.toFixed(2)}h added to your timesheet.`);
      } catch (error) {
        toast("Could not save entry", error.message, true);
      } finally {
        if (el.manualSubmit) el.manualSubmit.disabled = false;
      }
    });
  }

  /* ------------------------------- boot --------------------------------- */
  function boot() {
    initDialogs();
    setupDial();
    restoreTimerFields();
    renderTimer();

    if (el.startBtn) el.startBtn.addEventListener("click", startTimer);
    if (el.stopBtn) el.stopBtn.addEventListener("click", stopTimer);
    if (el.timerProject || el.timerTask || el.timerBillable) {
      renderTimer();
      [el.timerProject, el.timerTask, el.timerBillable].forEach((node) => {
        if (node) node.addEventListener("change", renderTimer);
      });
      if (el.timerTask) el.timerTask.addEventListener("input", renderTimer);
    }

    tickHandle = setInterval(renderTimer, 200);
    initManualEntry();
    refreshDashboard();

    if (document.body.dataset.print === "1") {
      window.addEventListener("load", () => setTimeout(() => window.print(), 400));
    }

    window.addEventListener("pagehide", () => clearInterval(tickHandle));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
