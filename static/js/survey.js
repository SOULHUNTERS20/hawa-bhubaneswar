/* survey.js - SOP steps 8 and 10: Likert questions -> DRS, plus the persistence question. */

var pid = Hawa.getId();
var surveyForm = document.getElementById("survey-form");

// Open the right phase from the Take part page (?phase=after)
if (/phase=after/.test(location.search)) {
  var radios = document.querySelectorAll('input[name="phase"]');
  radios[radios.length - 1].checked = true;
}

function phase() {
  var r = document.querySelector('input[name="phase"]:checked');
  return r ? r.value : "";
}

function togglePersist() {
  document.getElementById("persist-field").classList.toggle("hidden", phase() !== window.LAST_PHASE);
}
document.querySelectorAll('input[name="phase"]').forEach(function (r) { r.addEventListener("change", togglePersist); });
togglePersist();

function show(kind, html) {
  document.getElementById("survey-msg").innerHTML = '<div class="alert alert-' + kind + '">' + html + "</div>";
}

if (!pid) {
  document.getElementById("no-id-note").classList.remove("hidden");
  surveyForm.classList.add("hidden");
}

surveyForm.addEventListener("submit", function (e) {
  e.preventDefault();
  var answers = [];
  for (var i = 1; i <= window.Q_COUNT; i++) {
    var picked = document.querySelector('input[name="q' + i + '"]:checked');
    answers.push(picked ? Number(picked.value) : null);
  }
  if (answers.indexOf(null) >= 0) { show("error", "Please answer every question."); return; }
  var persist = document.querySelector('input[name="persist"]:checked');
  var payload = {
    participant_id: pid,
    phase: phase(),
    answers: answers,
    practices: Array.prototype.map.call(document.querySelectorAll('input[name="practice"]:checked'), function (c) { return c.value; }),
    persist: persist ? persist.value : "",
  };
  var btn = document.getElementById("survey-btn");
  btn.disabled = true;
  fetch("/api/survey", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d.ok) { show("error", (d.errors || ["Something went wrong."]).map(Hawa.esc).join("<br>")); return; }
      var text = "Saved! Your Decision Responsiveness Score (DRS) is <b>" + d.drs.toFixed(2) + " / 5</b>.";
      if (d.change !== null && d.change !== undefined) {
        text += " That is <b>" + (d.change >= 0 ? "+" : "") + d.change.toFixed(2) + "</b> compared with before the alerts.";
      }
      show("ok", text);
    })
    .catch(function () { show("error", "Could not reach the server."); })
    .finally(function () { btn.disabled = false; });
});
