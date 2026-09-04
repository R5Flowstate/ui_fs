"""Fit the fs_1v1_vs blur quads to the painted mask under a hard spill budget.

Spill, meaning blur outside the painted shape, is the failure that shows on screen,
so it is a CONSTRAINT here, not a term in a cost function. The search maximises
coverage subject to spill <= the budget, which defaults to zero.

Each half is fitted independently. Mirroring one half onto the other looks
harmless and is not: the mask is symmetric about pixel index 1004, but a
half-open interval [a,b) mirrors to [1005-b, 1005-a), and getting that +1 wrong
put a one-pixel column of blur outside the right badge tab on every row.

  python fit_blur_geom.py [--spill N]
"""

import json
import os
import sys

import numpy as np
from PIL import Image
import sere_paths

HERE = os.path.dirname(os.path.abspath(__file__))
MASK = sere_paths.art('shipped', '1v1_bg_blur_mask_cafe.png')
OUT = os.path.join(HERE, 'fs_1v1_vs_blur_geom.json')

BODY_Y0, BODY_Y1 = 34, 138               # body band, rows [Y0, Y1)
TAB_Y1 = 34


def edges(mask, x0, x1):
    """Per-row [first, last] set pixel inside the column window, or (-1,-1)."""
    H = mask.shape[0]
    lo = np.full(H, -1)
    hi = np.full(H, -1)
    sub = mask[:, x0:x1]
    for y in range(H):
        xs = np.where(sub[y])[0]
        if len(xs):
            lo[y], hi[y] = xs[0] + x0, xs[-1] + x0
    return lo, hi


# Scoring must match verify_blur_from_ruip.py exactly, or "spill 0" here and
# "spill 14" there are both right and neither is actionable. That verifier
# rasterises at SS x SS and counts a pixel as touched if ANY subsample centre
# lands inside, so a pixel the quad only clips a corner off still counts.
SS = 4
LO_PAD = 1.0 - 0.5 / SS                  # ceil(left - LO_PAD) = first touched
HI_PAD = 0.5 / SS                        # ceil(right - HI_PAD) - 1 = last touched


def band_score(rows, mL, mR, L0, slope, wd, y0):
    """Per-row spill/coverage for a parallelogram band, subsample-conservative."""
    # A slanted edge sweeps across x WITHIN a row, so sampling the row centre
    # under-reports by up to `slope` pixels and leaves single-pixel overshoots.
    # Take the outer extent over the row's full height for spill, the inner
    # extent for coverage.
    e0 = L0 + slope * (rows - y0)
    e1 = L0 + slope * (rows + 1.0 - y0)
    outL, inL = np.minimum(e0, e1), np.maximum(e0, e1)
    a = np.ceil(outL - LO_PAD).astype(int)
    bb = (np.ceil(inL + wd - HI_PAD) - 1).astype(int)
    valid = bb >= a
    spill = np.where(valid, np.maximum(0, mL - a) + np.maximum(0, bb - mR), 0)
    ca = np.ceil(inL - LO_PAD).astype(int)
    cb = (np.ceil(outL + wd - HI_PAD) - 1).astype(int)
    cover = np.where(cb >= ca,
                     np.maximum(0, np.minimum(cb, mR) - np.maximum(ca, mL) + 1), 0)
    return int(spill.sum()), int(cover.sum())


def rect_score(rows, mL, mR, x0, x1):
    a = int(np.ceil(x0 - LO_PAD))
    bb = int(np.ceil(x1 - HI_PAD)) - 1
    if bb < a:
        return 0, 0
    spill = np.maximum(0, mL - a) + np.maximum(0, bb - mR)
    cover = np.maximum(0, np.minimum(bb, mR) - np.maximum(a, mL) + 1)
    return int(spill.sum()), int(cover.sum())


def fit_half(mask, x0, x1, budget):
    mL, mR = edges(mask, x0, x1)
    rows = np.arange(BODY_Y0, BODY_Y1)
    bL, bR = mL[rows], mR[rows]

    best = None
    for slope in np.concatenate([np.arange(-0.72, -0.40, 0.005), np.arange(0.40, 0.72, 0.005)]):
        off = slope * (rows + 0.5 - BODY_Y0)
        for wd in np.arange(440.0, 380.0, -0.5):
            loBound = (bL - off).max()
            hiBound = (bR + 1.0 - wd - off).min()
            if loBound > hiBound + 1.5:
                continue
            for L0 in np.arange(loBound - 1.5, hiBound + 1.5, 0.25):
                sp, cov = band_score(rows, bL, bR, L0, slope, wd, BODY_Y0)
                if sp > budget:
                    continue
                if best is None or cov > best[0]:
                    best = (cov, sp, float(slope), float(L0), float(wd))
    if best is None:
        raise SystemExit('no feasible band at spill budget %d' % budget)
    cov, sp, slope, L0, wd = best
    print('  body  slope=%.3f  x@y%d=%.2f  width=%.1f   spill=%d cover=%d'
          % (slope, BODY_Y0, L0, wd, sp, cov))

    trows = np.arange(0, TAB_Y1)
    tL, tR = mL[trows], mR[trows]
    bestT = None
    t0, t1 = float(tL[tL >= 0].min()), float(tR.max())
    for tx0 in np.arange(t0 - 4.0, t0 + 8.0, 0.5):
        for tx1 in np.arange(t1 - 6.0, t1 + 6.0, 0.5):
            sp2, cov2 = rect_score(trows, tL, tR, tx0, tx1)
            if sp2 > budget:
                continue
            if bestT is None or cov2 > bestT[0]:
                bestT = (cov2, sp2, float(tx0), float(tx1))
    if bestT is None:
        raise SystemExit('no feasible tab at spill budget %d' % budget)
    cov2, sp2, tx0, tx1 = bestT
    print('  tab   x=[%.1f,%.1f) y=[0,%d)             spill=%d cover=%d'
          % (tx0, tx1, TAB_Y1, sp2, cov2))
    return dict(slope=slope, x0=L0, width=wd, tabX0=tx0, tabX1=tx1)


def main():
    budget = 0
    if '--spill' in sys.argv:
        budget = int(sys.argv[sys.argv.index('--spill') + 1])

    M = np.array(Image.open(MASK).convert('RGBA'))
    H, W = M.shape[:2]
    mask = (M[..., 3] > 127) & (M[..., 0] > 127)
    cols = mask.any(axis=0)
    split = W // 2
    while cols[split]:
        split += 1
    print('mask %dx%d set=%d  halves split at x=%d  spill budget=%d'
          % (W, H, mask.sum(), split, budget))

    print('left half:')
    left = fit_half(mask, 0, split, budget)
    print('right half:')
    right = fit_half(mask, split, W, budget)

    out = dict(W=float(W), H=float(H), bodyY0=float(BODY_Y0), bodyY1=float(BODY_Y1),
               tabY1=float(TAB_Y1), left=left, right=right)
    json.dump(out, open(OUT, 'w'), indent=2)
    print('\nwrote', OUT)


if __name__ == '__main__':
    main()
