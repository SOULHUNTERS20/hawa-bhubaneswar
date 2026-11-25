/* data.js - public table + three charts built from /api/submissions. */

var rows = [];
var charts = {};

Hawa.getJSON("/api/submissions").then(function (data) {
  rows = data.slice().sort(function (a, b) { return a.timestamp < b.timestamp ? 1 : -1; }); // newest first
  if (!rows.length) {
    document.getElementById("no-data").classList.remove("hidden");
    return;
  }
  document.getElementById("has-data").classList.remove("hidden");
  renderStats();
  renderTable();
  renderCharts();
}).catch(function () {
  var box = document.getElementById("no-data");
  box.classList.remove("hidden");
  box.textContent = "Community readings couldn't be loaded right now. Please reload the page.";
});

function avg(list) {
  var nums = list.filter(function (v) { return v !== null && v !== undefined; });
  return nums.length ? nums.reduce(function (a, b) { return a + b; }, 0) / nums.length : null;
}

// ---------- Stats ----------
function renderStats() {
  var ids = {};
  rows.forEach(function (r) { ids[r.participant_id] = true; });
  var flagged = rows.filter(function (r) { return r.flag; }).length;
  document.getElementById("d-total").textContent = rows.length;
  document.getElementById("d-people").textContent = Object.keys(ids).length;
  var f = document.getElementById("d-flagged");
  if (flagged) { f.textContent = flagged; } else { f.textContent = "None"; f.classList.add("empty"); }
}

// ---------- Table ----------
function cell(v, unit) { return v === null || v === undefined ? '<span class="muted">–</span>' : v + (unit || ""); }

function renderTable() {
  var filter = document.getElementById("zone-filter").value;
  var shown = rows.filter(function (r) { return !filter || r.zone_id === Number(filter); });
  var body = document.getElementById("rows");
  if (!shown.length) {
    body.innerHTML = '<tr><td colspan="11"><div class="empty">No readings for this zone yet. <a href="/submit">Be the first to submit</a></div></td></tr>';
    return;
  }
  // Hawa.esc() on every user-typed value, so nobody can inject HTML
  body.innerHTML = shown.map(function (r) {
    return '<tr class="' + (r.flag ? "flagged" : "") + '">' +
      "<td>" + Hawa.esc(r.timestamp) + "</td>" +
      "<td>" + Hawa.esc(r.participant_id) + "</td>" +
      "<td>Z" + r.zone_id + " " + Hawa.esc(r.zone_name) + "</td>" +
      "<td>" + (r.aqi !== null ? Hawa.chip(r.aqi) : cell(null)) + "</td>" +
      "<td>" + cell(r.pm25) + "</td>" +
      "<td>" + cell(r.temp, "°C") + "</td>" +
      "<td>" + Hawa.esc(r.feel) + "</td>" +
      "<td>" + Hawa.esc(r.activity) + "</td>" +
      '<td class="wrap-cell">' + Hawa.esc(r.note) + "</td>" +
      "<td>" + cell(r.api_aqi) + (r.api_aqi !== null
        ? ' <span class="muted small">' + (r.ref_source === "CPCB station" ? "station" : "model") + "</span>" : "") + "</td>" +
      "<td>" + (r.flag ? '<span class="flag-badge" title="' + Hawa.esc(r.flag) + '">Flagged</span>' : "") + "</td>" +
      "</tr>";
  }).join("");
}
document.getElementById("zone-filter").addEventListener("change", renderTable);

