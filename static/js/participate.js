/* participate.js - progress through the SOP steps, the next step to do, and today's alert. */

var pid = Hawa.getId();
var CHECK = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="3" ' +
  'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5 10 17l9-10"/></svg>';

function step(name) { return document.querySelector('.tp-step[data-step="' + name + '"]'); }

// state: "done" | "current" (the next thing to do) | "locked" | "" (open, not done)
function setStep(name, state, status) {
  var el = step(name);
  el.classList.remove("done", "current", "locked");
  if (state) el.classList.add(state);
  if (state === "locked") el.setAttribute("aria-disabled", "true"); else el.removeAttribute("aria-disabled");
  var num = el.querySelector(".tp-num");
  if (!num.dataset.n) num.dataset.n = num.textContent;
  num.innerHTML = state === "done" ? CHECK : num.dataset.n;
  el.querySelector(".tp-status").textContent = status || "";
}

function todayISO() {
  var d = new Date();
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}

function setProgress(fraction) {
  var pct = Math.round(100 * Math.max(0, Math.min(1, fraction)));
  document.getElementById("tp-pct").textContent = pct + "%";
  document.getElementById("tp-bar-fill").style.width = pct + "%";
}

function showCount(s) {
  if (!s.target) return;
  document.getElementById("tp-count").textContent = s.count >= s.target
    ? s.count + " participants registered (target of " + s.target + " reached)."
    : s.count + " of " + s.target + " participants registered so far.";
}

function notRegistered(s) {
  setStep("register", "current", "Start");
  ["before", "diary", "after", "hotspot"].forEach(function (n) { setStep(n, "locked", ""); });
  setProgress(0);
  if (s) showCount(s);
}

function render(s) {
  showCount(s);
  document.getElementById("tp-id").textContent = s.id;
  document.getElementById("tp-days").textContent = s.days_logged + " / " + s.study_days + " days";

  var registered = s.profile_complete;
  var before = s.survey_phases.indexOf("Before alerts") >= 0;
  var after = s.survey_phases.indexOf("After alerts") >= 0;
  var diaryDone = s.days_logged >= s.study_days;
  var loggedToday = s.last_diary_date === todayISO();

  // The first unfinished core step is the one to do next.
  var order = [["register", registered], ["before", before], ["diary", diaryDone], ["after", after]];
  var next = null;
  order.forEach(function (o) { if (!o[1] && !next) next = o[0]; });

  setStep("register", registered ? "done" : "current", registered ? "Done" : "Finish profile");
  setStep("before", before ? "done" : (next === "before" ? "current" : ""), before ? "Done" : (next === "before" ? "Start" : "Day 1"));

  var diaryText = diaryDone ? "Done" : (loggedToday ? "Today ✓ · " : "") + s.days_logged + " / " + s.study_days;
  if (next === "diary" && !loggedToday) diaryText = s.days_logged ? "Log today" : "Start";
  setStep("diary", diaryDone ? "done" : (next === "diary" ? "current" : ""), diaryText);

  setStep("after", after ? "done" : (next === "after" ? "current" : ""), after ? "Done" : (next === "after" ? "Start" : "Day " + s.study_days));
  setStep("hotspot", s.hotspots > 0 ? "done" : "", s.hotspots > 0 ? s.hotspots + " reported" : "Optional");

  // Overall progress: the four core steps, with the diary counting day by day.
  setProgress(((registered ? 1 : 0) + (before ? 1 : 0) + Math.min(1, s.days_logged / s.study_days) + (after ? 1 : 0)) / 4);
}

// Locked steps do nothing until the participant is registered.
document.querySelectorAll(".tp-step").forEach(function (a) {
  a.addEventListener("click", function (e) { if (a.classList.contains("locked")) e.preventDefault(); });
});

// Pollution spike: invite registered participants to the 3-question check-in
function showSpike() {
  Hawa.getJSON("/api/spike").then(function (s) {
    if (!s.spike) return;
    document.getElementById("spike-aqi").innerHTML = Hawa.chip(s.aqi);
    document.getElementById("spike-card").classList.remove("hidden");
  }).catch(function () {});
}

// "This week in your zone"
function showWeek(zoneId) {
  Hawa.getJSON("/api/insights").then(function (w) {
    var z = w.zones.filter(function (x) { return x.id === zoneId; })[0];
    if (!z || !z.lines.length) return;
    document.getElementById("week-title").textContent = "This week in Zone " + z.id + ": " + z.name;
    document.getElementById("week-chip").innerHTML = z.mean !== null ? Hawa.chip(z.mean) : "";
    document.getElementById("week-lines").innerHTML = z.lines.map(function (l) { return "<li>" + Hawa.esc(l) + "</li>"; }).join("");
    document.getElementById("week-card").classList.remove("hidden");
  }).catch(function () {});
}

if (pid && Hawa.zoneFromId(pid)) {
  showSpike();
  showWeek(Hawa.zoneFromId(pid));
}

if (!pid) {
  notRegistered(null);
  Hawa.getJSON("/api/study/status/none").then(showCount).catch(function () {});
} else {
  Hawa.getJSON("/api/study/status/" + encodeURIComponent(pid)).then(function (s) {
    if (s.registered) render(s); else notRegistered(s);
  }).catch(function () {});

  // Today's personalized alert
  Hawa.getJSON("/api/alert/" + encodeURIComponent(pid)).then(function (a) {
    if (!a.ok || !a.alerts.length) return;
    document.getElementById("alert-card").classList.remove("hidden");
    document.getElementById("alert-list").innerHTML = a.alerts.map(function (t) {
      return "<li>" + Hawa.esc(t) + "</li>";
    }).join("");
    document.getElementById("alert-total").textContent =
      "Expected exposure for your usual day: about " + Math.round(a.total) + " µg of PM2.5";
  }).catch(function () {});
}
