/* ==========================================================================
   common.js - code shared by every page.
   Everything useful is put on one object called `Hawa` so the page scripts
   can call e.g. Hawa.band(150) or Hawa.getId().
   ========================================================================== */

var Hawa = (function () {
  // ---------- CPCB AQI bands ----------
  var BANDS = [
    { max: 50, name: "Good", color: "#1f9d55" },
    { max: 100, name: "Satisfactory", color: "#8cc63f" },
    { max: 200, name: "Moderate", color: "#f2c94c" },
    { max: 300, name: "Poor", color: "#f2994a" },
    { max: 400, name: "Very Poor", color: "#e03b2f" },
    { max: Infinity, name: "Severe", color: "#8e1b1b" },
  ];

  /** Returns {name, color} for an AQI number, or null if there is no number. */
  function band(aqi) {
    if (aqi === null || aqi === undefined || isNaN(aqi)) return null;
    for (var i = 0; i < BANDS.length; i++) {
      if (aqi <= BANDS[i].max) return BANDS[i];
    }
  }

  /** HTML for a coloured AQI chip, e.g. "142 · Moderate". */
  function chip(aqi, withNumber) {
    var b = band(aqi);
    if (!b) return '<span class="aqi-chip">No data</span>';
    var text = withNumber === false ? b.name : Math.round(aqi) + " · " + b.name;
    return '<span class="aqi-chip" data-band="' + b.name + '">' + text + "</span>";
  }

  // CPCB PM2.5 breakpoints [conc low, conc high, AQI low, AQI high] (same as airquality.py)
  var PM25 = [[0, 30, 0, 50], [30, 60, 50, 100], [60, 90, 100, 200],
              [90, 120, 200, 300], [120, 250, 300, 400], [250, 380, 400, 500]];

  function aqiFromPm25(c) {
    if (c === null || c === undefined || isNaN(c)) return null;
    c = Math.max(0, c);
    for (var i = 0; i < PM25.length; i++) {
      var b = PM25[i];
      if (c <= b[1]) return Math.round(b[2] + (b[3] - b[2]) * (c - b[0]) / (b[1] - b[0]));
    }
    return 500;
  }

  function pm25FromAqi(aqi) {
    aqi = Math.max(0, Math.min(500, aqi));
    for (var i = 0; i < PM25.length; i++) {
      var b = PM25[i];
      if (aqi <= b[3]) return b[0] + (b[1] - b[0]) * (aqi - b[2]) / (b[3] - b[2]);
    }
    return 380;
  }

  // ---------- Zones ----------
  var zones = window.HAWA_ZONES || [];
  function zone(id) {
    for (var i = 0; i < zones.length; i++) if (zones[i].id === Number(id)) return zones[i];
    return null;
  }

  // ---------- Safe text ----------
  /** Always use this before putting user-typed text into HTML. */
  function esc(text) {
    return String(text === null || text === undefined ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // ---------- Fetch JSON helper ----------
  function getJSON(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error("Request failed: " + r.status);
      return r.json();
    });
  }

  // ---------- Participant ID in localStorage ----------
  var ID_KEY = "hawa-participant-id";
  function getId() {
    try { return localStorage.getItem(ID_KEY); } catch (e) { return null; }
  }
  function setId(id) {
    try { localStorage.setItem(ID_KEY, id); } catch (e) {}
  }
  function clearId() {
    try { localStorage.removeItem(ID_KEY); } catch (e) {}
  }
  /** "BBSR-Z3-482" -> 3 */
  function zoneFromId(id) {
    var m = /^BBSR-Z(\d)-/.exec(id || "");
    return m ? Number(m[1]) : null;
  }

  // ---------- Chart.js colours that follow light/dark mode ----------
  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  // One clearly different colour per zone (Z1..Z5) for line charts
  var ZONE_COLORS = ["#1f6fc5", "#e07b00", "#7b3fbf", "#2e9e48", "#c2255c"];

  function chartDefaults() {
    if (!window.Chart) return;
    Chart.defaults.color = css("--muted");
    Chart.defaults.borderColor = css("--border");
    Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  }

  return {
    BANDS: BANDS, band: band, chip: chip, aqiFromPm25: aqiFromPm25, pm25FromAqi: pm25FromAqi,
    zones: zones, zone: zone, esc: esc, getJSON: getJSON,
    getId: getId, setId: setId, clearId: clearId, zoneFromId: zoneFromId,
    css: css, ZONE_COLORS: ZONE_COLORS, chartDefaults: chartDefaults,
  };
})();

// ---------- Dark mode toggle ----------
document.getElementById("theme-toggle").addEventListener("click", function () {
  var root = document.documentElement;
  var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
  root.setAttribute("data-theme", next);
  try { localStorage.setItem("hawa-theme", next); } catch (e) {}
  // Pages with charts/maps listen for this to recolour themselves.
  document.dispatchEvent(new CustomEvent("themechange", { detail: next }));
});

// ---------- Narrow screens: scroll the link row so the current page is visible ----------
(function () {
  var nav = document.getElementById("nav");
  var active = nav && nav.querySelector("a.active");
  if (active && active.offsetLeft + active.offsetWidth > nav.clientWidth - 36) {
    nav.scrollLeft = active.offsetLeft - (nav.clientWidth - active.offsetWidth) / 2;
  }
})();

// ---------- Show the saved ID in the nav ("My ID" -> "BBSR-Z3-482") ----------
(function () {
  var id = Hawa.getId();
  var link = document.getElementById("nav-id-link");
  if (id && link) link.textContent = id;
})();
