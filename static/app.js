// Loads items from the Flask API and draws a sortable table.

let items = [];
let sortKey = "lowest_price";
let sortAscending = true;

function formatRobux(n) {
  return n == null ? "—" : n.toLocaleString();
}

function flagsText(item) {
  const flags = [];
  if (item.is_deal) flags.push("💰 Deal");
  if (item.projected_warning) flags.push("⚠️ Projected");
  if (item.rising) flags.push("📈 Rising");
  if (item.rare) flags.push("💎 Rare");
  if (item.hyped) flags.push("🔥 Hyped");
  return flags.join(" ");
}

function flagsTooltip(item) {
  const lines = [];
  if (item.projected_warning) lines.push(`Projected (${item.projected_reason}): RAP may be inflated, don't trust it.`);
  if (item.rap_change_pct != null) {
    lines.push(`Last ${item.history_days.toFixed(1)} days: RAP ${item.rap_change_pct.toFixed(0)}%, listings ${item.price_change_pct.toFixed(0)}%`);
  } else {
    lines.push("Not enough saved history yet for our own trend (needs ~3 days).");
  }
  lines.push(`Profit/discount measured against ${item.target_source}.`);
  return lines.join("\n");
}

function sortValue(item, key) {
  if (key === "flags") return flagsText(item);
  if (key === "name") return item.name.toLowerCase();
  return item[key];
}

function compare(a, b) {
  const x = sortValue(a, sortKey);
  const y = sortValue(b, sortKey);
  // Empty values always go to the bottom.
  if (x == null || x === -1) return 1;
  if (y == null || y === -1) return -1;
  if (x < y) return sortAscending ? -1 : 1;
  if (x > y) return sortAscending ? 1 : -1;
  return 0;
}

// ---------- Filters ----------

function numberOrNull(id) {
  const text = document.getElementById(id).value;
  return text === "" ? null : Number(text);
}

// Read the filter controls into a plain object (this is what presets save).
function readFilters() {
  return {
    min_price: numberOrNull("f-min-price"),
    max_price: numberOrNull("f-max-price"),
    min_demand: numberOrNull("f-min-demand"),
    trends: [...document.querySelectorAll(".f-trend:checked")].map(box => Number(box.value)),
    max_copies: numberOrNull("f-max-copies"),
    rare_only: document.getElementById("f-rare-only").checked,
    hide_projected: document.getElementById("f-hide-projected").checked,
    deals_only: document.getElementById("f-deals-only").checked,
    rising_only: document.getElementById("f-rising-only").checked,
  };
}

// Put a filters object back into the controls (used when loading a preset).
function writeFilters(filters) {
  document.getElementById("f-min-price").value = filters.min_price ?? "";
  document.getElementById("f-max-price").value = filters.max_price ?? "";
  document.getElementById("f-min-demand").value = filters.min_demand ?? "";
  document.querySelectorAll(".f-trend").forEach(box => {
    box.checked = (filters.trends || []).includes(Number(box.value));
  });
  document.getElementById("f-max-copies").value = filters.max_copies ?? "";
  document.getElementById("f-rare-only").checked = !!filters.rare_only;
  document.getElementById("f-hide-projected").checked = !!filters.hide_projected;
  document.getElementById("f-deals-only").checked = !!filters.deals_only;
  document.getElementById("f-rising-only").checked = !!filters.rising_only;
}

function passesFilters(item, f) {
  if (item.lowest_price == null) return false;
  if (f.min_price != null && item.lowest_price < f.min_price) return false;
  if (f.max_price != null && item.lowest_price > f.max_price) return false;
  if (f.min_demand != null && item.demand < f.min_demand) return false;
  if (f.trends.length > 0 && !f.trends.includes(item.trend)) return false;
  if (f.max_copies != null && (item.total_quantity == null || item.total_quantity > f.max_copies)) return false;
  if (f.rare_only && !item.rare) return false;
  if (f.hide_projected && item.projected_warning) return false;
  if (f.deals_only && !item.is_deal) return false;
  if (f.rising_only && !item.rising) return false;
  return true;
}

