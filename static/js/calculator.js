/* ==========================================================================
   calculator.js - Personal AQI (pAQI)

   Exposure model:  E = sum( Ci x Ti x IRi )
     Ci  = PM2.5 in microenvironment i  (ug/m3) = outdoor PM2.5 x factor
     Ti  = hours spent there
     IRi = inhalation rate (m3 of air breathed per hour)
   E is a dose in micrograms (ug/m3 x h x m3/h = ug).

   pAQI = the AQI of the air a resting adult (REFERENCE_IR) would have to
   breathe for 24 hours to receive the same dose E.
   ========================================================================== */

var REFERENCE_IR = 0.5; // m3/hour, an adult at rest / light activity

// f = infiltration factor (indoor or in-vehicle PM2.5 / outdoor PM2.5)
// ir = inhalation rate in m3/hour
// Values follow the Standard Operating Protocol (SOP) where it gives one:
//   infiltration: open windows / no filter 0.7-0.9 (0.8), closed windows / HEPA 0.1-0.3 (0.2),
//                 open air / traffic 1.0 (direct exposure)
//   breathing:    resting / desk 0.5, light walking 1.0, commuting 1.2 (SOP sample),
//                 heavy exercise / cycling 2.5-3.0
// Other values are typical estimates; edit them freely.
var COMMUTE = {
  two_wheeler: { label: "Two-wheeler (scooter / motorbike)", f: 1.0, ir: 1.2 },
  walk:        { label: "Walking", f: 1.0, ir: 1.2 },
  cycle:       { label: "Cycling", f: 1.0, ir: 2.5 },
  auto:        { label: "Auto-rickshaw", f: 0.9, ir: 1.2 },
  bus:         { label: "City bus (Mo Bus)", f: 0.8, ir: 1.0 },
  car_open:    { label: "Car, windows open", f: 0.8, ir: 1.0 },
  car_ac:      { label: "Car with AC, windows closed", f: 0.4, ir: 1.0 },
  none:        { label: "No commute / work from home", f: 0, ir: 0 },
};
var MASKS = { // share of PM2.5 the mask stops (real-world fit, not lab value)
  none:     { label: "No mask", filter: 0 },
  cloth:    { label: "Cloth mask", filter: 0.15 },
  surgical: { label: "Surgical / 3-ply mask", filter: 0.4 },
  n95:      { label: "N95 / FFP2 respirator (well fitted)", filter: 0.8 },
};
var WORK = {
  hepa:         { label: "AC office + air filter (SOP: filtered)", f: 0.2, ir: 0.5 },
  ac:           { label: "AC office / classroom, windows closed", f: 0.45, ir: 0.5 },
  ventilated:   { label: "Naturally ventilated, windows open", f: 0.8, ir: 0.5 },
  outdoor:      { label: "Outdoors / roadside shop or stall", f: 1.0, ir: 1.0 },
  construction: { label: "Construction site", f: 1.3, ir: 2.5 },
};
var EXERCISE = {
  none:      { label: "No exercise", f: 0, ir: 0 },
  walk_park: { label: "Walk in a park", f: 1.0, ir: 1.0 },
  jog:       { label: "Running / jogging outdoors", f: 1.0, ir: 3.0 },
  cycle:     { label: "Cycling outdoors", f: 1.0, ir: 2.5 },
  sports:    { label: "Park workout / outdoor sports", f: 1.0, ir: 2.5 },
  yoga:      { label: "Yoga / workout at home", f: 0.8, ir: 1.0 },
  gym:       { label: "Indoor AC gym", f: 0.4, ir: 2.5 },
};
var HOME = {
  purifier:   { label: "Windows closed / HEPA purifier", f: 0.2, ir: 0.5 },
  ac:         { label: "Closed room with AC", f: 0.45, ir: 0.5 },
  windows:    { label: "Windows open, no filter (typical home)", f: 0.8, ir: 0.5 },
  roadside:   { label: "Windows open, next to a busy road", f: 0.95, ir: 0.5 },
  solid_fuel: { label: "Cooking with wood / coal / kerosene", f: 1.5, ir: 0.5 },
};

// Starting choices for a typical person
var DEFAULTS = { commute: "two_wheeler", mask: "none", work: "ventilated", exercise: "walk_park", home: "windows" };

