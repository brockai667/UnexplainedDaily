/* UnexplainedDaily engine - runtime.
   Vsetko ide cez "ctl" objekty so settermi: GSAP tweenuje obycajne cisla, setter prepise SVG atribut.
   Ziadne GSAP CSS transformy na SVG <g> -> plne deterministicke pri seeku (render po frameoch).
   Generovany kod scen sa vklada do /*__SCENES__*​/, titulky do /*__CAPTIONS__*​/. */
var tl = gsap.timeline({ paused: true });
var CLK = { t: 0 };
var REAPPLY = [];
function $(id) { return document.getElementById(id); }
function ctl(init, apply) {
  var st = {}, o = {};
  Object.keys(init).forEach(function (k) {
    st[k] = init[k];
    Object.defineProperty(o, k, { get: function () { return st[k]; }, set: function (v) { st[k] = v; apply(st); }, enumerable: true });
  });
  REAPPLY.push(function () { apply(st); });
  return o;
}
function node(id, init) {
  var el = $(id), d = { x: 0, y: 0, r: 0, s: 1, sx: 1, sy: 1, o: 1 };
  for (var k in (init || {})) d[k] = init[k];
  return ctl(d, function (st) {
    el.setAttribute("transform", "translate(" + st.x.toFixed(2) + "," + st.y.toFixed(2) + ") rotate(" + st.r.toFixed(2) + ") scale(" +
      (st.s * st.sx).toFixed(4) + "," + (st.s * st.sy).toFixed(4) + ")");
    el.setAttribute("opacity", st.o < 0.004 ? 0 : st.o);
  });
}
/* skaluje okolo pevneho bodu vo world-suradniciach */
function cNode(id, cx, cy, init) {
  var el = $(id), d = { s: 1, o: 1, r: 0 };
  for (var k in (init || {})) d[k] = init[k];
  return ctl(d, function (st) {
    el.setAttribute("transform", "translate(" + cx + "," + cy + ") rotate(" + st.r.toFixed(2) + ") scale(" + st.s.toFixed(4) +
      ") translate(" + (-cx) + "," + (-cy) + ")");
    el.setAttribute("opacity", st.o < 0.004 ? 0 : st.o);
  });
}
/* "vyrastie zo zeme" / "zasype sa": zvisla mierka okolo baseY */
function riseNode(id, baseY) {
  var el = $(id);
  return ctl({ sy: 0, o: 0 }, function (st) {
    el.setAttribute("transform", "translate(0," + (baseY * (1 - st.sy)).toFixed(2) + ") scale(1," + st.sy.toFixed(4) + ")");
    el.setAttribute("opacity", st.o < 0.004 ? 0 : st.o);
  });
}
function pen(id, d0) {
  var el = $(id);
  return ctl({ d: d0 === undefined ? 0 : d0 }, function (st) { el.style.strokeDashoffset = (1 - st.d); el.style.opacity = st.d <= 0.002 ? 0 : 1; });
}
/* ANGLICKY KANAL: formatovanie cisel je zamerne locale-independent.
   NIKDY tu nepouzivaj toLocaleString()/Intl bez "en-US" - na sk-SK systeme by z "5.5 m" spravil "5,5 m". */
