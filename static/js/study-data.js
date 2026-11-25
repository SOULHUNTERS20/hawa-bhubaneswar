/* study-data.js - the "Study results" part of the Data page (SOP steps 1-10).
   Uses /api/study-summary, which only contains group totals. */

(function () {
  var studyCharts = {};

  function setText(id, text, empty) {
    var el = document.getElementById(id);
    el.textContent = text;
    el.classList.toggle("empty", !!empty);
  }

  /** Simple horizontal bars: {label: count} -> HTML. */
  function bars(id, counts, opts) {
    opts = opts || {};
    var el = document.getElementById(id);
    var keys = Object.keys(counts || {});
    if (!keys.length) { el.innerHTML = '<div class="empty">No data yet.</div>'; return; }
    if (opts.order) keys = opts.order.filter(function (k) { return k in counts; }).concat(keys.filter(function (k) { return opts.order.indexOf(k) < 0; }));
    var max = Math.max.apply(null, keys.map(function (k) { return Number(counts[k]) || 0; })) || 1;
    el.innerHTML = keys.map(function (k) {
      var v = counts[k];
      var label = opts.label ? opts.label(k) : k;
      return '<div class="bd-row"><div class="bd-head"><span>' + Hawa.esc(label) + "</span><span>" +
        Hawa.esc(v === null ? "–" : v + (opts.unit || "")) + '</span></div><div class="bd-track"><div class="bd-fill" style="width:' +
        Math.round(100 * (Number(v) || 0) / max) + '%"></div></div></div>';
    }).join("");
  }

  function zoneLabel(z) {
    var zone = Hawa.zone(z);
    return zone ? "Zone " + zone.id + ": " + zone.name : "Zone " + z;
  }

  function render(s) {
    Hawa.chartDefaults();
    Object.keys(studyCharts).forEach(function (k) { studyCharts[k].destroy(); });

    // ---- Steps 1-6: participants ----
    var reg = s.registration;
    setText("s-reg", reg.count ? reg.count + " / " + reg.target : "None yet", !reg.count);
    setText("s-profiles", reg.complete_profiles ? String(reg.complete_profiles) : "None yet", !reg.complete_profiles);
    var demo = document.getElementById("s-demographics");
    var groups = [["Residential zone", "s-by-zone", reg.by_zone, { label: zoneLabel }],
                  ["Age group", "s-by-age", reg.by_age],
                  ["Gender", "s-by-gender", reg.by_gender],
                  ["Occupation", "s-by-occ", reg.by_occupation],
                  ["Workplace", "s-by-work", reg.by_workplace]];
    demo.innerHTML = groups.map(function (g) {
      return '<div><h4 class="small">' + g[0] + '</h4><div class="mini-bars" id="' + g[1] + '"></div></div>';
    }).join("");
    groups.forEach(function (g) { bars(g[1], g[2], g[3]); });

    // ---- Step 7: diaries ----
    var d = s.diary;
    setText("s-diarists", d.participants ? String(d.participants) : "None yet", !d.participants);
    setText("s-days", d.person_days ? String(d.person_days) : "None yet", !d.person_days);
    setText("s-paqe", d.mean_daily_paqe !== null ? String(Math.round(d.mean_daily_paqe)) : "No data yet", d.mean_daily_paqe === null);
    bars("s-location", d.share_by_location, { unit: "%" });
    var zonePaqe = {};
    Object.keys(d.mean_by_zone).forEach(function (z) { zonePaqe[z] = d.mean_by_zone[z] === null ? null : Math.round(d.mean_by_zone[z]); });
    bars("s-zone-paqe", zonePaqe, { label: zoneLabel, unit: " µg" });
    document.getElementById("s-completed").textContent = d.person_days
      ? d.completed + " participant(s) have completed all " + d.study_days + " diary days."
      : "";
    if (d.trend.length) {
      studyCharts.paqe = new Chart(document.getElementById("paqe-chart"), {
        type: "line",
        data: {
          labels: d.trend.map(function (t) { return t.date; }),
          datasets: [{ label: "Average daily PAQE (µg)", data: d.trend.map(function (t) { return t.mean; }),
            borderColor: Hawa.css("--accent"), backgroundColor: Hawa.css("--accent"), tension: 0.3 }],
        },
        options: { maintainAspectRatio: false, scales: { y: { beginAtZero: true, title: { display: true, text: "µg PM2.5 per day" } } },
          plugins: { legend: { display: false } } },
      });
    }

    // ---- Steps 8 + 10: DRS and persistence ----
    var sv = s.survey;
    var phases = sv.phase_order; // ["Before alerts", "After alerts"]
    var before = sv.phases[phases[0]], after = sv.phases[phases[phases.length - 1]];
    setText("s-drs-before", before.mean_drs !== null ? before.mean_drs.toFixed(2) : "No data yet", before.mean_drs === null);
    setText("s-drs-after", after.mean_drs !== null ? after.mean_drs.toFixed(2) : "No data yet", after.mean_drs === null);
    var yes = sv.persist.Yes || 0, no = sv.persist.No || 0;
    setText("s-persist", yes + no ? Math.round(100 * yes / (yes + no)) + "% (" + yes + " of " + (yes + no) + ")" : "No data yet", !(yes + no));
    document.getElementById("s-drs-note").textContent = sv.paired
      ? sv.paired + " participant(s) answered both times. Average change in DRS: " +
        (sv.mean_change >= 0 ? "+" : "") + sv.mean_change.toFixed(2) + " (1 = Never … 5 = Always). n = " +
        before.n + " before, " + after.n + " after."
      : "The before/after comparison appears once participants have answered both surveys.";
    if (before.n || after.n) {
      studyCharts.drs = new Chart(document.getElementById("drs-chart"), {
        type: "bar",
        data: {
          labels: window.Q_SHORT,
          datasets: [
            { label: phases[0], data: before.question_means, backgroundColor: "#8a94a6", borderRadius: 6 },
            { label: phases[phases.length - 1], data: after.question_means, backgroundColor: Hawa.css("--accent"), borderRadius: 6 },
          ],
        },
        options: {
          maintainAspectRatio: false,
          scales: { y: { min: 0, max: 5, title: { display: true, text: "Average answer (1 Never – 5 Always)" } } },
          plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } },
            tooltip: { callbacks: { title: function (items) { return sv.questions[items[0].dataIndex]; } } } },
        },
      });
    }
    bars("s-practices", sv.practices);

    // ---- Step 9: hotspots ----
    bars("s-hs-type", s.hotspots.by_type);
    bars("s-hs-status", s.hotspots.by_status, { order: ["Verified", "Reported", "Not confirmed"] });

    // ---- Spike check-ins ----
    var c = s.checkins;
    var yesApp = c.checked_app.Yes || 0, noApp = c.checked_app.No || 0;
    setText("c-count", c.count ? c.count + (c.spikes ? " (" + c.spikes + " days)" : "") : "None yet", !c.count);
    setText("c-checked", yesApp + noApp ? Math.round(100 * yesApp / (yesApp + noApp)) + "%" : "No data yet", !(yesApp + noApp));
    setText("c-anxiety", c.mean_anxiety !== null ? c.mean_anxiety.toFixed(1) : "No data yet", c.mean_anxiety === null);
    bars("c-changes", c.plan_changes);
    var split = {};
    if (c.anxiety_checked !== null) split["Looked at the app"] = c.anxiety_checked.toFixed(1);
    if (c.anxiety_not_checked !== null) split["Didn't look"] = c.anxiety_not_checked.toFixed(1);
    bars("c-anx-split", split);

    // ---- Daily survey (CSOD form) ----
    var f = s.form;
    document.getElementById("f-answered").textContent = f.answered
      ? f.answered + " readings came with answers about the person's day."
      : "No answers yet. They appear here when people fill in 'About your day' on the Submit page.";
    var SHORT = ["Likely to go out for coffee", "Likely to go cycling", "Likely to game indoors",
                 "Comfortable going outside", "AQI app changes my routine"];
    var scales = {};
    f.scales.forEach(function (q, i) { if (q.mean !== null) scales[SHORT[i] || q.question] = q.mean.toFixed(1); });
    bars("f-scales", scales);
    bars("f-activities", f.activities);
    bars("f-actions", f.poor_actions);
    bars("f-source", f.aqi_source);
    bars("f-trigger", f.app_trigger);
    bars("f-change", f.app_change);
    bars("f-sky", f.sky);
    bars("f-outside", f.went_outside);
    bars("f-place", f.study_place);
  }

  // ---- This week, zone by zone ----
  Hawa.getJSON("/api/insights").then(function (w) {
    document.getElementById("insights-range").textContent = "From " + w.from + " to " + w.to + ". Shared with participants every week.";
    document.getElementById("insights-headline").textContent = w.headline;
    document.getElementById("insights").innerHTML = w.zones.map(function (z) {
      return '<div class="insight"><h4><span>Zone ' + z.id + ": " + Hawa.esc(z.name) + "</span>" +
        (z.mean !== null ? Hawa.chip(z.mean) : "") + "</h4>" +
        (z.lines.length ? "<ul>" + z.lines.map(function (l) { return "<li>" + Hawa.esc(l) + "</li>"; }).join("") + "</ul>"
                        : '<p class="muted small" style="margin:0">Not enough data this week yet.</p>') + "</div>";
    }).join("");
  }).catch(function () {
    document.getElementById("insights").innerHTML = '<div class="empty">Weekly insights couldn\'t be loaded right now.</div>';
  });

  var latest = null;
  Hawa.getJSON("/api/study-summary").then(function (s) { latest = s; render(s); }).catch(function () {
    document.getElementById("study").insertAdjacentHTML("beforeend",
      '<div class="wrap"><div class="alert alert-error">Could not load the study results.</div></div>');
  });
  document.addEventListener("themechange", function () { if (latest) render(latest); });
})();
