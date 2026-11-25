/* admin.js - the admin panel's table editor: search, filter, edit, delete, withdraw. */

var PAGE_SIZE = 50;
var state = { name: "readings", data: null, rows: [], page: 0, editing: null };

var $ = function (id) { return document.getElementById(id); };
var esc = Hawa.esc;

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------
function toast(text) {
  var t = $("toast");
  t.textContent = text;
  t.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(function () { t.classList.add("hidden"); }, 2600);
}

function post(url, body) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(function (r) {
    return r.json().catch(function () { return { ok: false, error: "Unexpected server reply." }; });
  });
}

// Diary rows store keys like "home_open"; show the readable label instead.
function display(column, value) {
  if (state.name === "diary" && ADMIN.labels[column] && ADMIN.labels[column][value]) {
    return ADMIN.labels[column][value].label;
  }
  return value;
}

function zoneOf(row) {
  if (row.Zone) return row.Zone;
  var m = /^BBSR-Z(\d)/.exec(row["Participant ID"] || "");
  return m ? m[1] : "";
}

// ---------------------------------------------------------------------------
// Filters for each table
// ---------------------------------------------------------------------------
function filtersFor(name) {
  var list = [{ label: "All rows", test: function () { return true; } }];
  if (name === "readings") list.push({ label: "Flagged only", test: function (r) { return !!r.Flag; } });
  if (name === "hotspots") {
    ["Reported", "Verified", "Not confirmed"].forEach(function (s) {
      list.push({ label: s === "Reported" ? "Waiting for verification" : s, test: function (r) { return r.Status === s; } });
    });
  }
  if (name === "survey") {
    ["Before alerts", "After alerts"].forEach(function (p) {
      list.push({ label: p, test: function (r) { return r.Phase === p; } });
    });
  }
  Hawa.zones.forEach(function (z) {
    list.push({ label: "Zone " + z.id + ": " + z.name, test: function (r) { return zoneOf(r) === String(z.id); } });
  });
  return list;
}

// ---------------------------------------------------------------------------
// Loading and drawing a table
// ---------------------------------------------------------------------------
function load(name) {
  state.name = name;
  state.page = 0;
  document.querySelectorAll(".admin-tabs button").forEach(function (b) {
    b.setAttribute("aria-selected", b.dataset.table === name ? "true" : "false");
  });
  $("admin-export").href = ADMIN.exports[name];
  $("admin-search").value = "";
  var filters = filtersFor(name);
  $("admin-filter").innerHTML = filters.map(function (f, i) {
    return '<option value="' + i + '">' + esc(f.label) + "</option>";
  }).join("");
  $("admin-tbody").innerHTML = '<tr><td class="muted">Loading…</td></tr>';

  Hawa.getJSON("/admin/api/" + name).then(function (d) {
    if (!d.ok) throw new Error(d.error);
    state.data = d;
    state.data.rows.reverse(); // newest first
    draw();
  }).catch(function (e) {
    $("admin-tbody").innerHTML = '<tr><td class="muted">Could not load this table. ' +
      (e && /401/.test(e.message) ?'Your session ended: <a href="">sign in again</a>.' : "Reload the page to try again.") +
      "</td></tr>";
  });
}

function visibleRows() {
  var q = $("admin-search").value.trim().toLowerCase();
  var filter = filtersFor(state.name)[Number($("admin-filter").value) || 0];
  return state.data.rows.filter(function (item) {
    if (!filter.test(item.row)) return false;
    if (!q) return true;
    return state.data.show.some(function (c) {
      return String(display(c, item.row[c]) || "").toLowerCase().indexOf(q) >= 0;
    });
  });
}

function draw() {
  var d = state.data;
  var rows = visibleRows();
  var pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  state.page = Math.min(state.page, pages - 1);
  var slice = rows.slice(state.page * PAGE_SIZE, (state.page + 1) * PAGE_SIZE);

  $("admin-thead").innerHTML = "<tr>" + d.show.map(function (c) { return "<th>" + esc(c) + "</th>"; }).join("") + "</tr>";
  if (!rows.length) {
    $("admin-tbody").innerHTML = '<tr><td colspan="' + d.show.length + '"><div class="empty">' +
      (d.rows.length ? "No rows match." : "Nothing here yet.") + "</div></td></tr>";
  } else {
    $("admin-tbody").innerHTML = slice.map(function (item) {
      var r = item.row;
      var cls = (r.Flag ? "flagged " : "") + (r.Status === "Reported" ? "pending" : "");
      return '<tr tabindex="0" data-i="' + item.i + '" class="' + cls + '">' + d.show.map(function (c) {
        var v = display(c, r[c]);
        if (c === "Status" && v) v = '<span class="status-pill" data-status="' + esc(v) + '">' + esc(v) + "</span>";
        else v = esc(v);
        return '<td class="' + (c === "Note" || c === "Description" || c === "Flag" || c === "Landmark" ? "wrap-cell" : "") + '">' + v + "</td>";
      }).join("") + "</tr>";
    }).join("");
  }
  $("admin-count").textContent = rows.length === d.rows.length
    ? d.rows.length + " rows" : rows.length + " of " + d.rows.length + " rows";
  $("page-info").textContent = "Page " + (state.page + 1) + " of " + pages;
  $("page-prev").disabled = state.page === 0;
  $("page-next").disabled = state.page >= pages - 1;
}

