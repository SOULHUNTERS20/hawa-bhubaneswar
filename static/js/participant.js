/* participant.js - SOP steps 1-6: consent + registration (anonymous ID and profile),
   linking an existing ID, and completing the profile of an older ID. */

var form = document.getElementById("profile-form");
var needsProfile = false; // true when this browser has an older ID without a profile

function message(elId, kind, text) {
  document.getElementById(elId).innerHTML = text ? '<div class="alert alert-' + kind + '">' + text + "</div>" : "";
}

function showState() {
  var id = Hawa.getId();
  document.getElementById("has-id").classList.toggle("hidden", !id);
  form.classList.toggle("hidden", !!id && !needsProfile);
  document.getElementById("zone-field").classList.toggle("hidden", !!id);
  document.getElementById("form-title").textContent = id ? "Complete your profile" : "Get my ID";
  document.getElementById("get-id-btn").textContent = id ? "Save my profile" : "Get my ID";
  if (id) {
    var z = Hawa.zone(Hawa.zoneFromId(id));
    document.getElementById("id-value").textContent = id;
    document.getElementById("id-zone").textContent = z ? "Zone " + z.id + ": " + z.name : "";
  }
  var link = document.getElementById("nav-id-link");
  if (link) link.textContent = id || "My ID";
}

// Does the saved ID still need its SOP profile?
function checkProfile() {
  var id = Hawa.getId();
  if (!id) { needsProfile = false; showState(); return; }
  fetch("/api/participant/" + encodeURIComponent(id)).then(function (r) {
    if (r.status === 404) {
      // The ID saved in this browser no longer exists on the server (e.g. removed by the team)
      Hawa.clearId();
      needsProfile = false;
      message("new-msg", "warn", "The ID saved on this device (" + Hawa.esc(id) + ") is no longer registered. Please register again.");
      showState();
      return;
    }
    return r.json().then(function (d) {
      needsProfile = d.exists && !d.profile_complete;
      showState();
    });
  }).catch(showState); // offline: keep the saved ID
}

function loadCount() {
  Hawa.getJSON("/api/study/status/none").then(function (d) {
    var pct = Math.min(100, Math.round(100 * d.count / d.target));
    document.getElementById("reg-bar").style.width = pct + "%";
    document.getElementById("reg-count").textContent = d.count >= d.target
      ? d.count + " participants registered (target of " + d.target + " reached)"
      : d.count + " of " + d.target + " participants registered";
  }).catch(function () {
    document.getElementById("reg-count").textContent = "";
  });
}

// ---- Register (new ID) or save the profile (existing ID) ----
form.addEventListener("submit", function (e) {
  e.preventDefault();
  var id = Hawa.getId();
  var btn = document.getElementById("get-id-btn");
  var payload = {
    zone: Number(document.getElementById("new-zone").value),
    age_group: document.getElementById("age_group").value,
    gender: document.getElementById("gender").value,
    occupation: document.getElementById("occupation").value,
    workplace: document.getElementById("workplace").value,
    consent: document.getElementById("consent").checked,
  };
  btn.disabled = true;
  fetch(id ? "/api/participant/" + encodeURIComponent(id) + "/profile" : "/api/participant", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.id || data.ok) {
        if (data.id) Hawa.setId(data.id);
        needsProfile = false;
        message("new-msg", "", "");
        showState();
        loadCount();
      } else {
        var list = (data.errors || [data.error || "Something went wrong."]).map(Hawa.esc);
        message("new-msg", "error", list.join("<br>"));
      }
    })
    .catch(function () { message("new-msg", "error", "Could not reach the server. Please try again."); })
    .finally(function () { btn.disabled = false; });
});

// ---- Link an existing ID ----
document.getElementById("link-btn").addEventListener("click", function () {
  var id = document.getElementById("link-input").value.trim().toUpperCase();
  if (!/^BBSR-Z[1-5]-\d{3}$/.test(id)) {
    message("link-msg", "error", "IDs look like BBSR-Z3-482.");
    return;
  }
  fetch("/api/participant/" + encodeURIComponent(id))
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.exists) {
        Hawa.setId(data.id);
        needsProfile = !data.profile_complete;
        message("link-msg", "ok", "Linked! " + Hawa.esc(data.id) + " is now saved on this device.");
        showState();
      } else {
        message("link-msg", "error", "We couldn't find that ID. Check for typos.");
      }
    })
    .catch(function () { message("link-msg", "error", "Could not reach the server."); });
});

// ---- Copy + forget ----
document.getElementById("copy-btn").addEventListener("click", function () {
  var btn = this;
  navigator.clipboard.writeText(Hawa.getId()).then(function () {
    btn.textContent = "Copied ✓";
    setTimeout(function () { btn.textContent = "Copy ID"; }, 1500);
  });
});

document.getElementById("forget-btn").addEventListener("click", function () {
  if (confirm("Remove this ID from this browser? Your past data stays in the study. Write the ID down first if you want to link it again.")) {
    Hawa.clearId();
    needsProfile = false;
    showState();
  }
});

showState();
checkProfile();
loadCount();