// ---------- Fill the <select> boxes from the objects above ----------
function fillSelect(id, options) {
  var select = document.getElementById(id);
  Object.keys(options).forEach(function (key) {
    var opt = document.createElement("option");
    opt.value = key;
    opt.textContent = options[key].label;
    select.appendChild(opt);
  });
  select.value = DEFAULTS[id];
}
fillSelect("commute", COMMUTE);
fillSelect("mask", MASKS);
fillSelect("work", WORK);
fillSelect("exercise", EXERCISE);
fillSelect("home", HOME);

// Start with the zone from the user's participant ID, if they have one
var savedZone = Hawa.zoneFromId(Hawa.getId());
if (savedZone) document.getElementById("zone").value = savedZone;

// ---------- Live PM2.5 per zone ----------
var livePm = {};     // zone id -> average PM2.5
var livePmFrom = {}; // zone id -> where it came from
Hawa.getJSON("/api/live").then(function (live) {
  live.zones.forEach(function (z) {
    // Prefer the official CPCB station; otherwise use the model's 24-hour average.
    if (z.station && z.station.pm25 !== null) {
      livePm[z.zone_id] = z.station.pm25;
      livePmFrom[z.zone_id] = "official CPCB station";
    } else {
      livePm[z.zone_id] = z.pm25_24h;
      livePmFrom[z.zone_id] = "model estimate";
    }
  });
  update();
}).catch(function () { update(); });

// ---------- Read the form ----------
function num(id) {
  var v = parseFloat(document.getElementById(id).value);
  return isNaN(v) || v < 0 ? 0 : v;
}

function readInputs() {
  var commute = document.getElementById("commute").value;
  var exercise = document.getElementById("exercise").value;
  return {
    zone: Number(document.getElementById("zone").value),
    customAqi: document.getElementById("custom-aqi").value,
    commute: commute,
    mask: document.getElementById("mask").value,
    work: document.getElementById("work").value,
    exercise: exercise,
    home: document.getElementById("home").value,
    commuteH: commute === "none" ? 0 : num("commute-h"),
    workH: num("work-h"),
    exerciseH: exercise === "none" ? 0 : num("exercise-h"),
  };
}

// ---------- The actual model ----------
function calculate(inp, outdoorPm) {
  var homeH = 24 - inp.commuteH - inp.workH - inp.exerciseH;
  var maskFilter = MASKS[inp.mask].filter;

  var parts = [
    { name: "Commute", hours: inp.commuteH, f: COMMUTE[inp.commute].f * (1 - maskFilter), ir: COMMUTE[inp.commute].ir },
    { name: "Work / study", hours: inp.workH, f: WORK[inp.work].f, ir: WORK[inp.work].ir },
    { name: "Exercise", hours: inp.exerciseH, f: EXERCISE[inp.exercise].f, ir: EXERCISE[inp.exercise].ir },
    { name: "Home / sleep", hours: Math.max(0, homeH), f: HOME[inp.home].f, ir: HOME[inp.home].ir },
  ];

  var total = 0;
  parts.forEach(function (p) {
    p.conc = outdoorPm * p.f;            // Ci
    p.dose = p.conc * p.hours * p.ir;    // Ci x Ti x IRi
    total += p.dose;
  });

  var equivalentPm = total / (24 * REFERENCE_IR);
  return { parts: parts, dose: total, homeH: homeH, equivalentPm: equivalentPm, paqi: Hawa.aqiFromPm25(equivalentPm) };
}

// "What if" = run the same model with one thing changed, compare the doses
function whatIfs(inp, outdoorPm, base) {
  var ideas = [];
  function tryChange(text, changes) {
    var copy = Object.assign({}, inp, changes);
    var result = calculate(copy, outdoorPm);
    var cut = base.dose > 0 ? (base.dose - result.dose) / base.dose * 100 : 0;
    if (cut >= 1) ideas.push({ text: text, cut: cut });
  }
  if (inp.commuteH > 0 && inp.mask !== "n95") tryChange("An N95 mask on your commute", { mask: "n95" });
  if (inp.home !== "purifier") tryChange("An air purifier in the room where you sleep", { home: "purifier" });
  if (inp.exerciseH > 0 && EXERCISE[inp.exercise].f >= 1) tryChange("Exercising indoors (AC gym) instead of outside", { exercise: "gym" });
  if (["two_wheeler", "walk", "cycle", "auto"].indexOf(inp.commute) >= 0 && inp.commuteH > 0)
    tryChange("Taking the bus instead", { commute: "bus" });
  if (inp.commuteH > 0.5) tryChange("Cutting your commute by half", { commuteH: inp.commuteH / 2 });
  ideas.sort(function (a, b) { return b.cut - a.cut; });
  return ideas;
}

