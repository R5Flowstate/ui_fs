"""Fit the fs_1v1_lobbyinfo blur widgets to the strip art's silhouette.

The strip is a hexagon: a rect with a pointed tip at each end whose two edges
are NOT perpendicular, so each tip needs two trapezoid widgets (one clip per
slant) beside one uncut centre rect, five widgets total. Fitting happens in
strip-local space (342x43); the emitted geometry and the gate mask are offset
to the strip's pixel-aligned position on the 1920x1080 canvas.

  python fit_lobby_blur.py
"""

import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from verify_blur_from_ruip import clip_poly, raster       # noqa: E402
import verify_blur_from_ruip as vb                        # noqa: E402
import sere_paths

ART = sere_paths.art('gallery', '_full', 'rui__flowstatecustom__strip_bg.png')
OUT = os.path.join(HERE, 'fs_1v1_lobbyinfo_blur_geom.json')
MASK_OUT = sere_paths.art('shipped', '1v1_lobbyinfo_blur_mask.png')

CANVAS_W, CANVAS_H = 1920, 1080
STRIP_X, STRIP_Y = 28.0, 56.0             # pixel-aligned strip origin
W, H = 342, 43


def halfplane_quad(a, s, y0, keep):
    d = np.array([s, 1.0]) / np.hypot(s, 1.0)
    n = keep * np.array([1.0, -s]) / np.hypot(s, 1.0)
    A = np.array([a, y0])
    p0, p1 = A - d * 4000.0, A + d * 4000.0
    off = n * 4000.0
    return [tuple(p0), tuple(p1), tuple(p1 + off), tuple(p0 + off)]


def widget_poly(w):
    x0, y0, x1, y1 = w['rect']
    poly = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if 'line' in w:
        ln = w['line']
        poly = clip_poly(poly, halfplane_quad(ln['a'], ln['s'], ln['y0'], ln['keep']))
    return [(x / W, y / H) for (x, y) in poly]


def spill_of(w, mask):
    cov = raster(widget_poly(w), W, H)
    return int((cov & ~mask).sum()), cov


def tighten(w, mask, inward):
    for _ in range(200):
        if spill_of(w, mask)[0] == 0:
            break
        w['line']['a'] += inward * 0.05
    else:
        raise SystemExit('no zero-spill intercept')
    while True:
        w['line']['a'] -= inward * 0.05
        if spill_of(w, mask)[0] != 0:
            w['line']['a'] += inward * 0.05
            return


def lsq(tr, rows):
    ys = np.array([y + 0.5 for y in rows if y in tr])
    xs = np.array([float(tr[y]) for y in rows if y in tr])
    s, a = np.polyfit(ys, xs, 1)
    return float(a + s * ys.mean()), float(s), float(ys.mean())


def main():
    a = np.array(Image.open(ART).convert('RGBA'))
    assert a.shape[:2] == (H, W), a.shape
    mask = a[..., 3] > 8

    lo = {y: np.where(mask[y])[0][0] for y in range(H) if mask[y].any()}
    hi = {y: np.where(mask[y])[0][-1] + 1 for y in range(H) if mask[y].any()}

    ka = min(lo, key=lo.get)                       # left tip apex row
    kb = max(hi, key=hi.get)                       # right tip apex row
    a_tl, s_tl, y_tl = lsq(lo, range(0, ka - 1))
    a_bl, s_bl, y_bl = lsq(lo, range(ka + 2, H))
    a_tr, s_tr, y_tr = lsq(hi, range(0, kb - 1))
    a_br, s_br, y_br = lsq(hi, range(kb + 2, H))
    ya_l = ((a_bl - s_bl * y_bl) - (a_tl - s_tl * y_tl)) / (s_tl - s_bl)
    ya_r = ((a_br - s_br * y_br) - (a_tr - s_tr * y_tr)) / (s_tr - s_br)
    xL = float(np.ceil(max(lo[0], lo[H - 1])) + 1)
    xR = float(np.floor(min(hi[0], hi[H - 1])) - 1)

    widgets = {
        'tip_tl': {'rect': [0.0, 0.0, xL, ya_l],
                   'line': {'a': a_tl - 0.5, 's': s_tl, 'y0': y_tl, 'keep': 1}},
        'tip_bl': {'rect': [0.0, ya_l, xL, float(H)],
                   'line': {'a': a_bl - 0.5, 's': s_bl, 'y0': y_bl, 'keep': 1}},
        'center': {'rect': [xL, 0.0, xR, float(H)]},
        'tip_tr': {'rect': [xR, 0.0, float(W), ya_r],
                   'line': {'a': a_tr + 0.5, 's': s_tr, 'y0': y_tr, 'keep': -1}},
        'tip_br': {'rect': [xR, ya_r, float(W), float(H)],
                   'line': {'a': a_br + 0.5, 's': s_br, 'y0': y_br, 'keep': -1}},
    }
    for w in widgets.values():
        if 'line' in w:
            tighten(w, mask, +w['line']['keep'])

    # overlap every internal seam so butted neighbours hide each other's AA edge
    def grow(w, i, want):
        step = 0.25 if want > 0 else -0.25
        for _ in range(int(abs(want) / 0.25)):
            w['rect'][i] += step
            if spill_of(w, mask)[0]:
                w['rect'][i] -= step
                return

    grow(widgets['tip_tl'], 2, 2.0)      # x1 into centre
    grow(widgets['tip_tl'], 3, 1.0)      # y1 across the apex seam
    grow(widgets['tip_bl'], 2, 2.0)
    grow(widgets['tip_bl'], 1, -1.0)
    grow(widgets['tip_tr'], 0, -2.0)
    grow(widgets['tip_tr'], 3, 1.0)
    grow(widgets['tip_br'], 0, -2.0)
    grow(widgets['tip_br'], 1, -1.0)

    cov = np.zeros((H, W), dtype=bool)
    for w in widgets.values():
        cov |= raster(widget_poly(w), W, H)
    spill = int((cov & ~mask).sum())
    miss = int((mask & ~cov).sum())
    print('local fit: %d widgets  mask=%d  SPILL=%d  miss=%d (%.3f%%)'
          % (len(widgets), mask.sum(), spill, miss, 100.0 * miss / mask.sum()))
    if spill:
        raise SystemExit('spill in local fit')

    # offset to canvas space
    for w in widgets.values():
        x0, y0, x1, y1 = w['rect']
        w['rect'] = [x0 + STRIP_X, y0 + STRIP_Y, x1 + STRIP_X, y1 + STRIP_Y]
        if 'line' in w:
            w['line']['a'] += STRIP_X
            w['line']['y0'] += STRIP_Y

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'W': CANVAS_W, 'H': CANVAS_H,
                   'strip': [STRIP_X, STRIP_Y, W, H],
                   'widgets': widgets}, f, indent=1)
    print('wrote', OUT)

    # full-canvas mask for the build gate
    full = np.zeros((CANVAS_H, CANVAS_W), dtype=bool)
    full[int(STRIP_Y):int(STRIP_Y) + H, int(STRIP_X):int(STRIP_X) + W] = mask
    rgba = np.zeros((CANVAS_H, CANVAS_W, 4), dtype=np.uint8)
    rgba[full] = (255, 0, 0, 255)
    Image.fromarray(rgba).save(MASK_OUT)
    print('wrote', MASK_OUT)


if __name__ == '__main__':
    main()
