const tokenInput = document.getElementById("jwtToken");
const saveTokenBtn = document.getElementById("saveTokenBtn");
const refreshLogsBtn = document.getElementById("refreshLogsBtn");
const refreshEventsBtn = document.getElementById("refreshEventsBtn");
const applyFiltersBtn = document.getElementById("applyFiltersBtn");
const applyLogFiltersBtn = document.getElementById("applyLogFiltersBtn");
const refreshQueueBtn = document.getElementById("refreshQueueBtn");
const retryQueueBtn = document.getElementById("retryQueueBtn");
const refreshAssignmentsBtn = document.getElementById("refreshAssignmentsBtn");
const filterService = document.getElementById("filterService");
const filterStatus = document.getElementById("filterStatus");
const windowMinutes = document.getElementById("windowMinutes");
const logEndpointFilter = document.getElementById("logEndpointFilter");
const logErrorFilter = document.getElementById("logErrorFilter");

const metricRequests = document.getElementById("metricRequests");
const metricErrors = document.getElementById("metricErrors");
const metricP95 = document.getElementById("metricP95");
const metricAvg = document.getElementById("metricAvg");
const wsaaTokenStatus = document.getElementById("wsaaTokenStatus");
const wsaaTokenExpiry = document.getElementById("wsaaTokenExpiry");
const wspciTokenStatus = document.getElementById("wspciTokenStatus");
const wspciTokenExpiry = document.getElementById("wspciTokenExpiry");
const logsTable = document.getElementById("logsTable");
const eventsTable = document.getElementById("eventsTable");
const errorsList = document.getElementById("errorsList");
const alertsList = document.getElementById("alertsList");
const operationsJson = document.getElementById("operationsJson");
const trafficSparkline = document.getElementById("trafficSparkline");
const errorSparkline = document.getElementById("errorSparkline");
const queueSummary = document.getElementById("queueSummary");
const queueTable = document.getElementById("queueTable");
const assignmentsSummary = document.getElementById("assignmentsSummary");
const assignmentsTable = document.getElementById("assignmentsTable");
const posList = document.getElementById("posList");
const tabButtons = document.querySelectorAll(".tab-btn");
const tabPanels = document.querySelectorAll(".tab-panel");
const refreshPosParamsBtn = document.getElementById("refreshPosParamsBtn");
const posParamsCuit = document.getElementById("posParamsCuit");
const posParamsJson = document.getElementById("posParamsJson");
const refreshWsfeParamsBtn = document.getElementById("refreshWsfeParamsBtn");
const paramsCuit = document.getElementById("paramsCuit");
const paramsMonId = document.getElementById("paramsMonId");
const paramsFchCotiz = document.getElementById("paramsFchCotiz");
const paramsPtoVta = document.getElementById("paramsPtoVta");
const paramsCbteTipo = document.getElementById("paramsCbteTipo");
const paramsCbteNro = document.getElementById("paramsCbteNro");
const wsfeParamsJson = document.getElementById("wsfeParamsJson");

const LS_TOKEN_KEY = "afrelay_monitor_jwt";

function getToken() {
  return localStorage.getItem(LS_TOKEN_KEY) || "";
}

function saveToken() {
  localStorage.setItem(LS_TOKEN_KEY, tokenInput.value.trim());
}

function buildQuery(params) {
  const q = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`);
  return q.length ? `?${q.join("&")}` : "";
}

function getFilters() {
  return {
    service: filterService.value,
    status: filterStatus.value,
    window: Number(windowMinutes.value || "60"),
    logEndpoint: logEndpointFilter.value.trim(),
    logErrorType: logErrorFilter.value.trim(),
  };
}

async function apiGet(path) {
  const token = getToken();
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await fetch(path, { headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${response.statusText} ${text}`);
  }
  return response.json();
}

async function apiPost(path) {
  return apiPostJson(path, {});
}

async function apiPostJson(path, payload) {
  const token = getToken();
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const response = await fetch(path, { method: "POST", headers, body: JSON.stringify(payload || {}) });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${response.statusText} ${text}`);
  }
  return response.json();
}

function fmtDate(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

function setTokenState(elementStatus, elementExpiry, data) {
  if (!data) {
    elementStatus.textContent = "-";
    elementExpiry.textContent = "-";
    return;
  }
  elementStatus.textContent = data.valid ? "VALID" : "INVALID";
  elementStatus.className = `metric ${data.valid ? "status-ok" : "status-error"}`;
  elementExpiry.textContent = data.expires_at ? `exp ${fmtDate(data.expires_at)}` : (data.last_error || "-");
}

function renderLogs(items) {
  logsTable.innerHTML = "";
  items.slice(0, 20).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${fmtDate(row.timestamp)}</td>
      <td>${row.path}</td>
      <td class="${row.ok ? "status-ok" : "status-error"}">${row.status_code}</td>
      <td>${row.duration_ms}</td>
      <td>${row.service || "-"}</td>
      <td>${row.error_type || "-"}</td>
      <td>${row.trace_id || "-"}</td>
    `;
    logsTable.appendChild(tr);
  });
}

