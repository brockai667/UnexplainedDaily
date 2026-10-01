/* doodle_lib.js - deterministic hand-drawn animation toolkit for HyperFrames (GSAP).
 *
 * Rule: every visual state is a PURE FUNCTION of timeline time t (seconds).
 * Each scene registers one proxy tween on the single paused timeline (D.drive); its onUpdate
 * calls the scene's render(t). The HyperFrames runtime seeks the timeline with events enabled,
 * so any frame can be rendered in any order by any worker. No Math.random, no clocks.
 */
(function () {
  "use strict";
  var D = (window.D = {});
  var NS = "http://www.w3.org/2000/svg";
  var INK = (D.INK = "#1b1b1b");
  D.FPS = 24;

  /* ------------------------------------------------------------------ math */
  D.clamp = function (v, a, b) { return v < a ? a : v > b ? b : v; };
  D.lerp = function (a, b, p) { return a + (b - a) * p; };
  D.prog = function (t, a, b) { return b <= a ? (t >= b ? 1 : 0) : D.clamp((t - a) / (b - a), 0, 1); };
  D.smooth = function (p) { p = D.clamp(p, 0, 1); return p * p * (3 - 2 * p); };
  D.hash = function (n) { var x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
  D.rnd = function (n, a, b) { return a + (b - a) * D.hash(n); };
  D.frame = function (t) { return Math.floor(t * D.FPS + 1e-3); };
  D.r1 = function (v) { return Math.round(v * 10) / 10; };
  D.r2 = function (v) { return Math.round(v * 100) / 100; };
  var EC = {};
  D.ease = function (e) {
    if (typeof e === "function") return e;
    if (!e || e === "none" || e === "linear") return function (p) { return p; };
    return EC[e] || (EC[e] = gsap.parseEase(e));
  };
  /* eased progress of t inside [a, b] */
  D.ev = function (t, a, b, e) { return D.ease(e || "power2.inOut")(D.prog(t, a, b)); };
  /* 0 before a, up to 1 over `up`, down to 0 over `down` ending at b */
  D.env = function (t, a, b, up, down) { return Math.max(0, Math.min(D.prog(t, a, a + up), 1 - D.prog(t, b - down, b))); };
  /* decaying spring wobble after t0 */
  D.jiggle = function (t, t0, amp, f, k) {
    if (t < t0) return 0;
    var u = t - t0;
    return amp * Math.exp(-k * u) * Math.sin(2 * Math.PI * f * u);
  };

  function rgb(c) {
    var h = c.charAt(0) === "#" ? c.slice(1) : c;
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  D.mix = function (a, b, p) {
    p = D.clamp(p, 0, 1);
    var x = rgb(a), y = rgb(b);
    return "rgb(" + Math.round(x[0] + (y[0] - x[0]) * p) + "," + Math.round(x[1] + (y[1] - x[1]) * p) + "," + Math.round(x[2] + (y[2] - x[2]) * p) + ")";
  };

  /* ------------------------------------------------------------------ tracks */
  function interp(a, b, p) {
    if (typeof a === "number") return a + (b - a) * p;
    if (Array.isArray(a)) {
      var r = [];
      for (var i = 0; i < a.length; i++) r.push(a[i] + (b[i] - a[i]) * p);
      return r;
    }
    return p < 1 ? a : b;
  }
  /* keys: [[t, value, ease]] ; the ease on a key shapes the segment that ARRIVES at it.
     value: number or array of numbers. Eases may overshoot (back/elastic). */
  D.track = function (keys, def) {
    def = def || "power2.inOut";
    return function (t) {
      if (t <= keys[0][0]) return keys[0][1];
      for (var i = 1; i < keys.length; i++) {
        if (t < keys[i][0]) {
          var a = keys[i - 1], b = keys[i];
          return interp(a[1], b[1], D.ease(b[2] || def)((t - a[0]) / (b[0] - a[0])));
        }
      }
      return keys[keys.length - 1][1];
    };
  };
  D.step = function (keys) {
    return function (t) {
      var v = keys[0][1];
      for (var i = 1; i < keys.length; i++) {
        if (t >= keys[i][0]) v = keys[i][1];
        else break;
      }
      return v;
    };
  };
  /* Pose timeline. base = {field: value}; moves = [[t0, t1, {field: value}, ease]].
     Numbers tween from their previous value to the new one over [t0, t1]; strings switch at t0.
     Author moves so that one field is never in two overlapping moves. */
  D.poses = function (base, moves) {
    var ms = moves.slice().sort(function (a, b) { return a[0] - b[0]; });
    var tr = {};
    Object.keys(base).forEach(function (fld) {
      var str = typeof base[fld] !== "number";
      var keys = [[-1e9, base[fld]]];
      ms.forEach(function (m) {
        if (!(fld in m[2])) return;
        if (str) keys.push([m[0], m[2][fld]]);
        else {
          var prev = keys[keys.length - 1][1];
          keys.push([m[0], prev, "none"]);
          keys.push([Math.max(m[1], m[0] + 1e-4), m[2][fld], m[3] || "power2.inOut"]);
        }
      });
      tr[fld] = str ? D.step(keys) : D.track(keys);
    });
    return function (t) {
      var o = {};
      for (var f in tr) o[f] = tr[f](t);
      return o;
    };
  };

  /* ------------------------------------------------------------------ timeline glue */
  /* one proxy tween per scene: render(t) is called for every seek inside [t0, t1] */
  D.drive = function (tl, t0, t1, render) {
    var o = { t: t0 };
    tl.fromTo(o, { t: t0 }, {
      t: t1, duration: t1 - t0, ease: "none", immediateRender: false,
      onUpdate: function () { render(o.t); }
    }, t0);
    render(t0);
  };

  /* gold word stamp: slam in with overshoot + slight rotation (GSAP tweens on an HTML element) */
  D.stamp = function (tl, sel, t, o) {
    o = o || {};
    tl.fromTo(sel, { opacity: 0 }, { opacity: 1, duration: 0.07, ease: "none", immediateRender: true }, t);
    tl.fromTo(sel, { scale: o.from || 2.3, rotation: o.r0 == null ? -12 : o.r0 },
      { scale: 1, rotation: o.r1 == null ? -4 : o.r1, duration: o.dur || 0.42, ease: o.ease || "back.out(2.2)", immediateRender: true }, t);
  };

  /* global screen FX (white flash + zoom lines) as pure functions of t; scenes push events */
  D.FX = { flashes: [], speeds: [] };   // flashes: [tPeak, peak, up, down]; speeds: [a, b, cx, cy]
  D.fxDriver = function (tl, total) {
    var fl = document.getElementById("fx_flash"), sg = document.getElementById("fx_speed_g");
    D.drive(tl, 0, total, function (t) {
      var o = 0, i, f;
      for (i = 0; i < D.FX.flashes.length; i++) {
        f = D.FX.flashes[i];
        if (t >= f[0] - f[2] && t < f[0] + f[3]) {
          var v = t < f[0] ? D.prog(t, f[0] - f[2], f[0]) : 1 - D.ease("power2.out")(D.prog(t, f[0], f[0] + f[3]));
          o = Math.max(o, v * f[1]);
        }
      }
      fl.style.opacity = o.toFixed(3);
      var so = 0;
      for (i = 0; i < D.FX.speeds.length; i++) {
        f = D.FX.speeds[i];
        if (t >= f[0] && t < f[1]) {
          var p = D.prog(t, f[0], f[1]);
          so = Math.sin(Math.PI * p);
          sg.setAttribute("transform", D.tf(f[2], f[3], p * 14, 0.75 + 0.6 * p));
        }
      }
      sg.setAttribute("opacity", so.toFixed(3));
    });
  };

  /* ------------------------------------------------------------------ svg helpers */
  D.el = function (parent, tag, at) {
    var e = document.createElementNS(NS, tag);
    if (at) for (var k in at) e.setAttribute(k, at[k]);
    if (parent) parent.appendChild(e);
    return e;
  };
  D.set = function (e, at) { for (var k in at) e.setAttribute(k, at[k]); };
  D.$ = function (id) { return document.getElementById(id); };
  D.tf = function (x, y, rot, sx, sy) {
    if (sy == null) sy = sx;
    var s = "translate(" + x.toFixed(2) + "," + y.toFixed(2) + ")";
    if (rot) s += " rotate(" + rot.toFixed(2) + ")";
    if (sx != null && (sx !== 1 || sy !== 1)) s += " scale(" + sx.toFixed(4) + "," + sy.toFixed(4) + ")";
    return s;
  };
  /* scale about a pivot point (bx, by) - squash & stretch of static art */
  D.tfAbout = function (bx, by, sx, sy, rot, dx, dy) {
    return "translate(" + (bx + (dx || 0)).toFixed(2) + "," + (by + (dy || 0)).toFixed(2) + ")" + (rot ? " rotate(" + rot.toFixed(2) + ")" : "") +
      " scale(" + sx.toFixed(4) + "," + sy.toFixed(4) + ") translate(" + (-bx).toFixed(2) + "," + (-by).toFixed(2) + ")";
  };
  D.stroke = function (w, col) {
    return { fill: "none", stroke: col || INK, "stroke-width": w || 7, "stroke-linecap": "round", "stroke-linejoin": "round" };
  };
  function P2(x, y) { return D.r1(x) + "," + D.r1(y); }
  D.P2 = P2;

  /* bumpy closed cloud/puff outline centred at 0,0 */
  D.puff = function (r, n, seed) {
    var pts = [], i;
    for (i = 0; i < n; i++) {
      var a = -Math.PI / 2 + (i / n) * Math.PI * 2 + D.rnd(seed + i * 3, -0.12, 0.12);
      var rr = r * D.rnd(seed + i * 7 + 1, 0.8, 1.0);
      pts.push([Math.cos(a) * rr, Math.sin(a) * rr]);
    }
    var d = "M" + P2(pts[0][0], pts[0][1]);
    for (i = 1; i <= n; i++) {
      var p = pts[i % n], q = pts[i - 1];
      var br = Math.max(Math.hypot(p[0] - q[0], p[1] - q[1]) * 0.62, r * 0.3);
      d += "A" + D.r1(br) + "," + D.r1(br) + " 0 0 1 " + P2(p[0], p[1]);
    }
    return d + "Z";
  };
  /* elliptical spiral (nausea swirl) */
  D.spiral = function (R, turns, n) {
    var d = "";
    for (var i = 0; i <= n; i++) {
      var u = i / n, a = u * turns * Math.PI * 2, r = R * (0.12 + 0.88 * u);
      d += (i ? "L" : "M") + P2(Math.cos(a) * r, Math.sin(a) * r * 0.78);
    }
    return d;
  };
  /* tear drop pointing up, height ~ 2.2 s */
  D.drop = function (s) {
    return "M0," + D.r1(-13 * s) + "C" + P2(4 * s, -5 * s) + " " + P2(8 * s, -1 * s) + " " + P2(8 * s, 4 * s) +
      "A" + D.r1(8 * s) + "," + D.r1(8 * s) + " 0 0 1 " + P2(-8 * s, 4 * s) + "C" + P2(-8 * s, -1 * s) + " " + P2(-4 * s, -5 * s) + " 0," + D.r1(-13 * s) + "Z";
  };
  /* vertical wiggle line from (x, y0) up to y0-len; phase moves the wave upward over time */
  D.waveUp = function (x, y0, len, amp, wl, phase, n) {
    var d = "";
    for (var i = 0; i <= n; i++) {
      var u = i / n, y = y0 - len * u;
      var a = amp * Math.sin(u * 0.5 * Math.PI + 0.3) ;
      d += (i ? "L" : "M") + P2(x + a * Math.sin((2 * Math.PI * (y0 - y)) / wl - phase), y);
    }
    return d;
  };

  /* ------------------------------------------------------------------ camera */
  /* keys: [[t, [zoom, fx, fy, sx, sy], ease]] : world point (fx,fy) is drawn at screen (sx,sy).
     zoom interpolates in log space. cam(t, dx, dy, rot) writes the transform and returns zoom. */
  D.camera = function (g, keys) {
    var tr = D.track(keys.map(function (k) {
      return [k[0], [Math.log(k[1][0]), k[1][1], k[1][2], k[1][3], k[1][4]], k[2]];
    }));
    var cam = function (t, dx, dy, rot) {
      var v = tr(t), z = Math.exp(v[0]);
      g.setAttribute("transform", "translate(" + (v[3] + (dx || 0)).toFixed(2) + "," + (v[4] + (dy || 0)).toFixed(2) + ")" +
        (rot ? " rotate(" + rot.toFixed(3) + ")" : "") + " scale(" + z.toFixed(5) + ") translate(" + (-v[1]).toFixed(2) + "," + (-v[2]).toFixed(2) + ")");
      cam.z = z;
      return z;
    };
    cam.z = 1;
    return cam;
  };
  /* frame-quantised camera shake with quadratic decay */
  D.shake = function (t, t0, dur, amp, seed) {
    if (t < t0 || t >= t0 + dur) return [0, 0];
    var e = 1 - (t - t0) / dur;
    e *= e;
    var fr = D.frame(t) + (seed || 0) * 97;
    return [amp * e * (D.hash(fr * 1.37) * 2 - 1), amp * e * (D.hash(fr * 2.71 + 11) * 2 - 1)];
  };
  /* hand-drawn line boil: switch turbulence seed every `every` frames */
  D.boil = function (turb, t, every, n) {
    var s = 1 + (Math.floor(D.frame(t) / (every || 3)) % (n || 4));
    if (turb._s !== s) { turb.setAttribute("seed", String(s)); turb._s = s; }
  };
  /* looping particle life -> {u: 0..1, c: cycle} or null before start */
  D.life = function (t, start, period, phase) {
    if (t < start) return null;
    var v = (t - start) / period + (phase || 0), c = Math.floor(v);
    return { u: v - c, c: c };
  };

  /* ------------------------------------------------------------------ 2-bone IK */
  /* returns [jointX, jointY, endX, endY]; side (+1/-1) picks the bend direction */
  D.ik = function (ax, ay, bx, by, l1, l2, side) {
    var dx = bx - ax, dy = by - ay, d = Math.sqrt(dx * dx + dy * dy) || 1e-6;
    var dd = D.clamp(d, Math.abs(l1 - l2) + 0.5, l1 + l2 - 0.5);
    var a = (l1 * l1 + dd * dd - l2 * l2) / (2 * dd);
    var h = Math.sqrt(Math.max(0, l1 * l1 - a * a));
    var ex = dx / d, ey = dy / d;
    return [ax + ex * a - ey * h * side, ay + ey * a + ex * h * side, ax + ex * dd, ay + ey * dd];
  };

  /* ------------------------------------------------------------------ stick figure rig */
  /* o: k (size), skin, hat (colour) + hat2, hair (colour), coat (bool), glasses (bool) */
  D.Fig = function (parent, o) {
    o = o || {};
    var k = (this.k = o.k || 1);
    this.o = o;
    this.r = 30 * k; this.T = 92 * k; this.th = 48 * k; this.sh = 46 * k; this.ua = 34 * k; this.fa = 32 * k;
    this.H0 = 86 * k; this.sOff = 22 * k;
    var g = (this.g = D.el(parent, "g", { "class": "fig" }));
    this.shadow = D.el(g, "ellipse", { rx: 44 * k, ry: 8 * k, fill: INK, opacity: 0.12 });
    /* paper-coloured halo under the limbs keeps the stick figure readable over busy backgrounds */
    var hg = D.el(g, "g", { opacity: 0.92 }), HS = D.stroke(18, "#fffdf6");
    this.halo = [];
    for (var hi = 0; hi < 5; hi++) this.halo.push(D.el(hg, "path", HS));
    this.haloHead = D.el(hg, "circle", { r: this.r + 5, fill: "#fffdf6" });
    this.armB = D.el(g, "path", D.stroke());
    this.legB = D.el(g, "path", D.stroke());
    this.legF = D.el(g, "path", D.stroke());
    this.torso = D.el(g, "path", D.stroke());
    if (o.coat) {
      this.coat = D.el(g, "path", { fill: o.coatColor || "#fdfcf7", stroke: INK, "stroke-width": 6, "stroke-linejoin": "round", "stroke-linecap": "round" });
      this.coatLine = D.el(g, "path", D.stroke(4.5));
    }
    if (o.stetho) this.stetho = D.el(g, "path", { fill: "none", stroke: "#5c6770", "stroke-width": 4.5, "stroke-linecap": "round", "stroke-linejoin": "round" });
    if (o.stetho) this.stethoEnd = D.el(g, "circle", { r: D.r1(5.5 * k), fill: "#c9d1d9", stroke: INK, "stroke-width": 3.5 });
    this.prop = D.el(g, "g", {});
    this.armF = D.el(g, "path", D.stroke());
    var h = (this.head = D.el(g, "g", {})), r = this.r;
    if (o.hair) {
      D.el(h, "path", {
        d: "M" + P2(-0.95 * r, -0.2 * r) + "L" + P2(-1.12 * r, -0.95 * r) + "L" + P2(-0.62 * r, -0.78 * r) + "L" + P2(-0.55 * r, -1.36 * r) +
          "L" + P2(-0.12 * r, -0.95 * r) + "L" + P2(0.18 * r, -1.42 * r) + "L" + P2(0.42 * r, -0.92 * r) + "L" + P2(0.9 * r, -1.2 * r) +
          "L" + P2(0.82 * r, -0.62 * r) + "L" + P2(1.1 * r, -0.4 * r) + "L" + P2(0.95 * r, -0.1 * r) + "Z",
        fill: o.hair, stroke: INK, "stroke-width": 5.5, "stroke-linejoin": "round"
      });
    }
    this.skull = D.el(h, "circle", { cx: 0, cy: 0, r: r, fill: o.skin || "#f5efe2", stroke: INK, "stroke-width": 7 });
    if (o.hat) this._hat(h, o.hat, o.hat2 || "#ffffff");
    if (o.cap) {            // official's peaked cap
      D.el(h, "path", { d: "M" + P2(-1.02 * r, -0.36 * r) + "C" + P2(-0.95 * r, -1.25 * r) + " " + P2(0.9 * r, -1.3 * r) + " " + P2(1.0 * r, -0.4 * r) + "Z",
        fill: o.cap, stroke: INK, "stroke-width": 6, "stroke-linejoin": "round" });
      D.el(h, "path", { d: "M" + P2(0.55 * r, -0.4 * r) + "Q" + P2(1.2 * r, -0.46 * r) + " " + P2(1.5 * r, -0.26 * r), fill: "none", stroke: INK, "stroke-width": 7, "stroke-linecap": "round" });
      D.el(h, "circle", { cx: D.r1(0.05 * r), cy: D.r1(-0.72 * r), r: D.r1(0.14 * r), fill: "#ffd166", stroke: INK, "stroke-width": 3 });
    }
    if (o.nurse) {          // nurse cap with a red cross
      D.el(h, "path", { d: "M" + P2(-0.7 * r, -0.72 * r) + "L" + P2(-0.55 * r, -1.28 * r) + "L" + P2(0.6 * r, -1.28 * r) + "L" + P2(0.72 * r, -0.72 * r) + "Z",
        fill: "#ffffff", stroke: INK, "stroke-width": 5, "stroke-linejoin": "round" });
      D.el(h, "path", { d: "M" + P2(0, -1.18 * r) + "L" + P2(0, -0.84 * r) + "M" + P2(-0.17 * r, -1.01 * r) + "L" + P2(0.17 * r, -1.01 * r),
        fill: "none", stroke: "#e63946", "stroke-width": 5, "stroke-linecap": "round" });
    }
    if (o.mirror) {         // doctor's head mirror on a band
      D.el(h, "path", { d: "M" + P2(-0.98 * r, -0.2 * r) + "Q" + P2(0, -0.78 * r) + " " + P2(0.98 * r, -0.3 * r), fill: "none", stroke: INK, "stroke-width": 5, "stroke-linecap": "round" });
      D.el(h, "circle", { cx: D.r1(0.42 * r), cy: D.r1(-0.66 * r), r: D.r1(0.3 * r), fill: "#dfe7ee", stroke: INK, "stroke-width": 5 });
      D.el(h, "circle", { cx: D.r1(0.42 * r), cy: D.r1(-0.66 * r), r: D.r1(0.1 * r), fill: INK });
    }
    this.eyeL = D.el(h, "circle", { r: 4.2 * k, fill: INK });
    this.eyeR = D.el(h, "circle", { r: 4.2 * k, fill: INK });
    this.eyeP = D.el(h, "path", D.stroke(4.5));
    this.mouth = D.el(h, "path", D.stroke(5));
    this.mouthO = D.el(h, "ellipse", { fill: INK });
    this.brow = D.el(h, "path", D.stroke(4.5));
    if (o.glasses) {
      var gl = D.el(h, "g", {});
      D.el(gl, "circle", { cx: -5 * k, cy: -5 * k, r: 9 * k, fill: "#ffffff", "fill-opacity": 0.35, stroke: INK, "stroke-width": 4 });
      D.el(gl, "circle", { cx: 13 * k, cy: -5 * k, r: 9 * k, fill: "#ffffff", "fill-opacity": 0.35, stroke: INK, "stroke-width": 4 });
      D.el(gl, "path", { d: "M" + P2(4 * k, -6 * k) + "L" + P2(4 * k, -6 * k) + "M" + P2(-14 * k, -6 * k) + "L" + P2(-27 * k, -9 * k), fill: "none", stroke: INK, "stroke-width": 4, "stroke-linecap": "round" });
      h.insertBefore(gl, this.eyeL);
    }
    this.J = {};
  };
  /* Peruvian chullo hat: dome + zigzag band + pom-pom + ear flap */
  D.Fig.prototype._hat = function (h, c1, c2) {
    var r = this.r;
    D.el(h, "path", {
      d: "M" + P2(-0.98 * r, -0.28 * r) + "L" + P2(-1.02 * r, 0.52 * r) + "L" + P2(-0.66 * r, -0.12 * r) + "Z",
      fill: c1, stroke: INK, "stroke-width": 5, "stroke-linejoin": "round"
    });
    D.el(h, "path", { d: "M" + P2(-1.02 * r, 0.52 * r) + "l0," + D.r1(0.34 * r), fill: "none", stroke: INK, "stroke-width": 4, "stroke-linecap": "round" });
    D.el(h, "path", {
      d: "M" + P2(-1.07 * r, -0.3 * r) + "C" + P2(-1.12 * r, -1.46 * r) + " " + P2(1.12 * r, -1.46 * r) + " " + P2(1.07 * r, -0.3 * r) + "Z",
      fill: c1, stroke: INK, "stroke-width": 6, "stroke-linejoin": "round"
    });
    var z = "M" + P2(-0.95 * r, -0.5 * r);
    for (var i = 1; i <= 8; i++) z += "L" + P2(-0.95 * r + (1.9 * r * i) / 8, (i % 2 ? -0.64 : -0.5) * r);
    D.el(h, "path", { d: z, fill: "none", stroke: c2, "stroke-width": 5, "stroke-linecap": "round", "stroke-linejoin": "round" });
    D.el(h, "circle", { cx: 0, cy: D.r1(-1.2 * r), r: D.r1(0.21 * r), fill: c2, stroke: INK, "stroke-width": 5 });
  };
  /* face in head-local coordinates (facing +x). F: eyes, mouth, brow, open, lx, ly */
  D.Fig.prototype._face = function (F) {
    var k = this.k, lx = (F.lx || 0) * k, ly = (F.ly || 0) * k;
    var e1x = -5 * k + lx, e2x = 13 * k + lx, ey = -5 * k + ly, s = 4.2 * k, d = "";
    var eyes = F.eyes || "dot";
    if (eyes === "dot" || eyes === "wide") {
      var er = (eyes === "wide" ? 5.4 : 4.2) * k;
      D.set(this.eyeL, { cx: D.r1(e1x), cy: D.r1(ey), r: D.r1(er), opacity: 1 });
      D.set(this.eyeR, { cx: D.r1(e2x), cy: D.r1(ey), r: D.r1(er), opacity: 1 });
    } else {
      this.eyeL.setAttribute("opacity", 0);
      this.eyeR.setAttribute("opacity", 0);
      if (eyes === "squint") {
        d = "M" + P2(e1x - s, ey - s) + "L" + P2(e1x + s * 0.8, ey) + "L" + P2(e1x - s, ey + s) +
          "M" + P2(e2x + s, ey - s) + "L" + P2(e2x - s * 0.8, ey) + "L" + P2(e2x + s, ey + s);
      } else if (eyes === "x") {
        d = "M" + P2(e1x - s, ey - s) + "L" + P2(e1x + s, ey + s) + "M" + P2(e1x + s, ey - s) + "L" + P2(e1x - s, ey + s) +
          "M" + P2(e2x - s, ey - s) + "L" + P2(e2x + s, ey + s) + "M" + P2(e2x + s, ey - s) + "L" + P2(e2x - s, ey + s);
      } else if (eyes === "closed") {
        d = "M" + P2(e1x - s, ey) + "Q" + P2(e1x, ey + s) + " " + P2(e1x + s, ey) + "M" + P2(e2x - s, ey) + "Q" + P2(e2x, ey + s) + " " + P2(e2x + s, ey);
      }
    }
    this.eyeP.setAttribute("d", d);
    var mx = 5 * k + lx * 0.6, my = 12.5 * k + ly * 0.4, m = F.mouth || "smile", w = 9 * k, d2 = "";
    if (m === "o") {
      var op = F.open == null ? 1 : F.open;
      D.set(this.mouthO, { cx: D.r1(mx), cy: D.r1(my + 1.5 * k), rx: D.r1((4 + 2.5 * op) * k), ry: D.r1((2.5 + 6.5 * op) * k), opacity: 1 });
    } else {
      this.mouthO.setAttribute("opacity", 0);
      if (m === "smile") d2 = "M" + P2(mx - w, my - 2 * k) + "Q" + P2(mx, my + 8 * k) + " " + P2(mx + w, my - 2 * k);
      else if (m === "flat") d2 = "M" + P2(mx - w * 0.75, my + k) + "L" + P2(mx + w * 0.75, my);
      else if (m === "frown") d2 = "M" + P2(mx - w, my + 4 * k) + "Q" + P2(mx, my - 5 * k) + " " + P2(mx + w, my + 4 * k);
      else if (m === "wavy") {
        d2 = "M" + P2(mx - 10 * k, my) + "q" + P2(2.5 * k, -5 * k) + " " + P2(5 * k, 0) + "q" + P2(2.5 * k, 5 * k) + " " + P2(5 * k, 0) +
          "q" + P2(2.5 * k, -5 * k) + " " + P2(5 * k, 0) + "q" + P2(2.5 * k, 5 * k) + " " + P2(5 * k, 0);
      }
    }
    this.mouth.setAttribute("d", d2);
    var b = F.brow || "none", d3 = "", bx1 = -5 * k + lx * 0.5, bx2 = 13 * k + lx * 0.5, by = -5 * k + ly * 0.5;
    if (b === "up") {
      d3 = "M" + P2(bx1 - 5 * k, by - 10 * k) + "Q" + P2(bx1, by - 15 * k) + " " + P2(bx1 + 5 * k, by - 10 * k) +
        "M" + P2(bx2 - 5 * k, by - 10 * k) + "Q" + P2(bx2, by - 15 * k) + " " + P2(bx2 + 5 * k, by - 10 * k);
    } else if (b === "puzzled") {
      d3 = "M" + P2(bx1 - 5 * k, by - 12 * k) + "Q" + P2(bx1, by - 18 * k) + " " + P2(bx1 + 5 * k, by - 12 * k) +
        "M" + P2(bx2 - 5 * k, by - 9 * k) + "L" + P2(bx2 + 6 * k, by - 10 * k);
    } else if (b === "worried") {
      d3 = "M" + P2(bx1 - 5 * k, by - 9 * k) + "L" + P2(bx1 + 4 * k, by - 12 * k) + "M" + P2(bx2 - 4 * k, by - 12 * k) + "L" + P2(bx2 + 5 * k, by - 9 * k);
    } else if (b === "angry") {
      d3 = "M" + P2(bx1 - 5 * k, by - 13 * k) + "L" + P2(bx1 + 5 * k, by - 8 * k) + "M" + P2(bx2 - 5 * k, by - 8 * k) + "L" + P2(bx2 + 5 * k, by - 13 * k);
    }
    this.brow.setAttribute("d", d3);
  };
  /* P: hip [x,y], gy, lean, tilt, f, feet [[x,y],[x,y]] (back, front), hands [[x,y],[x,y]], face, skin, shr, hunch */
  D.Fig.prototype.draw = function (P) {
    var k = this.k, f = P.f, R = Math.PI / 180;
    var la = P.lean * R, ux = Math.sin(la) * f, uy = -Math.cos(la), fx = Math.cos(la) * f, fy = Math.sin(la);
    var hx = P.hip[0], hy = P.hip[1];
    var nx = hx + ux * this.T, ny = hy + uy * this.T;
    var so = this.sOff - (P.shr || 0);
    var sx = nx - ux * so, sy = ny - uy * so;
    var hu = (P.hunch || 0) * k;
    var dT = "M" + P2(hx, hy) + "Q" + P2((hx + nx) / 2 - fx * hu, (hy + ny) / 2 - fy * hu) + " " + P2(nx, ny);
    var lb = D.ik(hx, hy, P.feet[0][0], P.feet[0][1], this.th, this.sh, -f);
    var lf = D.ik(hx, hy, P.feet[1][0], P.feet[1][1], this.th, this.sh, -f);
    var dLB = "M" + P2(hx, hy) + "L" + P2(lb[0], lb[1]) + "L" + P2(lb[2], lb[3]);
    var dLF = "M" + P2(hx, hy) + "L" + P2(lf[0], lf[1]) + "L" + P2(lf[2], lf[3]);
    var ab = D.ik(sx, sy, P.hands[0][0], P.hands[0][1], this.ua, this.fa, f);
    var af = D.ik(sx, sy, P.hands[1][0], P.hands[1][1], this.ua, this.fa, f);
    var eb = P.eb || [0, 0];                                   // 0..1 blend toward the opposite elbow bend
    if (eb[0] > 0) { var ab2 = D.ik(sx, sy, P.hands[0][0], P.hands[0][1], this.ua, this.fa, -f); ab[0] = D.lerp(ab[0], ab2[0], eb[0]); ab[1] = D.lerp(ab[1], ab2[1], eb[0]); }
    if (eb[1] > 0) { var af2 = D.ik(sx, sy, P.hands[1][0], P.hands[1][1], this.ua, this.fa, -f); af[0] = D.lerp(af[0], af2[0], eb[1]); af[1] = D.lerp(af[1], af2[1], eb[1]); }
    var dAB = "M" + P2(sx, sy) + "L" + P2(ab[0], ab[1]) + "L" + P2(ab[2], ab[3]);
    var dAF = "M" + P2(sx, sy) + "L" + P2(af[0], af[1]) + "L" + P2(af[2], af[3]);
    this.torso.setAttribute("d", dT);
    this.legB.setAttribute("d", dLB);
    this.legF.setAttribute("d", dLF);
    this.armB.setAttribute("d", dAB);
    this.armF.setAttribute("d", dAF);
    var hd5 = [dT, dLB, dLF, dAB, dAF];
    for (var q = 0; q < 5; q++) this.halo[q].setAttribute("d", hd5[q]);
    var pt = function (along, side) { return P2(hx + ux * along - fx * side, hy + uy * along - fy * side); };
    var T = this.T;
    if (this.coat) {
      var hem = -(this.o.coatLen == null ? 40 : this.o.coatLen) * k;
      this.coat.setAttribute("d", "M" + pt(T - 2 * k, 9 * k) + "L" + pt(hem, 25 * k) + "Q" + pt(hem - 7 * k, 0) + " " + pt(hem, -29 * k) +
        "L" + pt(T - 2 * k, -12 * k) + "Q" + pt(T + 3 * k, 0) + " " + pt(T - 2 * k, 9 * k) + "Z");
      this.coatLine.setAttribute("d", "M" + pt(T - 3 * k, -11 * k) + "L" + pt(T - 26 * k, -3 * k) + "L" + pt(hem - 4 * k, -8 * k) +
        "M" + pt(T - 3 * k, 8 * k) + "L" + pt(T - 22 * k, 0) + "M" + pt(T - 60 * k, -12 * k) + "L" + pt(T - 60 * k, -4 * k));
    }
    if (this.stetho) {
      this.stetho.setAttribute("d", "M" + pt(T - 3 * k, -10 * k) + "Q" + pt(T - 30 * k, -16 * k) + " " + pt(T - 44 * k, -9 * k) +
        "M" + pt(T - 3 * k, 7 * k) + "Q" + pt(T - 30 * k, 4 * k) + " " + pt(T - 44 * k, -9 * k) + "L" + pt(T - 62 * k, -13 * k));
      var se = [hx + ux * (T - 66 * k) + fx * 13 * k, hy + uy * (T - 66 * k) + fy * 13 * k];
      D.set(this.stethoEnd, { cx: D.r1(se[0]), cy: D.r1(se[1]) });
    }
    var ha = (P.lean + P.tilt) * R, hd = this.r + 1.5 * k;
    var cx = nx + Math.sin(ha) * f * hd, cy = ny - Math.cos(ha) * hd;
    this.head.setAttribute("transform", "translate(" + P2(cx, cy) + ") rotate(" + D.r1((P.lean + P.tilt) * f) + ")" + (f < 0 ? " scale(-1,1)" : ""));
    D.set(this.haloHead, { cx: D.r1(cx), cy: D.r1(cy) });
    if (P.skin !== this._skin) { this.skull.setAttribute("fill", P.skin); this._skin = P.skin; }
    this._face(P.face);
    var air = D.clamp((P.gy - this.H0 - hy) / (60 * k), 0, 1);
    D.set(this.shadow, { cx: D.r1(hx), cy: D.r1(P.gy + 3 * k), rx: D.r1(46 * k * (1 - 0.4 * air)), ry: D.r1(8 * k * (1 - 0.4 * air)) });
    this.J = {
      hip: [hx, hy], neck: [nx, ny], sh: [sx, sy], head: [cx, cy], headAng: (P.lean + P.tilt) * f,
      handB: [ab[2], ab[3]], handF: [af[2], af[3]], elbowF: [af[0], af[1]], elbowB: [ab[0], ab[1]], f: f
    };
  };

  /* ------------------------------------------------------------------ gait */
  /* trapezoid speed profile: acc / dec = fractions of the move spent speeding up / slowing down */
  function trap(p, a, b) {
    p = D.clamp(p, 0, 1);
    var A = 1 - a / 2 - b / 2, s;
    if (a > 0 && p < a) s = (p * p) / (2 * a);
    else if (p <= 1 - b || b <= 0) s = a / 2 + (p - a);
    else {
      var q = p - (1 - b);
      s = a / 2 + (1 - b - a) + q - (q * q) / (2 * b);
    }
    return s / A;
  }
  D.trap = trap;
  /* planted-foot gait: foot position (track coords) and lift for travelled distance d.
     Stance: the foot stays fixed while the body passes over it; swing: it travels one stride. */
  function foot(d, C, off, lift) {
    var v = d / C + off, n = Math.floor(v), u = v - n;
    var P = (n - off) * C + C / 4;
    if (u < 0.5) return [P, 0];
    var w = (u - 0.5) / 0.5;
    return [P + C * D.smooth(w), lift * Math.sin(Math.PI * w)];
  }

  /* ------------------------------------------------------------------ actor = rig + walk + poses */
  /* o: Fig options + x, gy (ground y), f (facing +1/-1), walkLean, stance */
  D.Actor = function (parent, o) {
    this.o = o;
    this.fig = new D.Fig(parent, o);
    this.gy = o.gy; this.x = o.x; this.f = o.f || 1;
    this.w = null;
    this.pose = null;
    this.stance = (o.stance || 22) * this.fig.k;
  };
  /* walk from x0 to x1 during [t0, t1]; the stride is fitted so the walk ends in double support */
  D.Actor.prototype.walk = function (t0, t1, x0, x1, o) {
    o = o || {};
    var k = this.fig.k, dist = Math.abs(x1 - x0), C0 = (o.stride || 124) * k;
    var m = Math.max(1, Math.round(dist / (C0 / 2)));
    this.w = { t0: t0, t1: t1, x0: x0, x1: x1, dist: dist, C: (2 * dist) / m, acc: o.acc || 0, dec: o.dec == null ? 0.35 : o.dec,
      lift: (o.lift || 17) * k, bob: (o.bob || 4) * k, dir: x1 >= x0 ? 1 : -1 };
    return this;
  };
  D.Actor.prototype.gait = function (t) {
    var W = this.w;
    if (!W) return { x: this.x, feet: [[this.x - this.stance * this.f, 0], [this.x + this.stance * this.f, 0]], bob: 0, rel: [0, 0], mv: 0 };
    var d = W.dist * trap(D.prog(t, W.t0, W.t1), W.acc, W.dec), C = W.C;
    var feet = [], rel = [];
    for (var i = 0; i < 2; i++) {
      var fp = foot(d, C, i ? 0.5 : 0, W.lift);
      feet.push([W.x0 + W.dir * fp[0], fp[1]]);
      rel.push((fp[0] - d) / (C / 4));
    }
    var mv = t < W.t0 ? 0 : 1 - D.prog(t, W.t1, W.t1 + 0.3);
    return { x: W.x0 + W.dir * d, feet: feet, bob: W.bob * Math.cos((4 * Math.PI * d) / C) * mv, rel: rel, mv: mv };
  };
  /* pose fields (lengths in k-units): lean tilt hipDx hipDy kneel shr hunch swing ebB ebF (elbow flip 0..1)
     hbx hby hfx hfy (hand targets relative to the shoulder: forward, down)
     wB wBx wBy aimB / wF wFx wFy aimF (world override; aim = stretch toward the target)
     eyes mouth brow open lx ly lookW lkx lky sick */
  /* extra fields: fd ("r"/"l" facing switch), sit (0..1 sit on the ground), shift (k-units, whole body incl. feet,
     along facing - negative = hop/step back) */
  D.Actor.prototype.render = function (t) {
    var F = this.fig, k = F.k, P = this.pose ? this.pose(t) : {};
    var G = this.gait(t), f = P.fd === "l" ? -1 : P.fd === "r" ? 1 : this.f;
    var lean = (P.lean || 0) + G.mv * (this.o.walkLean == null ? 6 : this.o.walkLean);
    var shx = (P.shift || 0) * k * f;
    var hip = [G.x + shx + (P.hipDx || 0) * k * f, this.gy - F.H0 + G.bob + (P.hipDy || 0) * k];
    var kn = D.clamp(P.kneel || 0, 0, 1.2), sit = D.clamp(P.sit || 0, 0, 1);
    if (kn) hip[1] += kn * (F.H0 - 0.9 * F.th);
    if (sit) hip[1] = D.lerp(hip[1], this.gy - 15 * k + (P.hipDy || 0) * k * 0.5, sit);
    var feet = [];
    for (var i = 0; i < 2; i++) {
      var fx0 = G.feet[i][0] + shx, fy0 = this.gy - G.feet[i][1];
      if (kn) {
        var kk = Math.min(kn, 1);
        fx0 = D.lerp(fx0, hip[0] - f * (F.sh * 0.92 + i * 9 * k), kk);
        fy0 = D.lerp(fy0, this.gy - 2, kk);
      }
      if (sit) {
        fx0 = D.lerp(fx0, hip[0] + f * (60 + i * 14) * k, sit);
        fy0 = D.lerp(fy0, this.gy - 2, sit);
      }
      feet.push([fx0, fy0]);
    }
    var R = Math.PI / 180, la = lean * R, ux = Math.sin(la) * f, uy = -Math.cos(la), ffx = Math.cos(la) * f, ffy = Math.sin(la);
    var so = F.sOff - (P.shr || 0) * k;
    var sx = hip[0] + ux * (F.T - so), sy = hip[1] + uy * (F.T - so);
    var armL = F.ua + F.fa, hands = [];
    var loc = [[P.hbx == null ? -3 : P.hbx, P.hby == null ? 64 : P.hby], [P.hfx == null ? 4 : P.hfx, P.hfy == null ? 64 : P.hfy]];
    for (var j = 0; j < 2; j++) {
      var lx = loc[j][0] * k, ly = loc[j][1] * k;
      var sw = (P.swing == null ? 1 : P.swing) * G.mv * -G.rel[j] * 0.5;
      if (sw) {
        var c = Math.cos(sw), s = Math.sin(sw), nlx = lx * c + ly * s, nly = -lx * s + ly * c;
        lx = nlx; ly = nly;
      }
      var wx = sx + ffx * lx - ux * ly, wy = sy + ffy * lx - uy * ly;
      var ww = j ? P.wF || 0 : P.wB || 0;
      if (ww) {
        var tx = j ? P.wFx : P.wBx, ty = j ? P.wFy : P.wBy;
        if (j ? P.aimF : P.aimB) {
          var dx = tx - sx, dy = ty - sy, dl = Math.hypot(dx, dy) || 1;
          tx = sx + (dx / dl) * armL * 0.985;
          ty = sy + (dy / dl) * armL * 0.985;
        }
        wx = D.lerp(wx, tx, ww);
        wy = D.lerp(wy, ty, ww);
      }
      hands.push([wx, wy]);
    }
    var face = { eyes: P.eyes, mouth: P.mouth, brow: P.brow, open: P.open, lx: P.lx || 0, ly: P.ly || 0 };
    if (P.lookW) {
      var ha = (lean + (P.tilt || 0)) * R, nx = hip[0] + ux * F.T, ny = hip[1] + uy * F.T;
      var hcx = nx + Math.sin(ha) * f * F.r, hcy = ny - Math.cos(ha) * F.r;
      var ddx = P.lkx - hcx, ddy = P.lky - hcy, dd = Math.hypot(ddx, ddy) || 1;
      face.lx = D.lerp(face.lx, (ddx / dd) * 5.5 * f, P.lookW);
      face.ly = D.lerp(face.ly, (ddy / dd) * 5.5, P.lookW);
    }
    var skin = this.o.skin || "#f5efe2";
    if (P.sick) skin = D.mix(skin, this.o.sickSkin || "#a3cf62", P.sick);
    F.draw({ hip: hip, gy: this.gy, lean: lean, tilt: P.tilt || 0, f: f, feet: feet, hands: hands, face: face, skin: skin, shr: (P.shr || 0) * k,
      hunch: P.hunch || 0, eb: [D.clamp(P.ebB || 0, 0, 1), D.clamp(P.ebF || 0, 0, 1)] });
    return F.J;
  };

  /* ================================================================== v2 reusable components */
  D.fade = function (u, a, b) { return Math.max(0, Math.min(1, u / a) * (1 - D.prog(u, b, 1))); };   // life envelope
  D.pop = function (t, t0, dur, ease) { return t < t0 ? 0 : D.ease(ease || "back.out(2.2)")(D.prog(t, t0, t0 + (dur || 0.35))); };
  D.uid = (function () { var n = 0; return function (p) { n += 1; return (p || "u") + "_" + n; }; })();
  D.defs = function (el) {
    var svg = el.ownerSVGElement || el, d = svg.querySelector("defs");
    if (!d) { d = D.el(null, "defs"); svg.insertBefore(d, svg.firstChild); }
    return d;
  };
  /* radial gradient in the owning svg's defs; stops [[offset, colour, opacity]] -> "url(#id)" */
  D.radial = function (el, stops) {
    var id = D.uid("rg"), g = D.el(D.defs(el), "radialGradient", { id: id });
    stops.forEach(function (s) { D.el(g, "stop", { offset: s[0], "stop-color": s[1], "stop-opacity": s[2] == null ? 1 : s[2] }); });
    return "url(#" + id + ")";
  };
  D.text = function (parent, str, at) { var e = D.el(parent, "text", at); e.textContent = str; return e; };

  /* looping puff emitter. o: parent, n, r [min,max], fill, sw, fo (fill-opacity), seed, bumps,
     life(i) -> {start, period, phase}, place(i, u, cycle, t) -> {x, y, s | sx, sy, rot, o} or null */
  D.Emitter = function (o) {
    this.o = o;
    this.g = [];
    var sd = o.seed || 0;
    for (var i = 0; i < o.n; i++) {
      var g = D.el(o.parent, "g", { opacity: 0 });
      D.el(g, "path", { d: D.puff(D.rnd(sd + i * 8.7 + 1, o.r[0], o.r[1]), o.bumps || 7, sd + i * 23 + 9), fill: o.fill || "#ffffff",
        "fill-opacity": o.fo == null ? 1 : o.fo, stroke: o.stroke || INK, "stroke-width": o.sw || 4.5, "stroke-linejoin": "round" });
      this.g.push(g);
    }
  };
  D.Emitter.prototype.render = function (t, gain) {
    var o = this.o, gn = gain == null ? 1 : gain;
    for (var i = 0; i < this.g.length; i++) {
      var lf = o.life(i), L = gn > 0 ? D.life(t, lf.start, lf.period, lf.phase || 0) : null;
      var p = L ? o.place(i, L.u, L.c, t) : null;
      if (!p || p.o <= 0) { this.g[i].setAttribute("opacity", 0); continue; }
      this.g[i].setAttribute("transform", D.tf(p.x, p.y, p.rot || 0, p.sx != null ? p.sx : p.s, p.sy != null ? p.sy : p.s));
      this.g[i].setAttribute("opacity", D.clamp(p.o * gn, 0, 1).toFixed(3));
    }
  };

  /* particles drifting in a box (e.g. arsenic). o: parent, n, box [x,y,w,h], r [min,max], fill, label, labelEvery, seed */
  D.Particles = function (o) {
    this.o = o;
    this.p = [];
    var sd = o.seed || 0;
    for (var i = 0; i < o.n; i++) {
      var g = D.el(o.parent, "g", {}), r = D.rnd(sd + i * 3.3, o.r[0], o.r[1]);
      D.el(g, "circle", { r: D.r1(r), fill: o.fill || "#e63946", stroke: INK, "stroke-width": 3.5 });
      if (o.label && i % (o.labelEvery || 3) === 0) {
        D.text(g, o.label, { x: 0, y: D.r1(r * 0.36), "text-anchor": "middle", "font-family": "Comic Neue", "font-weight": 700, "font-size": D.r1(r * 1.05), fill: "#ffffff" });
      }
      this.p.push({ g: g, x: o.box[0] + D.hash(sd + i * 5.1) * o.box[2], y: o.box[1] + D.hash(sd + i * 7.3) * o.box[3],
        a1: D.rnd(sd + i * 1.7, 10, 26), a2: D.rnd(sd + i * 2.9, 6, 16), w1: D.rnd(sd + i * 4.4, 0.6, 1.3), w2: D.rnd(sd + i * 6.6, 0.5, 1.1), ph: D.rnd(sd + i * 8.8, 0, 6.28) });
    }
  };
  D.Particles.prototype.render = function (t, pulse) {
    for (var i = 0; i < this.p.length; i++) {
      var q = this.p[i], s = 1 + (pulse || 0) * (0.3 + 0.12 * Math.sin(11 * t + i));
      q.g.setAttribute("transform", D.tf(q.x + q.a1 * Math.sin(q.w1 * t + q.ph), q.y + q.a2 * Math.sin(q.w2 * 1.3 * t + q.ph * 1.7), 18 * Math.sin(q.w2 * t + q.ph), s));
    }
  };

  /* reveal a stroked path from its start: new D.DrawOn(pathEl).set(progress) */
  D.DrawOn = function (el) {
    this.el = el;
    this.L = el.getTotalLength();
    el.setAttribute("stroke-dasharray", D.r1(this.L) + " " + D.r1(this.L + 20));
    this.set(0);
  };
  D.DrawOn.prototype.set = function (p) {
    p = D.clamp(p, 0, 1);
    this.el.setAttribute("stroke-dashoffset", D.r1(this.L * (1 - p)));
    this.el.setAttribute("opacity", p > 0.002 ? 1 : 0);
  };

  /* wobbly bumpy blob (thought cloud); regenerate every frame for a living outline */
  D.wobble = function (r, n, t, seed, amp, speed, flat) {
    var pts = [], i;
    for (i = 0; i < n; i++) {
      var a = -Math.PI / 2 + (i / n) * Math.PI * 2;
      var rr = r * (0.84 + 0.16 * D.hash(seed + i * 7 + 1)) * (1 + (amp || 0.06) * Math.sin((speed || 5) * t + i * 2.1 + seed));
      pts.push([Math.cos(a) * rr, Math.sin(a) * rr * (flat || 0.78)]);
    }
    var d = "M" + P2(pts[0][0], pts[0][1]);
    for (i = 1; i <= n; i++) {
      var p = pts[i % n], q = pts[i - 1], br = Math.max(Math.hypot(p[0] - q[0], p[1] - q[1]) * 0.62, r * 0.25);
      d += "A" + D.r1(br) + "," + D.r1(br) + " 0 0 1 " + P2(p[0], p[1]);
    }
    return d + "Z";
  };

  /* glass shards burst out of a window. o: parent, n, x, y (window centre), w, h, dir (+1/-1), t0, gy (floor), seed */
  D.Shards = function (o) {
    this.o = o;
    this.s = [];
    for (var i = 0; i < o.n; i++) {
      var sd = (o.seed || 0) + i * 13.7, sz = D.rnd(sd, 6, 13), g = D.el(o.parent, "g", { opacity: 0 });
      D.el(g, "path", { d: "M0," + D.r1(-sz) + "L" + P2(sz * 0.7, sz * 0.6) + "L" + P2(-sz * 0.6, sz * 0.4) + "Z",
        fill: o.fill || "#bfe6f7", stroke: INK, "stroke-width": 3, "stroke-linejoin": "round" });
      this.s.push({ g: g, x: o.x + D.rnd(sd + 1, -o.w / 2, o.w / 2), y: o.y + D.rnd(sd + 2, -o.h / 2, o.h / 2),
        vx: (o.dir || 1) * D.rnd(sd + 3, 50, 250), vy: -D.rnd(sd + 4, 80, 330), sp: D.rnd(sd + 5, -900, 900), d: D.rnd(sd + 6, 0, 0.05) });
    }
  };
  D.Shards.prototype.render = function (t) {
    var o = this.o;
    for (var i = 0; i < this.s.length; i++) {
      var q = this.s[i], u = t - o.t0 - q.d;
      if (u < 0 || u > 1.7) { q.g.setAttribute("opacity", 0); continue; }
      var x = q.x + q.vx * u, y = q.y + q.vy * u + 700 * u * u, rot = q.sp * u;
      if (y > o.gy) {
        var ul = (-q.vy + Math.sqrt(q.vy * q.vy + 2800 * (o.gy - q.y))) / 1400;
        x = q.x + q.vx * ul; y = o.gy; rot = q.sp * ul;
      }
      q.g.setAttribute("transform", D.tf(x, y, rot, 1));
      q.g.setAttribute("opacity", (1 - D.prog(u, 1.2, 1.7)).toFixed(3));
    }
  };

  /* fireball: arc-length parametrised cubic Bezier, accelerating, flickering flames, speed streaks, spinning rock,
     lingering smoke tail. o: parent, smokeParent, P [4 points], t0, t1, acc (start share of speed, 0..1), s0, s1 (scale),
     smoke (number of tail puffs), smokeUntil (0..1 of the path that leaves smoke) */
  D.Meteor = function (o) {
    this.o = o;
    var P = o.P, i;
    var bz = (this.bz = function (p, k) {
      var q = 1 - p;
      return q * q * q * P[0][k] + 3 * q * q * p * P[1][k] + 3 * q * p * p * P[2][k] + p * p * p * P[3][k];
    });
    var LUT = [0], L = 0, px = bz(0, 0), py = bz(0, 1);
    for (i = 1; i <= 240; i++) {
      var nx = bz(i / 240, 0), ny = bz(i / 240, 1);
      L += Math.hypot(nx - px, ny - py);
      LUT.push(L);
      px = nx; py = ny;
    }
    this.LUT = LUT; this.L = L;
    var g = (this.g = D.el(o.parent, "g", { opacity: 0 }));
    this.trail = D.el(g, "path", { fill: "none", stroke: "#f4a261", "stroke-width": 9, "stroke-linecap": "round" });
    this.flame = D.el(g, "g", {});
    this.fl = [];
    var tips = [[-160, -4, 42], [-148, 9, 37], [-172, -11, 47]];
    for (i = 0; i < 3; i++) {
      var fg = D.el(this.flame, "g", { opacity: i ? 0 : 1 }), tp = tips[i], wd = tp[2];
      D.el(fg, "path", { d: "M28,0C20," + (-wd) + " -40," + (-wd - 4) + " " + tp[0] + "," + tp[1] + "C-40," + (wd + 2) + " 20," + wd + " 28,0Z",
        fill: "#ffd166", stroke: INK, "stroke-width": 6, "stroke-linejoin": "round" });
      D.el(fg, "path", { d: "M22,0C14," + D.r1(-wd * 0.58) + " -26," + D.r1(-wd * 0.62) + " " + P2(tp[0] * 0.62, tp[1] * 0.6) + "C-26," + D.r1(wd * 0.62) + " 14," + D.r1(wd * 0.58) + " 22,0Z",
        fill: "#f4a261", stroke: INK, "stroke-width": 4.5, "stroke-linejoin": "round" });
      this.fl.push(fg);
    }
    this.rock = D.el(g, "g", {});
    D.el(this.rock, "path", { d: "M-30,-20L4,-36L32,-20L38,12L14,36L-22,32L-38,6Z", fill: "#4a4a4a", stroke: INK, "stroke-width": 7, "stroke-linejoin": "round" });
    D.el(this.rock, "circle", { cx: -8, cy: -6, r: 6, fill: INK });
    D.el(this.rock, "circle", { cx: 16, cy: 14, r: 4.5, fill: INK });
    D.el(this.rock, "circle", { cx: 12, cy: -18, r: 3.5, fill: INK });
    this.smoke = [];
    var n = o.smoke || 0, until = o.smokeUntil || 0.8;
    for (i = 0; i < n; i++) {
      var sg = D.el(o.smokeParent || o.parent, "g", { opacity: 0 });
      D.el(sg, "path", { d: D.puff(D.rnd(i * 4.7 + 3, 22, 34), 7, i * 17 + 5), fill: "#c9c9c9", stroke: INK, "stroke-width": 4, "stroke-linejoin": "round" });
      var sv = L * until * (i + 0.5) / n, p = this.pAt(sv);
      this.smoke.push({ g: sg, x: bz(p, 0) + D.rnd(i * 2.1, -8, 8), y: bz(p, 1) + D.rnd(i * 3.1, -8, 8), t: this.tAt(sv), dr: D.rnd(i * 5.3, -12, 12) });
    }
  };
  D.Meteor.prototype.pAt = function (s) {
    var LUT = this.LUT, n = LUT.length - 1;
    if (s <= 0) return 0;
    if (s >= this.L) return 1;
    var lo = 0, hi = n;
    while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (LUT[mid] < s) lo = mid; else hi = mid; }
    return (lo + (s - LUT[lo]) / (LUT[hi] - LUT[lo])) / n;
  };
  D.Meteor.prototype.sAt = function (t) {
    var o = this.o, a = o.acc == null ? 0.3 : o.acc, u = D.prog(t, o.t0, o.t1);
    return this.L * (a * u + (1 - a) * u * u);
  };
  D.Meteor.prototype.tAt = function (s) {            // inverse of sAt
    var o = this.o, a = o.acc == null ? 0.3 : o.acc, r = s / this.L;
    var u = a >= 1 ? r : (-a + Math.sqrt(a * a + 4 * (1 - a) * r)) / (2 * (1 - a));
    return o.t0 + u * (o.t1 - o.t0);
  };
  D.Meteor.prototype.pos = function (t) {
    var p = this.pAt(this.sAt(t));
    return [this.bz(p, 0), this.bz(p, 1), p];
  };
  D.Meteor.prototype.render = function (t) {
    var o = this.o, j;
    for (j = 0; j < this.smoke.length; j++) {
      var q = this.smoke[j], u = t - q.t;
      if (u < 0 || u > 3.2) { q.g.setAttribute("opacity", 0); continue; }
      q.g.setAttribute("transform", D.tf(q.x + q.dr * u, q.y - 10 * u, 20 * u, 0.45 + 0.9 * (1 - Math.exp(-1.6 * u))));
      q.g.setAttribute("opacity", (0.9 * Math.min(1, u / 0.08) * (1 - D.prog(u, 1.4, 3.2))).toFixed(3));
    }
    if (t < o.t0 || t >= o.t1) { this.g.setAttribute("opacity", 0); return; }
    var s = this.sAt(t), m = this.pos(t), q2 = this.pAt(s - 4);
    var ang = (Math.atan2(m[1] - this.bz(q2, 1), m[0] - this.bz(q2, 0)) * 180) / Math.PI;
    var a = o.acc == null ? 0.3 : o.acc, uu = D.prog(t, o.t0, o.t1);
    var v = (this.L * (a + 2 * (1 - a) * uu)) / (o.t1 - o.t0), sp = D.clamp(v / 1400, 0, 1.3);
    this.g.setAttribute("opacity", 1);
    this.g.setAttribute("transform", D.tf(m[0], m[1], ang, D.lerp(o.s0 || 0.86, o.s1 || 1.16, m[2])));
    var fi = Math.floor(D.frame(t) / 2) % 3;
    for (j = 0; j < 3; j++) this.fl[j].setAttribute("opacity", j === fi ? 1 : 0);
    this.flame.setAttribute("transform", "scale(" + (0.72 + 0.5 * sp + 0.07 * Math.sin(t * 53)).toFixed(3) + "," + (1 + 0.09 * Math.sin(t * 41)).toFixed(3) + ")");
    var Lt = 40 + 200 * sp;
    this.trail.setAttribute("d", "M-48,-22L" + D.r1(-48 - Lt) + ",-30M-58,2L" + D.r1(-58 - Lt * 1.25) + ",3M-46,24L" + D.r1(-46 - Lt * 0.8) + ",33");
    this.rock.setAttribute("transform", "rotate(" + (t * 170).toFixed(1) + ")");
  };

  /* impact behind a hill. o: back (layer behind the hill), front (layer in front), x, y, t0, gy (debris floor) */
  D.Impact = function (o) {
    this.o = o;
    var i, pts;
    this.glow = D.el(o.back, "ellipse", { cx: o.x, cy: o.y + 10, rx: 230, ry: 170, opacity: 0,
      fill: D.radial(o.back, [[0, "#fff6c2", 1], [0.5, "#ffd166", 0.85], [1, "#f4a261", 0]]) });
    var star = function (n, R, r) {
      var s = [];
      for (var k = 0; k < 2 * n; k++) { var a = (Math.PI * k) / n - Math.PI / 2, rr = k % 2 ? r : R; s.push(P2(Math.cos(a) * rr, Math.sin(a) * rr)); }
      return "M" + s.join("L") + "Z";
    };
    this.burst = D.el(o.back, "g", { opacity: 0 });
    D.el(this.burst, "path", { d: star(12, 150, 78), fill: "#ffd166", stroke: INK, "stroke-width": 7, "stroke-linejoin": "round" });
    D.el(this.burst, "path", { d: star(12, 88, 46), fill: "#fff6c2", stroke: INK, "stroke-width": 5, "stroke-linejoin": "round" });
    this.smoke = new D.Emitter({ parent: o.back, n: 6, r: [34, 44], fill: "#a9a9a9", sw: 5, seed: 40,
      life: function (k) { return { start: o.t0 + 0.1 + k * 0.2, period: 1.25 }; },
      place: function (k, u) { return { x: o.x + 30 * u + 14 * Math.sin(2 * Math.PI * (u + k * 0.3)), y: o.y + 6 - 360 * u, s: 0.5 + 1.3 * u, rot: 30 * u, o: D.fade(u, 0.1, 0.55) }; } });
    this.dust = [];
    for (i = 0; i < 9; i++) {
      var g = D.el(o.front, "g", { opacity: 0 });
      D.el(g, "path", { d: D.puff(D.rnd(i * 3 + 1, 30, 46), 7, i * 11 + 3), fill: "#efe5d3", stroke: INK, "stroke-width": 5, "stroke-linejoin": "round" });
      var a = ((-176 + (i / 8) * 172 + D.rnd(i * 5, -8, 8)) * Math.PI) / 180;
      this.dust.push({ g: g, ca: Math.cos(a), sa: Math.sin(a), R: D.rnd(i * 7 + 2, 150, 250), d: D.rnd(i * 13, 0, 0.08), sp: D.rnd(i * 17, -40, 40) });
    }
    this.deb = [];
    for (i = 0; i < 8; i++) {
      var g2 = D.el(o.front, "g", { opacity: 0 }), rr = D.rnd(i * 3 + 7, 7, 13);
      pts = [];
      for (var j = 0; j < 5; j++) { var aa = (j / 5) * Math.PI * 2, r2 = rr * D.rnd(i * 10 + j, 0.7, 1.1); pts.push(P2(Math.cos(aa) * r2, Math.sin(aa) * r2)); }
      D.el(g2, "path", { d: "M" + pts.join("L") + "Z", fill: "#5b5b5b", stroke: INK, "stroke-width": 4, "stroke-linejoin": "round" });
      this.deb.push({ g: g2, vx: (i % 2 ? 1 : -1) * D.rnd(i * 7 + 1, 90, 320), vy: -D.rnd(i * 9 + 2, 430, 700), sp: D.rnd(i * 11 + 3, -700, 700) });
    }
  };
  D.Impact.prototype.render = function (t) {
    var o = this.o, tau = t - o.t0, j, q, u;
    if (tau < 0) {
      this.burst.setAttribute("opacity", 0);
      this.glow.setAttribute("opacity", 0);
    } else {
      var s = tau < 0.12 ? D.ease("power2.out")(tau / 0.12) * 1.25 : 1.25 + 0.4 * D.prog(tau, 0.12, 0.5);
      this.burst.setAttribute("transform", D.tf(o.x, o.y - 6, tau * 40, s));
      this.burst.setAttribute("opacity", (1 - D.prog(tau, 0.16, 0.5)).toFixed(3));
      var gl = tau < 0.1 ? tau / 0.1 : 0.55 + 0.45 * Math.exp(-3 * (tau - 0.1)) + 0.1 * Math.sin(2 * Math.PI * 2.1 * tau);
      this.glow.setAttribute("opacity", D.clamp(gl, 0, 1).toFixed(3));
    }
    this.smoke.render(t);
    for (j = 0; j < this.dust.length; j++) {
      q = this.dust[j]; u = tau - q.d;
      if (u < 0) { q.g.setAttribute("opacity", 0); continue; }
      var ex = 1 - Math.exp(-4.2 * u);
      q.g.setAttribute("transform", D.tf(o.x + q.ca * q.R * ex, o.y + 8 + q.sa * q.R * 0.62 * ex - 26 * u, q.sp * u, 0.3 + 1.05 * ex + 0.12 * u));
      q.g.setAttribute("opacity", (1 - D.prog(u, 0.9, 1.75)).toFixed(3));
    }
    for (j = 0; j < this.deb.length; j++) {
      q = this.deb[j];
      var y = o.y - 10 + q.vy * tau + 750 * tau * tau;
      if (tau < 0.01 || tau > 1.3 || y > o.gy) { q.g.setAttribute("opacity", 0); continue; }
      q.g.setAttribute("transform", D.tf(o.x + q.vx * tau, y, q.sp * tau, 1));
      q.g.setAttribute("opacity", 1);
    }
  };

  /* cut-away crater (local coords: origin = ground level centre, bowl 580 x 400, soil 745 x 452).
     o: parent, fillT0/fillT1 (water rises), boilT0/boilT1 (bubbles start / full boil), drops [times]
     render(t, st): st.vis (0..1 small details), st.steam (0..1) */
  D.Crater = function (o) {
    this.o = o;
    var g = o.parent, i, BOWL = "M-290,0 C-282,235 -165,400 0,400 C165,400 282,235 290,0";
    var SOIL = "M-372,0 C-372,300 -250,452 0,452 C250,452 372,300 372,0", cid = D.uid("bowl");
    var cp = D.el(D.defs(g), "clipPath", { id: cid });
    D.el(cp, "path", { d: BOWL + " Z" });
    D.el(g, "path", { d: SOIL + " Z", fill: "#d9ae7e" });
    D.el(g, "path", { d: "M-330,40 C-326,260 -215,402 0,410 C215,402 326,260 330,40", fill: "none", stroke: "#a9764a", "stroke-width": 5, "stroke-dasharray": "30 22", "stroke-linecap": "round" });
    [[-334, 90, 17, 11], [322, 150, 15, 10], [-250, 300, 14, 9], [236, 318, 16, 10], [-40, 430, 15, 9], [120, 424, 12, 8], [-190, 395, 11, 7]].forEach(function (p) {
      D.el(g, "ellipse", { cx: p[0], cy: p[1], rx: p[2], ry: p[3], fill: "#b98b5e", stroke: INK, "stroke-width": 5 });
    });
    D.el(g, "path", { d: SOIL, fill: "none", stroke: INK, "stroke-width": 7, "stroke-linecap": "round", "stroke-linejoin": "round" });
    D.el(g, "path", { d: BOWL + " Z", fill: "#6b4f3a" });
    var cg = D.el(g, "g", { "clip-path": "url(#" + cid + ")" });
    this.water = D.el(cg, "path", { d: "", fill: "#4fa3d1" });
    this.deep = D.el(cg, "path", { d: "M-300,300 Q0,330 300,300 L300,420 L-300,420 Z", fill: "#3b8cc2", opacity: 0.55 });
    this.glow = D.el(cg, "ellipse", { cx: 0, cy: 345, rx: 180, ry: 118, fill: D.radial(g, [[0, "#ffe08a", 1], [0.45, "#ffb347", 0.75], [1, "#ff8c42", 0]]) });
    var hg = D.el(cg, "g", {});
    this.heat = [];
    for (i = 0; i < 5; i++) this.heat.push(D.el(hg, "path", { fill: "none", stroke: "#e63946", "stroke-width": 6, "stroke-linecap": "round" }));
    D.el(cg, "path", { d: "M-78,372 L-66,322 L-22,298 L32,304 L72,330 L82,368 L46,396 L-38,398 Z", fill: "#474747", stroke: INK, "stroke-width": 7, "stroke-linejoin": "round" });
    this.cracks = D.el(cg, "path", { d: "M-44,328 L-22,350 L-34,376 M8,314 L20,344 L4,372 M50,338 L62,362", fill: "none", stroke: "#f77f00", "stroke-width": 6, "stroke-linecap": "round", "stroke-linejoin": "round" });
    var bgp = D.el(cg, "g", {});
    this.surf = D.el(cg, "path", { d: "", fill: "none", stroke: INK, "stroke-width": 5, "stroke-linecap": "round", "stroke-linejoin": "round" });
    D.el(g, "path", { d: BOWL, fill: "none", stroke: INK, "stroke-width": 7, "stroke-linecap": "round", "stroke-linejoin": "round" });
    var pop = D.el(g, "g", {}), dropG = D.el(g, "g", {}), steamG = D.el(g, "g", {});
    this.bub = [];
    for (i = 0; i < 16; i++) {
      var b = D.el(bgp, "g", { opacity: 0 });
      D.el(b, "circle", { cx: 0, cy: 0, r: 10, fill: "#e6f5ff", stroke: INK, "stroke-width": 4 });
      D.el(b, "path", { d: "M-5,-3Q-4,-7 0,-7", fill: "none", stroke: "#ffffff", "stroke-width": 3, "stroke-linecap": "round" });
      var pg = D.el(pop, "g", { opacity: 0 });
      this.bub.push({ g: b, pg: pg, pr: D.el(pg, "ellipse", { cx: 0, cy: 0, rx: 10, ry: 4, fill: "none", stroke: INK, "stroke-width": 4 }), pl: D.el(pg, "path", D.stroke(4)),
        x0: D.rnd(i * 3.1 + 1, -75, 75), P: D.rnd(i * 5.7 + 2, 0.85, 1.35), ph: D.hash(i * 9.3 + 3), R: D.rnd(i * 2.3 + 4, 13, 25),
        st: i < 7 ? (o.boilT0 || 0) + i * 0.13 : (o.boilT1 || 0) + (i - 7) * 0.08 });
    }
    this.drops = [];
    (o.drops || []).forEach(function (tb, bi) {
      for (var n = 0; n < 8; n++) {
        var id = bi * 50 + n, dg = D.el(dropG, "g", { opacity: 0 });
        D.el(dg, "path", { d: D.drop(1.1), fill: "#4fa3d1", stroke: INK, "stroke-width": 4, "stroke-linejoin": "round" });
        this.drops.push({ g: dg, t0: tb + D.rnd(id * 1.3, 0, 0.08), x0: D.rnd(id * 2.9 + 1, -150, 150), vx: D.rnd(id * 3.7 + 2, -160, 160), vy: -D.rnd(id * 4.3 + 3, 360, 560) });
      }
    }, this);
    var self = this;
    this.steam = new D.Emitter({ parent: steamG, n: 13, r: [46, 66], bumps: 8, fill: "#ffffff", sw: 4.5, seed: 9,
      life: function (k) { return { start: -100, period: D.rnd(k * 1.9 + 3, 1.7, 2.3), phase: k / 13 }; },
      place: function (k, u) {
        var x0 = D.rnd(k * 4.1 + 2, -210, 210), dr = -D.rnd(k * 3.3 + 5, 50, 130), H = D.rnd(k * 6.1 + 6, 270, 340), s = 0.4 + 1.15 * u, lv = Math.min(self.lvl, 300);
        return { x: x0 * (1 - 0.3 * u) + dr * u + 14 * Math.sin(2 * Math.PI * (u + k * 0.07)), y: lv - 10 - H * u, sx: s * (1 - 0.12 * u), sy: s * (1 + 0.35 * u), o: D.fade(u, 0.1, 0.5) };
      } });
    this.lvl = 40;
  };
  D.Crater.prototype.level = function (t) {
    var o = this.o;
    return o.fillT0 == null ? 40 : D.lerp(410, 40, D.ev(t, o.fillT0, o.fillT1, "power2.inOut"));
  };
  D.Crater.prototype.render = function (t, st) {
    st = st || {};
    var o = this.o, vis = st.vis == null ? 1 : st.vis, lvl = (this.lvl = this.level(t)), j;
    var boil = o.boilT0 == null ? 1 : D.ev(t, o.boilT0, (o.boilT1 || o.boilT0) + 0.3, "power1.inOut");
    var A = 2.5 + 5.5 * boil, sy = function (x) { return lvl + A * (0.6 * Math.sin(0.034 * x - 6.2 * t) + 0.4 * Math.sin(0.081 * x + 8.3 * t + 1.7)); };
    if (lvl < 398) {
      var d = "";
      for (var x = -310; x <= 310; x += 20) d += (x === -310 ? "M" : "L") + x + "," + D.r1(sy(x));
      this.surf.setAttribute("d", d);
      this.water.setAttribute("d", d + "L310,430L-310,430Z");
      this.deep.setAttribute("opacity", (0.55 * D.prog(410 - lvl, 20, 120)).toFixed(3));
    } else {
      this.surf.setAttribute("d", "");
      this.water.setAttribute("d", "");
      this.deep.setAttribute("opacity", 0);
    }
    var sn = Math.sin(2 * Math.PI * 1.4 * t);
    this.glow.setAttribute("transform", D.tfAbout(0, 345, 1 + 0.08 * sn, 1 + 0.08 * sn));
    this.glow.setAttribute("opacity", (0.75 + 0.25 * sn).toFixed(3));
    this.cracks.setAttribute("stroke", D.mix("#f77f00", "#ffd166", 0.5 + 0.5 * sn));
    var HP = [[-100, 330], [-58, 282], [0, 262], [58, 282], [100, 330]];
    for (j = 0; j < 5; j++) {
      var u0 = D.life(t, -100, 0.75, j * 0.37).u;
      this.heat[j].setAttribute("d", D.waveUp(HP[j][0] * (1 + 0.25 * u0), HP[j][1] - 34 * u0, 36 + 10 * u0, 6, 22, t * 9 + j, 8));
      this.heat[j].setAttribute("opacity", Math.sin(Math.PI * u0).toFixed(3));
    }
    for (j = 0; j < this.bub.length; j++) {
      var b = this.bub[j], L = D.life(t, b.st, b.P, 0);
      if (!L || vis <= 0 || lvl > 290) { b.g.setAttribute("opacity", 0); b.pg.setAttribute("opacity", 0); continue; }
      var u = L.u, xo = b.x0 + D.rnd(j * 31 + L.c * 7, -26, 26);
      if (u < 0.8) {
        var q = u / 0.8;
        b.g.setAttribute("transform", D.tf(xo * (1 + 0.7 * q) + 9 * Math.sin(2 * Math.PI * (1.7 * q + b.ph)), D.lerp(318, lvl + 6, Math.pow(q, 1.25)), 0, D.lerp(3, b.R, q) / 10));
        b.g.setAttribute("opacity", vis.toFixed(3));
        b.pg.setAttribute("opacity", 0);
      } else {
        var v = (u - 0.8) / 0.2, xe = xo * 1.7 + 9 * Math.sin(2 * Math.PI * (1.7 + b.ph)), s = 1 + 1.2 * D.ease("power2.out")(v);
        b.g.setAttribute("opacity", 0);
        D.set(b.pr, { rx: D.r1(b.R * s), ry: D.r1(b.R * 0.35 * s) });
        var l1 = b.R * (0.9 + 0.9 * v), l0 = b.R * (0.7 + 0.5 * v);
        b.pl.setAttribute("d", "M" + P2(-l0, -l0 * 0.5) + "L" + P2(-l1, -l1 * 0.9) + "M" + P2(0, -l0 * 0.8) + "L" + P2(0, -l1 * 1.3) + "M" + P2(l0, -l0 * 0.5) + "L" + P2(l1, -l1 * 0.9));
        b.pg.setAttribute("transform", D.tf(xe, sy(xe), 0, 1));
        b.pg.setAttribute("opacity", ((1 - v) * vis).toFixed(3));
      }
    }
    for (j = 0; j < this.drops.length; j++) {
      var dq = this.drops[j], du = t - dq.t0, y = lvl + dq.vy * du + 750 * du * du;
      if (du < 0 || (du > 0.1 && y > lvl + 4) || vis <= 0) { dq.g.setAttribute("opacity", 0); continue; }
      dq.g.setAttribute("transform", D.tf(dq.x0 + dq.vx * du, y, (Math.atan2(-dq.vx, dq.vy + 1500 * du) * 180) / Math.PI, 1));
      dq.g.setAttribute("opacity", vis.toFixed(3));
    }
    this.steam.render(t, st.steam == null ? 1 : st.steam);
  };

  /* bicycle + rider (a D.Fig drawn inside the bike group). Local origin = rear wheel ground contact, x forward.
     o: s (bike scale), rider (Fig options), color */
  D.Bike = function (parent, o) {
    var s = (this.s = o.s || 1), R = (this.R = 27 * s), L = (this.L = 100 * s);
    this.g = D.el(parent, "g", {});
    this.wheels = [];
    for (var w = 0; w < 2; w++) {
      var wg = D.el(this.g, "g", {}), sp = "";
      for (var k = 0; k < 4; k++) { var a = (k * Math.PI) / 4; sp += "M" + P2(Math.cos(a) * R, Math.sin(a) * R) + "L" + P2(-Math.cos(a) * R, -Math.sin(a) * R); }
      D.el(wg, "path", { d: sp, fill: "none", stroke: INK, "stroke-width": 2.5 });
      D.el(wg, "circle", { cx: 0, cy: 0, r: R, fill: "none", stroke: INK, "stroke-width": 6 });
      D.el(wg, "circle", { cx: 0, cy: 0, r: 4 * s, fill: INK });
      this.wheels.push(wg);
    }
    this.BB = [0.42 * L, -R + 2 * s]; this.S = [0.26 * L, -R - 50 * s]; this.H = [0.84 * L, -R - 44 * s]; this.BAR = [0.8 * L, -R - 58 * s];
    var hub = [0, -R], fh = [L, -R], BB = this.BB, S = this.S, H = this.H, BAR = this.BAR;
    var fr = "M" + P2(hub[0], hub[1]) + "L" + P2(BB[0], BB[1]) + "L" + P2(S[0], S[1]) + "Z M" + P2(S[0], S[1]) + "L" + P2(H[0], H[1]) + "L" + P2(BB[0], BB[1]) +
      "M" + P2(H[0], H[1]) + "L" + P2(fh[0], fh[1]) + "M" + P2(H[0], H[1]) + "L" + P2(BAR[0], BAR[1]) + "M" + P2(BAR[0] - 10 * s, BAR[1] + 2 * s) + "L" + P2(BAR[0] + 9 * s, BAR[1] - 2 * s);
    D.el(this.g, "path", { d: fr, fill: "none", stroke: INK, "stroke-width": 11, "stroke-linecap": "round", "stroke-linejoin": "round" });
    D.el(this.g, "path", { d: fr, fill: "none", stroke: o.color || "#2a9d8f", "stroke-width": 5, "stroke-linecap": "round", "stroke-linejoin": "round" });
    D.el(this.g, "path", { d: "M" + P2(S[0] - 13 * s, S[1] - 3 * s) + "L" + P2(S[0] + 11 * s, S[1] - 3 * s), fill: "none", stroke: INK, "stroke-width": 8, "stroke-linecap": "round" });
    this.crank = D.el(this.g, "path", { fill: "none", stroke: INK, "stroke-width": 5, "stroke-linecap": "round" });
    this.fig = new D.Fig(this.g, o.rider || { k: 0.9 * s });
    this.fig.shadow.setAttribute("opacity", 0);
  };
  /* st: x, gy, rot (deg about the rear contact), dist (travelled px -> wheel + crank angle), lean, tilt, face, skin, wave (0..1 free arm up) */
  D.Bike.prototype.render = function (t, st) {
    var s = this.s, R = this.R, L = this.L, BB = this.BB, S = this.S, BAR = this.BAR, F = this.fig, k = F.k;
    this.g.setAttribute("transform", D.tf(st.x, st.gy, st.rot || 0, 1));
    var wa = ((st.dist || 0) / R) * (180 / Math.PI);
    this.wheels[0].setAttribute("transform", D.tf(0, -R, wa, 1));
    this.wheels[1].setAttribute("transform", D.tf(L, -R, wa, 1));
    var th = (st.dist || 0) / (R * 1.6), cl = 15 * s;
    var p1 = [BB[0] + Math.cos(th) * cl, BB[1] + Math.sin(th) * cl], p2 = [BB[0] - Math.cos(th) * cl, BB[1] - Math.sin(th) * cl];
    this.crank.setAttribute("d", "M" + P2(p1[0], p1[1]) + "L" + P2(p2[0], p2[1]) + "M" + P2(p1[0] - 6 * s, p1[1]) + "L" + P2(p1[0] + 6 * s, p1[1]) + "M" + P2(p2[0] - 6 * s, p2[1]) + "L" + P2(p2[0] + 6 * s, p2[1]));
    var lean = st.lean == null ? 24 : st.lean;
    var hand = [BAR[0] - 4 * s, BAR[1] + 3 * s], free = hand;
    if (st.wave) {                                   // free arm goes up (in world space) and waves
      var rr = -((st.rot || 0) * Math.PI) / 180, up = [Math.sin(rr), -Math.cos(rr)];
      var sh = [S[0] + 6 * s, S[1] - 70 * k];
      var wv = 0.35 * Math.sin(2 * Math.PI * 3 * t);
      var ux = up[0] * Math.cos(wv) - up[1] * Math.sin(wv), uy = up[0] * Math.sin(wv) + up[1] * Math.cos(wv);
      free = [D.lerp(hand[0], sh[0] + ux * 60 * k, st.wave), D.lerp(hand[1], sh[1] + uy * 60 * k, st.wave)];
    }
    F.draw({ hip: [S[0] + 2 * s, S[1] - 4 * s], gy: 0, lean: lean, tilt: st.tilt || 0, f: 1, feet: [p2, p1], hands: [hand, free],
      face: st.face || { eyes: "dot", mouth: "smile", lx: 3 }, skin: st.skin || "#f5efe2", eb: [0, 0] });
    return F.J;
  };

  /* dazed stars orbiting above a point */
  D.Stars = function (parent, n) {
    this.g = [];
    var st = "";
    for (var k = 0; k < 10; k++) { var a = (Math.PI * k) / 5 - Math.PI / 2, rr = k % 2 ? 4.5 : 11; st += (k ? "L" : "M") + P2(Math.cos(a) * rr, Math.sin(a) * rr); }
    for (var i = 0; i < (n || 3); i++) {
      var g = D.el(parent, "g", { opacity: 0 });
      D.el(g, "path", { d: st + "Z", fill: "#ffd166", stroke: INK, "stroke-width": 3.5, "stroke-linejoin": "round" });
      this.g.push(g);
    }
  };
  D.Stars.prototype.render = function (t, x, y, on, rx) {
    for (var i = 0; i < this.g.length; i++) {
      if (!on) { this.g[i].setAttribute("opacity", 0); continue; }
      var a = 2 * Math.PI * (1.1 * t + i / this.g.length);
      this.g[i].setAttribute("transform", D.tf(x + Math.cos(a) * (rx || 34), y + Math.sin(a) * (rx || 34) * 0.32, a * 57.3, 0.85 + 0.25 * Math.sin(a)));
      this.g[i].setAttribute("opacity", on.toFixed(3));
    }
  };

  /* sound arcs ")))" from a point in direction ang (deg) */
  D.Arcs = function (parent, n) {
    this.a = [];
    for (var i = 0; i < (n || 3); i++) this.a.push(D.el(parent, "path", { d: "M-10,-26Q14,0 -10,26", fill: "none", stroke: INK, "stroke-width": 6, "stroke-linecap": "round", opacity: 0 }));
  };
  D.Arcs.prototype.render = function (t, x, y, ang, on) {
    for (var i = 0; i < this.a.length; i++) {
      var u = D.life(t, 0, 0.5, i / this.a.length).u;
      this.a[i].setAttribute("transform", "translate(" + P2(x, y) + ") rotate(" + D.r1(ang) + ") translate(" + D.r1(10 + 70 * u) + ",0) scale(" + (0.55 + 0.9 * u).toFixed(3) + ")");
      this.a[i].setAttribute("opacity", ((on || 0) * Math.sin(Math.PI * u)).toFixed(3));
    }
  };
})();