// ---------- Presets ----------

let presets = [];

async function loadPresets() {
  presets = await (await fetch("/api/presets")).json();
  const select = document.getElementById("preset-select");
  const current = select.value;
  select.innerHTML = '<option value="">— Presets —</option>';
  for (const preset of presets) {
    const option = document.createElement("option");
    option.value = option.textContent = preset.name;
    select.appendChild(option);
  }
  select.value = current;
}

document.getElementById("preset-select").addEventListener("change", event => {
  const preset = presets.find(p => p.name === event.target.value);
  if (preset) {
    writeFilters(preset.filters);
    render();
  }
});

document.getElementById("preset-save").addEventListener("click", async () => {
  const name = prompt("Name for this preset:", document.getElementById("preset-select").value);
  if (!name) return;
  await fetch("/api/presets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, filters: readFilters() }),
  });
  await loadPresets();
  document.getElementById("preset-select").value = name;
});

document.getElementById("preset-delete").addEventListener("click", async () => {
  const name = document.getElementById("preset-select").value;
  if (!name || !confirm(`Delete preset "${name}"?`)) return;
  await fetch(`/api/presets/${encodeURIComponent(name)}`, { method: "DELETE" });
  await loadPresets();
});

document.getElementById("filters-clear").addEventListener("click", () => {
  writeFilters({});
  document.getElementById("preset-select").value = "";
  render();
});

document.getElementById("filters").addEventListener("input", render);

// ---------- Table ----------

function render() {
  const filters = readFilters();
  const rows = items.filter(item => passesFilters(item, filters)).sort(compare);
  document.getElementById("count").textContent = `${rows.length} items.`;

  const tbody = document.querySelector("#items tbody");
  tbody.innerHTML = "";
  for (const item of rows) {
    const tr = document.createElement("tr");
    if (item.projected_warning) tr.classList.add("projected");
    if (item.is_deal) tr.classList.add("deal");
    const link = `https://www.roblox.com/catalog/${item.id}`;
    tr.innerHTML = `
      <td><a href="${link}" target="_blank" rel="noopener"></a></td>
      <td class="num">${formatRobux(item.lowest_price)}</td>
      <td class="num">${formatRobux(item.rap)}</td>
      <td class="num">${formatRobux(item.value)}</td>
      <td class="num">${item.discount_pct == null ? "—" : item.discount_pct + "%"}</td>
      <td class="num ${item.profit > 0 ? "gain" : ""}">${formatRobux(item.profit)}</td>
      <td>${item.demand_name}</td>
      <td>${item.trend_name}</td>
      <td class="num">${formatRobux(item.total_quantity)}</td>
      <td></td>`;
    const signals = tr.lastElementChild;
    signals.textContent = flagsText(item);
    signals.title = flagsTooltip(item);
    tr.querySelector("a").textContent = item.name;  // textContent = safe from HTML injection
    tbody.appendChild(tr);
  }

  document.querySelectorAll("th").forEach(th => {
    th.classList.toggle("sorted", th.dataset.key === sortKey);
    th.dataset.dir = th.dataset.key === sortKey ? (sortAscending ? "▲" : "▼") : "";
  });
}

async function loadItems() {
  const response = await fetch("/api/items");
  items = await response.json();
  render();
  checkForNewDeals();
}

// ---------- Alerts ----------
// A deal is identified by item + price, so the same listing only alerts once,
// but a new, cheaper listing of the same item alerts again.

function dealKey(item) {
  return `${item.id}:${item.lowest_price}`;
}

// Pure function (no browser APIs) so it can be tested on its own.
function findNewDeals(allItems, filters, seenKeys) {
  return allItems.filter(item => item.is_deal && passesFilters(item, filters) && !seenKeys.has(dealKey(item)));
}

// Remember which deals we already alerted about, even across page reloads.
// Wrapped in try/catch because browser storage can be blocked.
function loadSeen() {
  try { return new Set(JSON.parse(localStorage.getItem("seenDeals") || "[]")); } catch { return new Set(); }
}
function saveSeen(seen) {
  try { localStorage.setItem("seenDeals", JSON.stringify([...seen].slice(-2000))); } catch {}
}
function alertsEnabled() {
  try { return localStorage.getItem("alertsEnabled") === "1"; } catch { return false; }
}
function setAlertsEnabled(on) {
  try { localStorage.setItem("alertsEnabled", on ? "1" : "0"); } catch {}
}

