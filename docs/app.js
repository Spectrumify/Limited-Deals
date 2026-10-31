// GitHub Pages version of the dashboard. Reads data/items.json, which the hourly
// GitHub Actions job writes. Everything else (filters, sorting, presets) runs in the browser.

let items = [];
let sortKey = "lowest_price";
let sortAscending = true;
const SUGGESTIONS_SHOWN = 8;

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
  if (item.stale) flags.push("⏳ Old price");
  return flags.join(" ");
}

function flagsTooltip(item) {
  const lines = [];
  if (item.projected_warning) lines.push(`Projected (${item.projected_reason}): RAP may be inflated, don't trust it.`);
  if (item.stale) lines.push("This price wasn't refreshed in the last run, so it may already be sold.");
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
  if (x == null || x === -1) return 1;  // empty values always go to the bottom
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

// Same rules as deals.passes_filters in Python.
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

// ---------- Presets (saved in this browser only; wrapped in try/catch in case storage is blocked) ----------

const DEFAULT_PRESETS = {
  "Under 5k, high demand": { max_price: 5000, min_demand: 3, hide_projected: true },
  "Starting (1200)": { min_price: 1, max_price: 1200 },
};

function loadPresets() {
  try {
    const saved = localStorage.getItem("presets");
    if (saved) return JSON.parse(saved);
  } catch {}
  return { ...DEFAULT_PRESETS };
}

function savePresets(presets) {
  try { localStorage.setItem("presets", JSON.stringify(presets)); } catch {}
}

function showPresets(selected = "") {
  const select = document.getElementById("preset-select");
  select.innerHTML = '<option value="">— Presets —</option>';
  for (const name of Object.keys(loadPresets()).sort()) {
    const option = document.createElement("option");
    option.value = option.textContent = name;
    select.appendChild(option);
  }
  select.value = selected;
}

document.getElementById("preset-select").addEventListener("change", event => {
  const filters = loadPresets()[event.target.value];
  if (filters) {
    writeFilters({ trends: [], ...filters });
    render();
  }
});

document.getElementById("preset-save").addEventListener("click", () => {
  const name = prompt("Name for this preset:", document.getElementById("preset-select").value);
  if (!name) return;
  const presets = loadPresets();
  presets[name] = readFilters();
  savePresets(presets);
  showPresets(name);
});

document.getElementById("preset-delete").addEventListener("click", () => {
  const name = document.getElementById("preset-select").value;
  if (!name || !confirm(`Delete preset "${name}"?`)) return;
  const presets = loadPresets();
  delete presets[name];
  savePresets(presets);
  showPresets();
});

document.getElementById("filters-clear").addEventListener("click", () => {
  writeFilters({});
  document.getElementById("preset-select").value = "";
  render();
});

document.getElementById("filters").addEventListener("input", render);

// ---------- Suggestions (lists are worked out by the hourly job) ----------

function suggestionLine(item, list) {
  const price = `${item.lowest_price.toLocaleString()} R$`;
  if (list === "deals") return `${price}, ${item.discount_pct}% below ${item.target_source}, ~${item.profit.toLocaleString()} R$ profit`;
  if (list === "rising") {
    const why = item.rap_change_pct != null ? `RAP +${item.rap_change_pct.toFixed(0)}% in ${item.history_days.toFixed(1)} days` : "Rolimons: raising";
    return `${price}, ${why}`;
  }
  return `${price} now, deal at ≤ ${item.buy_below.toLocaleString()} R$ (needs −${item.drop_needed_pct}%)`;
}

const EMPTY_TEXT = {
  deals: "None right now. Good deals are rare; Discord alerts will catch them.",
  rising: "None yet. Our own trend needs ~3 days of history.",
  watch: "Nothing close yet.",
};

function renderSuggestions() {
  const filters = { ...readFilters(), deals_only: false, rising_only: false };
  for (const name of ["deals", "rising", "watch"]) {
    const entries = items
      .filter(item => item.suggestion === name && passesFilters(item, filters))
      .sort((a, b) => a.suggestion_rank - b.suggestion_rank)
      .slice(0, SUGGESTIONS_SHOWN);
    const ol = document.getElementById(`sugg-${name}`);
    ol.innerHTML = "";
    if (entries.length === 0) {
      const li = document.createElement("li");
      li.className = "muted empty";
      li.textContent = EMPTY_TEXT[name];
      ol.appendChild(li);
    }
    for (const item of entries) {
      const li = document.createElement("li");
      const link = document.createElement("a");
      link.href = `https://www.roblox.com/catalog/${item.id}`;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = item.name;
      const detail = document.createElement("div");
      detail.className = "muted";
      detail.textContent = suggestionLine(item, name);
      li.append(link, detail);
      ol.appendChild(li);
    }
  }
}

// ---------- Table ----------

function render() {
  const filters = readFilters();
  const rows = items.filter(item => passesFilters(item, filters)).sort(compare);
  document.getElementById("filter-summary").textContent =
    `Showing ${rows.length.toLocaleString()} of ${items.length.toLocaleString()} items`;
  renderSuggestions();

  const tbody = document.querySelector("#items tbody");
  tbody.innerHTML = "";
  for (const item of rows) {
    const tr = document.createElement("tr");
    if (item.projected_warning) tr.classList.add("projected");
    if (item.is_deal) tr.classList.add("deal");
    tr.innerHTML = `
      <td><a target="_blank" rel="noopener"></a></td>
      <td class="num">${formatRobux(item.lowest_price)}</td>
      <td class="num">${formatRobux(item.rap)}</td>
      <td class="num">${formatRobux(item.value)}</td>
      <td class="num">${item.discount_pct == null ? "—" : item.discount_pct + "%"}</td>
      <td class="num ${item.profit > 0 ? "gain" : ""}">${formatRobux(item.profit)}</td>
      <td class="num">${formatRobux(item.buy_below)}</td>
      <td></td>
      <td></td>
      <td class="num">${formatRobux(item.total_quantity)}</td>
      <td></td>`;
    const link = tr.querySelector("a");
    link.href = `https://www.roblox.com/catalog/${item.id}`;
    link.textContent = item.name;  // textContent = safe from HTML injection
    tr.cells[7].textContent = item.demand_name;
    tr.cells[8].textContent = item.trend_name;
    tr.cells[10].textContent = flagsText(item);
    tr.cells[10].title = flagsTooltip(item);
    tbody.appendChild(tr);
  }

  document.querySelectorAll("th").forEach(th => {
    th.classList.toggle("sorted", th.dataset.key === sortKey);
    th.dataset.dir = th.dataset.key === sortKey ? (sortAscending ? "▲" : "▼") : "";
  });
}

document.querySelectorAll("th").forEach(th => {
  th.addEventListener("click", () => {
    const key = th.dataset.key;
    sortAscending = key === sortKey ? !sortAscending : true;
    sortKey = key;
    render();
  });
});

// ---------- Loading data ----------

function showSettings(settings) {
  document.getElementById("settings-text").textContent =
    `Deal = at least ${settings.min_discount_pct}% below value/RAP AND at least ${settings.min_profit} R$ profit ` +
    `after the fee (you keep ${settings.seller_keep_pct}% of a sale). Projected = RAP jumped ${settings.projection_ratio}× ` +
    `without listings following. Rising = RAP and listings up ${settings.rising_pct}%+.`;
}

async function loadData() {
  const status = document.getElementById("status");
  try {
    // ?t=... skips cached copies so you always see the latest hourly data.
    const response = await fetch(`data/items.json?t=${Date.now()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    items = data.items;
    document.getElementById("budget").textContent = data.budget.toLocaleString();
    showSettings(data.settings);
    const updated = new Date(data.generated_at * 1000);
    const minutesAgo = Math.round((Date.now() - updated) / 60000);
    status.textContent = `Updated ${updated.toLocaleString()} (${minutesAgo} min ago)` +
      // GitHub often runs the schedule only every 4-8 hours, so warn only after a long gap.
      (minutesAgo > 12 * 60 ? " ⚠️ the refresh job may be failing" : "");
    render();
  } catch (error) {
    status.textContent = `⚠️ Couldn't load data (${error.message}). Try again in a minute.`;
  }
}

showPresets();
loadData();
setInterval(loadData, 5 * 60 * 1000);
