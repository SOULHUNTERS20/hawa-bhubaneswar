/* hotspots.js - SOP step 9: report a hotspot and show the public register. */

var pid = Hawa.getId();
var typeSelect = document.getElementById("hs-type");

if (pid) {
  document.getElementById("hs-zone").value = Hawa.zoneFromId(pid) || 1;
} else {
  document.getElementById("no-id-note").classList.remove("hidden");
}

typeSelect.addEventListener("change", function () {
  var m = window.HS_METHODS[typeSelect.value];
  document.getElementById("hs-method").textContent = m ? "Student verification: " + m : "";
});

function statusChip(s) {
  var cls = s === "Verified" ? "alert-ok" : s === "Not confirmed" ? "alert-error" : "alert-warn";
  return '<span class="alert ' + cls + '" style="padding:2px 10px;font-size:.8rem;border-radius:99px">' + Hawa.esc(s) + "</span>";
}

function loadRegister() {
  Hawa.getJSON("/api/hotspots").then(function (rows) {
    var body = document.getElementById("hs-rows");
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="6"><div class="empty">No hotspots reported yet. Be the first.</div></td></tr>';
      return;
    }
    body.innerHTML = rows.map(function (r) {
      var z = Hawa.zone(r.Zone);
      return "<tr><td>" + Hawa.esc(r.Timestamp) + "</td><td>" + (z ? "Z" + z.id + " " + Hawa.esc(z.name) : "") +
        "</td><td>" + Hawa.esc(r.Type) + '</td><td class="wrap-cell">' + Hawa.esc(r.Landmark) +
        '</td><td class="wrap-cell">' + Hawa.esc(r.Description) +
        (r["Verification note"] ? '<br><span class="muted small">Check: ' + Hawa.esc(r["Verification note"]) + "</span>" : "") +
        "</td><td>" + statusChip(r.Status) + "</td></tr>";
    }).join("");
  }).catch(function () {
    document.getElementById("hs-rows").innerHTML =
      '<tr><td colspan="6"><div class="empty">The register couldn\'t be loaded right now. Please reload the page.</div></td></tr>';
  });
}

document.getElementById("hotspot-form").addEventListener("submit", function (e) {
  e.preventDefault();
  var btn = document.getElementById("hs-btn");
  var msg = document.getElementById("hs-msg");
  btn.disabled = true;
  fetch("/api/hotspot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      participant_id: pid,
      zone: Number(document.getElementById("hs-zone").value),
      type: typeSelect.value,
      landmark: document.getElementById("hs-landmark").value.trim(),
      description: document.getElementById("hs-desc").value.trim(),
      safe: document.getElementById("hs-safe").checked,
    }),
  })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.ok) {
        msg.innerHTML = '<div class="alert alert-ok">Thank you! Your report is in the register as “Reported” until students verify it.</div>';
        document.getElementById("hotspot-form").reset();
        document.getElementById("hs-zone").value = Hawa.zoneFromId(pid) || 1;
        document.getElementById("hs-method").textContent = "";
        loadRegister();
      } else {
        msg.innerHTML = '<div class="alert alert-error">' + (d.errors || ["Something went wrong."]).map(Hawa.esc).join("<br>") + "</div>";
      }
    })
    .catch(function () { msg.innerHTML = '<div class="alert alert-error">Could not reach the server.</div>'; })
    .finally(function () { btn.disabled = false; });
});

loadRegister();
