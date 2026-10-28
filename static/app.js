// Loads items from the Flask API and draws a sortable table.

let items = [];
let sortKey = "lowest_price";
let sortAscending = true;

function formatRobux(n) {
  return n == null ? "—" : n.toLocaleString();
}

function flagsText(item) {
  const flags = [];
  if (item.projected) flags.push("⚠️ Projected");
  if (item.rare) flags.push("💎 Rare");
  if (item.hyped) flags.push("🔥 Hyped");
  return flags.join(" ");
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
}

function passesFilters(item, f) {
  if (item.lowest_price == null) return false;
  if (f.min_price != null && item.lowest_price < f.min_price) return false;
  if (f.max_price != null && item.lowest_price > f.max_price) return false;
  if (f.min_demand != null && item.demand < f.min_demand) return false;
  if (f.trends.length > 0 && !f.trends.includes(item.trend)) return false;
  if (f.max_copies != null && (item.total_quantity == null || item.total_quantity > f.max_copies)) return false;
  if (f.rare_only && !item.rare) return false;
  if (f.hide_projected && item.projected) return false;
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
    if (item.projected) tr.classList.add("projected");
    const link = `https://www.roblox.com/catalog/${item.id}`;
    tr.innerHTML = `
      <td><a href="${link}" target="_blank" rel="noopener"></a></td>
      <td class="num">${formatRobux(item.lowest_price)}</td>
      <td class="num">${formatRobux(item.rap)}</td>
      <td class="num">${formatRobux(item.value)}</td>
      <td>${item.demand_name}</td>
      <td>${item.trend_name}</td>
      <td class="num">${formatRobux(item.total_quantity)}</td>
      <td>${flagsText(item)}</td>`;
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
}

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

loadPresets();
refresh();
setInterval(refresh, 30000);  // only reads our local server, not Roblox