function notify(title, body, url) {
  const note = new Notification(title, { body, tag: url || title });
  if (url) note.onclick = () => window.open(url, "_blank");
}

function checkForNewDeals() {
  if (!alertsEnabled() || !("Notification" in window) || Notification.permission !== "granted") return;
  const seen = loadSeen();
  const newDeals = findNewDeals(items, readFilters(), seen);
  if (newDeals.length === 0) return;

  newDeals.sort((a, b) => b.profit - a.profit);
  if (newDeals.length <= 3) {
    for (const item of newDeals) {
      notify(`💰 Deal: ${item.name}`,
        `${item.lowest_price.toLocaleString()} R$ (${item.discount_pct}% below ${item.target_source}), ` +
        `~${item.profit.toLocaleString()} R$ profit after fee`,
        `https://www.roblox.com/catalog/${item.id}`);
    }
  } else {
    const best = newDeals[0];
    notify(`💰 ${newDeals.length} new deals`, `Best: ${best.name} for ${best.lowest_price.toLocaleString()} R$ (~${best.profit.toLocaleString()} R$ profit)`);
  }
  newDeals.forEach(item => seen.add(dealKey(item)));
  saveSeen(seen);
  document.getElementById("alerts-msg").textContent =
    `Last alert ${new Date().toLocaleTimeString()}: ${newDeals.length} new deal(s)`;
}

const alertsToggle = document.getElementById("alerts-toggle");

alertsToggle.addEventListener("change", async () => {
  const msg = document.getElementById("alerts-msg");
  if (!alertsToggle.checked) {
    setAlertsEnabled(false);
    msg.textContent = "Alerts off.";
    return;
  }
  if (!("Notification" in window)) {
    alertsToggle.checked = false;
    msg.textContent = "This browser doesn't support notifications.";
    return;
  }
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    alertsToggle.checked = false;
    msg.textContent = "Notifications are blocked. Allow them for 127.0.0.1 in your browser's site settings.";
    return;
  }
  setAlertsEnabled(true);
  msg.textContent = "Alerts on. Keep this tab open (it can be in the background).";
  checkForNewDeals();
});

alertsToggle.checked = alertsEnabled() && "Notification" in window && Notification.permission === "granted";

async function loadStatus() {
  const status = await (await fetch("/api/status")).json();
  const el = document.getElementById("status");
  if (status.last_error) {
    el.textContent = `⚠️ Last refresh failed: ${status.last_error}`;
  } else if (status.last_refresh) {
    el.textContent = `Last refreshed ${new Date(status.last_refresh * 1000).toLocaleTimeString()}`;
  } else {
    el.textContent = "First refresh in progress (takes ~30 s)…";
  }
}

document.querySelectorAll("th").forEach(th => {
  th.addEventListener("click", () => {
    const key = th.dataset.key;
    sortAscending = key === sortKey ? !sortAscending : true;
    sortKey = key;
    render();
  });
});

async function refresh() {
  await Promise.all([loadItems(), loadStatus()]);
}

// ---------- Deal settings ----------

const settingsForm = document.getElementById("settings-form");

async function loadSettings() {
  const settings = await (await fetch("/api/settings")).json();
  for (const [key, value] of Object.entries(settings)) {
    if (settingsForm.elements[key]) settingsForm.elements[key].value = value;
  }
}

settingsForm.addEventListener("submit", async event => {
  event.preventDefault();
  const body = Object.fromEntries(new FormData(settingsForm));
  const response = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result = await response.json();
  document.getElementById("settings-msg").textContent = response.ok ? "Saved." : result.error;
  if (response.ok) loadItems();  // deals are recalculated on the server
});

loadSettings();
loadPresets();
refresh();
setInterval(refresh, 30000);  // only reads our local server, not Roblox
