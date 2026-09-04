"""Fit the fs_1v1_vs blur widgets exactly to the painted mask.

Each plate is seven widgets, each an axis-aligned rect cut by one rotated clip
quad, so every mask edge segment gets its true slope instead of one shared
compromise: tab (45-degree chamfer diamond), arrow tip above the outer apex,
outer edge below it, and the inner V edge as three segments around its notch.

Spill is a constraint, not a cost: every slanted line starts at its least
squares fit and is nudged toward the plate interior until the widget rasters
zero pixels outside the mask, scored with the same supersampled rasteriser the
.ruip verifier uses so the two can never disagree.

  python fit_blur_exact.py [--report-only]
"""

import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from verify_blur_from_ruip import clip_poly, raster            # noqa: E402
import sere_paths

MASK = sere_paths.art('shipped', '1v1_bg_blur_mask_cafe.png')
OUT = os.path.join(HERE, 'fs_1v1_vs_blur_geom.json')

W, H = 1005, 138
TAB_Y1 = 34
BODY_Y0, BODY_Y1 = 34, 138


def load_mask():
    m = np.array(Image.open(MASK).convert('RGBA'))
    return (m[..., 3] > 127) & (m[..., 0] > 127)


def trace(mask, rows, lo, hi, side):
    """Per-row first ('lo') or last+1 ('hi') set column in [lo, hi)."""
    out = {}
    for y in rows:
        xs = np.where(mask[y, lo:hi])[0]
        if len(xs):
            out[y] = lo + (xs[0] if side == 'lo' else xs[-1] + 1)
    return out


def lsq(tr, rows):
    ys = np.array([y + 0.5 for y in rows if y in tr])
    xs = np.array([tr[y] for y in rows if y in tr], dtype=float)
    s, a = np.polyfit(ys, xs, 1)
    return float(a + s * ys.mean()), float(s), float(ys.mean())


def halfplane_quad(a, s, y0, keep):
    """A huge quad whose one edge is the line x = a + s*(y - y0)."""
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
    if 'diamond' in w:
        dm = w['diamond']
        poly = clip_poly(poly, halfplane_quad(dm['c1'], -1.0, 0.0, 1))   # x >= c1 - y
        poly = clip_poly(poly, halfplane_quad(dm['c2'], 1.0, 0.0, -1))   # x <= c2 + y
    return [(x / W, y / H) for (x, y) in poly]


def spill_of(w, mask):
    cov = raster(widget_poly(w), W, H)
    return int((cov & ~mask).sum()), cov


EDGE = {'x0': 0, 'y0': 1, 'x1': 2, 'y1': 3}


def grow(w, key, want, mask):
    """Extend one rect edge across an internal seam so butted neighbours
    overlap, because each widget's AA edge then lands inside the other's interior.
    Gated: stops growing the moment the widget would spill outside the mask."""
    i = EDGE[key]
    step = 0.25 if want > 0 else -0.25
    for _ in range(int(abs(want) / 0.25)):
        w['rect'][i] += step
        if spill_of(w, mask)[0]:
            w['rect'][i] -= step
            return


def tighten(w, key, field, mask, inward):
    """Nudge one line intercept until this widget rasters zero spill, then
    relax back out while it stays zero."""
    for _ in range(200):
        if spill_of(w, mask)[0] == 0:
            break
        w[key][field] += inward * 0.05
    else:
        raise SystemExit('no zero-spill intercept for %s' % key)
    while True:
        w[key][field] -= inward * 0.05
        if spill_of(w, mask)[0] != 0:
            w[key][field] += inward * 0.05
            return


