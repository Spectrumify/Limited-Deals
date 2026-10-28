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

function render() {
  const rows = items.filter(item => item.lowest_price != null).sort(compare);
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

refresh();
setInterval(refresh, 30000);  // only reads our local server, not Roblox
