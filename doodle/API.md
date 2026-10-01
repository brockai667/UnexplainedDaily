# Doodle screenplay API (cheat sheet)

One episode = ONE file `screenplay.yaml` in a folder `queue/<NNN-name>/` next to a `meta.json` (title, description, tags, music_credit).
No JavaScript. Worked examples (read both): `examples/carancas2/screenplay.yaml` (35 s, 5 scenes) and
`examples/koepenick/screenplay.yaml` (custom shapes, carrying, follow cam). `examples/devon1855/` is a longer 45 s one.
`factory.py` takes the alphabetically first `queue/` folder, so number the folders (`004-...`).

```
python doodle/factory.py --dry-run [--name 001-devon1855] [--keep]   # whole chain on a queue folder: copies it to work/NAME, sp.py, qa.py -> out/NAME.mp4, NAME_sheet.jpg, NAME.txt
python doodle/sp.py doodle/work/NAME     # voice (cached in work/) + compile -> index.html. Errors: "SCREENPLAY ERROR: scene 'x' beat #7 (who do) ..."
python doodle/qa.py doodle/work/NAME     # check + render + -16 LUFS + analysis -> renders/NAME.mp4 + renders/NAME_sheet.jpg, exit 1 on FAIL
npx --yes hyperframes@0.8.77 snapshot doodle/work/NAME -o snap --at 1,2.5,4 --no-end --describe false   # quick stills
```
Run sp.py / qa.py on a COPY in `work/` (factory.py --keep leaves one), not on `queue/` or `examples/`: they write index.html, assets/, work/, renders/ into the folder.
Workflow: sentences -> for each sentence decide what must be SEEN (every named thing is on screen) -> scenes -> compile ->
snapshots at key words -> fix -> `qa.py` -> look at the sheet. `qa.py --no-render` re-analyses the last render.

## Canvas & layout
720 x 1280, y down. World (drawings) is visible above y≈926; below it are the captions (auto, 3 words, gold = spoken word).
Gold overlays sit at the top (y 100-260). Ground lines usually y 850-905; characters stand on `gy`.
Character size: `k: 1` ≈ 240 px feet-to-head-top (head radius 30k). Villagers 0.95-1.2, heroes 1.4-1.6, background 0.8.
Colours: red orange yellow teal purple blue green brown white cream navy pink gray black, or "#rrggbb" (quote it).

## File skeleton
```yaml
title: My story
voice: {voice: am_michael, speed: 1.10, pause: 0.30}   # Kokoro; pause = gap between sentences
tail: 1.5                                              # seconds after the last word
music: sneaky_snitch.mp3                               # optional, ducked under the voice; bare name = assets/music/<name>, or an absolute path
loop: {at: "s10.end+0.55", dur: 1.3}                   # optional seamless loop: last page lifts, scene 1 frame 0 returns
sentences: {s1: "First sentence.", s2: "Second one."}  # ~10 sentences ≈ 35 s; keys are free (s1..sN)
gold: [...]            # big yellow words, see Gold
styles: {...}          # named styles for shapes
shapes: {...}          # custom drawings, see Shapes
scenes: [...]          # see Scenes
sfx: [{at: "word:bang", name: boom, gain: 0.8}]         # extra sound cues (optional)
```

## Scenes
```yaml
- id: street                  # unique
  sents: [s2, s3]             # consecutive sentences; the scene runs from its first sentence to the next scene
  in: {type: slide}           # cut (default) | slide | drop | flash | whip | zoom
  camera: {zoom: 1.2, at: [400, 700], screen: [360, 640]}   # world point `at` shown at screen point, magnified
  fixed_strokes: true         # lines keep their width when the camera zooms far in on small things
  set: [...]                  # backgrounds + world objects (drawn first, in list order)
  props: [...]                # effects / objects (drawn after the set)
  cast: [...]                 # characters (kind char is default; later = in front)
  beats: [...]                # {at, who, do, ...}
```
whip/zoom: `in: {type: whip, target: [x,y] | "id:anchor", from: [x,y]}` - the previous scene's camera rushes into `target`
(its world), the new scene starts tight on its world point `from` and settles to its `camera`. whip adds speed lines + flash.
Every object: `id` (needed for beats), `kind`, `layer: back|mid|top`, `hidden: true` (starts invisible), `scale`, `rot`, `opacity`.
Objects exist only in their scene: re-declare a person in each scene (same look = same person).