// ---------- Draw the results ----------
function update() {
  var inp = readInputs();
  var errorBox = document.getElementById("calc-error");

  // Outdoor PM2.5: custom AQI if given, otherwise the live value for the zone
  var outdoorPm = null;
  var hint = document.getElementById("zone-hint");
  if (inp.customAqi !== "" && !isNaN(parseFloat(inp.customAqi))) {
    outdoorPm = Hawa.pm25FromAqi(parseFloat(inp.customAqi));
    hint.textContent = "Using your AQI (≈ " + outdoorPm.toFixed(0) + " µg/m³ PM2.5).";
  } else if (livePm[inp.zone] !== undefined && livePm[inp.zone] !== null) {
    outdoorPm = livePm[inp.zone];
    hint.textContent = "Live PM2.5 for this zone: " + outdoorPm.toFixed(1) + " µg/m³ (" + livePmFrom[inp.zone] + ").";
  } else {
    hint.textContent = "Live data unavailable. Enter an outdoor AQI below to continue.";
  }

  // Keep the hours inputs sensible
  document.getElementById("commute-h").disabled = inp.commute === "none";
  document.getElementById("exercise-h").disabled = inp.exercise === "none";
  var homeH = 24 - inp.commuteH - inp.workH - inp.exerciseH;
  document.getElementById("home-h").value = Math.max(0, homeH).toFixed(2).replace(/\.?0+$/, "");

  if (homeH < 0) {
    errorBox.textContent = "Your commute, work and exercise add up to more than 24 hours. Please reduce them.";
    errorBox.classList.remove("hidden");
    return;
  }
  errorBox.classList.add("hidden");
  if (outdoorPm === null) return;

  var r = calculate(inp, outdoorPm);
  var outdoorAqi = Hawa.aqiFromPm25(outdoorPm);

  // Big numbers
  var youBand = Hawa.band(r.paqi);
  document.getElementById("paqi").textContent = r.paqi;
  document.getElementById("paqi-band").textContent = youBand.name;
  document.getElementById("you-box").setAttribute("data-band", youBand.name);
  document.getElementById("outdoor").textContent = outdoorAqi;
  document.getElementById("outdoor-band").innerHTML = Hawa.chip(outdoorAqi, false);

  // One-line summary
  var diff = outdoorAqi > 0 ? Math.round((r.paqi - outdoorAqi) / outdoorAqi * 100) : 0;
  var compare = diff === 0 ? "about the same as" : Math.abs(diff) + "% " + (diff > 0 ? "higher than" : "lower than");
  document.getElementById("summary-line").innerHTML =
    "You inhale about <b>" + Math.round(r.dose) + " µg</b> of PM2.5 a day. Your personal AQI is <b>" + compare +
    "</b> the outdoor AQI. As a rough rule of thumb, that is like smoking <b>" +
    (r.equivalentPm / 22).toFixed(1) + " cigarettes</b> a day (Berkeley Earth: 22 µg/m³ over 24 h ≈ 1 cigarette).";

  // Breakdown bars
  var html = "";
  r.parts.forEach(function (p) {
    var share = r.dose > 0 ? p.dose / r.dose * 100 : 0;
    html += '<div class="bd-row"><div class="bd-head"><span><b>' + p.name + "</b> · " +
      +p.hours.toFixed(2) + " h · " + p.conc.toFixed(0) + " µg/m³</span><span>" + share.toFixed(0) + "%</span></div>" +
      '<div class="bd-track"><div class="bd-fill" style="width:' + share.toFixed(1) + '%"></div></div></div>';
  });
  document.getElementById("breakdown").innerHTML = html;

  // What-ifs
  var ideas = whatIfs(inp, outdoorPm, r);
  document.getElementById("whatif").innerHTML = ideas.length
    ? ideas.map(function (i) {
        return "<li>" + i.text + " would cut your exposure by <b>" + Math.round(i.cut) + "%</b>.</li>";
      }).join("")
    : '<li>Your day is already well protected. Nice!</li>';
}

// Recalculate whenever anything in the form changes
document.getElementById("calc-form").addEventListener("input", update);
document.getElementById("calc-form").addEventListener("change", update);
update();