function numEN(v, dec) {
  var p = (dec ? v.toFixed(dec) : String(Math.round(v))).split(".");
  return p[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (p.length > 1 ? "." + p[1] : "");
}
function n3(id, fmt) {
  var els = $(id).getElementsByTagName("text");
  return ctl({ v: 0 }, function (st) {
    var s = fmt(st.v);
    for (var i = 0; i < els.length; i++) if (els[i].textContent !== s) els[i].textContent = s;
  });
}
function camSet(id, cx, cy, z) {
  $(id).setAttribute("transform", "translate(540,960) scale(" + z.toFixed(4) + ") translate(" + (-cx).toFixed(2) + "," + (-cy).toFixed(2) + ")");
}
function camSetR(id, cx, cy, z, rot) {
  $(id).setAttribute("transform", "translate(540,960) rotate(" + rot.toFixed(2) + ") scale(" + z.toFixed(4) +
    ") translate(" + (-cx).toFixed(2) + "," + (-cy).toFixed(2) + ")");
}
/* kamera so zamknutou zemou: ciara zeme gy je vzdy na obrazovke na 960+up */
/* Globalne doladenie ramovania podla sveta. Scenu nastavuje build pred prvym
   zaberom: na mori treba tesnejsi orez, inak je Bob maly a nizko. */
var ZB = 1, UB = 1;
function GCam(id, gy, init) {
  var d = { x: 540, z: 1, up: 330, shx: 0, shy: 0, dive: 0 };
  for (var k in (init || {})) d[k] = init[k];
  return ctl(d, function (st) {
    var z = st.z * ZB;
    camSet(id, st.x + st.shx, gy - st.up * UB / z + st.shy + st.dive, z);
  });
}
function pop(n, t, dur, ov) { tl.fromTo(n, { s: 0, o: 1 }, { s: 1, o: 1, duration: dur || 0.32, ease: "back.out(" + (ov || 2.6) + ")", immediateRender: false }, t); }
function unpop(n, t, dur) { tl.to(n, { s: 0, duration: dur || 0.16, ease: "power2.in" }, t); }
function slamIn(n, t, from, to, dur) {
  tl.fromTo(n, { s: from === undefined ? 1.9 : from, o: 1 }, { s: 1, o: 1, duration: dur || 0.22, ease: "back.out(1.7)", immediateRender: false }, t);
}
function shake(cam, t, amp, dur) {
  tl.to(cam, { shy: amp, duration: 0.04 }, t);
  tl.to(cam, { shy: 0, duration: dur || 0.34, ease: "elastic.out(1.7,0.2)" }, t + 0.04);
}
function ball(id, x0, y0, vx, vy, g, t0, dur, spin) {
  var n = node(id, { o: 0 });
  var c = ctl({ tau: -1 }, function (st) {
    if (st.tau < 0 || st.tau > dur) { n.o = 0; return; }
    n.o = 1; n.x = x0 + vx * st.tau; n.y = y0 + vy * st.tau + 0.5 * g * st.tau * st.tau; n.r = (spin || 0) * st.tau;
  });
  tl.fromTo(c, { tau: 0 }, { tau: dur, duration: dur, ease: "none", immediateRender: false }, t0);
  tl.set(c, { tau: -1 }, t0 + dur + 0.001);
}

/* ---------------------------------------------------------------- RIG */
function Rig(p, init) {
  var E = {};
  ["root", "body", "lL", "lL2", "lR", "lR2", "aL", "aL2", "aR", "aR2", "head", "hat", "eyeL", "eyeR", "mouth", "mouthO"].forEach(function (k) { E[k] = $(p + "_" + k); });
  var d = { x: 0, y: 0, ox: 0, oy: 0, rot: 0, s: 1, flip: 1, sq: 1, o: 1, lean: 0, drop: 0, lL: 4, lL2: 0, lR: -4, lR2: 0,
    aL: 14, aL2: 10, aR: -14, aR2: 10, head: 0, w: 0, wa: 0, ph: 0, A: 26, idle: 0, wave: 0, trem: 0, eye: 0, mo: 0,
    hatx: 0, haty: 0, hatr: 0, hato: 1, seed: 0 };
  for (var k in (init || {})) d[k] = init[k];
  function R(el, a) { el.setAttribute("transform", "rotate(" + a.toFixed(2) + ")"); }
  return ctl(d, function (st) {
    var t = CLK.t, sn = Math.sin(st.ph), cs = Math.cos(st.ph), w = st.w, A = st.A;
    var bob = w * 7 * Math.abs(sn) + st.idle * 2.5 * Math.sin(t * 5.2 + st.seed);
    var tr = st.trem * Math.sin(t * 40 + st.seed);
    E.root.setAttribute("transform", "translate(" + (st.x + st.ox).toFixed(2) + "," + (st.y + st.oy).toFixed(2) + ") rotate(" + st.rot.toFixed(2) +
      ") scale(" + (st.s * st.flip * (1 + (1 - st.sq) * 0.5)).toFixed(4) + "," + (st.s * st.sq).toFixed(4) + ")");
    E.root.setAttribute("opacity", st.o < 0.004 ? 0 : st.o);
    E.body.setAttribute("transform", "translate(0," + (-120 + st.drop + bob).toFixed(2) + ") rotate(" + (st.lean + st.idle * 1.2 * Math.sin(t * 2.6 + st.seed)).toFixed(2) + ")");
    R(E.lL, -(st.lL + w * A * sn + tr)); R(E.lL2, -(st.lL2 - w * 58 * Math.max(0, cs)));
    R(E.lR, -(st.lR - w * A * sn - tr)); R(E.lR2, -(st.lR2 - w * 58 * Math.max(0, -cs)));
    R(E.aL, -(st.aL - st.wa * A * 1.15 * sn + st.wave * 22 * Math.sin(t * 15)));
    R(E.aL2, -(st.aL2 + st.wa * 14 + st.wave * 18 * Math.sin(t * 15 + 1)));
    R(E.aR, -(st.aR + st.wa * A * 1.15 * sn)); R(E.aR2, -(st.aR2 + st.wa * 14));
    E.head.setAttribute("transform", "rotate(" + (st.head + st.idle * 1.5 * Math.sin(t * 3.1 + 1 + st.seed)).toFixed(2) + ")");
    if (E.hat) { E.hat.setAttribute("transform", "translate(" + st.hatx.toFixed(2) + "," + st.haty.toFixed(2) + ") rotate(" + st.hatr.toFixed(2) + ")"); E.hat.setAttribute("opacity", st.hato); }
    E.eyeL.setAttribute("r", (11 * st.eye).toFixed(2)); E.eyeR.setAttribute("r", (11 * st.eye).toFixed(2));
    E.mouth.setAttribute("opacity", st.mo > 0.2 ? 0 : 1);
    E.mouthO.setAttribute("rx", (7 * st.mo).toFixed(2)); E.mouthO.setAttribute("ry", (10 * st.mo).toFixed(2));
  });
}
var STAND = { lean: 0, drop: 0, lL: 4, lL2: 0, lR: -4, lR2: 0, aL: 14, aL2: 10, aR: -14, aR2: 10, head: 0 };
var SHRUG = { lean: 0, drop: 0, lL: 10, lL2: 0, lR: -10, lR2: 0, aL: 128, aL2: 74, aR: -128, aR2: -74, head: 6 };
var POINT = { lean: -4, aL: 150, aL2: 20, aR: -30, aR2: 20, head: -18 };
var DIG_A = { lean: 40, aL: 52, aL2: 28, aR: 74, aR2: 22, drop: 22, lL: 40, lL2: -58, lR: -16, lR2: -22, head: 12 };
var DIG_B = { lean: -16, aL: 204, aL2: 26, aR: 216, aR2: 22, drop: 0, lL: 10, lL2: -6, lR: -12, lR2: -4, head: -14 };
function pose(r, p, t, dur, ease) { var v = {}; for (var k in p) v[k] = p[k]; v.duration = dur; v.ease = ease || "power2.out"; tl.to(r, v, t); }
function setPose(r, p, t) { var v = {}; for (var k in p) v[k] = p[k]; tl.set(r, v, t); }

/* hodiny: prva vec v kazdom renderi -> proceduralne veci su cista funkcia casu */
var boils = [].slice.call(document.querySelectorAll(".boil"));
var sunRays = [].slice.call(document.querySelectorAll(".sunray"));
var sunRays2 = [].slice.call(document.querySelectorAll(".sunray2"));   // zaverecny zaber: dobehne na rotate(0) v TOTAL
var clock = ctl({ t: 0 }, function (st) {
  CLK.t = st.t;
  var seed = 1 + (Math.floor(st.t * 8) % 4);
  for (var i = 0; i < boils.length; i++) boils[i].setAttribute("seed", seed);
  for (var j = 0; j < sunRays.length; j++) sunRays[j].setAttribute("transform", "rotate(" + (st.t * 14).toFixed(2) + ")");
  for (var j2 = 0; j2 < sunRays2.length; j2++) sunRays2[j2].setAttribute("transform", "rotate(" + ((st.t - TM.total) * 14).toFixed(2) + ")");
  for (var k = 1; k < REAPPLY.length; k++) REAPPLY[k]();
});
tl.to(clock, { t: TM.total, duration: TM.total, ease: "none" }, 0);
var OM = Math.PI * 1.9, PH0 = Math.PI / 2, STEP = Math.PI / OM;

/* ---------------------------------------------------------------- spolocny "svet so zemou" */
function smooth(u) { u = Math.max(0, Math.min(1, u)); return u * u * (3 - 2 * u); }
function hill(x) { return 1260 - 360 * smooth(x / 1300); }
var GY = 1290;                      // standardna ciara zeme vo svete

/* Uvodny/zaverecny zaber: Bob kraca svetom (kopec/breh/sneh/pust).
   terrain(x) dodava build podla spec["world"] - rovnaky profil musi mat prvy aj posledny zaber. */
/* shipId != null -> svet `sea`: po hladine sa neklaca, lod nesie hrdinu.
   Hojdanie je funkciou POLOHY (bx), nie casu - inak by sa posledna snimka
   nezhodovala s nultou a neviditelna slucka by sa rozbila. */
function HillShot(p, rigId, cloudOff, terrain, shipId, deck) {
  var ter = terrain || hill;
  var rg = Rig(rigId, { s: shipId ? 1.06 : 1.35, lean: 7, A: 26 });
  var shipN = shipId ? node(shipId, { s: 1 }) : null;
  var DK = deck || { x: 46, y: 184, sub: 62 };
  var cam = ctl({ bx: 100, lead: 120, z: 1.68, shx: 0, shy: 0 }, function (st) {
    var by = ter(st.bx);
    if (shipN) {
      var ph = st.bx / 150;
      var sy = by + DK.sub + 9 * Math.sin(ph);
      var rr = 2.4 * Math.sin(ph * 0.78);
      shipN.x = st.bx; shipN.y = sy; shipN.r = rr;
      var a = rr * Math.PI / 180;
      rg.x = st.bx + DK.x * Math.cos(a) + DK.y * Math.sin(a);
      rg.y = sy - DK.y * Math.cos(a) + DK.x * Math.sin(a);
      rg.lean = 7 + rr;
    } else { rg.x = st.bx; rg.y = by; }
    var cx = st.bx + st.lead, cy = by - 315 / st.z;
    camSet(p + "_cam", cx + st.shx, cy + st.shy, st.z);
    var zf = 1 + (st.z - 1) * 0.25;
    $(p + "_far").setAttribute("transform", "translate(540,960) scale(" + zf.toFixed(4) + ") translate(" +
      (-(540 + (cx - 540) * 0.18)).toFixed(2) + "," + (-(960 + (cy - 960) * 0.18)).toFixed(2) + ")");
    $(p + "_cloud").setAttribute("transform", "translate(" + cloudOff().toFixed(2) + ",0)");
  });
  var gh = node(p + "_ghost", { o: 0 });
  var gp = [pen(p + "_g0", 1), pen(p + "_g1", 1)];
  for (var i = 0; i < 7; i++) gp.push(pen(p + "_gp" + i, 1));
  return { rig: rg, cam: cam, ghost: gh };
}

/*__SCENES__*/

/*__CAPTIONS__*/

for (var q = 0; q < REAPPLY.length; q++) REAPPLY[q]();
window.__timelines = window.__timelines || {}; window.__timelines["main"] = tl;
