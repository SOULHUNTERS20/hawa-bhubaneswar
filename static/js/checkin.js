/* checkin.js - the 3-question pollution spike check-in (CSOD Phase 3 micro-survey). */

var pid = Hawa.getId();
var form = document.getElementById("checkin-form");
var msg = document.getElementById("checkin-msg");

if (!pid) {
  document.getElementById("no-id-note").classList.remove("hidden");
  form.classList.add("hidden");
}

// Current city AQI, for context
Hawa.getJSON("/api/spike").then(function (s) {
  var box = document.getElementById("checkin-now");
  if (s.aqi === null) { box.innerHTML = ""; return; }
  box.innerHTML = "City AQI right now: <b>" + s.aqi + "</b> " + Hawa.chip(s.aqi, false);
}).catch(function () { document.getElementById("checkin-now").innerHTML = ""; });

// "No change" and the other answers exclude each other
form.querySelectorAll('input[name="changes"]').forEach(function (box) {
  box.addEventListener("change", function () {
    if (!box.checked) return;
    form.querySelectorAll('input[name="changes"]').forEach(function (other) {
      if (other !== box && (box.value === "No change" || other.value === "No change")) other.checked = false;
    });
  });
});

function show(kind, lines) {
  msg.innerHTML = '<div class="alert alert-' + kind + '">' + lines.map(Hawa.esc).join("<br>") + "</div>";
}

form.addEventListener("submit", function (e) {
  e.preventDefault();
  var checked = form.querySelector('input[name="checked"]:checked');
  var anxiety = form.querySelector('input[name="anxiety"]:checked');
  var changes = Array.prototype.map.call(form.querySelectorAll('input[name="changes"]:checked'), function (b) { return b.value; });
  var errors = [];
  if (!checked) errors.push("Please answer question 1.");
  if (!changes.length) errors.push("Please answer question 2 (choose 'No change' if nothing changed).");
  if (!anxiety) errors.push("Please answer question 3.");
  if (errors.length) return show("error", errors);

  var btn = document.getElementById("checkin-btn");
  btn.disabled = true;
  fetch("/api/checkin", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ participant_id: pid, checked_app: checked.value, plan_changes: changes, anxiety: Number(anxiety.value) }),
  })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.ok) {
        form.reset();
        show("ok", ["Thank you! Your check-in was saved."]);
      } else {
        show("error", d.errors || ["Something went wrong."]);
      }
    })
    .catch(function () { show("error", ["Could not reach the server. Please try again."]); })
    .finally(function () { btn.disabled = false; });
});
