"""Turn a painted blur mask into the fewest axis-aligned rectangles that cover it.

The engine cannot rotate, shear or image-mask a screen-blur quad, so a blur
region is always a union of axis-aligned rectangles. This reads a mask (any
solid colour where blur belongs, transparent or black elsewhere) and greedily
peels off the largest all-set rectangle until the shape is covered.

  python mask_to_rects.py <mask.png> [--coverage 0.995] [--max 64] [--out rects.json]
"""

import argparse
import json
import os

import numpy as np
from PIL import Image


def load_mask(path):
    im = Image.open(path).convert('RGBA')
    a = np.asarray(im)
    alpha, rgb = a[..., 3], a[..., :3].astype(int)
    # painted = visible and not black
    return (alpha > 127) & (rgb.max(2) > 40), im.size


def largest_rect(mask):
    """Largest all-True axis-aligned rectangle. Histogram scan, O(w*h)."""
    h, w = mask.shape
    heights = np.zeros(w, dtype=np.int32)
    best = (0, 0, 0, 0, 0)                      # area, x, y, w, h
    for y in range(h):
        heights = np.where(mask[y], heights + 1, 0)
        stack = []                              # (startIndex, height)
        for x in range(w + 1):
            cur = heights[x] if x < w else 0
            start = x
            while stack and stack[-1][1] >= cur:
                s, ht = stack.pop()
                area = ht * (x - s)
                if area > best[0]:
                    best = (area, s, y - ht + 1, x - s, ht)
                start = s
            if cur:
                stack.append((start, cur))
    return best


def decompose_exact(mask):
    """Pixel-exact cover: one rect per maximal run of identical row-spans."""
    h, w = mask.shape
    rects, prev, run_y0 = [], None, 0
    for y in range(h + 1):
        spans = []
        if y < h:
            xs = np.flatnonzero(mask[y])
            if len(xs):
                s = xs[0]
                for i in range(1, len(xs)):
                    if xs[i] != xs[i - 1] + 1:
                        spans.append((int(s), int(xs[i - 1]) + 1))
                        s = xs[i]
                spans.append((int(s), int(xs[-1]) + 1))
        if prev is not None and spans != prev:
            for x0, x1 in prev:
                rects.append({"x": x0, "y": run_y0, "w": x1 - x0, "h": y - run_y0})
            run_y0 = y
        elif prev is None:
            run_y0 = y
        prev = spans
    return rects


def grow_interior_edges(rects, mask, overlap=1):
    """Overlap neighbours so anti-aliased edges cannot leave a seam.

    Each quad fades its own edges, and two abutting fades do not sum back to
    opaque. One pixel of overlap is often not enough: a RUI drawn into a smaller
    panel is downscaled, so an authored pixel is less than a screen pixel while
    the fade is not. Grow a pixel at a time, and only while every pixel beyond
    the edge is still inside the mask, so the outer silhouette stays exactly
    where it was painted, however large `overlap` gets.
    """
    h, w = mask.shape
    out = []
    for r in rects:
        x0, y0 = r["x"], r["y"]
        x1, y1 = x0 + r["w"], y0 + r["h"]
        for _ in range(overlap):
            if x0 > 0 and mask[y0:y1, x0 - 1].all():
                x0 -= 1
            if x1 < w and mask[y0:y1, x1].all():
                x1 += 1
            if y0 > 0 and mask[y0 - 1, x0:x1].all():
                y0 -= 1
            if y1 < h and mask[y1, x0:x1].all():
                y1 += 1
        out.append({"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0})
    return out


def decompose(mask, coverage=0.995, max_rects=64):
    total = int(mask.sum())
    if not total:
        raise SystemExit('mask is empty, nothing painted')
    remaining = mask.copy()
    rects, covered = [], 0
    while covered / total < coverage and len(rects) < max_rects:
        area, x, y, w, h = largest_rect(remaining)
        if area <= 0:
            break
        rects.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})
        remaining[y:y + h, x:x + w] = False
        covered += area
    return rects, covered, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mask')
    ap.add_argument('--coverage', type=float, default=0.995)
    ap.add_argument('--max', type=int, default=64)
    ap.add_argument('--exact', action='store_true',
                    help='pixel-exact cover, interior edges overlapped')
    ap.add_argument('--overlap', type=int, default=3,
                    help='px each rect grows into its neighbours (never outside the mask)')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    mask, (w, h) = load_mask(args.mask)
    total = int(mask.sum())
    if args.exact:
        rects = grow_interior_edges(decompose_exact(mask), mask, args.overlap)
    else:
        rects, _, total = decompose(mask, args.coverage, args.max)

    cover = np.zeros_like(mask)
    for r in rects:
        cover[r["y"]:r["y"] + r["h"], r["x"]:r["x"] + r["w"]] = True
    missed = int((mask & ~cover).sum())
    spill = int((cover & ~mask).sum())

    print('mask      %dx%d, %d painted px' % (w, h, total))
    print('rects     %d' % len(rects))
    print('coverage  %.3f%%  (%d painted px uncovered)'
          % (100.0 * (total - missed) / total, missed))
    print('spill     %d px outside the mask' % spill)

    out = args.out or os.path.splitext(args.mask)[0] + '_rects.json'
    doc = {"maskWidth": w, "maskHeight": h, "source": os.path.basename(args.mask),
           "rects": rects}
    with open(out, 'wb') as f:
        f.write(json.dumps(doc, indent=2).encode('utf-8'))
    print('wrote     %s' % out)


if __name__ == '__main__':
    main()
