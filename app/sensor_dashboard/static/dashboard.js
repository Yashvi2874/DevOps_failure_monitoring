const TEMP_LIMIT = 35;      // same threshold as the SensorOverheat alert
const CO2_LIMIT = 1500;
const PM25_LIMIT = 100;

const sensorsEl = document.getElementById("sensors");
const alertsEl = document.getElementById("alerts");
const connectionEl = document.getElementById("connection");
const simEnabled = document.body.dataset.simulation === "on";

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function setConnection(ok, text) {
  connectionEl.textContent = text;
  connectionEl.className = "pill " + (ok ? "pill-ok" : "pill-bad");
}

function sparkline(points) {
  if (points.length < 2) return "";
  const w = 200, h = 46, pad = 3;
  const lo = Math.min(...points, TEMP_LIMIT - 5);
  const hi = Math.max(...points, TEMP_LIMIT + 2);
  const x = (i) => pad + (i * (w - 2 * pad)) / (points.length - 1);
  const y = (v) => h - pad - ((v - lo) * (h - 2 * pad)) / (hi - lo || 1);
  const line = points.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const limitY = y(TEMP_LIMIT).toFixed(1);
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
    <line x1="0" x2="${w}" y1="${limitY}" y2="${limitY}" stroke="#fca5a5" stroke-dasharray="4 3"/>
    <polyline points="${line}" fill="none" stroke="#0f766e" stroke-width="2"/>
  </svg>`;
}

function statusPill(sensor) {
  if (!sensor.online) return '<span class="pill pill-bad">OFFLINE</span>';
  if (sensor.values.temperature > TEMP_LIMIT) return '<span class="pill pill-bad">OVERHEAT</span>';
  if (sensor.values.co2 > CO2_LIMIT || sensor.values.pm25 > PM25_LIMIT) {
    return '<span class="pill pill-warn">POOR AIR</span>';
  }
  return '<span class="pill pill-ok">ONLINE</span>';
}

function stat(label, value, unit, high) {
  return `<div class="stat ${high ? "high" : ""}">
    <div class="label">${label}</div>
    <div class="num">${value}<small> ${unit}</small></div>
  </div>`;
}

function renderSensors(sensors) {
  sensorsEl.innerHTML = sensors.map((s) => {
    const v = s.values;
    const seen = s.online
      ? `updated ${s.seconds_since_update.toFixed(0)}s ago`
      : `no reading for ${s.seconds_since_update.toFixed(0)}s · ${s.read_errors} failed reads`;
    return `<article class="card ${s.online ? "" : "offline"}">
      <div class="card-head">
        <div><h3>${esc(s.name)}</h3><div class="loc">${esc(s.location)}</div></div>
        ${statusPill(s)}
      </div>
      <div class="temp">
        <div class="value ${v.temperature > TEMP_LIMIT ? "hot" : ""}">${v.temperature.toFixed(1)}°C</div>
        ${sparkline(s.history)}
      </div>
      <div class="stats">
        ${stat("Humidity", v.humidity.toFixed(0), "%", false)}
        ${stat("CO₂", v.co2.toFixed(0), "ppm", v.co2 > CO2_LIMIT)}
        ${stat("PM2.5", v.pm25.toFixed(0), "µg/m³", v.pm25 > PM25_LIMIT)}
      </div>
      <div class="seen">${seen}</div>
    </article>`;
  }).join("");
}

function renderSimControls(sensors) {
  const box = document.getElementById("sim-sensors");
  if (!box) return;
  const buttons = [
    ["overheat", "Overheat"],
    ["offline", "Go offline"],
    ["pollution", "Pollution spike"],
  ];
  box.innerHTML = sensors.map((s) => `<div class="sim-row">
      <b>${esc(s.name)} · ${esc(s.location)}</b>
      ${buttons.map(([scenario, label]) => {
        const on = s.scenarios.includes(scenario);
        return `<button class="btn ${on ? "on" : ""}" data-sensor="${esc(s.id)}"
          data-scenario="${scenario}" data-active="${on ? "false" : "true"}">
          ${on ? "Stop: " : ""}${label}</button>`;
      }).join("")}
    </div>`).join("");
}

async function loadReadings() {
  try {
    const res = await fetch("/api/readings", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderSensors(data.sensors);
    if (simEnabled) renderSimControls(data.sensors);
    setConnection(true, "live");
  } catch (err) {
    setConnection(false, `API error: ${err.message}`);
  }
}

function timeSince(iso) {
  const secs = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  return secs < 90 ? `${secs.toFixed(0)}s ago` : `${(secs / 60).toFixed(0)} min ago`;
}

async function loadAlerts() {
  try {
    const res = await fetch("/api/alerts", { cache: "no-store" });
    const data = await res.json();
    if (!data.available) {
      alertsEl.innerHTML = '<div class="alerts-off">Alertmanager is not reachable, so alerts are not shown here.</div>';
      return;
    }
    if (data.alerts.length === 0) {
      alertsEl.innerHTML = '<div class="alerts-ok">No active alerts. Everything looks healthy.</div>';
      return;
    }
    alertsEl.innerHTML = data.alerts.map((a) => `<div class="alert ${esc(a.severity)}">
        <span class="pill ${a.severity === "critical" ? "pill-bad" : "pill-warn"}">${esc(a.severity)}</span>
        <span class="name">${esc(a.name)}</span>
        <span>${esc(a.summary)}</span>
        <span class="since">since ${timeSince(a.starts_at)}</span>
      </div>`).join("");
  } catch (err) {
    alertsEl.innerHTML = '<div class="alerts-off">Could not load alerts.</div>';
  }
}

async function simulate(scenario, body) {
  const status = document.getElementById("sim-status");
  try {
    const res = await fetch(`/api/simulate/${scenario}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json();
    status.textContent = res.ok ? `Done: ${scenario}` : `Failed: ${data.error}`;
    if (scenario === "reset") {
      document.querySelector('[data-global="api-errors"]').classList.remove("on");
    }
  } catch (err) {
    status.textContent = `Request failed: ${err.message}`;
  }
  loadReadings();
}

document.addEventListener("click", (event) => {
  const btn = event.target.closest("button");
  if (!btn) return;
  if (btn.dataset.global) {
    const active = btn.dataset.global === "api-errors" ? !btn.classList.contains("on") : true;
    if (btn.dataset.global === "api-errors") btn.classList.toggle("on", active);
    simulate(btn.dataset.global, { active });
  } else if (btn.dataset.scenario) {
    simulate(btn.dataset.scenario, {
      sensor: btn.dataset.sensor,
      active: btn.dataset.active === "true",
    });
  }
});

const host = window.location.hostname;
document.getElementById("link-prometheus").href = `http://${host}:9090/alerts`;
document.getElementById("link-alertmanager").href = `http://${host}:9093`;
document.getElementById("link-receiver").href = `http://${host}:5001`;

async function syncApiErrorButton() {
  const btn = document.querySelector('[data-global="api-errors"]');
  if (!btn) return;
  try {
    const data = await (await fetch("/api/simulation", { cache: "no-store" })).json();
    btn.classList.toggle("on", data.api_errors);
  } catch (err) {
    // the next page load will sync it
  }
}

syncApiErrorButton();
loadReadings();
loadAlerts();
setInterval(loadReadings, 2000);
setInterval(loadAlerts, 5000);
