const tokenInput = document.getElementById("jwtToken");
const saveTokenBtn = document.getElementById("saveTokenBtn");
const refreshBtn = document.getElementById("refreshBtn");
const filterService = document.getElementById("filterService");
const filterStatus = document.getElementById("filterStatus");
const logEndpointFilter = document.getElementById("logEndpointFilter");
const logErrorFilter = document.getElementById("logErrorFilter");
const logsTable = document.getElementById("logsTable");

const LS_TOKEN_KEY = "afrelay_monitor_jwt";

function getToken() {
  return localStorage.getItem(LS_TOKEN_KEY) || "";
}

function buildQuery(params) {
  const q = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`);
  return q.length ? `?${q.join("&")}` : "";
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

function fmtDate(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

function renderLogs(items) {
  logsTable.innerHTML = "";
  items.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${fmtDate(row.timestamp)}</td>
      <td>${row.method || "-"}</td>
      <td>${row.path}</td>
      <td class="${row.ok ? "status-ok" : "status-error"}">${row.status_code}</td>
      <td>${row.duration_ms}</td>
      <td>${row.service || "-"}</td>
      <td>${row.error_type || "-"}</td>
      <td>${row.cuit || "-"}</td>
      <td>${row.trace_id || "-"}</td>
    `;
    logsTable.appendChild(tr);
  });
}

async function refreshLogs() {
  const query = buildQuery({
    page: 1,
    page_size: 500,
    service: filterService.value,
    status: filterStatus.value,
    endpoint: logEndpointFilter.value.trim(),
    error_type: logErrorFilter.value.trim(),
  });
  const data = await apiGet(`/ui/logs${query}`);
  renderLogs(data.items || []);
}

saveTokenBtn.addEventListener("click", () => {
  localStorage.setItem(LS_TOKEN_KEY, tokenInput.value.trim());
  refreshLogs();
});

refreshBtn.addEventListener("click", () => refreshLogs());
filterService.addEventListener("change", () => refreshLogs());
filterStatus.addEventListener("change", () => refreshLogs());

tokenInput.value = getToken();
refreshLogs();
setInterval(refreshLogs, 15000);
