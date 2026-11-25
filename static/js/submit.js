/* submit.js - the daily survey form.
   The browser does quick checks for a friendly experience, but the server
   (app.py -> api_submit) re-checks everything, because browsers can be bypassed. */

var form = document.getElementById("survey");
var msg = document.getElementById("form-msg");

// ---- Pre-fill the ID and zone from localStorage ----
var savedId = Hawa.getId();
if (savedId) {
  document.getElementById("participant_id").value = savedId;
  document.getElementById("zone").value = Hawa.zoneFromId(savedId) || 1;
} else {
  document.getElementById("no-id-alert").classList.remove("hidden");
}

// ---- Note character counter ----
var note = document.getElementById("note");
note.addEventListener("input", function () {
  document.getElementById("note-count").textContent = note.value.length;
});

// ---- "Use live temperature" button ----
document.getElementById("fill-temp").addEventListener("click", function () {
  var zoneId = Number(document.getElementById("zone").value);
  Hawa.getJSON("/api/live").then(function (live) {
    var z = live.zones.filter(function (x) { return x.zone_id === zoneId; })[0];
    if (z && z.temp !== null && z.temp !== undefined) document.getElementById("temp").value = z.temp;
    else alert("Live temperature isn't available right now.");
  }).catch(function () { alert("Live temperature isn't available right now."); });
});

function showMessage(kind, lines) {
  var body = lines.length === 1 ? Hawa.esc(lines[0])
    : "<ul>" + lines.map(function (l) { return "<li>" + Hawa.esc(l) + "</li>"; }).join("") + "</ul>";
  msg.innerHTML = '<div class="alert alert-' + kind + '">' + body + "</div>";
}

function checkRange(value, low, high, label, errors) {
  if (value === "") return;
  var n = Number(value);
  if (isNaN(n) || n < low || n > high) errors.push(label + " must be between " + low + " and " + high + ".");
}

// ---- "About your day" answers (CSOD form questions, all optional) ----
function picked(name) {
  var el = form.querySelector('input[name="' + name + '"]:checked');
  return el ? el.value : "";
}
function pickedAll(name) {
  return Array.prototype.map.call(form.querySelectorAll('input[name="' + name + '"]:checked'), function (el) { return el.value; });
}
function aboutYourDay() {
  var day = {
    aqi_source: document.getElementById("aqi_source").value,
    sky: picked("sky"), humidity: picked("humidity"), activities: pickedAll("activities"),
    study_place: picked("study_place"), went_outside: picked("went_outside"),
    app_trigger: picked("app_trigger"), poor_actions: pickedAll("poor_actions"), app_change: picked("app_change"),
  };
  form.querySelectorAll(".pills.scale").forEach(function (group) {
    var el = group.querySelector("input:checked");
    day[group.dataset.col] = el ? Number(el.value) : "";
  });
  return day;
}

// ---- Submit ----
form.addEventListener("submit", function (event) {
  event.preventDefault();
  var feel = form.querySelector('input[name="feel"]:checked');

  var payload = {
    participant_id: document.getElementById("participant_id").value.trim().toUpperCase(),
    zone: Number(document.getElementById("zone").value),
    aqi: document.getElementById("aqi").value,
    pm25: document.getElementById("pm25").value,
    temp: document.getElementById("temp").value,
    feel: feel ? feel.value : "",
    activity: document.getElementById("activity").value,
    note: note.value.trim(),
    consent: document.getElementById("consent").checked,
    day: aboutYourDay(),
  };

  // Quick browser-side checks
  var errors = [];
  if (!/^BBSR-Z[1-5]-\d{3}$/.test(payload.participant_id)) errors.push("Participant ID should look like BBSR-Z3-482.");
  checkRange(payload.aqi, 0, 500, "AQI", errors);
  checkRange(payload.pm25, 0, 999, "PM2.5", errors);
  checkRange(payload.temp, -5, 55, "Temperature", errors);
  if (!payload.feel) errors.push("Please choose how the air smells / feels.");
  if (!payload.activity) errors.push("Please choose what you were doing.");
  if (!payload.consent) errors.push("Please tick the consent box.");
  if (errors.length) { showMessage("error", errors); return; }

  var btn = document.getElementById("submit-btn");
  btn.disabled = true;
  btn.textContent = "Sending…";

  fetch("/api/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (!data.ok) { showMessage("error", data.errors || ["Something went wrong."]); return; }
      Hawa.setId(payload.participant_id); // remember the ID for next time
      var text = "Thank you! Your reading was saved.";
      if (data.flagged) text += " It is quite different from the live model value, so the team will double-check it (it is kept, not deleted).";
      showMessage("ok", [text]);
      form.reset();
      document.getElementById("participant_id").value = payload.participant_id;
      document.getElementById("zone").value = payload.zone;
      document.getElementById("note-count").textContent = "0";
      document.getElementById("no-id-alert").classList.add("hidden");
    })
    .catch(function () { showMessage("error", ["Could not reach the server. Please try again."]); })
    .finally(function () { btn.disabled = false; btn.textContent = "Submit reading"; });
});