## Timing ("at", "until")
`2.5` seconds | `"word:blast"` start of word (scene sentences first, then all; case/punctuation ignored) | `"word:blast.end"` |
`"word:s10/poison"` word in sentence s10 | `"word:the#2"` 2nd occurrence | `"s3"` / `"s3.end"` sentence | `"scene"` / `"scene.end"` |
`"prev"` start of the PREVIOUS BEAT IN THE LIST, `"prev.end"` its start+dur | `"hit:wave@house"` / `"hit:wave@x=250"` when shockwave
`wave` reaches that object's x (its `go` beat must come earlier in the list) | any of these `+0.3` / `-0.1`. QUOTE anything with ":".
Beat keys: `at, who, do`, then `dur` (s) or `until` (a time; for continuous verbs = end time), `ease` (power2.inOut, back.out(1.8),
sine.inOut, power2.in, none...), `sfx: name | [name, gain] | none`.
`repeat: {every: 0.35, n: 8 | until: "word:stop", cycle: [{name: hands_up}, {name: stand}]}` on ANY beat = that beat
again every `every` s (`n` times, or until that time); `cycle` (or `alt: {...}` = 2-step) overrides keys per step: alternating
poses, `dx`/`dy` for hopping, `to` for rotate. Use it for dancing, hammering, waving, stomping, running-in-place instead of
writing the same beat 30 times. Example: `{at: "word:dance", who: frau, do: pose, name: hands_up, dur: 0.16, repeat: {every: 0.32,
until: "scene.end-0.3", cycle: [{name: hands_up}, {name: kneel}, {name: stand}, {name: point}]}}`.

## Generic verbs (every object)
move {to: [x,y] (positioned kinds*) | dx, dy, dur} · path {points: [[x,y]..] (4 pts = curve), dur, acc 0..1, orient: true} ·
rotate {to: deg} · scale {to} · fade {to: 0..1} · show · hide · pop {to} · stamp {from: 2.3, r0: -12, r1: -3} (+thud) ·
shake {amp, dur} · jiggle {amp: 0.1, freq, decay} · bob / rock / pulse {amp, freq, until} · spin {speed: deg/s, until} ·
attach {to: id, anchor: hand, offset: [dx,dy]} (carried from now) · detach (stays where let go).
*positioned kinds (own x,y): house building tent sign text rock shape flask bigface crater. Carry-able: shape text rock flask sign tent house
(also `on: id, anchor: hand, offset: [dx,dy]` in the object = carried from the start). Anchors below.

## Kinds (set / props)
| kind | params | verbs / anchors |
|---|---|---|
| sky | clouds [[x,y,w],..], drift px/s | - |
| mountains | base (foot y), peaks [[x,y],..], color, snow: false | - |
| hill | x0, x1, top, base, peak (summit x), color | anchors center, top |
| ground | y, x0, x1, gaps [[a,b]], tufts [x,..] | - |
| house | x, y (bottom centre), w, h, wall, roof | center, top |
| building | x, y, w, h, wall, windows n, type clinic (red cross) or plain | shatter {window: i or all, stagger} (+glass) |
| tent | x, y, scale (white medical tent) | center, door |
| sign | x, y, scale, text ("!"), color | hammer {hits: 3, every: 0.2} (drops in, thuds) |
| tape | x0, x1, y, height, sag (police tape on posts) | unroll {dur}; center/left/right |
| line | points, style ink/gold/dash, width, color, arrows start/end/both | draw_line {dur}; center/start/end |
| text | x, y, text, size, style ink/gold, color | - |
| rock | x, y, size, glow: false | center, top (glowing cracks) |
| shape | shape (custom or check cross question exclaim arrow_down), x, y | parts `id.group` take generic verbs |
| rider | x (start), gy, k, bike (colour), hat [c1,c2] | ride {from, to, dur/until}, wobble, tip_over, wave, face {name} |
| meteor | path (4 points, curve), smoke (puffs 24), s0, s1 | fly {dur/until, acc} (+whoosh) |
| impact | at [x,y], clip (hide below y), floor | explode (+boom): flash, fireball, debris |
| shockwave | at [x,y] (ground centre), speed px/s | go (ring arcs + dust; enables `hit:`) |
| crater | x, y, scale, level empty/full | water_level {to: full, dur}, boil, splash; center, rock, surface |
| underground | top, water (y), pit [x, w], crack [[x,y],..], layers [3 colours] | center, water, surface |
| thought | on: char | pop, grow {to: 1.35}, darken, bolt (dark worry cloud) |
| flask | x, y, label, color, fumes: false | bubbling bottle; center, top |
| bigface | x, y, r, hat [c1,c2] | bump (close-up trembling face, sweat) |
| emitter | emitter: type (below) | see Emitters |

## Characters (cast)
`{id: vil, x: 300, gy: 900, k: 1.3, facing: l, hat: [orange, cream], face: scared}` Looks (combine freely):
`hat: [c1,c2]` Andean chullo · `cap: navy` peaked uniform cap · `nurse: true` · `hair: "#6d4c41"` spiky hair · `coat: true|colour`,
`coat_len: 14..40` · `glasses` · `stetho` · `mirror` (doctor) · `skin` · `hidden: true`. One body type (stick figure).
Verbs: enter {from: left/right/x, to: x, dur/until, stride, lift} · walk_to {to, dur} · exit {to: left/right, dur} · turn {facing: l/r}
· pose {name, dur} · point {target} · look {target} · face {name} · color {to: green/normal/colour} · hold {prop: megaphone /
magnifier / thermometer} · drop · startle · jump_back {dist} · step_back {dist} · kneel_down {target} · bend_over · sit_down ·
sniff · tremble {amount, until} · nod / sway / heave {until} · get_sick {style: belly/sit/sway/none, face, spiral: false, sweat: false}
· dizzy {until} (spiral) · sweat {until}. Targets: "up", "down", "ground", [x,y], "id" or "id:anchor".
Poses: stand point look_up lean_in hands_up cover (hands to face) head (hands on head) cheeks belly kneel sit shrug scratch think
(chin) shade (eyes) reach megaphone stop ("halt" hand) cower clasp help (leans to someone) recoil wave (waving) arms_crossed.
Faces: ok happy wow shout sick dizzy scared think flat curious worried sad angry sleep.
Anchors: head top hand mouth prop feet center. The whole group also takes generic verbs (fade, hide, shake...).