// ---------- Charts ----------
function renderCharts() {
  Hawa.chartDefaults();
  Object.keys(charts).forEach(function (k) { charts[k].destroy(); });
  var zones = Hawa.zones;
  var withAqi = rows.filter(function (r) { return r.effective_aqi !== null; });

  // 1) Line: daily average per zone
  var days = {};
  withAqi.forEach(function (r) { days[r.timestamp.slice(0, 10)] = true; });
  var labels = Object.keys(days).sort();
  var lineSets = zones.map(function (z, i) {
    return {
      label: "Z" + z.id + " " + z.name,
      data: labels.map(function (day) {
        var v = avg(withAqi.filter(function (r) { return r.zone_id === z.id && r.timestamp.slice(0, 10) === day; })
                         .map(function (r) { return r.effective_aqi; }));
        return v === null ? null : Math.round(v);
      }),
      borderColor: Hawa.ZONE_COLORS[i], backgroundColor: Hawa.ZONE_COLORS[i],
      spanGaps: true, tension: 0.3, pointRadius: 3,
    };
  });
  charts.line = new Chart(document.getElementById("line-chart"), {
    type: "line",
    data: { labels: labels, datasets: lineSets },
    options: {
      maintainAspectRatio: false,
      scales: { y: { beginAtZero: true, title: { display: true, text: "AQI" } } },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
    },
  });

  // 2) Bar: average per zone, coloured by band
  var zoneLabels = zones.map(function (z) { return "Z" + z.id; });
  var zoneAvg = zones.map(function (z) {
    var v = avg(withAqi.filter(function (r) { return r.zone_id === z.id; }).map(function (r) { return r.effective_aqi; }));
    return v === null ? null : Math.round(v);
  });
  charts.bar = new Chart(document.getElementById("bar-chart"), {
    type: "bar",
    data: {
      labels: zoneLabels,
      datasets: [{
        label: "Average community AQI",
        data: zoneAvg,
        backgroundColor: zoneAvg.map(function (v) { var b = Hawa.band(v); return b ? b.color : "#a7b0ab"; }),
        borderRadius: 6,
      }],
    },
    options: {
      maintainAspectRatio: false,
      scales: { y: { beginAtZero: true } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { title: function (items) { return zones[items[0].dataIndex].name; } } },
      },
    },
  });

  // 3) Community vs official: only rows where both values exist.
  //    "Official" = CPCB station (zones 3, 5) or the model (zones without a station).
  var paired = withAqi.filter(function (r) { return r.api_aqi !== null; });
  var comm = [], model = [], source = [];
  zones.forEach(function (z) {
    var zr = paired.filter(function (r) { return r.zone_id === z.id; });
    var c = avg(zr.map(function (r) { return r.effective_aqi; }));
    var m = avg(zr.map(function (r) { return r.api_aqi; }));
    comm.push(c === null ? null : Math.round(c));
    model.push(m === null ? null : Math.round(m));
    var fromStation = zr.filter(function (r) { return r.ref_source === "CPCB station"; }).length;
    source.push(!zr.length ? "–" : fromStation === zr.length ? "CPCB station"
      : fromStation === 0 ? "Model" : "Station + model");
  });
  charts.vs = new Chart(document.getElementById("vs-chart"), {
    type: "bar",
    data: {
      labels: zoneLabels,
      datasets: [
        { label: "Community", data: comm, backgroundColor: Hawa.css("--accent"), borderRadius: 6 },
        { label: "Official (CPCB station or model)", data: model, backgroundColor: "#8a94a6", borderRadius: 6 },
      ],
    },
    options: {
      maintainAspectRatio: false,
      scales: { y: { beginAtZero: true } },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
    },
  });

  // Gap table
  var html = "<thead><tr><th>Zone</th><th>Paired readings</th><th>Community avg</th><th>Official avg</th>" +
    "<th>Compared with</th><th>Gap</th></tr></thead><tbody>";
  zones.forEach(function (z, i) {
    var n = paired.filter(function (r) { return r.zone_id === z.id; }).length;
    var gap = comm[i] !== null && model[i] !== null ? comm[i] - model[i] : null;
    html += "<tr><td>Z" + z.id + " " + Hawa.esc(z.name) + "</td><td>" + n + "</td><td>" + cell(comm[i]) + "</td><td>" +
      cell(model[i]) + "</td><td>" + source[i] + "</td><td>" +
      (gap === null ? '<span class="muted">No data yet</span>' : (gap > 0 ? "+" : "") + gap) + "</td></tr>";
  });
  document.getElementById("vs-table").innerHTML = html + "</tbody>";
}

document.addEventListener("themechange", function () { if (rows.length) renderCharts(); });