function renderEvents(items) {
  eventsTable.innerHTML = "";
  items.slice(0, 20).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${fmtDate(row.timestamp)}</td>
      <td>${row.event_type}</td>
      <td class="${row.status === "success" ? "status-ok" : "status-error"}">${row.status}</td>
      <td>${row.service}</td>
      <td>${row.error_type || "-"}</td>
      <td>${row.trace_id || "-"}</td>
    `;
    eventsTable.appendChild(tr);
  });
}

function renderErrors(items) {
  errorsList.innerHTML = "";
  if (!items.length) {
    errorsList.innerHTML = "<li>No errors in selected window.</li>";
    return;
  }
  items.slice(0, 8).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = `${item.key} | count=${item.count} | last=${fmtDate(item.last_seen)}`;
    errorsList.appendChild(li);
  });
}

function renderAlerts(items) {
  alertsList.innerHTML = "";
  if (!items.length) {
    alertsList.innerHTML = "<li>No active alerts.</li>";
    return;
  }
  items.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = `[${item.severity}] ${item.title}`;
    alertsList.appendChild(li);
  });
}

function renderQueue(data) {
  const summary = data.summary || {};
  queueSummary.textContent =
    `pending=${summary.pending || 0} | retrying=${summary.retrying || 0} | ` +
    `processing=${summary.processing || 0} | done=${summary.done || 0} | failed=${summary.failed || 0}`;

  queueTable.innerHTML = "";
  (data.items || []).slice(0, 30).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.id}</td>
      <td>${row.job_type}</td>
      <td class="${row.status === "done" ? "status-ok" : (row.status === "failed" ? "status-error" : "")}">${row.status}</td>
      <td>${row.attempts}</td>
      <td>${fmtDate(row.next_retry_at)}</td>
      <td>${row.last_error || "-"}</td>
    `;
    queueTable.appendChild(tr);
  });
}