## Emitters (`kind: emitter`)
Source: `at: [x,y]` or `on: id` (+ `anchor:`, default head). Beats: `emit {until}` / `start` / `stop` (continuous), `burst` (one volley).
- steam smoke fumes dust bubbles: n, r [min,max], color, period (life s), rise, drift, spread, s0, s1, opacity,
  path [[x,y],..] (particles travel along it), prewarm: true
- sparks drops shards (burst): n, spread, dir, vmin, vmax, life, floor (px below source where they vanish), size, color,
  `shape: name` = any custom shape as particle (coins, leaves...)
- stars (dazed, on:) · sweat (on:) · spiral (on:) · sound (")))" from on:'s prop, dir deg) · birds (at, n, dir -1/1; burst)
- particles: box [x,y,w,h], n, r, color, label ("As"), label_every; beat pulse (floating labelled molecules)

## Camera & fx
`who: cam` - push / pull / pan / tilt / frame / move {zoom, target: [x,y] | "id:anchor", screen: [x,y] (default [360,640]),
dur | until, ease}: all the same framing move (name it by intent) · whip (fast push) · reset · shake {amp, dur} ·
follow {target: id, anchor, dur, zoom}. `who: fx` - flash {peak: 0.7} · lines {dur, target: [x,y]} (speed lines).

## Gold (yellow key words, auto thud / ticks)
`{word: "2007", label: "2007", kind: stamp, top: 128, size: 120, until: "word:X", stamp: {from: 2.4, r0: -14, r1: -4}}`
kind stamp (slams in at the word) | counter (counts from `from` 0 to the label number, `dur`) | measure (gold double arrow +
label IN the world: `points: [[x,y],[x,y]], label_at: [x,y], size`). `label: "POISON|OR PANIC?"` "|" = new line.
`until` default = scene end - 0.45. Changing number: end the old one before the new one stamps (until: "word:two-0.1").

## Shapes (custom drawings)
```yaml
styles: {cloth: {fill: "#3d5a80", width: 6}, brass: {fill: yellow, width: 4}}
shapes:
  cashbox:                                   # coordinates relative to the object's x,y
    - {rect: [-40, -18, 80, 46, 6], fill: "#6d6875"}                 # x, y, w, h, corner radius
    - {group: lid, pivot: [-40, -18], items: [{rect: [-42, -32, 84, 16, 5], fill: gray}]}   # animatable part
    - {circle: [0, 6, 6], style: brass}
```
Items: `path: "M0,0 Q10,-20 20,0"` (SVG d) · `poly: [[x,y],..]` (closed) · `line: [[x,y],..]` (open) · `circle: [cx,cy,r]` ·
`ellipse: [cx,cy,rx,ry]` · `rect: [x,y,w,h,r]` · `text: [x,y,"str"]` + size · `group: name, pivot: [x,y], items: [...]` ·
`use: other, at: [x,y], scale`. Attributes: fill (default none), stroke (default black), width (default 7), opacity, dash "8 6", style.
Use: `{id: box, kind: shape, shape: cashbox, x: 360, y: 860}`; beats on parts: `{at: "word:cash", who: box.lid, do: rotate, to: -55}`.
Draw in the house style: thick black outline (width 5-7), flat fills, round joins; 1 unit = 1 px at camera zoom 1.

## Sound
Names: whoosh boom thud glass bubbles hiss clatter tick. Automatic: explode→boom, shatter→glass, tip_over→clatter, stamp→thud,
hammer→thud per hit, fly→whoosh, boil→bubbles, gold stamp/counter, slide/drop/whip/zoom transitions. Add `sfx:` to any beat.

## Gotchas
- `prev` follows LIST order: inserting a beat between a chain re-targets `prev`. Use `word:` anchors for important hits.
- `hit:` needs the shockwave's `go` beat above it in the list.
- `move to:` on non-positioned kinds (sky, ground, line, tape, rider, emitter...) shifts the whole drawing - use dx/dy.
- Keep the story readable: <= 5 moving things per shot; background people first in `cast`, main actor last.
- Clouds/objects near y 100-260 can sit under gold words - move them or the camera.
- Continuous verbs (tremble, emit, spin...) run until `until` or the scene end; one-shot verbs use `dur`.
- Names are validated (kinds, verbs, poses, faces, emitters, sfx, shapes, `on:` targets); the error lists the valid ones.
