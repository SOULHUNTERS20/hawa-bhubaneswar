/* home.js - fills in the stats, zone cards and "city right now" card. */

// 1) Community stats + latest reading per zone
Hawa.getJSON("/api/summary").then(function (data) {
  // Empty states instead of zeros
  setStat("stat-submissions", data.submissions, "None yet");
  setStat("stat-participants", data.participants, "Be the first");

  data.zones.forEach(function (z) {
    var slot = document.querySelector('.zone-card[data-zone="' + z.id + '"] .zone-slot');
    if (!z.latest) {
      slot.innerHTML = '<div class="empty">No data yet. <a href="/submit">Be the first to submit</a></div>';
      return;
    }
    var aqi = z.latest.effective_aqi;
    slot.innerHTML =
      '<div class="zone-reading">' +
        '<span class="num">' + Math.round(aqi) + "</span>" + Hawa.chip(aqi, false) +
      "</div>" +
      '<p class="muted small" style="margin:6px 0 0">Latest community reading · ' +
        Hawa.esc(z.latest.timestamp) + " · " + z.count + (z.count === 1 ? " reading" : " readings") +
      "</p>";
  });
}).catch(function () {
  document.querySelectorAll(".zone-slot").forEach(function (s) {
    s.innerHTML = '<div class="empty">Could not load community data.</div>';
  });
});

function setStat(id, value, emptyText) {
  var el = document.getElementById(id);
  if (value > 0) {
    el.textContent = value;
  } else {
    el.textContent = emptyText;
    el.classList.add("empty");
  }
}

// 2) Live city average from Open-Meteo
Hawa.getJSON("/api/live").then(function (live) {
  // Official station value where a zone has one, otherwise the model (same as the Advisory page)
  var values = live.zones.map(function (z) { return z.station && z.station.aqi != null ? z.station.aqi : z.aqi; })
                         .filter(function (v) { return v !== null && v !== undefined; });
  if (!values.length) {
    document.getElementById("now-aqi").textContent = "—";
    document.getElementById("now-meta").textContent = "Live data is unavailable right now.";
    return;
  }
  var avg = Math.round(values.reduce(function (a, b) { return a + b; }, 0) / values.length);
  var b = Hawa.band(avg);
  document.getElementById("now-aqi").textContent = avg;
  document.getElementById("now-band").innerHTML = Hawa.chip(avg, false);
  document.getElementById("now-stripe").style.background = b.color;
  document.getElementById("now-meta").innerHTML =
    "Average of the 5 zones (CPCB stations where available, otherwise the model). Updated "+ Hawa.esc(live.fetched_at) +
    (live.status === "stale" ? " · <b>showing last saved value</b>" : "") +
    ' · <a href="/live">See each zone →</a>';
}).catch(function () {
  document.getElementById("now-meta").textContent = "Live data is unavailable right now.";
});