function renderAssignments(data) {
  const items = data.items || [];
  assignmentsSummary.textContent = `rows=${data.count || items.length}`;
  assignmentsTable.innerHTML = "";
  items.slice(0, 200).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.periodo}</td>
      <td>${row.orden}</td>
      <td>${row.cuit}</td>
      <td>${row.pto_vta}</td>
      <td>${row.cbte_tipo}</td>
      <td>${row.caea_code || "-"}</td>
      <td>${row.cbte_from}-${row.cbte_to}</td>
      <td>${row.invoices_count}</td>
      <td class="status-ok">${row.informed_count}</td>
      <td>${row.pending_inform_count}</td>
      <td class="${row.error_count > 0 ? "status-error" : ""}">${row.error_count}</td>
    `;
    assignmentsTable.appendChild(tr);
  });
}

function renderPosList(assignments) {
  const byPos = new Map();
  assignments.forEach((row) => {
    const key = String(row.pto_vta);
    if (!byPos.has(key)) {
      byPos.set(key, { total: 0, types: new Set() });
    }
    const entry = byPos.get(key);
    entry.total += Number(row.invoices_count || 0);
    entry.types.add(String(row.cbte_tipo));
  });

  posList.innerHTML = "";
  if (!byPos.size) {
    posList.innerHTML = "<li>No POS with CAEA movements yet.</li>";
    return;
  }

  Array.from(byPos.entries())
    .sort((a, b) => Number(a[0]) - Number(b[0]))
    .forEach(([pos, entry]) => {
      const li = document.createElement("li");
      const types = Array.from(entry.types).sort((a, b) => Number(a) - Number(b)).join(", ");
      li.textContent = `POS ${pos} | types=${types} | invoices=${entry.total}`;
      posList.appendChild(li);
    });
}

function activateTab(tabName) {
  tabButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  tabPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.panel === tabName);
  });
}

async function refreshWsfePosParams() {
  const cuit = Number((posParamsCuit.value || "").trim());
  if (!cuit) {
    posParamsJson.textContent = "Please enter a valid CUIT.";
    return;
  }
  posParamsJson.textContent = "Loading...";
  try {
    const puntosVenta = await apiPostJson("/wsfe/params/puntos-venta", { Cuit: cuit });
    posParamsJson.textContent = JSON.stringify({ cuit, puntos_venta: puntosVenta }, null, 2);
  } catch (error) {
    posParamsJson.textContent = `WSFE POS refresh failed: ${error.message}`;
  }
}

async function refreshWsfeParamsSnapshot() {
  const cuit = Number((paramsCuit.value || "").trim());
  if (!cuit) {
    wsfeParamsJson.textContent = "Please enter a valid CUIT.";
    return;
  }
  const monId = (paramsMonId.value || "USD").trim() || "USD";
  const fchCotiz = (paramsFchCotiz.value || "").trim();
  const ptoVta = Number((paramsPtoVta.value || "").trim() || "0");
  const cbteTipo = Number((paramsCbteTipo.value || "").trim() || "0");
  const cbteNro = Number((paramsCbteNro.value || "").trim() || "0");

  wsfeParamsJson.textContent = "Loading...";
  try {
    const [cotizacion, concepto, opcional, paises, actividades, puntosVenta, lastAuthorized] = await Promise.all([
      apiPostJson("/wsfe/params/cotizacion", { Cuit: cuit, MonId: monId, ...(fchCotiz ? { FchCotiz: fchCotiz } : {}) }),
      apiPostJson("/wsfe/params/types-concepto", { Cuit: cuit }),
      apiPostJson("/wsfe/params/types-opcional", { Cuit: cuit }),
      apiPostJson("/wsfe/params/types-paises", { Cuit: cuit }),
      apiPostJson("/wsfe/params/actividades", { Cuit: cuit }),
      apiPostJson("/wsfe/params/puntos-venta", { Cuit: cuit }),
      ptoVta && cbteTipo
        ? apiPostJson("/wsfe/invoices/last-authorized", { Cuit: cuit, PtoVta: ptoVta, CbteTipo: cbteTipo })
        : Promise.resolve({ status: "skipped", message: "Set PtoVta and CbteTipo to fetch last authorized." }),
    ]);

    let invoiceQuery = { status: "skipped", message: "Set CbteNro to query specific invoice." };
    if (ptoVta && cbteTipo && cbteNro) {
      invoiceQuery = await apiPostJson("/wsfe/invoices/query", {
        Cuit: cuit,
        PtoVta: ptoVta,
        CbteTipo: cbteTipo,
        CbteNro: cbteNro,
      });
    }

    wsfeParamsJson.textContent = JSON.stringify(
      {
        cuit,
        puntos_venta: puntosVenta,
        last_authorized: lastAuthorized,
        invoice_query: invoiceQuery,
        cotizacion,
        types_concepto: concepto,
        types_opcional: opcional,
        types_paises: paises,
        actividades,
      },
      null,
      2
    );
  } catch (error) {
    wsfeParamsJson.textContent = `WSFE params refresh failed: ${error.message}`;
  }
}

function drawSparkline(container, values, lineColor, fillColor) {
  const width = 520;
  const height = 110;
  const pad = 8;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const spread = max - min || 1;
  const step = values.length > 1 ? (width - pad * 2) / (values.length - 1) : 0;

  const points = values.map((value, i) => {
    const x = pad + i * step;
    const y = height - pad - ((value - min) / spread) * (height - pad * 2);
    return `${x},${y}`;
  });
  const baseline = height - pad;
  const areaPoints = [`${pad},${baseline}`, ...points, `${width - pad},${baseline}`].join(" ");

  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="trend sparkline">
      <polyline points="${areaPoints}" fill="${fillColor}" stroke="none"></polyline>
      <polyline points="${points.join(" ")}" fill="none" stroke="${lineColor}" stroke-width="2.5" stroke-linecap="round"></polyline>
    </svg>
  `;
}

function buildSeries(logItems, selectedWindowMinutes) {
  const now = Date.now();
  const windowMs = selectedWindowMinutes * 60 * 1000;
  const bucketMinutes = selectedWindowMinutes <= 180 ? 1 : Math.ceil(selectedWindowMinutes / 120);
  const bucketMs = bucketMinutes * 60 * 1000;
  const bucketsCount = Math.ceil(windowMs / bucketMs);

  const requests = Array.from({ length: bucketsCount }, () => 0);
  const errors = Array.from({ length: bucketsCount }, () => 0);

  const start = now - windowMs;
  logItems.forEach((row) => {
    const ts = new Date(row.timestamp).getTime();
    if (Number.isNaN(ts) || ts < start || ts > now) return;
    const idx = Math.min(Math.floor((ts - start) / bucketMs), bucketsCount - 1);
    requests[idx] += 1;
    if (!row.ok) errors[idx] += 1;
  });

  return { requests, errors };
}

