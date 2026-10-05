/* runtime.js - interprets a compiled screenplay (window.SP) with doodle_lib (window.D).
 * Every object = SVG group + channels (keyframed values) filled from BEATS; one D.drive per scene renders
 * everything as a pure function of time. No hand-written GSAP per episode. */
(function () {
  "use strict";
  var RT = (window.RT = {}), INK = D.INK, P2 = D.P2;
  var PAPER = "#fffdf6";
  var COL = { red: "#d62828", orange: "#f77f00", yellow: "#fcbf49", teal: "#2a9d8f", purple: "#7b2cbf", blue: "#3a86ff",
    green: "#52b788", brown: "#8d6e63", white: "#ffffff", cream: "#fff3b0", navy: "#264653", pink: "#e76f51", gray: "#9e9e9e", black: INK };
  var col = (RT.col = function (c, d) { return c == null ? d : COL[c] || c; });

  /* ------------------------------------------------------------ channels */
  function Chan(v) { this.base = v; this.seg = []; }
  Chan.prototype.at = function (t) {
    var v = this.base;
    for (var i = 0; i < this.seg.length; i++) {
      var s = this.seg[i];
      if (t < s.t0) continue;
      v = t < s.t1 ? D.lerp(s.from, s.v, D.ease(s.e)((t - s.t0) / (s.t1 - s.t0))) : s.v;
    }
    return v;
  };
  Chan.prototype.to = function (t0, dur, v, e) {
    var from = this.at(t0);
    this.seg.push({ t0: t0, t1: t0 + Math.max(dur || 0, 1e-4), from: from, v: v, e: e || "power2.inOut" });
    return this;
  };
  Chan.prototype.set = function (t0, v) { this.seg.push({ t0: t0, t1: t0, from: v, v: v, e: "none" }); return this; };   // instant, already true at t0
  function Steps(v) { this.base = v; this.k = []; }
  Steps.prototype.at = function (t) { var v = this.base; for (var i = 0; i < this.k.length; i++) if (t >= this.k[i][0]) v = this.k[i][1]; return v; };
  Steps.prototype.set = function (t, v) { this.k.push([t, v]); this.k.sort(function (a, b) { return a[0] - b[0]; }); return this; };
  RT.Chan = Chan; RT.Steps = Steps;

  /* ------------------------------------------------------------ static art (JS port of svgkit) */
  var S7 = D.stroke(7), S5 = D.stroke(5);
  function fillS(fill, w) { return { fill: fill, stroke: INK, "stroke-width": w || 7, "stroke-linecap": "round", "stroke-linejoin": "round" }; }
  function path(g, d, at) { var a = at || S7; var o = {}; for (var k in a) o[k] = a[k]; o.d = d; return D.el(g, "path", o); }
  RT.cloud = function (g, cx, cy, w, h) {
    h = h || w * 0.38;
    var n = 5, pts = [], d, i;
    for (i = 0; i <= n; i++) pts.push([cx + Math.cos(Math.PI - (Math.PI * i) / n) * w / 2, cy - Math.sin(Math.PI - (Math.PI * i) / n) * h]);
    d = "M" + P2(pts[0][0], cy);
    for (i = 1; i <= n; i++) { var r = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]) * 0.62; d += "A" + D.r1(r) + "," + D.r1(r) + " 0 0 1 " + P2(pts[i][0], i === n ? cy : pts[i][1]); }
    return path(g, d + "Z", fillS("#ffffff", 5));
  };
  function redCross(g, cx, cy, s) {
    D.el(g, "rect", { x: cx - s, y: cy - s, width: 2 * s, height: 2 * s, rx: 6, fill: "#ffffff", stroke: INK, "stroke-width": 5 });
    var a = s * 0.62;
    path(g, "M" + P2(cx, cy - a) + "L" + P2(cx, cy + a) + "M" + P2(cx - a, cy) + "L" + P2(cx + a, cy), { fill: "none", stroke: "#e63946", "stroke-width": Math.max(6, s * 0.42), "stroke-linecap": "round" });
  }
  RT.redCross = redCross;
  function windowG(g, x, y, w, h) {
    var ok = D.el(g, "g", {}), br = D.el(g, "g", { opacity: 0 });
    D.el(ok, "rect", { x: x, y: y, width: w, height: h, fill: "#8ecae6", stroke: INK, "stroke-width": 5 });
    path(ok, "M" + P2(x + 8, y + h - 10) + "L" + P2(x + w * 0.45, y + 8), { stroke: "#ffffff", "stroke-width": 5, "stroke-linecap": "round", fill: "none" });
    D.el(br, "rect", { x: x, y: y, width: w, height: h, fill: "#3d4f5c", stroke: INK, "stroke-width": 5 });
    path(br, "M" + P2(x, y) + "L" + P2(x + w * 0.35, y + h * 0.3) + "L" + P2(x + w * 0.2, y + h * 0.55) + "L" + P2(x, y + h * 0.7) + "Z M" + P2(x + w, y) + "L" + P2(x + w * 0.7, y + h * 0.25) +
      "L" + P2(x + w, y + h * 0.45) + "Z M" + P2(x, y + h) + "L" + P2(x + w * 0.3, y + h * 0.78) + "L" + P2(x + w * 0.55, y + h) + "Z M" + P2(x + w, y + h) + "L" + P2(x + w * 0.8, y + h * 0.7) + "L" + P2(x + w * 0.62, y + h) + "Z",
      { fill: "#bfe6f7", stroke: INK, "stroke-width": 3, "stroke-linejoin": "round" });
    return { ok: ok, br: br, cx: x + w / 2, cy: y + h / 2, w: w, h: h };
  }

  /* ------------------------------------------------------------ base object: transform channels + generic verbs */
  function Obj(sc, def, parent) {
    this.sc = sc; this.def = def; this.id = def.id;
    this.g = D.el(parent, "g", {});
    if (def.id) this.g.setAttribute("data-oid", def.id);                 // look.py finds the object on screen by this (no effect on rendering)
    this.x = new Chan(def.x || 0); this.y = new Chan(def.y || 0);
    this.s = new Chan(def.scale == null ? 1 : def.scale); this.r = new Chan(def.rot || 0);
    this.o = new Chan(def.hidden ? 0 : def.opacity == null ? 1 : def.opacity);
    this.fx = []; this.paths = []; this.vis = true;
  }
  Obj.prototype.xf = function (t) {
    var q = { x: this.x.at(t), y: this.y.at(t), s: this.s.at(t), r: this.r.at(t), o: this.o.at(t), sx: 1, sy: 1 }, i;
    for (i = 0; i < this.paths.length; i++) { var p = this.paths[i]; if (t >= p.t0) { var pp = pathAt(p, t); q.x = pp[0]; q.y = pp[1]; if (p.orient) q.r = pp[2]; } }
    var A = this.att ? this.att.at(t) : null;                            // carried by another object (attach / on:)
    if (A) { var tg = this.sc.objs[A.on], fa = tg ? tg.anchor(A.anchor, t) : [0, 0]; q.x = fa[0] + A.dx; q.y = fa[1] + A.dy; }
    for (i = 0; i < this.fx.length; i++) {
      var f = this.fx[i];
      if (t < f.t0 || t > f.t1) continue;
      if (f.type === "shake") { var e = 1 - (t - f.t0) / (f.t1 - f.t0), fr = D.frame(t); q.x += f.amp * e * (D.hash(fr * 1.37 + f.seed) * 2 - 1); q.y += f.amp * e * (D.hash(fr * 2.71 + f.seed) * 2 - 1); }
      else if (f.type === "jiggle") { var j = D.jiggle(t, f.t0, f.amp, f.freq, f.decay); q.sy *= 1 + j; q.sx *= 1 - 0.6 * j; }
      else if (f.type === "bob") q.y += f.amp * Math.sin(2 * Math.PI * f.freq * (t - f.t0));
      else if (f.type === "rock") q.r += f.amp * Math.sin(2 * Math.PI * f.freq * (t - f.t0));
      else if (f.type === "pulse") { var pu = 1 + f.amp * Math.sin(2 * Math.PI * f.freq * (t - f.t0)); q.sx *= pu; q.sy *= pu; }
      else if (f.type === "spin") q.r += f.speed * (t - f.t0);
    }
    return q;
  };
  Obj.prototype.place = function (t) {
    var q = this.xf(t), sx = q.s * q.sx, sy = q.s * q.sy;
    this.g.setAttribute("transform", "translate(" + P2(q.x, q.y) + ")" + (q.r ? " rotate(" + D.r2(q.r) + ")" : "") + (sx !== 1 || sy !== 1 ? " scale(" + Math.max(1e-3, sx).toFixed(4) + "," + Math.max(1e-3, sy).toFixed(4) + ")" : ""));
    this.g.setAttribute("opacity", D.clamp(q.o, 0, 1).toFixed(3));
    this.vis = q.o > 0.02;
    return q;
  };
  Obj.prototype.render = function (t) { this.place(t); };
  Obj.prototype.anchor = function (name, t) { var q = this.xf(t), a = (this.def.anchors || {})[name] || this.anchors[name] || [0, 0]; return [q.x + a[0] * q.s, q.y + a[1] * q.s]; };
  Obj.prototype.anchors = { center: [0, 0] };
  Obj.prototype.beat = function (b) { return genericBeat(this, b); };
  RT.Obj = Obj;
  /* objects whose art is drawn in absolute world coordinates: the root is not moved by def.x / def.y */
  function absObj(sc, def, parent) { var o = new Obj(sc, { id: def.id, hidden: def.hidden, opacity: def.opacity }, parent); o.def = def; return o; }
  RT.absObj = absObj;

  function bez(P, p) {
    if (P.length === 4) { var q = 1 - p; return [q * q * q * P[0][0] + 3 * q * q * p * P[1][0] + 3 * q * p * p * P[2][0] + p * p * p * P[3][0], q * q * q * P[0][1] + 3 * q * q * p * P[1][1] + 3 * q * p * p * P[2][1] + p * p * p * P[3][1]]; }
    var f = p * (P.length - 1), n = Math.min(P.length - 2, Math.floor(f)), r = f - n;           // polyline (smoothstep between points)
    var rr = r * r * (3 - 2 * r);
    return [D.lerp(P[n][0], P[n + 1][0], rr), D.lerp(P[n][1], P[n + 1][1], rr)];
  }
  function pathAt(p, t) {
    var u = D.prog(t, p.t0, p.t1), a = p.acc == null ? 0.5 : p.acc, s = a * u + (1 - a) * u * u;
    if (p.ease) s = D.ease(p.ease)(u);
    var q = bez(p.pts, s), q2 = bez(p.pts, Math.max(0, s - 0.01)), q3 = bez(p.pts, Math.min(1, s + 0.01));
    return [q[0], q[1], (Math.atan2(q3[1] - q2[1], q3[0] - q2[0]) * 180) / Math.PI];
  }
  RT.bez = bez;

  var DEF_EASE = { move: "power2.inOut", scale: "back.out(1.8)", rotate: "power2.inOut", fade: "power1.inOut" };
  function genericBeat(o, b) {
    var t = b.t, d = b.dur, e = b.ease;
    switch (b.do) {
      case "move":
        if (b.to) { o.x.to(t, d == null ? 0.5 : d, b.to[0], e || DEF_EASE.move); o.y.to(t, d == null ? 0.5 : d, b.to[1], e || DEF_EASE.move); }
        else { if (b.dx) o.x.to(t, d == null ? 0.5 : d, o.x.at(t) + b.dx, e || DEF_EASE.move); if (b.dy) o.y.to(t, d == null ? 0.5 : d, o.y.at(t) + b.dy, e || DEF_EASE.move); }
        return true;
      case "path": case "fly_path":
        o.paths.push({ t0: t, t1: t + (d || 1), pts: b.points, acc: b.acc, ease: b.ease, orient: !!b.orient });
        return true;
      case "rotate": o.r.to(t, d == null ? 0.4 : d, b.to, e || DEF_EASE.rotate); return true;
      case "scale": o.s.to(t, d == null ? 0.35 : d, b.to, e || DEF_EASE.scale); return true;
      case "fade": o.o.to(t, d == null ? 0.3 : d, b.to == null ? 0 : b.to, e || DEF_EASE.fade); return true;
      case "show": o.o.set(t, 1); return true;
      case "hide": o.o.set(t, 0); return true;
      case "pop":
        o.o.set(t, 1); o.s.set(t, 0.001); o.s.to(t, d == null ? 0.35 : d, b.to == null ? o.s.base || 1 : b.to, e || "back.out(2.2)"); return true;
      case "stamp":
        o.o.set(t, 0); o.o.to(t, 0.07, 1, "none"); o.s.set(t, b.from || 2.3); o.s.to(t, d == null ? 0.42 : d, b.to == null ? o.s.base || 1 : b.to, e || "back.out(2.2)");
        o.r.set(t, (b.r0 == null ? -12 : b.r0) + (o.def.rot || 0)); o.r.to(t, d == null ? 0.42 : d, (b.r1 == null ? -3 : b.r1) + (o.def.rot || 0), "power2.out"); return true;
      case "shake": o.fx.push({ type: "shake", t0: t, t1: t + (d || 0.3), amp: b.amp || 10, seed: o.fx.length * 17 + 3 }); return true;
      case "jiggle": o.fx.push({ type: "jiggle", t0: t, t1: t + 2, amp: b.amp || 0.1, freq: b.freq || 6, decay: b.decay || 6 }); return true;
      case "bob": case "rock": case "pulse":
        o.fx.push({ type: b.do, t0: t, t1: b.until != null ? b.until : t + (d || 60), amp: b.amp || (b.do === "pulse" ? 0.06 : b.do === "rock" ? 4 : 5), freq: b.freq || 1.2 }); return true;
      case "spin": o.fx.push({ type: "spin", t0: t, t1: b.until != null ? b.until : t + (d || 60), speed: b.speed || 90 }); return true;
      case "attach": {                                                   // follow another object's anchor (hand by default) from t
        var off = b.offset || [0, 0];
        o.att = o.att || new Steps(null);
        o.att.set(t, { on: b.to, anchor: b.anchor || "hand", dx: off[0], dy: off[1] });
        return true;
      }
      case "detach": {                                                   // stay where it was let go
        if (!o.att) return true;
        var A0 = o.att.at(t - 1e-4);
        if (A0) { var tg0 = o.sc.objs[A0.on], p0 = tg0 ? tg0.anchor(A0.anchor, t) : [0, 0]; o.x.set(t, p0[0] + A0.dx); o.y.set(t, p0[1] + A0.dy); }
        o.att.set(t, null);
        return true;
      }
    }
    return false;
  }
  RT.genericBeat = genericBeat;

  /* ------------------------------------------------------------ kinds registry */
  var K = (RT.kinds = {});
  function inherit(C) { C.prototype = Object.create(Obj.prototype); C.prototype.constructor = C; return C; }

  /* sky: clouds drifting */
  K.sky = function (sc, def, parent) {
    var o = absObj(sc, def, parent), drift = def.drift == null ? 8 : def.drift;
    var cl = (def.clouds || []).map(function (c, i) { var g = D.el(o.g, "g", {}); RT.cloud(g, c[0], c[1], c[2] || 130, c[3]); return { g: g, dir: i % 2 ? -0.8 : 1 }; });
    o.render = function (t) { o.place(t); cl.forEach(function (c) { c.g.setAttribute("transform", "translate(" + (drift * c.dir * (t - sc.t0)).toFixed(1) + ",0)"); }); };
    return o;
  };
  K.mountains = function (sc, def, parent) {
    var o = absObj(sc, def, parent), pk = def.peaks || [[-40, 690], [40, 610], [100, 650], [185, 560], [262, 640], [330, 600], [420, 668], [500, 590], [585, 650], [660, 585], [780, 660]];
    var base = def.base || 860, ridge = "M" + pk.map(function (p) { return P2(p[0], p[1]); }).join("L");
    path(o.g, ridge + "L" + P2(pk[pk.length - 1][0], base) + "L" + P2(pk[0][0], base) + "Z", { fill: def.color || "#dde5ea" });
    path(o.g, ridge, { fill: "none", stroke: "#5f6f7c", "stroke-width": 4.5, "stroke-linecap": "round", "stroke-linejoin": "round" });
    if (def.snow !== false) pk.forEach(function (p, i) {
      if (i === 0 || i === pk.length - 1 || p[1] > pk[i - 1][1] || p[1] > pk[i + 1][1]) return;
      var x = p[0], y = p[1];
      path(o.g, "M" + P2(x - 24, y + 24) + "L" + P2(x, y) + "L" + P2(x + 24, y + 24) + "L" + P2(x + 12, y + 18) + "L" + P2(x + 2, y + 28) + "L" + P2(x - 10, y + 18) + "Z",
        { fill: "#ffffff", stroke: "#5f6f7c", "stroke-width": 4, "stroke-linejoin": "round" });
    });
    return o;
  };
  K.hill = function (sc, def, parent) {
    var o = absObj(sc, def, parent), x0 = def.x0 == null ? 380 : def.x0, x1 = def.x1 == null ? 780 : def.x1, top = def.top || 684, base = def.base || 860;
    var px = def.peak == null ? (x0 + x1) / 2 : def.peak;
    var d = "M" + P2(x0, base - 4) + "Q" + P2(x0 + (px - x0) * 0.4, top + 4) + " " + P2(px, top) + "Q" + P2(px + (x1 - px) * 0.6, top) + " " + P2(x1, top + 58);
    path(o.g, d + "L" + P2(x1, base) + "L" + P2(x0, base) + "Z", { fill: col(def.color, "#a7c957") });
    path(o.g, d, { fill: "none", stroke: INK, "stroke-width": 7, "stroke-linecap": "round", "stroke-linejoin": "round" });
    o.anchors = { center: [px, (top + base) / 2], top: [px, top] };
    return o;
  };
  K.ground = function (sc, def, parent) {
    var o = absObj(sc, def, parent), y = def.y || 856, x0 = def.x0 == null ? -60 : def.x0, x1 = def.x1 == null ? 780 : def.x1, gaps = def.gaps || [];
    var cuts = [[x0, x1]];
    gaps.forEach(function (gp) { var nc = []; cuts.forEach(function (c) { if (gp[1] <= c[0] || gp[0] >= c[1]) nc.push(c); else { if (gp[0] > c[0]) nc.push([c[0], gp[0]]); if (gp[1] < c[1]) nc.push([gp[1], c[1]]); } }); cuts = nc; });
    cuts.forEach(function (c) { var m = (c[0] + c[1]) / 2; path(o.g, "M" + P2(c[0], y) + "Q" + P2((c[0] + m) / 2, y - 8) + " " + P2(m, y) + "T" + P2(c[1], y - 2), { fill: "none", stroke: INK, "stroke-width": 7, "stroke-linecap": "round" }); });
    (def.tufts || []).forEach(function (x) { path(o.g, "M" + P2(x, y) + "l-5,-15 M" + P2(x + 7, y) + "l1,-20 M" + P2(x + 14, y) + "l6,-14", { fill: "none", stroke: INK, "stroke-width": 4, "stroke-linecap": "round" }); });
    return o;
  };
  /* anchored objects: x,y = bottom centre (houses, buildings, tents, signs) */
  K.house = function (sc, def, parent) {
    var w = def.w || 130, h = def.h || 104, o = new Obj(sc, def, parent), g = o.g;
    D.el(g, "rect", { x: -w / 2, y: -h, width: w, height: h, fill: col(def.wall, "#f4a261"), stroke: INK, "stroke-width": 7 });
    path(g, "M" + P2(-w / 2 - 22, -h) + "L" + P2(0, -h - 0.6 * w) + "L" + P2(w / 2 + 22, -h) + "Z", fillS(col(def.roof, "#8d6e63")));
    D.el(g, "rect", { x: w * 0.02, y: -70, width: w * 0.26, height: 70, fill: "#8d6e63", stroke: INK, "stroke-width": 7 });
    D.el(g, "rect", { x: -w / 2 + 18, y: -h + 26, width: 36, height: 36, fill: "#8ecae6", stroke: INK, "stroke-width": 5 });
    path(g, "M" + P2(-w / 2 + 36, -h + 26) + "L" + P2(-w / 2 + 36, -h + 62) + "M" + P2(-w / 2 + 18, -h + 44) + "L" + P2(-w / 2 + 54, -h + 44), S5);
    o.anchors = { center: [0, -h / 2], top: [0, -h - 0.6 * w] };
    return o;
  };
  K.building = function (sc, def, parent, beats) {
    var w = def.w || 180, h = def.h || 140, o = new Obj(sc, def, parent), g = o.g, n = def.windows == null ? 2 : def.windows;
    D.el(g, "rect", { x: -w / 2, y: -h, width: w, height: h, fill: col(def.wall, "#eef4f7"), stroke: INK, "stroke-width": 7 });
    path(g, "M" + P2(-w / 2 - 10, -h) + "L" + P2(w / 2 + 10, -h), { fill: "none", stroke: INK, "stroke-width": 12, "stroke-linecap": "round" });
    D.el(g, "rect", { x: -22, y: -78, width: 44, height: 78, fill: "#8d6e63", stroke: INK, "stroke-width": 7 });
    var wins = [];
    for (var i = 0; i < n; i++) { var wx = n === 1 ? -w / 2 + 18 : -w / 2 + 18 + (i * (w - 80)) / (n - 1); wins.push(windowG(g, wx, -h + 40, 44, 44)); }
    if ((def.type || "clinic") === "clinic") { path(g, "M0," + (-h) + "L0," + (-h - 30), S7); redCross(g, 0, -h - 52, 26); }
    o.anchors = { center: [0, -h / 2], top: [0, -h - 60] };
    o.shards = [];
    var brk = [];
    (beats || []).forEach(function (b) {
      if (b.do !== "shatter") return;
      var list = b.window == null || b.window === "all" ? wins.map(function (_, k) { return k; }) : [].concat(b.window);
      list.forEach(function (k, m) {
        var tt = b.t + m * (b.stagger || 0);
        brk.push([k, tt]);
        o.shards.push(new D.Shards({ parent: sc.layer("front"), n: 10, x: (def.x || 0) + wins[k].cx, y: (def.y || 0) + wins[k].cy, w: 44, h: 44, dir: b.dir || -1, t0: tt, gy: (def.y || 0) + 2, seed: 40 + k * 17 }));
      });
    });
    o.render = function (t) {
      o.place(t);
      wins.forEach(function (wd, k) { var b = brk.some(function (x) { return x[0] === k && t >= x[1]; }); wd.ok.setAttribute("opacity", b ? 0 : 1); wd.br.setAttribute("opacity", b ? 1 : 0); });
      o.shards.forEach(function (s) { s.render(t); });
    };
    o.beat = function (b) { return b.do === "shatter" ? true : genericBeat(o, b); };
    return o;
  };
  K.tent = function (sc, def, parent) {
    var o = new Obj(sc, def, parent), g = o.g;
    path(g, "M-96,0 L-70,-104 L70,-104 L96,0 Z", fillS("#ffffff"));
    path(g, "M-70,-104 L-44,0 M70,-104 L44,0", S5);
    path(g, "M-30,0 L0,-66 L30,0 Z", fillS("#dfe7ee", 5));
    path(g, "M0,-104 L0,-150", S5); path(g, "M0,-150 L34,-140 L0,-130 Z", fillS("#e63946", 5));
    redCross(g, 0, -82, 16);
    o.anchors = { center: [0, -60], door: [0, -10] };
    return o;
  };
  K.sign = function (sc, def, parent, beats) {
    var o = new Obj(sc, def, parent), g = D.el(o.g, "g", {});
    path(g, "M0,0 L0,-120", { fill: "none", stroke: INK, "stroke-width": 9, "stroke-linecap": "round" });
    path(g, "M-52,-112 L0,-200 L52,-112 Z", fillS(col(def.color, "#ffd166")));
    D.text(g, def.text || "!", { x: 0, y: -126, "text-anchor": "middle", "font-family": "Comic Neue", "font-weight": 700, "font-size": 64, fill: INK });
    var hits = [];
    (beats || []).forEach(function (b) { if (b.do === "hammer") for (var i = 0; i < (b.hits || 3); i++) hits.push(b.t + 0.12 + i * (b.every || 0.2)); });
    o.render = function (t) {
      var q = o.place(t), dy = 0, sq = 0;
      if (hits.length) {
        var ts = hits[0] - 0.12, n = hits.length, step = 54 / n;
        dy = t < ts ? -300 : D.lerp(-300, -54, D.ev(t, ts, ts + 0.12, "power2.in"));
        hits.forEach(function (h, i) { if (t >= h) dy = D.lerp(-54 + i * step, -54 + (i + 1) * step, D.ev(t, h, h + 0.05, "power3.in")); sq += D.jiggle(t, h + 0.05, 0.06, 9, 14); });
        g.setAttribute("opacity", t < ts ? 0 : 1);
      }
      g.setAttribute("transform", "translate(0," + D.r1(dy) + ") scale(" + (1 + sq).toFixed(3) + "," + (1 - sq).toFixed(3) + ")");
    };
    o.beat = function (b) { return b.do === "hammer" ? true : genericBeat(o, b); };
    o.anchors = { center: [0, -150], top: [0, -200] };
    return o;
  };
  /* tape between two posts: x0,x1 at ground y; unroll reveals it */
  K.tape = function (sc, def, parent, beats) {
    var o = absObj(sc, def, parent), g = o.g, x0 = def.x0, x1 = def.x1, y = def.y, top = y - (def.height || 54), sag = def.sag == null ? 12 : def.sag;
    var posts = [x0, x1].map(function (x) { var pg = D.el(g, "g", { opacity: 0 }); path(pg, "M" + P2(x, y + 4) + "L" + P2(x, top - 10), { fill: "none", stroke: INK, "stroke-width": 8, "stroke-linecap": "round" }); D.el(pg, "circle", { cx: x, cy: top - 10, r: 6, fill: "#e63946", stroke: INK, "stroke-width": 3 }); return pg; });
    var cid = D.uid("tape"), cp = D.el(D.defs(g), "clipPath", { id: cid }), cr = D.el(cp, "rect", { x: x0 - 12, y: top - 60, width: 0, height: 140 });
    var tg = D.el(g, "g", { "clip-path": "url(#" + cid + ")" }), d = "M" + P2(x0, top) + "Q" + P2((x0 + x1) / 2, top + 2 * sag) + " " + P2(x1, top);
    path(tg, d, { fill: "none", stroke: INK, "stroke-width": 15, "stroke-linecap": "round" });
    path(tg, d, { fill: "none", stroke: "#ffd166", "stroke-width": 9 });
    path(tg, d, { fill: "none", stroke: INK, "stroke-width": 9, "stroke-dasharray": "12 12" });
    var un = null;
    (beats || []).forEach(function (b) { if (b.do === "unroll") un = b; });
    o.render = function (t) {
      o.place(t);
      if (!un) { cr.setAttribute("width", x1 - x0 + 24); posts.forEach(function (p) { p.setAttribute("opacity", 1); }); return; }
      posts.forEach(function (p, i) { var s = D.pop(t, un.t + i * 0.08, 0.3); p.setAttribute("opacity", t < un.t + i * 0.08 ? 0 : 1); p.setAttribute("transform", D.tfAbout(i ? x1 : x0, y, 1, Math.max(0.001, s))); });
      cr.setAttribute("width", D.r1((x1 - x0 + 24) * D.ev(t, un.t + 0.15, un.t + 0.15 + (un.dur || 0.7), "power2.inOut")));
    };
    o.beat = function (b) { return b.do === "unroll" ? true : genericBeat(o, b); };
    o.anchors = { center: [(x0 + x1) / 2, top], left: [x0, top], right: [x1, top] };
    return o;
  };
  /* straight / poly line: styles ink | gold | dash ; draw_line reveals it; arrows: both|end */
  K.line = function (sc, def, parent, beats) {
    var o = absObj(sc, def, parent), pts = def.points, d = "M" + pts.map(function (p) { return P2(p[0], p[1]); }).join("L");
    var st = def.style || "ink", w = def.width || 7, els = [];
    if (st === "gold") { els.push(path(o.g, d, { fill: "none", stroke: INK, "stroke-width": w * 2, "stroke-linecap": "round", "stroke-linejoin": "round" })); els.push(path(o.g, d, { fill: "none", stroke: "#FFCD28", "stroke-width": w, "stroke-linecap": "round", "stroke-linejoin": "round" })); }
    else els.push(path(o.g, d, { fill: "none", stroke: col(def.color, INK), "stroke-width": w, "stroke-linecap": "round", "stroke-linejoin": "round", "stroke-dasharray": st === "dash" ? "18 14" : null }));
    var heads = [];
    if (def.arrows) {
      var mkHead = function (a, b) {
        var ang = Math.atan2(b[1] - a[1], b[0] - a[0]), hg = D.el(o.g, "g", {}), l = 16;
        var hd = "M" + P2(b[0] + Math.cos(ang + 2.5) * l, b[1] + Math.sin(ang + 2.5) * l) + "L" + P2(b[0], b[1]) + "L" + P2(b[0] + Math.cos(ang - 2.5) * l, b[1] + Math.sin(ang - 2.5) * l);
        if (st === "gold") path(hg, hd, { fill: "none", stroke: INK, "stroke-width": w * 2, "stroke-linecap": "round", "stroke-linejoin": "round" });
        path(hg, hd, { fill: "none", stroke: st === "gold" ? "#FFCD28" : col(def.color, INK), "stroke-width": w, "stroke-linecap": "round", "stroke-linejoin": "round" });
        heads.push({ g: hg, x: b[0], y: b[1] });
      };
      if (def.arrows === "both" || def.arrows === "start") mkHead(pts[1], pts[0]);
      if (def.arrows === "both" || def.arrows === "end") mkHead(pts[pts.length - 2], pts[pts.length - 1]);
    }
    var dr = null;
    (beats || []).forEach(function (b) { if (b.do === "draw_line" || b.do === "draw") dr = b; });
    var ons = dr && st !== "dash" ? els.map(function (e) { return new D.DrawOn(e); }) : null;
    o.render = function (t) {
      o.place(t);
      if (!dr) return;
      var p = D.ev(t, dr.t, dr.t + (dr.dur || 0.4), "power2.out");
      if (ons) ons.forEach(function (e) { e.set(p); }); else els.forEach(function (e) { e.setAttribute("opacity", p > 0 ? 1 : 0); });
      heads.forEach(function (h) { var s = D.pop(t, dr.t + (dr.dur || 0.4) - 0.05, 0.25); h.g.setAttribute("transform", D.tfAbout(h.x, h.y, Math.max(0.001, s), Math.max(0.001, s))); });
    };
    o.beat = function (b) { return b.do === "draw_line" || b.do === "draw" ? true : genericBeat(o, b); };
    o.anchors = { center: [(pts[0][0] + pts[pts.length - 1][0]) / 2, (pts[0][1] + pts[pts.length - 1][1]) / 2], start: pts[0], end: pts[pts.length - 1] };
    return o;
  };
  /* world text (e.g. gold measure label or a sign): style gold | ink */
  K.text = function (sc, def, parent) {
    var o = new Obj(sc, def, parent), gold = (def.style || "ink") === "gold", sz = def.size || 40;
    D.text(o.g, def.text || "", { x: 0, y: 0, "text-anchor": "middle", "dominant-baseline": "central", "font-family": "Comic Neue", "font-weight": 700, "font-size": sz,
      fill: gold ? "#FFCD28" : col(def.color, INK), stroke: gold ? INK : "none", "stroke-width": gold ? sz * 0.15 : 0, "stroke-linejoin": "round", "paint-order": "stroke fill" });
    return o;
  };
  /* rock: dark stone with glowing, pulsing cracks and an optional halo */
  K.rock = function (sc, def, parent) {
    var o = new Obj(sc, def, parent), g = o.g, s = def.size || 1;
    if (def.glow !== false) o.halo = D.el(g, "ellipse", { cx: 0, cy: 0, rx: 150 * s, ry: 105 * s, fill: D.radial(g, [[0, "#ffe08a", 1], [0.5, "#ffb347", 0.7], [1, "#ff8c42", 0]]) });
    path(g, "M" + [[-62, 18], [-50, -22], [-14, -40], [30, -34], [60, -10], [66, 20], [36, 38], [-30, 40]].map(function (p) { return P2(p[0] * s, p[1] * s); }).join("L") + "Z", fillS("#474747"));
    o.cr = path(g, "M" + P2(-30 * s, -8 * s) + "L" + P2(-12 * s, 10 * s) + "L" + P2(-22 * s, 28 * s) + "M" + P2(10 * s, -22 * s) + "L" + P2(20 * s, 2 * s) + "L" + P2(6 * s, 24 * s) + "M" + P2(40 * s, -4 * s) + "L" + P2(50 * s, 16 * s),
      { fill: "none", stroke: "#f77f00", "stroke-width": 5, "stroke-linecap": "round", "stroke-linejoin": "round" });
    D.el(g, "circle", { cx: 34 * s, cy: 24 * s, r: 5 * s, fill: INK });
    o.render = function (t) {
      o.place(t);
      var sn = Math.sin(2 * Math.PI * 1.3 * t);
      o.cr.setAttribute("stroke", D.mix("#f77f00", "#ffd166", 0.5 + 0.5 * sn));
      if (o.halo) { o.halo.setAttribute("opacity", (0.7 + 0.3 * sn).toFixed(3)); o.halo.setAttribute("transform", "scale(" + (1 + 0.08 * sn).toFixed(3) + ")"); }
    };
    o.anchors = { center: [0, 0], top: [0, -40 * s] };
    return o;
  };
  /* custom shape from the screenplay's shapes table (mini drawing language) */
  function drawItems(sc, g, items, parts) {
    (items || []).forEach(function (it) {
      var st = it.style ? sc.styles[it.style] || {} : {}, a = {};
      a.fill = it.fill != null ? col(it.fill) : st.fill != null ? col(st.fill) : "none";
      a.stroke = it.stroke != null ? col(it.stroke) : st.stroke != null ? col(st.stroke) : INK;
      a["stroke-width"] = it.width != null ? it.width : st.width != null ? st.width : 7;
      a["stroke-linecap"] = "round"; a["stroke-linejoin"] = "round";
      if (it.opacity != null) a.opacity = it.opacity;
      if (it.dash) a["stroke-dasharray"] = it.dash;
      if (a.stroke === "none") delete a["stroke-width"];
      if (it.path) { a.d = it.path; D.el(g, "path", a); }
      else if (it.poly || it.line) { var pp = it.poly || it.line; a.d = "M" + pp.map(function (p) { return P2(p[0], p[1]); }).join("L") + (it.poly ? "Z" : ""); if (it.line && it.fill == null) a.fill = "none"; D.el(g, "path", a); }
      else if (it.circle) { a.cx = it.circle[0]; a.cy = it.circle[1]; a.r = it.circle[2]; D.el(g, "circle", a); }
      else if (it.ellipse) { a.cx = it.ellipse[0]; a.cy = it.ellipse[1]; a.rx = it.ellipse[2]; a.ry = it.ellipse[3]; D.el(g, "ellipse", a); }
      else if (it.rect) { a.x = it.rect[0]; a.y = it.rect[1]; a.width = it.rect[2]; a.height = it.rect[3]; if (it.rect[4]) a.rx = it.rect[4]; D.el(g, "rect", a); }
      else if (it.text) { D.text(g, String(it.text[2]), { x: it.text[0], y: it.text[1], "text-anchor": "middle", "dominant-baseline": "central", "font-family": "Comic Neue", "font-weight": 700, "font-size": it.size || 40, fill: it.fill != null ? col(it.fill) : INK }); }
      else if (it.group) {
        var pv = it.pivot || [0, 0], gg = D.el(g, "g", {}), inner = D.el(gg, "g", { transform: "translate(" + P2(-pv[0], -pv[1]) + ")" });
        drawItems(sc, inner, it.items, parts);
        parts[it.group] = { g: gg, pv: pv };
      } else if (it.use) {                                              // reuse another shape
        var ug = D.el(g, "g", { transform: "translate(" + P2(it.at ? it.at[0] : 0, it.at ? it.at[1] : 0) + ") scale(" + (it.scale || 1) + ")" });
        drawItems(sc, ug, sc.shapes[it.use], parts);
      }
    });
  }
  RT.drawItems = drawItems;
  K.shape = function (sc, def, parent) {
    var o = new Obj(sc, def, parent), parts = {};
    drawItems(sc, o.g, BUILTIN[def.shape] || sc.shapes[def.shape], parts);
    o.parts = {};
    Object.keys(parts).forEach(function (k) {                          // animatable sub-parts: id.part (pivot = their origin)
      var p = parts[k], po = new Obj(sc, { id: def.id + "." + k, x: p.pv[0], y: p.pv[1] }, null);
      po.g = p.g; po.g.setAttribute("data-oid", po.id);                 // the part's own group replaces the one made by Obj
      o.parts[k] = po; sc.objs[def.id + "." + k] = po;
    });
    o.render = function (t) { o.place(t); for (var k in o.parts) o.parts[k].place(t); };
    return o;
  };
  var BUILTIN = (RT.BUILTIN = {
    check: [{ line: [[-44, 0], [-12, 34], [52, -42]], width: 30 }, { line: [[-44, 0], [-12, 34], [52, -42]], stroke: "#52b788", width: 17 }],
    cross: [{ line: [[-36, -36], [36, 36]], width: 30 }, { line: [[36, -36], [-36, 36]], width: 30 }, { line: [[-36, -36], [36, 36]], stroke: "#e63946", width: 17 }, { line: [[36, -36], [-36, 36]], stroke: "#e63946", width: 17 }],
    question: [{ text: [0, 0, "?"], size: 92 }],
    exclaim: [{ text: [0, 0, "!"], size: 92 }],
    arrow_down: [{ line: [[0, -50], [0, 40]], width: 9 }, { line: [[-24, 16], [0, 42], [24, 16]], width: 9 }]
  });

  /* ------------------------------------------------------------ characters */
  var POSES = (RT.POSES = {
    stand: { lean: 0, tilt: 0, hipDx: 0, hipDy: 0, kneel: 0, sit: 0, shr: 0, ebB: 0, ebF: 0, hbx: -3, hby: 64, hfx: 4, hfy: 64, swing: 1, wF: 0, wB: 0, hunch: 0 },
    point: { wF: 1, swing: 0 },
    look_up: { tilt: -16, lean: -4 },
    lean_in: { lean: 10, tilt: 8 },
    hands_up: { hfx: 30, hfy: -60, hbx: -30, hby: -56, ebB: 1, lean: -10, wF: 0, swing: 0 },
    cover: { hfx: 24, hfy: -36, hbx: -16, hby: -30, lean: -8, wF: 0, swing: 0 },
    head: { hfx: 30, hfy: -56, hbx: -30, hby: -54, ebB: 1, wF: 0, swing: 0 },
    cheeks: { hfx: 21, hfy: -44, hbx: -12, hby: -46, wF: 0, swing: 0 },
    belly: { lean: 38, hipDx: -8, hipDy: 6, tilt: 14, hbx: 14, hby: 40, hfx: 18, hfy: 46, wF: 0, swing: 0 },
    kneel: { kneel: 1, lean: 26, tilt: 12, hbx: 12, hby: 42, wF: 1, swing: 0 },
    sit: { sit: 1, lean: -6, tilt: 10, hbx: -26, hby: 44, ebB: 1, hfx: 16, hfy: 38, wF: 0, swing: 0 },
    shrug: { hfx: 30, hfy: 22, hbx: -34, hby: 22, ebB: 1, ebF: 1, shr: 11, tilt: -12, lean: -2, wF: 0, swing: 0 },
    scratch: { hbx: -20, hby: -60, ebB: 1, tilt: 7, swing: 0 },
    think: { hfx: 18, hfy: -34, tilt: 6, wF: 0, swing: 0 },
    shade: { hfx: 26, hfy: -60, wF: 0, swing: 0 },
    reach: { hfx: 55, hfy: 20, wF: 0, swing: 0, lean: 3 },
    megaphone: { hfx: 34, hfy: -4, lean: 6, tilt: -6, wF: 0, swing: 0 },
    stop: { hbx: 30, hby: 20, swing: 0 },
    cower: { hipDy: 7, lean: -8, hbx: 22, hby: -52, hfx: 26, hfy: -50, ebB: 1, wF: 0, swing: 0 },
    clasp: { hbx: 14, hby: 36, hfx: 20, hfy: 32, wF: 0, swing: 0 },
    help: { lean: 22, tilt: 10, hfx: 40, hfy: 30, wF: 0, swing: 0 },
    recoil: { lean: -4, tilt: -12 },
    wave: { hfx: 24, hfy: -62, ebF: 1, wF: 0, swing: 0 },
    arms_crossed: { hbx: 16, hby: 34, hfx: 12, hfy: 30, ebB: 1, wF: 0, swing: 0 }
  });
  var FACES = (RT.FACES = {
    ok: { eyes: "dot", mouth: "smile", brow: "none", open: 0 }, happy: { eyes: "closed", mouth: "smile", brow: "none", open: 0 },
    wow: { eyes: "wide", mouth: "o", brow: "up", open: 0.8 }, shout: { eyes: "dot", mouth: "o", brow: "up", open: 0.9 },
    sick: { eyes: "squint", mouth: "wavy", brow: "worried", open: 0 }, dizzy: { eyes: "x", mouth: "wavy", brow: "none", open: 0 },
    scared: { eyes: "wide", mouth: "wavy", brow: "worried", open: 0 }, think: { eyes: "dot", mouth: "flat", brow: "puzzled", open: 0 },
    flat: { eyes: "dot", mouth: "flat", brow: "none", open: 0 }, curious: { eyes: "dot", mouth: "o", brow: "none", open: 0.4 },
    worried: { eyes: "dot", mouth: "flat", brow: "worried", open: 0 }, sad: { eyes: "dot", mouth: "frown", brow: "worried", open: 0 },
    angry: { eyes: "dot", mouth: "frown", brow: "angry", open: 0 }, sleep: { eyes: "closed", mouth: "flat", brow: "none", open: 0 }
  });
  var NUMF = ["lean", "tilt", "hipDx", "hipDy", "shift", "kneel", "sit", "shr", "ebB", "ebF", "hbx", "hby", "hfx", "hfy", "swing", "open", "lx", "ly", "sick", "lookW", "wF", "wB", "hunch"];
  function foot(d, C, off, lift) {
    var v = d / C + off, n = Math.floor(v), u = v - n, P = (n - off) * C + C / 4;
    if (u < 0.5) return [P, 0];
    var w = (u - 0.5) / 0.5;
    return [P + C * D.smooth(w), lift * Math.sin(Math.PI * w)];
  }
  function Char(sc, def, parent, beats) {
    Obj.call(this, sc, def, parent);
    this.x.base = 0; this.y.base = 0;
    var k = (this.k = def.k || 1), hat = def.hat;
    this.fig = new D.Fig(this.g, { k: k, skin: def.skin || "#f5efe2", hat: hat ? col(hat[0] || hat) : null, hat2: hat && hat[1] ? col(hat[1]) : "#fff3b0",
      cap: def.cap ? col(def.cap) : null, nurse: !!def.nurse, hair: def.hair ? col(def.hair) : null, coat: !!def.coat, coatColor: def.coat && def.coat !== true ? col(def.coat) : null,
      coatLen: def.coat_len, glasses: !!def.glasses, stetho: !!def.stetho, mirror: !!def.mirror });
    this.gy = def.gy == null ? 900 : def.gy; this.x0 = def.x == null ? 360 : def.x;
    this.C = {}; var self = this;
    NUMF.forEach(function (f) { self.C[f] = new Chan(POSES.stand[f] != null ? POSES.stand[f] : 0); });
    this.C.lx.base = 3.5; this.C.swing.base = 1;
    var face = FACES[def.face || "ok"];
    this.eyes = new Steps(face.eyes); this.mouth = new Steps(face.mouth); this.brow = new Steps(face.brow); this.C.open.base = face.open;
    this.fd = new Steps(def.facing === "l" ? -1 : 1);
    this.aim = new Steps(null); this.look = new Steps(null); this.hold = new Steps(null); this.skinTo = new Steps("#a3cf62");
    this.walks = []; this.mods = [];
    this.props = {}; this.spirals = []; this.sweats = []; this._t = null;
  }
  inherit(Char);
  K.char = function (sc, def, parent, beats) { return new Char(sc, def, parent, beats); };
  Char.prototype.pose = function (t, fields, dur, ease) {
    for (var f in fields) if (this.C[f]) this.C[f].to(t, dur, fields[f], ease);
  };
  Char.prototype.face = function (t, name) {
    var F = FACES[name] || FACES.ok;
    this.eyes.set(t, F.eyes); this.mouth.set(t, F.mouth); this.brow.set(t, F.brow); this.C.open.to(t, 0.15, F.open, "back.out(2)");
  };
  Char.prototype.walkSeg = function (t, dur, x0, x1, o) {
    var k = this.k, dist = Math.abs(x1 - x0), C0 = (o.stride || 124) * k, m = Math.max(1, Math.round(dist / (C0 / 2)));
    var seg = { t0: t, t1: t + dur, x0: x0, x1: x1, dist: dist, C: dist > 0 ? (2 * dist) / m : C0, m: m, dir: x1 >= x0 ? 1 : -1, acc: o.acc || 0, dec: o.dec == null ? 0.35 : o.dec,
      lift: (o.lift || 17) * k, bob: (o.bob || 4) * k, off: 0 };
    var prev = this.walks[this.walks.length - 1];
    if (prev) {                                                       // keep feet continuous between walks
      var pe = this.feetOf(prev, prev.dist), best = 0, bd = 1e9;
      [0, 0.5].forEach(function (off) { seg.off = off; var s0 = this.feetOf(seg, 0), dd = Math.abs(s0[0][0] - pe[0][0]) + Math.abs(s0[1][0] - pe[1][0]); if (dd < bd) { bd = dd; best = off; } }, this);
      seg.off = best;
    }
    this.walks.push(seg);
  };
  Char.prototype.feetOf = function (W, d) {
    var r = [];
    for (var i = 0; i < 2; i++) { var fp = foot(d, W.C, (i ? 0.5 : 0) + W.off, W.lift); r.push([W.x0 + W.dir * fp[0], fp[1], (fp[0] - d) / (W.C / 4)]); }
    return r;
  };
  Char.prototype.gait = function (t) {
    var W = null, i;
    for (i = 0; i < this.walks.length; i++) if (t >= this.walks[i].t0 || i === 0) W = this.walks[i];
    if (!W) { var st = 20 * this.k, f = this.fd.at(t); return { x: this.x0, feet: [[this.x0 - st * f, 0, 0], [this.x0 + st * f, 0, 0]], bob: 0, mv: 0 }; }
    var d = W.dist * D.trap(D.prog(t, W.t0, W.t1), W.acc, W.dec), ft = this.feetOf(W, d);
    var mv = t < W.t0 ? 0 : 1 - D.prog(t, W.t1, W.t1 + 0.3);
    return { x: W.x0 + W.dir * d, feet: ft, bob: W.bob * Math.cos((4 * Math.PI * d) / W.C) * mv, mv: mv };
  };
  Char.prototype.resolve = function (spec, t) {                        // target -> world point
    if (!spec) return null;
    if (Array.isArray(spec)) return spec;
    if (spec === "up") { var h = this.fig.J.head || [this.x0, this.gy - 300]; return [h[0] + this.fd.at(t) * 60, h[1] - 400]; }
    if (spec === "down") { var h2 = this.fig.J.head || [this.x0, this.gy - 300]; return [h2[0] + this.fd.at(t) * 80, this.gy]; }
    if (spec === "ground") return [this.gait(t).x + this.fd.at(t) * 60 * this.k, this.gy - 2];
    var o = this.sc.objs[spec.split(":")[0]];
    return o ? o.anchor(spec.split(":")[1] || "center", t) : null;
  };
  Char.prototype.beat = function (b) {
    var t = b.t, self = this, k = this.k, d = b.dur, e = b.ease;
    var X = function (v) { return v === "left" ? -140 : v === "right" ? 860 : v; };
    switch (b.do) {
      case "enter": { var fx0 = X(b.from == null ? (this.x0 > 360 ? "right" : "left") : b.from), tx0 = X(b.to == null ? this.x0 : b.to);
        this.walkSeg(t, d || 1.4, fx0, tx0, b); this.fd.set(t - 1e-3, fx0 > tx0 ? -1 : 1); return true; }
      case "walk_to": case "walk": { var g0 = this.gait(t).x; this.walkSeg(t, d || 1.0, g0, X(b.to), b); this.fd.set(t, X(b.to) >= g0 ? 1 : -1); return true; }
      case "exit": { var g1 = this.gait(t).x, to = X(b.to || (g1 > 360 ? "right" : "left")); this.walkSeg(t, d || 1.2, g1, to, b); this.fd.set(t, to >= g1 ? 1 : -1); return true; }
      case "turn": this.fd.set(t, b.facing === "l" ? -1 : b.facing === "r" ? 1 : -this.fd.at(t)); this.C.hipDy.to(t, 0.06, -6, "power2.out"); this.C.hipDy.to(t + 0.06, 0.1, 0, "power2.in"); return true;
      case "pose": {
        var P = POSES[b.name];
        if (!P) throw new Error("unknown pose " + b.name);
        this.pose(t, P, d == null ? 0.26 : d, e || "back.out(1.6)");
        if (b.name === "point" || b.name === "kneel") { this.aim.set(t, b.target || (b.name === "kneel" ? "ground" : "up")); }
        this.mods.forEach(function (m) { if ((m.type === "scratch" || m.type === "wave") && m.t1 > t) m.t1 = t; });   // a new pose ends scratching / waving
        if (b.name === "scratch" || b.name === "wave") this.mods.push({ type: b.name, t0: t + 0.2, t1: t + 60 });
        return true;
      }
      case "get_sick": {                                               // green skin + sick face + bend/sit + dizzy spiral + sweat
        var st = b.style || "belly", un = b.until;
        this.skinTo.set(t, "#a3cf62"); this.C.sick.to(t, 0.4, 1, "power1.inOut"); this.face(t + 0.1, b.face || "sick");
        if (st === "belly") this.beat({ t: t + 0.12, do: "bend_over", until: un });
        else if (st === "sit") this.beat({ t: t + 0.12, do: "sit_down", until: un });
        else if (st === "sway") this.mods.push({ type: "sway", t0: t + 0.3, t1: un != null ? un : t + 60, amp: 4, freq: 1.3 });
        if (b.spiral !== false) this.beat({ t: t + 0.25, do: "dizzy", until: un });
        if (b.sweat !== false) this.beat({ t: t + 0.2, do: "sweat", until: un });
        return true;
      }
      case "dizzy": { var dg = D.el(this.fxLayer(), "g", { opacity: 0 }), dsp = D.stroke(4); dsp.d = D.spiral(19 * Math.max(0.8, k), 2.3, 40); D.el(dg, "path", dsp);
        this.spirals.push({ g: dg, t0: t, t1: b.until != null ? b.until : t + (d || 60) }); return true; }
      case "sweat": { var wg = D.el(this.fxLayer(), "g", { opacity: 0 }); path(wg, D.drop(0.65 * Math.max(0.8, k) * (b.size || 1)), fillS("#8ecae6", 3));
        this.sweats.push({ g: wg, t0: t, t1: b.until != null ? b.until : t + (d || 60), per: b.period || 0.62 }); return true; }
      case "point": this.pose(t, POSES.point, d == null ? 0.22 : d, e || "back.out(1.8)"); this.aim.set(t, b.target || "up"); return true;
      case "face": this.face(t, b.name); return true;
      case "color": this.skinTo.set(t, b.to === "green" || b.to == null ? "#a3cf62" : col(b.to)); this.C.sick.to(t, d == null ? 0.45 : d, b.to === "normal" ? 0 : 1, "power1.inOut"); return true;
      case "look": this.C.lookW.to(t, d == null ? 0.15 : d, 1, "power2.out"); this.look.set(t, b.target || "up");
        if (b.target === "up") this.C.tilt.to(t, 0.25, -16, "power3.out"); return true;
      case "hold": this.hold.set(t, b.prop || null); return true;
      case "drop": this.hold.set(t, null); return true;
      case "startle":
        this.pose(t, POSES.hands_up, 0.1, "power2.out"); this.C.hipDy.to(t, 0.1, -26, "power2.out"); this.C.hipDy.to(t + 0.1, 0.12, 6, "power2.in"); this.C.hipDy.to(t + 0.22, 0.2, 0, "power2.out"); return true;
      case "jump_back":
        this.pose(t, POSES.hands_up, 0.3, "power2.out"); this.C.shift.to(t, 0.3, this.C.shift.at(t) - (b.dist || 16), "power2.out");
        this.C.hipDy.to(t, 0.12, -16, "power2.out"); this.C.hipDy.to(t + 0.12, 0.14, 5, "power2.in"); this.C.hipDy.to(t + 0.26, 0.16, 0, "power2.out"); return true;
      case "step_back":
        this.C.shift.to(t, 0.3, this.C.shift.at(t) - (b.dist || 26), "power2.out"); this.C.lean.to(t, 0.3, -8, "power2.out"); this.C.lean.to(t + 0.35, 0.25, 0);
        this.C.hipDy.to(t, 0.14, -8, "power2.out"); this.C.hipDy.to(t + 0.14, 0.16, 0, "power2.in"); return true;
      case "kneel_down":
        this.C.hipDy.to(t, 0.12, -8, "power2.out"); this.C.lean.to(t, 0.12, -5, "power2.out");
        this.pose(t + 0.12, { kneel: 1, lean: 24, tilt: 14, hbx: 12, hby: 42, wF: 1, swing: 0 }, 0.2, "power2.in"); this.C.hipDy.to(t + 0.12, 0.2, 0, "power2.in");
        this.aim.set(t + 0.12, b.target || "ground"); this.C.hipDy.to(t + 0.32, 0.12, 7, "power2.out"); this.C.hipDy.to(t + 0.44, 0.26, 0, "back.out(2)"); this.C.lean.to(t + 0.44, 0.26, 30, "back.out(2)");
        this.mods.push({ type: "heave", t0: t + 0.7, t1: b.until != null ? b.until : t + 60 }); return true;
      case "bend_over":
        this.pose(t, { lean: -5, hbx: 14, hby: 40, hfx: 18, hfy: 46, swing: 0, wF: 0 }, 0.12, "power2.out");
        this.pose(t + 0.12, { lean: 38, hipDx: -8, hipDy: 6, tilt: 14 }, 0.26, "back.out(1.7)");
        this.mods.push({ type: "heave", t0: t + 0.4, t1: b.until != null ? b.until : t + 60 }); return true;
      case "sit_down":
        this.C.hipDy.to(t, 0.1, -6, "power2.out"); this.C.lean.to(t, 0.1, -4);
        this.pose(t + 0.1, { sit: 1, hipDy: 0, lean: -6, tilt: 10, hbx: -26, hby: 44, ebB: 1, hfx: 16, hfy: 38, swing: 0, wF: 0 }, 0.28, "power2.in");
        this.mods.push({ type: "sway", t0: t + 0.4, t1: b.until != null ? b.until : t + 60, amp: 3, freq: 1.3 }); return true;
      case "sniff":
        this.C.tilt.to(t, 0.12, -14, "power2.out"); this.C.lean.to(t, 0.12, -6, "power2.out"); this.face(t, "sick");
        this.C.sick.to(t + 0.05, 0.45, 1, "power1.inOut"); this.pose(t + 0.12, { hfx: 22, hfy: -30, swing: 0, wF: 0 }, 0.23, "back.out(1.6)"); return true;
      case "tremble": case "nod": case "heave": case "sway":
        this.mods.push({ type: b.do, t0: t, t1: b.until != null ? b.until : t + (d || 60), amp: b.amount || b.amp, freq: b.freq }); return true;
    }
    return genericBeat(this, b);
  };
  Char.prototype.fxLayer = function () { if (!this.fxg) this.fxg = D.el(this.sc.layer("top"), "g", {}); return this.fxg; };
  Char.prototype.anchor = function (name, t) {                         // always evaluated at time t (renders the rig there)
    if (t == null) t = this._t == null ? this.sc.t0 : this._t;
    this.render(t);
    var J = this.fig.J;
    if (name === "head") return J.head;
    if (name === "top") return [J.head[0], J.head[1] - this.fig.r - 10];
    if (name === "hand") return J.handF;
    if (name === "mouth") return [J.head[0] + J.f * this.fig.r * 0.45, J.head[1] + this.fig.r * 0.4];
    if (name === "prop" && this.propTip) return this.propTip;
    if (name === "feet") return [J.hip[0], this.gy];
    return [J.hip[0], J.hip[1] - this.fig.T * 0.5];
  };
  Char.prototype.render = function (t) {
    if (this._t === t && this.fig.J.head) return this.fig.J;          // already drawn for this time (anchors of other objects)
    this._t = t;
    var F = this.fig, k = F.k, C = this.C, P = {}, f;
    for (var n = 0; n < NUMF.length; n++) P[NUMF[n]] = C[NUMF[n]].at(t);
    var G = this.gait(t);
    f = this.fd.at(t);
    for (var m = 0; m < this.mods.length; m++) {
      var md = this.mods[m];
      if (t < md.t0 || t > md.t1) continue;
      var env = D.prog(t, md.t0, md.t0 + 0.3), fr = Math.floor(D.frame(t) / 2), ph = 2 * Math.PI * (t - md.t0);
      if (md.type === "tremble") { var a = md.amp || 1.4; P.hipDx += a * (D.hash(fr * 1.7 + m) * 2 - 1) * env; P.tilt += 1.5 * a * (D.hash(fr * 2.9 + 1 + m) * 2 - 1) * env; }
      else if (md.type === "nod") P.tilt += (md.amp || 6) * Math.sin(ph * (md.freq || 2.2)) * env;
      else if (md.type === "heave") { P.lean += (md.amp || 3.5) * Math.sin(ph * (md.freq || 2.4)) * env; P.tilt += 4 * Math.sin(ph * (md.freq || 2.4) - 0.8) * env; }
      else if (md.type === "sway") { P.lean += (md.amp || 6) * Math.sin(ph * (md.freq || 1.25)) * env; P.hipDx -= 0.5 * (md.amp || 6) * Math.sin(ph * (md.freq || 1.25)) * env; P.tilt += (md.amp || 6) * Math.sin(ph * (md.freq || 1.25) - 0.9) * env; }
      else if (md.type === "scratch") { P.hbx += 4 * Math.sin(2 * Math.PI * 7 * t) * env; P.hby += 3 * Math.sin(2 * Math.PI * 7 * t + 1.2) * env; }
      else if (md.type === "wave") P.hfx += 12 * Math.sin(2 * Math.PI * 3 * t) * env;
    }
    var q = this.place(t);
    var lean = P.lean + G.mv * 6, shx = P.shift * k * f;
    var hip = [G.x + shx + P.hipDx * k * f, this.gy - F.H0 + G.bob + P.hipDy * k];
    var kn = D.clamp(P.kneel, 0, 1.2), sit = D.clamp(P.sit, 0, 1);
    if (kn) hip[1] += kn * (F.H0 - 0.9 * F.th);
    if (sit) hip[1] = D.lerp(hip[1], this.gy - 15 * k + P.hipDy * k * 0.5, sit);
    var feet = [];
    for (var i = 0; i < 2; i++) {
      var fx0 = G.feet[i][0] + shx, fy0 = this.gy - G.feet[i][1];
      if (kn) { fx0 = D.lerp(fx0, hip[0] - f * (F.sh * 0.92 + i * 9 * k), Math.min(kn, 1)); fy0 = D.lerp(fy0, this.gy - 2, Math.min(kn, 1)); }
      if (sit) { fx0 = D.lerp(fx0, hip[0] + f * (60 + i * 14) * k, sit); fy0 = D.lerp(fy0, this.gy - 2, sit); }
      feet.push([fx0, fy0]);
    }
    var R = Math.PI / 180, la = lean * R, ux = Math.sin(la) * f, uy = -Math.cos(la), ffx = Math.cos(la) * f, ffy = Math.sin(la);
    var so = F.sOff - P.shr * k, sx = hip[0] + ux * (F.T - so), sy = hip[1] + uy * (F.T - so), armL = F.ua + F.fa, hands = [];
    var loc = [[P.hbx, P.hby], [P.hfx, P.hfy]];
    for (var j = 0; j < 2; j++) {
      var lx = loc[j][0] * k, ly = loc[j][1] * k, sw = P.swing * G.mv * -G.feet[j][2] * 0.5;
      if (sw) { var c = Math.cos(sw), s = Math.sin(sw), nl = lx * c + ly * s; ly = -lx * s + ly * c; lx = nl; }
      var wx = sx + ffx * lx - ux * ly, wy = sy + ffy * lx - uy * ly, ww = j ? P.wF : P.wB;
      if (ww > 0) {
        var tg = this.resolve(j ? this.aim.at(t) : null, t);
        if (tg) {
          var aimSpec = this.aim.at(t), stretch = aimSpec !== "ground";
          var tx = tg[0], ty = tg[1];
          if (stretch) { var dx = tx - sx, dy = ty - sy, dl = Math.hypot(dx, dy) || 1; tx = sx + (dx / dl) * armL * 0.985; ty = sy + (dy / dl) * armL * 0.985; }
          wx = D.lerp(wx, tx, ww); wy = D.lerp(wy, ty, ww);
        }
      }
      hands.push([wx, wy]);
    }
    var face = { eyes: this.eyes.at(t), mouth: this.mouth.at(t), brow: this.brow.at(t), open: P.open, lx: P.lx, ly: P.ly };
    if (P.lookW > 0) {
      var lt = this.resolve(this.look.at(t), t);
      if (lt) {
        var ha = (lean + P.tilt) * R, nx = hip[0] + ux * F.T, ny = hip[1] + uy * F.T, hcx = nx + Math.sin(ha) * f * F.r, hcy = ny - Math.cos(ha) * F.r;
        var ddx = lt[0] - hcx, ddy = lt[1] - hcy, dd = Math.hypot(ddx, ddy) || 1;
        face.lx = D.lerp(face.lx, (ddx / dd) * 5.5 * f, P.lookW); face.ly = D.lerp(face.ly, (ddy / dd) * 5.5, P.lookW);
      }
    }
    var skin = this.def.skin || "#f5efe2";
    if (P.sick > 0) skin = D.mix(skin, this.skinTo.at(t), P.sick);
    F.draw({ hip: hip, gy: this.gy, lean: lean, tilt: P.tilt, f: f, feet: feet, hands: hands, face: face, skin: skin, shr: P.shr * k, hunch: P.hunch,
      eb: [D.clamp(P.ebB, 0, 1), D.clamp(P.ebF, 0, 1)] });
    this.renderProp(t);
    var J = F.J, r = F.r, i2;
    for (i2 = 0; i2 < this.spirals.length; i2++) {                      // dizzy spiral above the head
      var s = this.spirals[i2];
      if (t < s.t0 || t > s.t1 || q.o <= 0.02) { s.g.setAttribute("opacity", 0); continue; }
      s.g.setAttribute("transform", D.tf(J.head[0], J.head[1] - r - 22 * k + 3 * Math.sin(2 * Math.PI * 1.6 * t + i2), -420 * (t - s.t0), Math.max(0.001, D.pop(t, s.t0, 0.28, "back.out(2.5)"))));
      s.g.setAttribute("opacity", 1);
    }
    for (i2 = 0; i2 < this.sweats.length; i2++) {                       // sweat drops flying off the head
      var w = this.sweats[i2], L = t <= w.t1 ? D.life(t, w.t0, w.per, 0) : null;
      if (!L || q.o <= 0.02) { w.g.setAttribute("opacity", 0); continue; }
      var v = L.u;
      w.g.setAttribute("transform", D.tf(J.head[0] - J.f * (r + 4 + 7 * v), J.head[1] - r * 0.2 + 50 * v * v + 8 * v, J.f * 12, 1));
      w.g.setAttribute("opacity", (Math.min(1, v / 0.1) * (1 - D.prog(v, 0.7, 1))).toFixed(3));
    }
    return F.J;
  };
  /* hand-held props: megaphone | magnifier | thermometer | flag */
  Char.prototype.renderProp = function (t) {
    var name = this.hold.at(t), J = this.fig.J, p;
    for (var key in this.props) this.props[key].g.setAttribute("opacity", key === name ? 1 : 0);
    if (!name) { this.propTip = null; return; }
    if (!this.props[name]) this.props[name] = PROP[name](this.fig.prop, this);
    p = this.props[name];
    p.place(t, J);
  };
  var PROP = (RT.PROP = {
    megaphone: function (parent, ch) {
      var g = D.el(parent, "g", {});
      path(g, "M-4,-9 L44,-24 L44,24 L-4,9 Z", fillS("#e9c46a", 5)); path(g, "M8,8 L4,22", { fill: "none", stroke: INK, "stroke-width": 6, "stroke-linecap": "round" });
      return { g: g, place: function (t, J) { var s = 1.45 * ch.k / 1.12; g.setAttribute("transform", "translate(" + P2(J.handF[0], J.handF[1]) + ") scale(" + (s * J.f).toFixed(3) + "," + s.toFixed(3) + ") rotate(-12)"); ch.propTip = [J.handF[0] + J.f * 64 * s, J.handF[1] - 14 * s]; } };
    },
    magnifier: function (parent, ch) {
      var g = D.el(parent, "g", {}), lid = D.uid("lens"), cp = D.el(D.defs(g), "clipPath", { id: lid });
      D.el(cp, "circle", { cx: 94, cy: 0, r: 40 });
      path(g, "M0,0 L52,0", { fill: "none", stroke: INK, "stroke-width": 17, "stroke-linecap": "round" }); path(g, "M0,0 L52,0", { fill: "none", stroke: "#8d6e63", "stroke-width": 11, "stroke-linecap": "round" });
      var inner = D.el(g, "g", { "clip-path": "url(#" + lid + ")" });
      D.el(inner, "rect", { x: 40, y: -60, width: 120, height: 120, fill: "#e8f3f8" });
      var mag = D.el(inner, "g", {});
      D.el(mag, "circle", { cx: 94, cy: 58, r: 70, fill: "#8a8a8a", stroke: INK, "stroke-width": 6 });
      for (var i = 0; i < 12; i++) D.el(mag, "circle", { cx: D.r1(94 + D.rnd(i * 3.3, -55, 55)), cy: D.r1(D.rnd(i * 4.7, 10, 90)), r: D.r1(D.rnd(i * 5.9, 3, 8)), fill: i % 3 ? "#5a5a5a" : "#b8b8b8" });
      D.el(g, "circle", { cx: 94, cy: 0, r: 44, fill: "none", stroke: INK, "stroke-width": 9 });
      path(g, "M70,-26 Q62,-10 64,6", { fill: "none", stroke: "#ffffff", "stroke-width": 5, "stroke-linecap": "round" });
      return { g: g, place: function (t, J) { g.setAttribute("transform", "translate(" + P2(J.handF[0], J.handF[1]) + ") scale(" + J.f + ",1) rotate(-22)"); mag.setAttribute("transform", "translate(" + D.r1(4 * Math.sin(3 * t)) + ",0)"); ch.propTip = [J.handF[0] + J.f * 87, J.handF[1] - 35]; } };
    },
    thermometer: function (parent, ch) {
      var g = D.el(parent, "g", {}), TL = 236;
      D.el(g, "rect", { x: -44, y: -17, width: TL + 44, height: 34, rx: 17, fill: "#ffffff", stroke: INK, "stroke-width": 6 });
      var colp = path(g, "", { fill: "none", stroke: "#e63946", "stroke-width": 13, "stroke-linecap": "round" });
      D.el(g, "circle", { cx: TL, cy: 0, r: 27, fill: "#e63946", stroke: INK, "stroke-width": 6 });
      return { g: g, place: function (t, J) { var lv = ch.level ? ch.level(t) : 0.2; colp.setAttribute("d", "M" + (TL - 20) + ",0L" + D.r1(TL - 20 - lv * (TL + 12)) + ",0"); g.setAttribute("transform", "translate(" + P2(J.handF[0], J.handF[1]) + ") scale(" + J.f + ",1) rotate(22)"); ch.propTip = [J.handF[0] + J.f * TL * 0.93, J.handF[1] + TL * 0.37]; } };
    }
  });

  /* cyclist: bike + rider; ride / wobble / tip_over / wave */
  K.rider = function (sc, def, parent, beats) {
    var o = absObj(sc, def, parent), bike = new D.Bike(o.g, { s: def.bike_scale || 1, color: col(def.bike, "#2a9d8f"), rider: { k: def.k || 0.92, hat: def.hat ? col(def.hat[0]) : null, hat2: def.hat ? col(def.hat[1]) : null } });
    var rides = [], tip = null, wave = null, wob = null, faces = new Steps({ eyes: "dot", mouth: "smile", lx: 3 }), x0 = def.x == null ? -150 : def.x, gy = def.gy || 903;
    (beats || []).forEach(function (b) {
      if (b.do === "ride") rides.push({ t0: b.t, t1: b.t + (b.dur || 3), x0: b.from == null ? x0 : b.from, x1: b.to });
      if (b.do === "wobble") { wob = b; faces.set(b.t, { eyes: "wide", mouth: "o", open: 0.8, brow: "up", lx: 1, ly: -1 }); }
      if (b.do === "tip_over") { tip = b; faces.set(b.t + (b.dur || 0.34) + 0.02, { eyes: "closed", mouth: "smile", lx: 2 }); }
      if (b.do === "wave") wave = b;
      if (b.do === "face") faces.set(b.t, FACES[b.name] || FACES.ok);
    });
    function xAt(t) {
      var x = x0, i, r;
      for (i = 0; i < rides.length; i++) { r = rides[i]; if (t >= r.t0) x = r.x0 + (r.x1 - r.x0) * D.prog(t, r.t0, r.t1); }
      if (wob && t > wob.t) { var r0 = rides.filter(function (q) { return q.t0 <= wob.t; }).pop(); if (r0) { var v = (r0.x1 - r0.x0) / (r0.t1 - r0.t0), xw = r0.x0 + v * (wob.t - r0.t0); x = xw + (v / 3) * (1 - Math.exp(-3 * (t - wob.t))); } }
      return x;
    }
    o.render = function (t) {
      o.place(t);
      var x = xAt(t), rot = 0;
      if (wob && t >= wob.t) rot = 10 * Math.sin(2 * Math.PI * 4 * (t - wob.t)) * (1 - D.prog(t - wob.t, 0.2, 0.42));
      if (tip && t >= tip.t) { var d = tip.dur || 0.34; rot -= 76 * D.ease("power2.in")(D.prog(t, tip.t, tip.t + d)); if (t > tip.t + d) rot += D.jiggle(t, tip.t + d, 7, 3, 6); }
      var J = bike.render(t, { x: x, gy: gy, rot: rot, dist: Math.max(0, x - x0), lean: 24 - 0.1 * rot, face: faces.at(t), wave: wave ? D.ev(t, wave.t, wave.t + 0.25, "power2.out") : 0 });
      var a = (rot * Math.PI) / 180;
      o.head = [x + J.head[0] * Math.cos(a) - J.head[1] * Math.sin(a), gy + J.head[0] * Math.sin(a) + J.head[1] * Math.cos(a)];
      o.xNow = x;
    };
    o.anchor = function (name, t) { o.render(t); return name === "head" || name === "top" ? [o.head[0], o.head[1] - (name === "top" ? 40 : 0)] : [o.xNow + 50, gy - 60]; };
    o.beat = function (b) { return ["ride", "wobble", "tip_over", "wave", "face"].indexOf(b.do) >= 0 ? true : genericBeat(o, b); };
    return o;
  };

  /* ------------------------------------------------------------ fx objects */
  K.meteor = function (sc, def, parent, beats) {
    var fly = (beats || []).filter(function (b) { return b.do === "fly"; })[0] || { t: -10, dur: 1 };
    var o = absObj(sc, def, parent), m = new D.Meteor({ parent: o.g, smokeParent: D.el(o.g, "g", {}), P: def.path, t0: fly.t, t1: fly.t + (fly.dur || 1),
      acc: fly.acc == null ? 0.34 : fly.acc, s0: def.s0 || 0.55, s1: def.s1 || 1.15, smoke: def.smoke == null ? 24 : def.smoke, smokeUntil: 0.8 });
    o.render = function (t) { o.place(t); m.render(t); };
    o.anchor = function (name, t) { var p = m.pos(t); return [p[0], p[1]]; };
    o.beat = function (b) { return b.do === "fly" ? true : genericBeat(o, b); };
    return o;
  };
  K.impact = function (sc, def, parent, beats) {
    var ex = (beats || []).filter(function (b) { return b.do === "explode"; })[0] || { t: 1e9 };
    var o = new Obj(sc, { id: def.id }, parent), front = sc.layer("front");
    var im = new D.Impact({ back: o.g, front: D.el(front, "g", {}), x: def.at[0], y: def.at[1], t0: ex.t, gy: def.floor || 905 });
    if (def.clip) { var cid = D.uid("imp"), cp = D.el(D.defs(o.g), "clipPath", { id: cid }); D.el(cp, "rect", { x: -400, y: -400, width: 1600, height: def.clip + 400 }); o.g.setAttribute("clip-path", "url(#" + cid + ")"); }
    o.render = function (t) { im.render(t); };
    o.anchor = function () { return [def.at[0], def.at[1] - 60]; };
    o.beat = function (b) { return b.do === "explode" ? true : genericBeat(o, b); };
    return o;
  };
  K.shockwave = function (sc, def, parent, beats) {
    var go = (beats || []).filter(function (b) { return b.do === "go"; })[0] || { t: 1e9 }, o = new Obj(sc, { id: def.id }, parent), front = sc.layer("top");
    var RX = def.at[0], RY = def.at[1], V = def.speed || 390, arcs = [], dust = [], i;
    for (i = 0; i < 3; i++) arcs.push(D.el(front, "path", { fill: "none", stroke: INK, "stroke-width": [7, 5, 3.5][i], "stroke-linecap": "round", opacity: 0 }));
    for (i = 0; i < 10; i++) { var dg = D.el(o.g, "g", { opacity: 0 }); path(dg, D.puff(D.rnd(i * 2.7, 20, 30), 6, i * 7 + 2), fillS("#efe5d3", 4)); dust.push({ g: dg, x: RX - 55 - i * 60 }); }
    o.render = function (t) {
      var R = V * (t - go.t), on = t >= go.t && R < 760;
      for (var j = 0; j < 3; j++) {
        var r = R - j * 24;
        if (!on || r < 30) { arcs[j].setAttribute("opacity", 0); continue; }
        var a1 = Math.PI + Math.min(0.62, 230 / r);
        arcs[j].setAttribute("d", "M" + P2(RX - r, RY) + "A" + D.r1(r) + "," + D.r1(r) + " 0 0 1 " + P2(RX + Math.cos(a1) * r, RY + Math.sin(a1) * r));
        arcs[j].setAttribute("opacity", ([0.95, 0.6, 0.35][j] * (1 - D.prog(R, 560, 760))).toFixed(3));
      }
      dust.forEach(function (q) { var u = t - go.t - (RX - q.x) / V; if (u < 0 || u > 0.9) { q.g.setAttribute("opacity", 0); return; } q.g.setAttribute("transform", D.tf(q.x - 30 * u, RY - 8 - 34 * u, 0, 0.35 + 0.8 * (1 - Math.exp(-5 * u)))); q.g.setAttribute("opacity", (1 - D.prog(u, 0.45, 0.9)).toFixed(3)); });
    };
    o.beat = function (b) { return b.do === "go" ? true : genericBeat(o, b); };
    return o;
  };
  K.crater = function (sc, def, parent, beats) {
    var o = new Obj(sc, def, parent), wl = null, boil = null, drops = [];
    (beats || []).forEach(function (b) { if (b.do === "water_level") wl = b; if (b.do === "boil") boil = b; if (b.do === "splash") drops.push(b.t); });
    var inner = D.el(o.g, "g", {});
    var c = new D.Crater({ parent: inner, fillT0: wl ? wl.t : null, fillT1: wl ? wl.t + (wl.dur || 0.6) : null, boilT0: boil ? boil.t : def.level === "empty" ? 1e9 : -100,
      boilT1: boil ? boil.t + (boil.ramp || 0.3) : -100, drops: drops });
    if (!wl && def.level === "empty") c.level = function () { return 410; };
    o.render = function (t, ctx) { o.place(t); var z = (ctx ? ctx.z : 1) * (def.scale || 1); c.render(t, { vis: D.prog(z, 0.57, 0.8), steam: 0.55 + 0.45 * D.prog(z, 0.5, 0.8) }); };
    o.anchors = { center: [0, 0], rock: [0, 345], surface: [0, 40] };
    o.beat = function (b) { return ["water_level", "boil", "splash"].indexOf(b.do) >= 0 ? true : genericBeat(o, b); };
    return o;
  };
  K.underground = function (sc, def, parent) {
    var o = absObj(sc, def, parent), g = o.g, top = def.top || 640, wt = def.water || 1292, x0 = -400, x1 = 1100, i;
    var bands = def.layers || ["#c9a06e", "#b5835a", "#9c6b4a"], n = bands.length, h = (wt - top) / n;
    for (i = 0; i < n; i++) path(g, "M" + P2(x0, top + i * h) + "L" + P2(x1, top + i * h) + "L" + P2(x1, top + (i + 1) * h + 8) + "L" + P2(x0, top + (i + 1) * h + 8) + "Z", { fill: bands[i] });
    for (i = 1; i < n; i++) path(g, "M" + P2(x0, top + i * h) + "Q0," + D.r1(top + i * h - 14) + " 360," + D.r1(top + i * h) + "T" + P2(x1, top + i * h), { fill: "none", stroke: "#6d4c35", "stroke-width": 5, "stroke-dasharray": "26 18", "stroke-linecap": "round" });
    [[60, 0.09, 16, 10], [250, 0.18, 12, 8], [640, 0.12, 18, 11], [140, 0.4, 22, 13], [380, 0.49, 16, 10], [600, 0.38, 20, 12],   // pebbles: scattered, never on the crack
      [90, 0.74, 30, 18], [330, 0.83, 24, 14], [560, 0.71, 34, 20], [690, 0.87, 22, 13]].forEach(function (p) {
      D.el(g, "ellipse", { cx: p[0], cy: D.r1(top + p[1] * (wt - top)), rx: p[2], ry: p[3], fill: D.mix(bands[Math.min(n - 1, Math.floor(p[1] * n))], "#3b2a1e", 0.25), stroke: INK, "stroke-width": 4 });
    });
    var water = path(g, "", { fill: "#4fa3d1" }), wline = path(g, "", { fill: "none", stroke: INK, "stroke-width": 5 });
    o.anchors = { center: [360, (top + wt) / 2], water: [360, wt + 60], surface: [def.pit ? def.pit[0] : 360, top] };
    if (def.crack) { var cd = "M" + def.crack.map(function (p) { return P2(p[0], p[1]); }).join("L"); path(g, cd, { fill: "none", stroke: "#3b2a1e", "stroke-width": 16 }); path(g, cd, { fill: "none", stroke: INK, "stroke-width": 5, "stroke-dasharray": "3 14" }); }
    var pit = def.pit;
    path(g, pit ? "M" + P2(x0, top) + "L" + P2(pit[0] - pit[1] / 2, top) + "M" + P2(pit[0] + pit[1] / 2, top) + "L" + P2(x1, top) : "M" + P2(x0, top) + "L" + P2(x1, top), S7);
    if (pit) path(g, "M" + P2(pit[0] - pit[1] / 2, top) + "Q" + P2(pit[0], top + 60) + " " + P2(pit[0] + pit[1] / 2, top), fillS("#8a6446"));
    o.render = function (t) {
      o.place(t);
      var d = "";
      for (var x = -60; x <= 780; x += 30) d += (x === -60 ? "M" : "L") + x + "," + D.r1(wt + 5 * Math.sin(0.03 * x - 3.1 * t) + 3 * Math.sin(0.07 * x + 4.3 * t));
      wline.setAttribute("d", d); water.setAttribute("d", d + "L780," + (wt + 700) + "L-60," + (wt + 700) + "Z");
    };
    return o;
  };
  /* thought cloud above a character (on:) - pop / grow / darken / bolt */
  K.thought = function (sc, def, parent, beats) {
    var o = absObj(sc, def, parent), who = def.on, g1 = D.el(o.g, "circle", { r: 10, fill: "#4a4f57", stroke: INK, "stroke-width": 4, opacity: 0 }), g2 = D.el(o.g, "circle", { r: 16, fill: "#4a4f57", stroke: INK, "stroke-width": 5, opacity: 0 });
    var cg = D.el(o.g, "g", { opacity: 0 }), cloud = path(cg, "", fillS("#6b7280")), scr = "", sa = 0, i;
    for (i = 0; i < 26; i++) { sa += 2.1 + D.hash(i * 3.7) * 1.4; var rr = 18 + 34 * D.hash(i * 5.3); scr += (i ? "L" : "M") + P2(Math.cos(sa) * rr * 1.3, Math.sin(sa) * rr * 0.7); }
    var sg = path(cg, scr, { fill: "none", stroke: "#f1f1f1", "stroke-width": 4.5, "stroke-linecap": "round", "stroke-linejoin": "round" });
    var bolt = path(cg, "M-8,-34 L10,-6 L-4,-4 L12,30", { fill: "none", stroke: "#ffd166", "stroke-width": 7, "stroke-linecap": "round", "stroke-linejoin": "round", opacity: 0 });
    var popT = 1e9, grow = new Chan(1), dark = new Chan(0), boltT = 1e9;
    (beats || []).forEach(function (b) { if (b.do === "pop") popT = b.t; if (b.do === "grow") grow.to(b.t, b.dur || 0.35, b.to || 1.35, "back.out(2)"); if (b.do === "darken") dark.to(b.t, b.dur || 0.35, b.to == null ? 1 : b.to); if (b.do === "bolt") boltT = b.t; });
    var head = function (t) { var ch = sc.objs[who]; return ch ? ch.anchor("head", t) : [def.x || 360, def.y || 400]; };
    var rad = function () { var ch = sc.objs[who]; return ch && ch.fig ? ch.fig.r : 40; };
    var home = null;                                                   // the cloud stays where it popped up (does not shake with the head)
    var centre = function () { if (!home) { var h0 = head(Math.min(popT + 0.24, 1e6)); home = [h0[0] + 30 + (def.dx || 0), h0[1] - rad() - 180 + (def.dy || 0)]; } return home; };
    o.render = function (t) {
      var h = head(t), r = rad(), c = centre();
      var a1 = D.pop(t, popT, 0.25), a2 = D.pop(t, popT + 0.12, 0.25), a3 = D.pop(t, popT + 0.24, 0.4, "back.out(2)");
      D.set(g1, { cx: D.r1(h[0] + 16), cy: D.r1(h[1] - r - 20), r: D.r1(10 * a1), opacity: a1 > 0 ? 1 : 0 });
      D.set(g2, { cx: D.r1(h[0] + 24), cy: D.r1(h[1] - r - 58), r: D.r1(16 * a2), opacity: a2 > 0 ? 1 : 0 });
      cloud.setAttribute("d", D.wobble(96, 9, t, 4, 0.08 + 0.05 * dark.at(t), 7));
      cloud.setAttribute("fill", D.mix("#6b7280", "#2f333a", dark.at(t)));
      sg.setAttribute("transform", "rotate(" + D.r1(40 * Math.sin(1.7 * t)) + ")");
      bolt.setAttribute("opacity", t > boltT && Math.floor(D.frame(t) / 3) % 2 === 0 ? 1 : 0);
      cg.setAttribute("transform", D.tf(c[0] + 3 * Math.sin(5 * t), c[1] + 3 * Math.cos(4 * t), 0, Math.max(0.001, a3 * grow.at(t))));
      cg.setAttribute("opacity", a3 > 0 ? 1 : 0);
    };
    o.anchor = function () { return centre(); };
    o.ready = function () { centre(); };
    o.beat = function (b) { return ["pop", "grow", "darken", "bolt"].indexOf(b.do) >= 0 ? true : genericBeat(o, b); };
    return o;
  };
  /* flask with bubbling liquid, label and fumes */
  K.flask = function (sc, def, parent, beats) {
    var o = new Obj(sc, def, parent), g = o.g, bid = D.uid("flask"), body = "M-30,-160 L30,-160 L30,-72 Q120,-40 120,50 Q120,160 0,160 Q-120,160 -120,50 Q-120,-40 -30,-72 Z";
    var cp = D.el(D.defs(g), "clipPath", { id: bid }); path(cp, body, {});
    path(g, body, fillS("#eef7f0", 8));
    var cg = D.el(g, "g", { "clip-path": "url(#" + bid + ")" }), liq = path(cg, "", { fill: col(def.color, "#7bc96f") }), bg = D.el(cg, "g", {});
    path(g, body, { fill: "none", stroke: INK, "stroke-width": 8, "stroke-linejoin": "round" });
    D.el(g, "rect", { x: -40, y: -196, width: 80, height: 44, rx: 8, fill: "#b08968", stroke: INK, "stroke-width": 7 });
    if (def.label) { D.el(g, "rect", { x: -62, y: 28, width: 124, height: 70, rx: 10, fill: "#ffffff", stroke: INK, "stroke-width": 6 }); D.text(g, def.label, { x: 0, y: 79, "text-anchor": "middle", "font-family": "Comic Neue", "font-weight": 700, "font-size": 48, fill: INK }); }
    var bub = new D.Emitter({ parent: bg, n: 9, r: [6, 12], bumps: 6, fill: "#e8f7df", sw: 3, seed: 81,
      life: function (k) { return { start: -100, period: D.rnd(k * 2.3, 0.8, 1.3), phase: k / 9 }; },
      place: function (k, u) { return { x: D.rnd(k * 4.1, -80, 80) + 6 * Math.sin(10 * u + k), y: 140 - 150 * u, s: 0.5 + 0.7 * u, o: D.fade(u, 0.1, 0.8) }; } });
    var fum = new D.Emitter({ parent: sc.layer("back"), n: 9, r: [26, 40], fill: "#b7e08f", sw: 4.5, seed: 83,
      life: function (k) { return { start: -100, period: 1.9, phase: k / 9 }; },
      place: function (k, u, c, t) { var q = o.xf(t); return { x: q.x + 24 * Math.sin(3 * u + k) + (k % 2 ? 1 : -1) * 40 * u, y: q.y - 200 - 190 * u, s: 0.45 + 1.1 * u, rot: 30 * u, o: 0.9 * D.fade(u, 0.12, 0.55) * q.o }; } });
    o.render = function (t) {
      o.place(t);
      var d = "";
      for (var x = -130; x <= 130; x += 20) d += (x === -130 ? "M" : "L") + x + "," + D.r1(-4 + 6 * Math.sin(0.06 * x - 5 * t) + 3 * Math.sin(0.11 * x + 7 * t));
      liq.setAttribute("d", d + "L130,180L-130,180Z");
      bub.render(t); fum.render(t, def.fumes === false ? 0 : 1);
    };
    o.anchors = { center: [0, 0], top: [0, -200] };
    return o;
  };
  /* big close-up face: trembling, pupils shake, sweat */
  K.bigface = function (sc, def, parent, beats) {
    var o = new Obj(sc, def, parent), g = D.el(o.g, "g", {}), r = def.r || 150, hat = def.hat || ["orange", "cream"], c1 = col(hat[0]), c2 = col(hat[1]);
    D.el(g, "circle", { cx: 0, cy: 0, r: r, fill: "#f5efe2", stroke: INK, "stroke-width": 9 });
    path(g, "M" + P2(-1.02 * r, -0.28 * r) + "L" + P2(-1.05 * r, 0.55 * r) + "L" + P2(-0.66 * r, -0.1 * r) + "Z", fillS(c1));
    path(g, "M" + P2(1.02 * r, -0.28 * r) + "L" + P2(1.05 * r, 0.55 * r) + "L" + P2(0.66 * r, -0.1 * r) + "Z", fillS(c1));
    path(g, "M" + P2(-1.07 * r, -0.3 * r) + "C" + P2(-1.12 * r, -1.46 * r) + " " + P2(1.12 * r, -1.46 * r) + " " + P2(1.07 * r, -0.3 * r) + "Z", fillS(c1, 9));
    var z = "M" + P2(-0.95 * r, -0.5 * r);
    for (var i = 1; i <= 10; i++) z += "L" + P2(-0.95 * r + (1.9 * r * i) / 10, (i % 2 ? -0.66 : -0.5) * r);
    path(g, z, { fill: "none", stroke: c2, "stroke-width": 9, "stroke-linecap": "round", "stroke-linejoin": "round" });
    D.el(g, "circle", { cx: 0, cy: -1.2 * r, r: 0.21 * r, fill: c2, stroke: INK, "stroke-width": 8 });
    D.el(g, "circle", { cx: -0.35 * r, cy: -0.03 * r, r: 0.24 * r, fill: "#ffffff", stroke: INK, "stroke-width": 7 });
    D.el(g, "circle", { cx: 0.35 * r, cy: -0.03 * r, r: 0.24 * r, fill: "#ffffff", stroke: INK, "stroke-width": 7 });
    var pl = D.el(g, "circle", { r: 11, fill: INK }), pr = D.el(g, "circle", { r: 11, fill: INK });
    path(g, "M" + P2(-0.59 * r, -0.36 * r) + "L" + P2(-0.16 * r, -0.27 * r) + "M" + P2(0.19 * r, -0.27 * r) + "L" + P2(0.61 * r, -0.36 * r), { fill: "none", stroke: INK, "stroke-width": 9, "stroke-linecap": "round" });
    var mouth = path(g, "", { fill: "none", stroke: INK, "stroke-width": 8 }), sw = [];
    for (i = 0; i < 3; i++) { var sg = D.el(o.g, "g", { opacity: 0 }); path(sg, D.drop(1.8), fillS("#8ecae6", 5)); sw.push(sg); }
    var bumps = [];
    (beats || []).forEach(function (b) { if (b.do === "bump") bumps.push(b.t); });
    o.render = function (t) {
      o.place(t);
      var fr = Math.floor(D.frame(t) / 2), amp = 2.2, j = 0;
      bumps.forEach(function (bt) { amp += 3 * D.env(t, bt - 0.05, bt + 1.0, 0.1, 0.6); j += D.jiggle(t, bt, 0.1, 3.5, 4); });
      g.setAttribute("transform", "translate(" + P2(amp * (D.hash(fr * 1.3) * 2 - 1), amp * (D.hash(fr * 2.1 + 3) * 2 - 1)) + ") scale(" + (1 + j).toFixed(3) + ")");
      var px = 3 * (D.hash(fr * 3.7) * 2 - 1), py = 3 * (D.hash(fr * 4.3 + 1) * 2 - 1);
      D.set(pl, { cx: D.r1(-0.35 * r + px), cy: D.r1(py) }); D.set(pr, { cx: D.r1(0.35 * r + px), cy: D.r1(py) });
      var m = "M" + P2(-0.41 * r, 0.6 * r);
      for (var k = 1; k <= 8; k++) m += " Q" + P2(-0.41 * r + k * 15.5 - 7.75, 0.6 * r + (k % 2 ? -12 : 12) * (0.8 + 0.2 * Math.sin(9 * t + k))) + " " + P2(-0.41 * r + k * 15.5, 0.6 * r);
      mouth.setAttribute("d", m);
      for (var n = 0; n < 3; n++) {
        var L = D.life(t, -100, 0.8, n / 3), v = L.u, side = n === 1 ? 1 : -1;
        sw[n].setAttribute("transform", D.tf(side * (1.05 * r + 14 * v), -0.27 * r + n * 18 + 90 * v * v, side * -14, 1));
        sw[n].setAttribute("opacity", (Math.min(1, v / 0.1) * (1 - D.prog(v, 0.7, 1))).toFixed(3));
      }
    };
    o.beat = function (b) { return b.do === "bump" ? true : genericBeat(o, b); };
    return o;
  };

  /* ------------------------------------------------------------ emitters */
  var EMIT = (RT.EMIT = {
    steam: { n: 10, r: [40, 58], fill: "#ffffff", sw: 4.5, period: 2.0, rise: 300, drift: -70, spread: 160, s0: 0.4, s1: 1.5 },
    smoke: { n: 8, r: [32, 44], fill: "#a9a9a9", sw: 5, period: 1.4, rise: 360, drift: 30, spread: 30, s0: 0.5, s1: 1.8 },
    fumes: { n: 8, r: [30, 42], fill: "#cfe8a8", sw: 4.5, period: 1.8, rise: 200, drift: -160, spread: 60, s0: 0.4, s1: 1.4 },
    dust: { n: 9, r: [26, 40], fill: "#efe5d3", sw: 4.5, period: 1.6, rise: 60, drift: 0, spread: 260, s0: 0.3, s1: 1.4 },
    bubbles: { n: 12, r: [6, 12], fill: "#e6f5ff", sw: 3.5, period: 1.0, rise: 120, drift: 0, spread: 120, s0: 0.5, s1: 1.2 },
    sparks: { n: 12, size: 1 }, drops: { n: 9, size: 1.1 }, shards: { n: 10 },
    stars: { n: 3 }, sweat: { n: 2 }, spiral: { n: 1 }, sound: { n: 3 }, particles: { n: 20 }, birds: { n: 3, size: 1.25, dir: -1 }
  });
  K.emitter = function (sc, def, parent, beats) {
    var type = def.emitter, E = {}, key, o = new Obj(sc, { id: def.id }, parent), wins = [], bursts = [], P = null;
    for (key in EMIT[type] || {}) E[key] = EMIT[type][key];
    for (key in def) E[key] = def[key];
    (beats || []).forEach(function (b) {
      if (b.do === "emit" || b.do === "start") wins.push([b.t, b.until != null ? b.until : b.t + (b.dur || 1e6)]);
      if (b.do === "stop") { var w = wins[wins.length - 1]; if (w) w[1] = Math.min(w[1], b.t); }
      if (b.do === "burst") bursts.push(b.t);
    });
    if (def.prewarm) wins.push([-100, 1e6]);
    var src = function (t) {
      if (def.on) { var ch = sc.objs[def.on]; if (ch) { var a = ch.anchor(def.anchor || (type === "sound" ? "prop" : "head"), t); return a || [0, 0]; } }
      return def.at || [360, 640];
    };
    var active = function (t) { for (var i = 0; i < wins.length; i++) if (t >= wins[i][0] && t < wins[i][1]) return true; return false; };
    var fillC = col(E.color, E.fill);
    if (type === "steam" || type === "smoke" || type === "fumes" || type === "bubbles" || type === "dust") {
      var n = E.n, per = E.period;
      var em = new D.Emitter({ parent: o.g, n: n, r: E.r, fill: fillC, sw: E.sw, bumps: type === "bubbles" ? 6 : 7, seed: (def.seed || 0) + 11,
        life: function (k) { return { start: -1000, period: per, phase: k / n }; },
        place: function (k, u, c, t) {
          var birth = t - u * per;
          var okw = false;
          for (var i = 0; i < wins.length; i++) if (birth >= wins[i][0] && birth < wins[i][1]) okw = true;
          if (!okw) return null;
          var s0 = src(birth), sd = k * 7.1 + c * 3.3, x, y;
          if (E.path) { var pp = bez(E.path, u); x = pp[0] + 10 * Math.sin(7 * u + k); y = pp[1]; }
          else { x = s0[0] + D.rnd(sd, -E.spread / 2, E.spread / 2) * (type === "dust" ? 0.2 + u : 1) + E.drift * u + 12 * Math.sin(2 * Math.PI * (u + k * 0.13)); y = s0[1] - E.rise * u; }
          var s = E.s0 + (E.s1 - E.s0) * u;
          return { x: x, y: y, sx: s * (type === "steam" ? 1 - 0.12 * u : 1), sy: s * (type === "steam" ? 1 + 0.35 * u : 1), rot: 25 * u, o: (E.opacity || 0.95) * D.fade(u, 0.1, 0.5) };
        } });
      o.render = function (t) { em.render(t); };
    } else if (type === "particles") {
      P = new D.Particles({ parent: o.g, n: E.n, box: E.box, r: E.r || [16, 26], fill: col(E.color, "#d62828"), label: E.label, labelEvery: E.label_every || 2, seed: def.seed || 5 });
      var pulses = [];
      (beats || []).forEach(function (b) { if (b.do === "pulse") pulses.push(b.t); });
      o.render = function (t) { var pu = 0; pulses.forEach(function (pt) { pu = Math.max(pu, D.env(t, pt - 0.05, pt + 0.7, 0.12, 0.35)); }); P.render(t, pu); };
    } else if (type === "drops" || type === "shards" || type === "sparks") {
      var parts = [], nn = E.n, i2;
      bursts.forEach(function (bt, bi) {
        for (i2 = 0; i2 < nn; i2++) {
          var id = bi * 50 + i2, g = D.el(o.g, "g", { opacity: 0 });
          if (E.shape) drawItems(sc, D.el(g, "g", { transform: "scale(" + (E.size || 1) + ")" }), BUILTIN[E.shape] || sc.shapes[E.shape], {});   // custom particle art
          else if (type === "drops") path(g, D.drop(E.size || 1.1), fillS(col(E.color, "#4fa3d1"), 4));
          else if (type === "shards") path(g, "M0,-10 L7,6 L-6,4 Z", fillS("#bfe6f7", 3));
          else path(g, "M0,-9 L2,-2 L9,0 L2,2 L0,9 L-2,2 L-9,0 L-2,-2 Z", fillS("#ffd166", 3));
          parts.push({ g: g, t0: bt + D.rnd(id * 1.3, 0, 0.06), dx: D.rnd(id * 2.9 + 1, -(E.spread || 150), E.spread || 150), vx: D.rnd(id * 3.7 + 2, -160, 160) * (E.dir || 1), vy: -D.rnd(id * 4.3 + 3, E.vmin || 360, E.vmax || 560), sp: D.rnd(id * 5.1, -600, 600) });
        }
      });
      o.render = function (t) {
        var s0 = src(t);
        parts.forEach(function (q) {
          var u = t - q.t0, y = q.vy * u + 750 * u * u;
          if (u < 0 || u > (E.life || 1.2) || (u > 0.1 && y > (E.floor || 4))) { q.g.setAttribute("opacity", 0); return; }
          var ang = type === "drops" ? (Math.atan2(-q.vx, q.vy + 1500 * u) * 180) / Math.PI : q.sp * u;
          q.g.setAttribute("transform", D.tf(s0[0] + q.dx * 0.3 + q.vx * u, s0[1] + y, ang, 1));
          q.g.setAttribute("opacity", 1);
        });
      };
    } else if (type === "stars") {
      var st = new D.Stars(o.g, E.n);
      o.render = function (t) { var h = src(t); st.render(t, h[0], h[1] - 36, active(t) ? 1 : 0, 32); };
    } else if (type === "sweat") {
      var sw = [];
      for (var s2 = 0; s2 < E.n; s2++) { var wg = D.el(o.g, "g", { opacity: 0 }); path(wg, D.drop(E.size || 0.8), fillS("#8ecae6", 3.5)); sw.push(wg); }
      o.render = function (t) {
        var ch = sc.objs[def.on], h = src(t), r = ch && ch.fig ? ch.fig.r : 40, f = ch && ch.fig && ch.fig.J.f ? ch.fig.J.f : 1;
        sw.forEach(function (wg, m) {
          var t0 = wins.length ? wins[0][0] : 1e9, L = active(t) ? D.life(t, t0 + m * 0.31, 0.62, 0) : null;
          if (!L) { wg.setAttribute("opacity", 0); return; }
          var v = L.u, sd = m % 2 ? 1 : -1;
          wg.setAttribute("transform", D.tf(h[0] + sd * f * (r + 6 + 10 * v), h[1] - r * 0.2 + 70 * v * v + 12 * v, sd * -12, 1));
          wg.setAttribute("opacity", (Math.min(1, v / 0.1) * (1 - D.prog(v, 0.7, 1))).toFixed(3));
        });
      };
    } else if (type === "spiral") {
      var sg2 = D.el(o.g, "g", { opacity: 0 }), sp = D.stroke(4.5);
      sp.d = D.spiral(E.size || 22, 2.4, 44); D.el(sg2, "path", sp);
      o.render = function (t) {
        var ch = sc.objs[def.on], h = src(t), r = ch && ch.fig ? ch.fig.r : 40, t0 = wins.length ? wins[0][0] : 1e9;
        if (!active(t)) { sg2.setAttribute("opacity", 0); return; }
        sg2.setAttribute("transform", D.tf(h[0] + 4, h[1] - r - 30 + 4 * Math.sin(2 * Math.PI * 1.6 * t), -420 * (t - t0), Math.max(0.001, D.pop(t, t0, 0.28, "back.out(2.5)"))));
        sg2.setAttribute("opacity", 1);
      };
    } else if (type === "sound") {
      var arcs = new D.Arcs(o.g, E.n);
      o.render = function (t) { var h = src(t), ch = sc.objs[def.on], f = ch && ch.fig && ch.fig.J.f ? ch.fig.J.f : 1; arcs.render(t, h[0], h[1], def.dir != null ? def.dir : f > 0 ? -8 : 188, active(t) ? 1 : 0); };
    } else if (type === "birds") {                                       // birds flap away from 'at' on every burst
      var fl = [], b0 = def.at || [360, 600];
      bursts.forEach(function (bt, bi) {
        for (var i4 = 0; i4 < E.n; i4++) {
          var id4 = bi * 20 + i4, bgp = D.el(o.g, "g", { opacity: 0 });
          fl.push({ g: bgp, p: D.el(bgp, "path", D.stroke(4.5)), t0: bt + i4 * 0.07, x: b0[0] - 24 + i4 * 24, y: b0[1] + (i4 % 2) * 14,
            vx: E.dir * D.rnd(id4 * 3 + 9, 120, 170), vy: -D.rnd(id4 * 5 + 4, 190, 250), ph: i4 * 1.7 });
        }
      });
      o.render = function (t) {
        fl.forEach(function (q) {
          var u = t - q.t0;
          if (u < 0 || u > 2.2) { q.g.setAttribute("opacity", 0); return; }
          var w = Math.sin(2 * Math.PI * 7 * u + q.ph);
          q.p.setAttribute("d", "M-16," + D.r1(-3 - 9 * w) + "Q-8," + D.r1(-10 - 9 * w) + " 0,0Q8," + D.r1(-10 - 9 * w) + " 16," + D.r1(-3 - 9 * w));
          q.g.setAttribute("transform", D.tf(q.x + q.vx * u, q.y + q.vy * u + 10 * Math.sin(3 * u), 0, E.size));
          q.g.setAttribute("opacity", 1);
        });
      };
    } else throw new Error("unknown emitter " + type);
    o.beat = function (b) { return ["emit", "start", "stop", "burst", "pulse"].indexOf(b.do) >= 0 ? true : genericBeat(o, b); };
    return o;
  };

  /* ------------------------------------------------------------ scene assembly */
  var CARRY = { shape: 1, text: 1, rock: 1, flask: 1, sign: 1, tent: 1, house: 1 };   // kinds that can be carried (on: / attach)
  RT.scene = function (tl, S, ctx) {
    var sc = { id: S.id, t0: S.t0, objs: {}, styles: ctx.styles || {}, shapes: ctx.shapes || {}, lay: {} };
    var cam = D.$("cam_" + S.id);
    ["back", "mid", "front", "top"].forEach(function (n) { sc.lay[n] = D.el(cam, "g", { "class": "lay_" + n }); });
    sc.setfront = D.el(null, "g", { "class": "setfront" });            // effects in front of the set, behind props/cast
    sc.layer = function (n) { return n === "front" ? sc.setfront : sc.lay[n] || sc.lay.mid; };
    var byWho = {}, sfOn = false;
    S.beats.forEach(function (b) { (byWho[b.who] = byWho[b.who] || []).push(b); });
    var list = [], TOP_EMIT = { sweat: 1, spiral: 1, stars: 1, sound: 1 };
    S.objects.forEach(function (def) {
      var kind = def.kind, maker = K[kind];
      if (!maker) throw new Error("unknown kind " + kind + " (" + def.id + ")");
      if (!sfOn && def.section !== "set") { sc.lay.mid.appendChild(sc.setfront); sfOn = true; }
      var lay = def.layer || (kind === "emitter" && TOP_EMIT[def.emitter] ? "top" : "mid");
      var o = maker(sc, def, lay === "mid" ? sc.lay.mid : sc.layer(lay), byWho[def.id] || []);
      o.def = o.def || def; o.id = def.id; o.kindName = kind;
      if (o.g && o.g.setAttribute) o.g.setAttribute("data-kind", kind);
      if (def.on && CARRY[kind]) { var of0 = def.offset || [0, 0]; o.att = new Steps({ on: def.on, anchor: def.anchor || "hand", dx: of0[0], dy: of0[1] }); }
      if (def.id) sc.objs[def.id] = o;
      list.push(o);
    });
    if (!sfOn) sc.lay.mid.appendChild(sc.setfront);
    S.beats.forEach(function (b) {
      if (b.who === "cam") return;
      var o = sc.objs[b.who];
      if (!o) throw new Error("beat for unknown object " + b.who);
      if (!o.beat(b)) throw new Error("object " + b.who + " cannot do " + b.do);
    });
    list.forEach(function (o) { if (o.ready) o.ready(); });
    /* characters render last: other objects may evaluate a character at another time (anchors), the final DOM must be 't' */
    var order = list.filter(function (o) { return !(o instanceof Char); }).concat(list.filter(function (o) { return o instanceof Char; }));
    /* camera: keyframed framings [zoom, focus x, y, screen x, y] + shakes + smooth follow */
    var keys = [[S.t0, [Math.log(S.cam0[0]), S.cam0[1], S.cam0[2], S.cam0[3], S.cam0[4]]]], cur = S.cam0.slice(), shakes = [], follows = [];
    S.beats.forEach(function (b) {
      if (b.who !== "cam") return;
      if (b.do === "shake") { shakes.push([b.t, b.dur || 0.3, b.amp || 10]); return; }
      if (b.do === "follow") { follows.push(b); return; }
      var z = b.zoom == null ? cur[0] : b.zoom, at = b.target || [cur[1], cur[2]], scr = b.screen || [360, 640];
      if (typeof at === "string") { var ob = sc.objs[at.split(":")[0]]; at = ob ? ob.anchor(at.split(":")[1] || "center", b.t + (b.dur || 0.6)) : [cur[1], cur[2]]; }
      if (b.do === "reset") { z = 1; at = [360, 640]; scr = [360, 640]; }
      keys.push([b.t, [Math.log(cur[0]), cur[1], cur[2], cur[3], cur[4]], "none"]);
      cur = [z, at[0], at[1], scr[0], scr[1]];
      keys.push([b.t + (b.dur == null ? 0.6 : b.dur), [Math.log(z), at[0], at[1], scr[0], scr[1]], b.ease || (b.do === "whip" ? "power2.in" : "power2.inOut")]);
    });
    keys.sort(function (a, b) { return a[0] - b[0]; });
    var camTr = D.track(keys);
    var pg = D.$("pg_" + S.id), turb = D.$("turb_" + S.id);
    var rctx = { z: 1 };
    var loop = ctx.loop, home = loop && S.home, last = loop && S.last;
    function renderAll(t) {
      var dx = 0, dy = 0, v = camTr(t), z = Math.exp(v[0]), fx = v[1], fy = v[2], sx = v[3], sy = v[4];
      shakes.forEach(function (s, i) { var q = D.shake(t, s[0], s[1], s[2], i + 1); dx += q[0]; dy += q[1]; });
      follows.forEach(function (f) {
        var w = D.env(t, f.t, f.t + (f.dur || 1), 0.35, 0.35);
        if (w <= 0) return;
        var o = sc.objs[f.target], p = o ? o.anchor(f.anchor || "center", t) : null;
        if (!p) return;
        fx = D.lerp(fx, p[0], w); fy = D.lerp(fy, p[1] + (f.offset || 0), w); sx = D.lerp(sx, 360, w); sy = D.lerp(sy, 640, w);
        if (f.zoom) z = Math.exp(D.lerp(Math.log(z), Math.log(f.zoom), w));
      });
      cam.setAttribute("transform", "translate(" + (sx + dx).toFixed(2) + "," + (sy + dy).toFixed(2) + ") scale(" + z.toFixed(5) + ") translate(" + (-fx).toFixed(2) + "," + (-fy).toFixed(2) + ")");
      rctx.z = z;
      D.boil(turb, t, 3, 4);
      for (var i = 0; i < order.length; i++) order[i].render(t, rctx);
    }
    D.drive(tl, S.t0, S.t1, function (t) {
      if (home) {
        if (t >= S.end && t < loop.t0) { pg.style.opacity = "0"; return; }
        pg.style.opacity = "1";
        if (t >= loop.t0) { pg.style.transform = "translate(0px," + (420 * (1 - D.ev(t, loop.t0, loop.t1, "power2.inOut"))).toFixed(2) + "px)"; renderAll(0); return; }
        pg.style.transform = "translate(0px,0px)";
      }
      if (last) pg.style.transform = "translate(0px," + (-1420 * D.ev(t, loop.t0, loop.t1, "power2.inOut")).toFixed(2) + "px)";
      renderAll(t);
    });
    window.__SP_OBJECTS = (window.__SP_OBJECTS || []).concat(list.filter(function (o) { return o.id; }).map(function (o) { return { id: o.id, scene: S.id, kind: o.kindName, obj: o }; }));
    return sc;
  };

  /* gold counters (HTML): from -> to over dur, fade at until */
  RT.counter = function (tl, g) {
    var el = D.$("gold_" + g.key);
    D.drive(tl, 0, g.total, function (t) {
      var u = t - g.t;
      if (u < 0 || t >= g.until) { el.style.opacity = "0"; return; }
      var n = Math.round(D.lerp(g.from || 0, g.to, D.ease("power2.out")(D.prog(u, 0.05, g.dur || 0.6))));
      if (el.textContent !== String(n)) el.textContent = String(n);
      var s = D.lerp(0.4, 1, D.ease("back.out(2.5)")(D.prog(u, 0, 0.25))) + 0.12 * Math.max(0, 1 - Math.abs(u - (g.dur || 0.6) - 0.02) / 0.1);
      el.style.opacity = (1 - D.prog(t, g.until - 0.06, g.until)).toFixed(3);
      el.style.transform = "scale(" + s.toFixed(3) + ") rotate(-3deg)";
    });
  };
})();
