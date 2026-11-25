/* diary.js - SOP step 7: edit a day's time blocks, save it, show PAQE + alerts. */

var pid = Hawa.getId();
var tbody = document.getElementById("blocks");
var dateInput = document.getElementById("diary-date");

function hourText(h) {
  var hh = h % 24;
  var label = ((hh % 12) || 12) + " " + (hh < 12 ? "AM" : "PM");
  return h >= 24 ? label + " (next day)" : label;
}

function options(obj, selected, labelKey) {
  return Object.keys(obj).map(function (k) {
    return '<option value="' + k + '"' + (k === selected ? " selected" : "") + ">" + Hawa.esc(obj[k][labelKey] || obj[k].label) + "</option>";
  }).join("");
}

function hourOptions(from, to, selected) {
  var html = "";
  for (var h = from; h <= to; h++) {
    html += '<option value="' + h + '"' + (h === selected ? " selected" : "") + ">" + hourText(h) + "</option>";
  }
  return html;
}

function addRow(b) {
  b = b || { start: 6, end: 7, location: "home_open", activity: "indoor" };
  var tr = document.createElement("tr");
  tr.innerHTML =
    '<td><select class="b-start" aria-label="From">' + hourOptions(0, 23, b.start) + "</select></td>" +
    '<td><select class="b-end" aria-label="To">' + hourOptions(1, 36, b.end) + "</select></td>" +
    '<td><select class="b-loc" aria-label="Location">' + options(window.MICRO, b.location) + "</select></td>" +
    '<td><select class="b-act" aria-label="Activity">' + options(window.ACTS, b.activity) + "</select></td>" +
    '<td><button type="button" class="btn btn-sm btn-danger b-del" aria-label="Remove block">✕</button></td>';
  tr.querySelector(".b-del").addEventListener("click", function () { tr.remove(); });
  tbody.appendChild(tr);
}

function setBlocks(blocks) {
  tbody.innerHTML = "";
  blocks.forEach(addRow);
}

function readBlocks() {
  return Array.prototype.map.call(tbody.querySelectorAll("tr"), function (tr) {
    return {
      start: Number(tr.querySelector(".b-start").value),
      end: Number(tr.querySelector(".b-end").value),
      location: tr.querySelector(".b-loc").value,
      activity: tr.querySelector(".b-act").value,
    };
  });
}

function showProgress(logged, total) {
  document.getElementById("progress-text").textContent = logged + " of " + total + " days logged";
  document.getElementById("progress-bar").style.width = Math.min(100, Math.round(100 * logged / total)) + "%";
}

function fmt(v, unit) { return v === null || v === undefined || v === "" ? "–" : v + (unit || ""); }

function showResults(d) {
  document.getElementById("results").classList.remove("hidden");
  document.getElementById("results-title").textContent = "Your exposure on " + d.date + " (study day " + d.day_no + ")";
  document.getElementById("result-rows").innerHTML = d.rows.map(function (r) {
    return "<tr><td>" + Hawa.esc(r.time) + "</td><td>" + Hawa.esc(r.location_label) + "</td><td>" +
      Hawa.esc(r.activity_label) + "</td><td>" + r.hours + " h</td><td>" + fmt(r.outdoor, " µg/m³") + "</td><td>" +
      r.factor + "</td><td>" + fmt(r.micro, " µg/m³") + "</td><td>" + r.rate + " m³/h</td><td><b>" + fmt(r.paqe, " µg") + "</b></td></tr>";
  }).join("");
  document.getElementById("result-total").innerHTML = "Total PAQE for the day: <b>" + Math.round(d.total) +
    " µg</b> of PM2.5 inhaled.<br><span class=\"muted small\">Hourly PM2.5 source: " + Hawa.esc(d.source || "") + "</span>";
  document.getElementById("result-alerts").innerHTML = d.alerts.map(function (a) {
    return "<li>" + Hawa.esc(a) + "</li>";
  }).join("");
  showProgress(d.days_logged, d.study_days);
  document.getElementById("results").scrollIntoView({ behavior: "smooth" });
}

function loadDay() {
  document.getElementById("results").classList.add("hidden"); // results belong to the previous date
  fetch("/api/diary/" + encodeURIComponent(pid) + "?date=" + encodeURIComponent(dateInput.value)).then(function (r) {
    if (r.status === 404) {
      document.getElementById("no-id-note").classList.remove("hidden");
      document.getElementById("diary-card").classList.add("hidden");
      return;
    }
    if (!r.ok) throw new Error(r.status);
    return r.json().then(function (d) {
      setBlocks(d.blocks);
      showProgress(d.days_logged, d.study_days);
      document.getElementById("diary-msg").innerHTML = d.saved
        ? '<div class="alert alert-ok">You already saved this day. Saving again replaces it.</div>' : "";
    });
  }).catch(function () {
    if (!tbody.children.length) setBlocks(window.SOP_DAY);
    document.getElementById("progress-text").textContent = "";
    document.getElementById("diary-msg").innerHTML =
      '<div class="alert alert-error">Couldn\'t load your diary right now. Check your connection and reload the page.</div>';
  });
}

if (!pid) {
  document.getElementById("no-id-note").classList.remove("hidden");
  document.getElementById("diary-card").classList.add("hidden");
} else {
  loadDay();
  dateInput.addEventListener("change", loadDay);
  document.getElementById("add-block").addEventListener("click", function () { addRow(); });
  document.getElementById("sop-day").addEventListener("click", function () { setBlocks(window.SOP_DAY); });

  document.getElementById("save-diary").addEventListener("click", function () {
    var btn = this;
    btn.disabled = true;
    btn.textContent = "Calculating…";
    fetch("/api/diary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ participant_id: pid, date: dateInput.value, blocks: readBlocks() }),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.ok) {
          document.getElementById("diary-msg").innerHTML = '<div class="alert alert-ok">Saved! Day ' + d.day_no + " recorded.</div>";
          showResults(d);
        } else {
          document.getElementById("diary-msg").innerHTML = '<div class="alert alert-error">' + Hawa.esc(d.error) + "</div>";
        }
      })
      .catch(function () {
        document.getElementById("diary-msg").innerHTML = '<div class="alert alert-error">Could not reach the server.</div>';
      })
      .finally(function () { btn.disabled = false; btn.textContent = "Save day and calculate my PAQE"; });
  });
}
