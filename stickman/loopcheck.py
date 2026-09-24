# -*- coding: utf-8 -*-
"""Kontrola neviditelnej slucky: porovna posledny frame s prvym.

    python loopcheck.py out\\<slug>.mp4 [out\\<slug>_loop.jpg]

Spravna slucka NEMA nulovy rozdiel - posledny frame ma byt presne jeden krok PRED prvym.
Referencia "prvy vs druhy frame" ukazuje, ako velky je bezny posun o jeden frame.
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.abspath(__file__))


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(f"{cmd}\n{r.stdout[-800:]}\n{r.stderr[-800:]}")
    return r.stdout


def main(final, sheet=None):
    work = os.path.join(ROOT, "work")
    os.makedirs(work, exist_ok=True)
    nfr = int(sh(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                  "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", final]).strip())
    paths = {}
    for name, idx in (("first", 0), ("last", nfr - 1), ("second", 1)):
        paths[name] = os.path.join(work, f"loop_{name}.png")
        sh(["ffmpeg", "-v", "error", "-y", "-i", final, "-vf", f"select=eq(n\\,{idx})", "-frames:v", "1", paths[name]])
    A = Image.open(paths["first"]).convert("RGB")
    B = Image.open(paths["last"]).convert("RGB")
    C = Image.open(paths["second"]).convert("RGB")

    def stats(x, y, label):
        d = np.asarray(ImageChops.difference(x, y), dtype=np.float32)
        print(f"{label:30s} mean|d|={d.mean():6.2f}/255   max={d.max():3.0f}   "
              f"pixels>16: {(d.max(axis=2) > 16).mean() * 100:5.2f}%")
        return d.mean()

    print(f"frames={nfr}")
    seam = stats(B, A, "last  vs first  (sev)")
    ref = stats(A, C, "first vs second (referencia)")
    print("VERDIKT:", "slucka sedi" if seam <= ref * 1.8 + 1.0 else "SEV JE VIDIET - preverit")
    if sheet:
        w, h = A.size
        s = Image.new("RGB", (w * 2 + 12, h), "white")
        s.paste(B, (0, 0))
        s.paste(A, (w + 12, 0))
        s.save(sheet, quality=92)
        print("sheet:", sheet, "= [posledny frame | prvy frame]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
