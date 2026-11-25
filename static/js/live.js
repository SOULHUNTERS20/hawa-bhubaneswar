/* live.js - shows official station data (where a zone has a station)
   and the Open-Meteo model estimate for each zone. */

var chart = null;
var liveData = null;

Hawa.getJSON("/api/live").then(function (live) {
  liveData = live;
  renderStatus(live);
  renderCards(live);
  renderChart(live);
}).catch(function () {
  renderStatus({ status: "unavailable", zones: [] });
});

function renderStatus(live) {
  var bar = document.getElementById("status-bar");
  if (live.status === "unavailable" || !live.zones.length) {
    bar.innerHTML = '<span class="dot off"></span> Live data is unavailable right now and nothing has been saved yet. Please try again later.';
    document.getElementById("live-grid").innerHTML = '<div class="empty">No live data yet.</div>';
    return;
  }
  var html;
  if (live.status === "stale") {
    html = '<span class="dot stale"></span> The satellite model (Open-Meteo) is busy right now, so model values are from <b>' +
      Hawa.esc(live.fetched_at) + "</b>.";
  } else {
    html = '<span class="dot"></span> Updated <b>' + Hawa.esc(live.fetched_at) +
      '</b> <span class="muted">· refreshes every 30 minutes</span>';
  }

  // Official station status
  var notes = {
    no_key: "Official station data isn't connected yet, so every zone shows the model estimate.",
    error: "OpenAQ (official stations) could not be reached. Station values shown are from earlier.",
    not_found: "The Bhubaneswar stations sent no usable reading this time, so every zone shows the model estimate.",
  };
  if (notes[live.station_status]) {
    html += '<div class="muted small" style="width:100%">' + notes[live.station_status] + "</div>";
  }

  // The model works on a coarse grid, so nearby zones often get identical values.
  var pm = live.zones.map(function (z) { return z.pm25_24h; });
  if (pm.every(function (v) { return v === pm[0]; })) {
    html += '<div class="alert alert-warn" style="width:100%">The model puts all five zones in the same ~40 km grid square, ' +
      "so it gives them the same value. Only zones 3 and 5 have an official monitor. Community readings are the only " +
      "way to see the differences between neighbourhoods. That is the point of this project.</div>";
  }
  bar.innerHTML = html;
}

function fmt(value, unit) {
  return value === null || value === undefined ? "–" : Math.round(value * 10) / 10 + (unit || "");
}

function bigNumber(aqi) {
  var b = Hawa.band(aqi);
  return '<div style="display:flex;align-items:baseline;gap:10px">' +
      '<span class="big">' + (aqi !== null && aqi !== undefined ? aqi : "–") + "</span>" + Hawa.chip(aqi, false) +
    "</div>" +
    '<div class="band-bar"' + (b ? ' data-band="' + b.name + '"' : "") + "></div>";
}

function renderCards(live) {
  var html = "";
  live.zones.forEach(function (lz) {
    var z = Hawa.zone(lz.zone_id);
    var s = lz.station;
    html += '<article class="card live-card">' +
      '<div class="zone-top"><span class="zone-num">' + z.id + '</span><span class="tag">' + Hawa.esc(z.type) + "</span></div>" +
      '<h3 style="margin:10px 0 8px">' + Hawa.esc(z.name) + "</h3>";

    if (s) {
      // ---- Zone with an official station: station first, model second ----
      html += '<div class="source-label">Official CPCB station</div>' +
        bigNumber(s.aqi) +
        '<div class="muted small">' + Hawa.esc(s.name) + "<br>Updated " + Hawa.esc(s.updated || "–") +
          (s.stale ? " · <b>older value</b>" : "") + "</div>" +
        '<div class="kv">' +
          "<div><span>PM2.5 (latest hour)</span><b>" + fmt(s.pm25, " µg/m³") + "</b></div>" +
          "<div><span>PM10 (latest hour)</span><b>" + fmt(s.pm10, " µg/m³") + "</b></div>" +
        "</div>" +
        '<div class="model-line"><span>Model estimate</span>' + Hawa.chip(lz.aqi) +
          '<span class="muted">' + fmt(lz.temp, " °C") + "</span></div>";
    } else {
      // ---- Zone without a station: model only ----
      html += '<div class="source-label">Model estimate</div>' +
        bigNumber(lz.aqi) +
        '<div class="kv">' +
          "<div><span>PM2.5 now</span><b>" + fmt(lz.pm25_now, " µg/m³") + "</b></div>" +
          "<div><span>PM2.5 24h avg</span><b>" + fmt(lz.pm25_24h, " µg/m³") + "</b></div>" +
          "<div><span>PM10 now</span><b>" + fmt(lz.pm10_now, " µg/m³") + "</b></div>" +
          "<div><span>Temperature</span><b>" + fmt(lz.temp, " °C") + "</b></div>" +
        "</div>" +
        '<div class="model-line muted small">' +
          (z.station ? "Official station has no reading right now." : "No official monitor in this zone.") +
        "</div>";
    }
    html += "</article>";
  });
  document.getElementById("live-grid").innerHTML = html;
}

function renderChart(live) {
  if (!live.zones.length) return;
  Hawa.chartDefaults();
  var labels = live.zones[0].hourly.time;
  var datasets = live.zones.map(function (lz, i) {
    return {
      label: "Zone " + lz.zone_id + ": " + Hawa.zone(lz.zone_id).name,
      data: lz.hourly.pm25,
      borderColor: Hawa.ZONE_COLORS[i],
      backgroundColor: Hawa.ZONE_COLORS[i],
      tension: 0.35,
      pointRadius: 0,
      borderWidth: 2,
    };
  });
  if (chart) chart.destroy();
  chart = new Chart(document.getElementById("pm-chart"), {
    type: "line",
    data: { labels: labels, datasets: datasets },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: { y: { beginAtZero: true, title: { display: true, text: "PM2.5 (µg/m³)" } } },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
    },
  });
}

// Redraw the chart in the new colours when dark mode is toggled
document.addEventListener("themechange", function () { if (liveData) renderChart(liveData); });