function findItem(i) {
  return state.data.rows.filter(function (item) { return item.i === i; })[0];
}

// ---------------------------------------------------------------------------
// Edit dialog
// ---------------------------------------------------------------------------
function fieldHtml(column, rule, value) {
  var id = "f-" + column.replace(/[^a-z0-9]/gi, "_");
  var input;
  if (rule.type === "choice") {
    var labels = state.name === "diary" ? ADMIN.labels[column] : null;
    input = '<select id="' + id + '" data-col="' + esc(column) + '">' + rule.options.map(function (o) {
      var text = labels && labels[o] ? labels[o].label : (o === "" ? "Not answered" : o);
      if (column === "Zone") text = "Zone " + o + ": " + Hawa.zone(Number(o)).name;
      return '<option value="' + esc(o) + '"' + (o === value ? " selected" : "") + ">" + esc(text) + "</option>";
    }).join("") + "</select>";
  } else if (rule.type === "number") {
    input = '<input type="number" id="' + id + '" data-col="' + esc(column) + '" value="' + esc(value) + '" min="' +
      rule.min + '" max="' + rule.max + '" step="' + (rule.whole ? 1 : 0.1) + '"' + (rule.blank ? "" : " required") + ">";
  } else if (rule.max > 100) {
    input = '<textarea id="' + id + '" data-col="' + esc(column) + '" maxlength="' + rule.max + '" rows="2">' + esc(value) + "</textarea>";
  } else {
    input = '<input type="text" id="' + id + '" data-col="' + esc(column) + '" value="' + esc(value) + '" maxlength="' + rule.max + '">';
  }
  return '<div class="field"><label for="' + id + '">' + esc(column) + "</label>" + input + "</div>";
}

function openEditor(i) {
  var item = findItem(i);
  if (!item) return;
  state.editing = item;
  var d = state.data;
  var locked = d.show.filter(function (c) { return !d.edit[c]; });
  $("edit-title").textContent = "Edit " + d.label.toLowerCase().replace(/s$/, "") + " row";
  $("edit-locked").innerHTML = locked.map(function (c) {
    return "<div><dt>" + esc(c) + "</dt><dd>" + (esc(display(c, item.row[c])) || "–") + "</dd></div>";
  }).join("");
  $("edit-fields").innerHTML = Object.keys(d.edit).map(function (c) {
    return fieldHtml(c, d.edit[c], item.row[c] || "");
  }).join("");
  $("edit-msg").innerHTML = "";
  $("edit-withdraw").classList.toggle("hidden", state.name !== "participants");
  $("edit-dialog").showModal();
}

function showError(text) {
  $("edit-msg").innerHTML = '<div class="alert alert-error">' + esc(text) + "</div>";
}

$("edit-save").addEventListener("click", function () {
  var item = state.editing;
  var fields = {};
  $("edit-fields").querySelectorAll("[data-col]").forEach(function (el) { fields[el.dataset.col] = el.value; });
  var btn = this;
  btn.disabled = true;
  post("/admin/api/" + state.name + "/update", { index: item.i, original: item.row, fields: fields })
    .then(function (d) {
      if (!d.ok) return showError(d.error);
      item.row = d.row;
      $("edit-dialog").close();
      draw();
      toast("Saved.");
    })
    .catch(function () { showError("Could not reach the server."); })
    .finally(function () { btn.disabled = false; });
});

$("edit-delete").addEventListener("click", function () {
  var item = state.editing;
  if (!confirm("Delete this row permanently? This can't be undone.")) return;
  post("/admin/api/" + state.name + "/delete", { index: item.i, original: item.row }).then(function (d) {
    if (!d.ok) return showError(d.error);
    // Rows after the deleted one move up by one in the file.
    state.data.rows = state.data.rows.filter(function (x) { return x !== item; });
    state.data.rows.forEach(function (x) { if (x.i > item.i) x.i -= 1; });
    $("edit-dialog").close();
    draw();
    toast("Row deleted.");
  }).catch(function () { showError("Could not reach the server."); });
});

$("edit-withdraw").addEventListener("click", function () {
  var pid = state.editing.row["Participant ID"];
  if (!confirm("Withdraw " + pid + "?\n\nThis deletes their profile, readings, diary and survey answers. " +
               "Their hotspot reports stay in the register without their ID. This can't be undone.")) return;
  post("/admin/api/withdraw", { participant_id: pid }).then(function (d) {
    if (!d.ok) return showError(d.error);
    location.reload();
  }).catch(function () { showError("Could not reach the server."); });
});

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------
document.querySelectorAll(".admin-tabs button").forEach(function (b) {
  b.addEventListener("click", function () { load(b.dataset.table); });
});
$("admin-search").addEventListener("input", function () { state.page = 0; draw(); });
$("admin-filter").addEventListener("change", function () { state.page = 0; draw(); });
$("page-prev").addEventListener("click", function () { state.page -= 1; draw(); });
$("page-next").addEventListener("click", function () { state.page += 1; draw(); });
$("admin-tbody").addEventListener("click", function (e) {
  var tr = e.target.closest("tr[data-i]");
  if (tr) openEditor(Number(tr.dataset.i));
});
$("admin-tbody").addEventListener("keydown", function (e) {
  var tr = e.target.closest("tr[data-i]");
  if (tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openEditor(Number(tr.dataset.i)); }
});

load("readings");