def fit_half(mask):
    """Fit the LEFT plate of `mask` (columns [0, W//2))."""
    mid = W // 2
    side = {}

    # tab: flat rows give the rect, rows 0..3 give the 45-degree chamfers
    flo = trace(mask, range(4, TAB_Y1), 0, mid, 'lo')
    fhi = trace(mask, range(4, TAB_Y1), 0, mid, 'hi')
    tx0 = float(min(flo.values()))
    tx1 = float(max(fhi.values()))
    clo = trace(mask, range(0, 4), 0, mid, 'lo')
    chi = trace(mask, range(0, 4), 0, mid, 'hi')
    c1 = float(np.mean([x + y for y, x in clo.items()]))            # x + y = c1
    c2 = float(np.mean([(x - 1) - y for y, x in chi.items()]))      # x - y = c2
    tab = {'rect': [tx0, 0.0, tx1, float(TAB_Y1)],
           'diamond': {'c1': c1, 'c2': c2}}
    tighten(tab, 'diamond', 'c1', mask, +1)
    tighten(tab, 'diamond', 'c2', mask, -1)
    side['tab'] = tab

    # outer edge: arrow tip above the apex, straight edge below it
    body = range(BODY_Y0, BODY_Y1)
    olo = trace(mask, body, 0, mid, 'lo')
    apex = min(olo, key=olo.get)
    a_oa, s_oa, y_oa = lsq(olo, range(BODY_Y0, apex - 1))
    a_ob, s_ob, y_ob = lsq(olo, range(apex + 2, BODY_Y1))
    ya = ((a_ob - s_ob * y_ob) - (a_oa - s_oa * y_oa)) / (s_oa - s_ob)
    xcut = float(np.ceil(a_ob + s_ob * (BODY_Y1 - y_ob)) + 2)
    arrow = {'rect': [0.0, float(BODY_Y0), xcut, ya],
             'line': {'a': a_oa - 0.5, 's': s_oa, 'y0': y_oa, 'keep': 1}}
    out = {'rect': [0.0, ya, xcut, float(BODY_Y1)],
           'line': {'a': a_ob - 0.5, 's': s_ob, 'y0': y_ob, 'keep': 1}}
    tighten(arrow, 'line', 'a', mask, +1)
    tighten(out, 'line', 'a', mask, +1)
    side['arrow'], side['out'] = arrow, out

    # inner V edge: rising, notch back, rising again
    ilo = trace(mask, body, 0, mid, 'hi')
    # the notch is the one sustained decreasing run in an otherwise rising edge
    runs = []
    y = 50
    while y < 110:
        if ilo[y + 1] < ilo[y]:
            y0n = y
            while y < 110 and ilo[y + 1] <= ilo[y]:
                y += 1
            runs.append((ilo[y0n] - ilo[y], y0n, y))
        y += 1
    _, k1, k2 = max(runs)
    a_ia, s_ia, y_ia = lsq(ilo, range(BODY_Y0, k1 - 1))
    a_nk, s_nk, y_nk = lsq(ilo, range(k1 + 1, k2))
    a_ib, s_ib, y_ib = lsq(ilo, range(k2 + 2, BODY_Y1))
    yk1 = ((a_nk - s_nk * y_nk) - (a_ia - s_ia * y_ia)) / (s_ia - s_nk)
    yk2 = ((a_ib - s_ib * y_ib) - (a_nk - s_nk * y_nk)) / (s_nk - s_ib)
    xin = float(np.floor(min(ilo[y] for y in range(k2 - 1, k2 + 3))) - 1)
    in_l = {'rect': [xcut, float(BODY_Y0), xin, float(BODY_Y1)],
            'line': {'a': a_ia + 0.5, 's': s_ia, 'y0': y_ia, 'keep': -1}}
    in_ur = {'rect': [xin, float(BODY_Y0), float(np.ceil(ilo[k1]) + 2), yk1],
             'line': {'a': a_ia + 0.5, 's': s_ia, 'y0': y_ia, 'keep': -1}}
    notch = {'rect': [xin, yk1, float(np.ceil(ilo[k1]) + 2), yk2],
             'line': {'a': a_nk + 0.5, 's': s_nk, 'y0': y_nk, 'keep': -1}}
    in_b = {'rect': [xin, yk2, float(np.ceil(ilo[BODY_Y1 - 1]) + 2), float(BODY_Y1)],
            'line': {'a': a_ib + 0.5, 's': s_ib, 'y0': y_ib, 'keep': -1}}
    for wdg in (in_l, in_ur, notch, in_b):
        tighten(wdg, 'line', 'a', mask, -1)
    # in_l and in_ur share the ia line; keep the tighter of the two fits
    a_shared = min(in_l['line']['a'], in_ur['line']['a'])
    in_l['line']['a'] = in_ur['line']['a'] = a_shared
    side['in_l'], side['in_ur'] = in_l, in_ur
    side['notch'], side['in_b'] = notch, in_b

    # overlap every internal seam (tab/body, arrow/out, outer/inner, notch)
    for name, edges in {'tab': [('y1', 1.5)],
                        'arrow': [('x1', 2.0), ('y1', 1.5)],
                        'out': [('x1', 2.0), ('y0', -1.5)],
                        'in_l': [('x0', -2.0)],
                        'in_ur': [('x0', -2.0), ('y1', 1.5)],
                        'notch': [('x0', -2.0), ('y0', -1.5), ('y1', 1.5)],
                        'in_b': [('x0', -2.0), ('y0', -1.5)]}.items():
        for key, want in edges:
            grow(side[name], key, want, mask)
    return side


def mirror_side(side):
    out = {}
    for name, w in side.items():
        m = {k: v for k, v in w.items()}
        x0, y0, x1, y1 = w['rect']
        m['rect'] = [W - x1, y0, W - x0, y1]
        if 'line' in w:
            ln = w['line']
            m['line'] = {'a': W - ln['a'], 's': -ln['s'],
                         'y0': ln['y0'], 'keep': -ln['keep']}
        if 'diamond' in w:
            dm = w['diamond']
            m['diamond'] = {'c1': W - dm['c2'], 'c2': W - dm['c1']}
        out[name] = m
    return out


def score(sides, mask, label):
    cov = np.zeros((H, W), dtype=bool)
    for side in sides.values():
        for w in side.values():
            cov |= raster(widget_poly(w), W, H)
    spill = int((cov & ~mask).sum())
    miss = int((mask & ~cov).sum())
    n = sum(len(s) for s in sides.values())
    print('%s: %d widgets  mask=%d covered=%d  SPILL=%d  miss=%d (%.3f%%)'
          % (label, n, mask.sum(), int((cov & mask).sum()), spill,
             miss, 100.0 * miss / mask.sum()))
    rgb = np.dstack([(cov & ~mask) * 255, (cov & mask) * 180, (mask & ~cov) * 255])
    Image.fromarray(rgb.astype(np.uint8)).save(os.path.join(HERE, 'geom_check.png'))
    return spill, miss


def main():
    mask = load_mask()
    left = fit_half(mask)
    right_flip = fit_half(np.fliplr(mask))
    sides = {'left': left, 'right': mirror_side(right_flip)}
    spill, miss = score(sides, mask, 'fit')
    if spill:
        raise SystemExit('fit left %d px of spill' % spill)
    if '--report-only' not in sys.argv:
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump({'version': 2, 'W': W, 'H': H, 'sides': sides}, f, indent=1)
        print('wrote', OUT)


if __name__ == '__main__':
    main()
