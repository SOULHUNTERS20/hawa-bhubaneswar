/* map.js - Leaflet map with one coloured marker per zone. */

// ---- 1. Create the map centred on Bhubaneswar ----
var map = L.map("map", { scrollWheelZoom: false }).setView([20.31, 85.83], 12);

// Free OpenStreetMap tiles. In dark mode, style.css inverts their colours.
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

// ---- 2. Load community + live data, then draw markers ----
var summary = null;
var live = null;
var mode = "community";
var markers = [];

Promise.all([
  Hawa.getJSON("/api/summary"),
  Hawa.getJSON("/api/live").catch(function () { return { zones: [], status: "unavailable" }; }),
]).then(function (results) {
  summary = results[0];
  live = results[1];
  drawMarkers();
  var note = live.fetched_at ? "Live model data updated " + live.fetched_at + "." : "Live model data unavailable.";
  if (live.status === "stale") note += " Showing the last saved value.";
  document.getElementById("map-note").textContent = note;
}).catch(function () {
  document.getElementById("map-note").textContent = "Zone data couldn't be loaded right now. Please reload the page.";
});

function liveFor(zoneId) {
  for (var i = 0; i < live.zones.length; i++) if (live.zones[i].zone_id === zoneId) return live.zones[i];
  return null;
}

function drawMarkers() {
  markers.forEach(function (m) { map.removeLayer(m); });
  markers = [];

  summary.zones.forEach(function (z) {
    var liveZone = liveFor(z.id);
    var communityAqi = z.latest ? z.latest.effective_aqi : null;
    // "Official / model": the CPCB station value if the zone has one, else the model
    var liveAqi = null;
    if (liveZone) liveAqi = liveZone.station ? liveZone.station.aqi : liveZone.aqi;
    var shown = mode === "community" ? communityAqi : liveAqi;
    var b = Hawa.band(shown);

    // A round marker made of HTML so we can colour it with the CPCB band
    var icon = L.divIcon({
      className: "",
      html: '<div class="map-marker"' + (b ? ' data-band="' + b.name + '"' : "") + ">" +
            (shown !== null ? Math.round(shown) : "–") + "</div>",
      iconSize: [40, 40],
      iconAnchor: [20, 20],
      popupAnchor: [0, -20],
    });

    var marker = L.marker([z.lat, z.lon], { icon: icon, title: z.name })
      .addTo(map)
      .bindPopup(popupHtml(z, liveZone));
    markers.push(marker);
  });
}

function popupHtml(z, liveZone) {
  var html = '<div class="popup"><h4>Zone ' + z.id + ": " + Hawa.esc(z.name) + "</h4>" +
    '<div class="muted small">' + Hawa.esc(z.type) + "</div>" +
    (liveZone && liveZone.station
      ? '<p style="margin:8px 0 2px">Official CPCB station: ' + Hawa.chip(liveZone.station.aqi) +
        '<br><span class="muted small">' + Hawa.esc(liveZone.station.name) + "</span></p>"
      : '<p style="margin:8px 0 2px" class="muted small">No official monitor in this zone</p>') +
    '<p style="margin:2px 0 8px">Model estimate: ' + (liveZone ? Hawa.chip(liveZone.aqi) : "unavailable") + "</p>";

  if (!z.recent.length) {
    html += '<div class="empty">No data yet. <a href="/submit">Be the first to submit</a></div>';
  } else {
    html += "<b>Latest community readings</b>";
    z.recent.forEach(function (r) {
      html += '<div class="reading small">' +
        "<div>" + Hawa.esc(r.timestamp) + " · " + (r.effective_aqi !== null ? Hawa.chip(r.effective_aqi) : "no AQI") + "</div>" +
        "<div>" + (r.pm25 !== null ? "PM2.5 " + r.pm25 + " µg/m³ · " : "") +
                 (r.temp !== null ? r.temp + "°C · " : "") + Hawa.esc(r.feel) + "</div>" +
        (r.note ? '<div class="muted">“' + Hawa.esc(r.note) + "”</div>" : "") +
        "</div>";
    });
  }
  return html + "</div>";
}

// ---- 3. Community / live toggle ----
document.querySelectorAll(".segmented button").forEach(function (btn) {
  btn.addEventListener("click", function () {
    document.querySelectorAll(".segmented button").forEach(function (b) { b.classList.remove("on"); });
    btn.classList.add("on");
    mode = btn.getAttribute("data-mode");
    if (summary) drawMarkers();
  });
});