async function refreshAll() {
  const filters = getFilters();
  try {
    const logsQuery = buildQuery({
      page: 1,
      page_size: 300,
      service: filters.service,
      status: filters.status,
      endpoint: filters.logEndpoint,
      error_type: filters.logErrorType,
    });
    const eventsQuery = buildQuery({
      page: 1,
      page_size: 200,
      service: filters.service,
      status: filters.status === "ok" ? "success" : (filters.status || ""),
    });
    const timedQuery = buildQuery({ window_minutes: filters.window });

    const [summary, logs, errors, tokens, ops, alerts, events, queue, assignments] = await Promise.all([
      apiGet(`/ui/metrics/summary${timedQuery}`),
      apiGet(`/ui/logs${logsQuery}`),
      apiGet(`/ui/errors${buildQuery({ window_minutes: filters.window, group_by: "error_type" })}`),
      apiGet("/ui/tokens/status"),
      apiGet(`/ui/operations/summary${timedQuery}`),
      apiGet("/ui/alerts"),
      apiGet(`/ui/events${eventsQuery}`),
      apiGet("/ui/caea/queue?limit=200"),
      apiGet("/ui/caea/assignments?limit=200"),
    ]);

    metricRequests.textContent = summary.total_requests;
    metricErrors.textContent = summary.error_count;
    metricP95.textContent = `${summary.p95_ms} ms`;
    metricAvg.textContent = `${summary.avg_ms} ms`;
    setTokenState(wsaaTokenStatus, wsaaTokenExpiry, tokens.wsaa);
    setTokenState(wspciTokenStatus, wspciTokenExpiry, tokens.wspci);
    renderLogs(logs.items || []);
    renderEvents(events.items || []);
    renderErrors(errors.items || []);
    renderAlerts(alerts.active || []);
    renderQueue(queue);
    renderAssignments(assignments);
    renderPosList(assignments.items || []);
    operationsJson.textContent = JSON.stringify(ops, null, 2);

    const series = buildSeries(logs.items || [], filters.window);
    drawSparkline(trafficSparkline, series.requests, "#2f6f5e", "rgba(47,111,94,0.14)");
    drawSparkline(errorSparkline, series.errors, "#b22f25", "rgba(178,47,37,0.14)");
  } catch (error) {
    console.error(error);
    operationsJson.textContent = `Monitor refresh failed: ${error.message}`;
  }
}

saveTokenBtn.addEventListener("click", () => {
  saveToken();
  refreshAll();
});

applyFiltersBtn.addEventListener("click", () => refreshAll());
applyLogFiltersBtn.addEventListener("click", () => refreshAll());

refreshLogsBtn.addEventListener("click", async () => {
  const filters = getFilters();
  const query = buildQuery({
    page: 1,
    page_size: 300,
    service: filters.service,
    status: filters.status,
    endpoint: filters.logEndpoint,
    error_type: filters.logErrorType,
  });
  const data = await apiGet(`/ui/logs${query}`);
  renderLogs(data.items || []);
});

refreshEventsBtn.addEventListener("click", async () => {
  const filters = getFilters();
  const query = buildQuery({
    page: 1,
    page_size: 200,
    service: filters.service,
    status: filters.status === "ok" ? "success" : (filters.status || ""),
  });
  const data = await apiGet(`/ui/events${query}`);
  renderEvents(data.items || []);
});

refreshQueueBtn.addEventListener("click", async () => {
  const data = await apiGet("/ui/caea/queue?limit=200");
  renderQueue(data);
});

retryQueueBtn.addEventListener("click", async () => {
  await apiPost("/ui/caea/queue/retry?limit=30");
  const data = await apiGet("/ui/caea/queue?limit=200");
  renderQueue(data);
});

refreshAssignmentsBtn.addEventListener("click", async () => {
  const data = await apiGet("/ui/caea/assignments?limit=200");
  renderAssignments(data);
  renderPosList(data.items || []);
});

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => activateTab(btn.dataset.tab));
});

refreshPosParamsBtn.addEventListener("click", refreshWsfePosParams);
refreshWsfeParamsBtn.addEventListener("click", refreshWsfeParamsSnapshot);

tokenInput.value = getToken();
refreshAll();
setInterval(refreshAll, 15000);
