"""Replay the engine's transform + clip math from a shipped .ruip and report
exactly which pixels the RUI will blur.

SERE's preview does not implement `clipXfrmIdx`, so a clipped widget previews as
its full unclipped quad. This reads the packed bytes instead: it walks the
transform stream, applies opcode 4 (OnePin_Rigid) and opcode 1+12 (clone +
rotate) with the same arithmetic the engine uses, intersects each material
widget's quad with its clip transform's quad, and rasterises the result.

  python verify_blur_from_ruip.py <name.ruip> <name.cpp> [mask.png]
"""

import os
import re
import struct
import sys

import numpy as np
from PIL import Image

HDR = '<IHHQffffHHHHHHHHHHH2xIIIIQQQQQQQQQQQIQ'
HDR_NAMES = (
    'magic packageVersion ruiVersion nameOffset elementWidth elementHeight '
    'elementWidthRcp elementHeightRcp defaultValuesSize dataStructSize '
    'styleDescriptorCount unk_A4 renderJobCount argClusterCount argCount '
    'keyframingCount transformDataSize nameSize rpakPtrCount argNamesSize '
    'renderJobSize keyframingSize defaultStringsSize argNamesOffset '
    'argClusterOffset argumentsOffset styleDescriptorOffset renderJobOffset '
    'keyframingOffset transformDataOffset defaultValuesOffset '
    'defaultStringDataOffset rpakPtrOffset defaultStringsDataSize '
    'pointerFixupCount pointerFixupOffset').split()

WIDGET_SIZE = {0: 28, 1: 50, 2: 30, 3: 30, 4: 48, 5: 14}
SS = 4                                   # supersampling factor per axis


class Xf:
    """position + a full 2x2 grad, both in element-normalised units."""

    def __init__(self, pos, grad):
        self.pos = pos                   # (x, y)
        self.grad = grad                 # (xx, xy, yx, yy)

    def corners(self):
        px, py = self.pos
        xx, xy, yx, yy = self.grad
        return [(px, py), (px + xx, py + xy),
                (px + xx + yx, py + xy + yy), (px + yx, py + yy)]


def read_header(b):
    return dict(zip(HDR_NAMES, struct.unpack_from(HDR, b, 0)))


def f32(b, dvo, off):
    return struct.unpack_from('<f', b, dvo + off)[0]


def parse_sizes(cpp_text):
    """transformSize[N] = _mm_set_ps(h,0,0,w);  literals only."""
    out = {}
    for m in re.finditer(r'transformSize\[(\d+)\]\s*=\s*_mm_set_ps\(\s*'
                         r'([-\d.eE]+)\s*,\s*[-\d.eE]+\s*,\s*[-\d.eE]+\s*,\s*([-\d.eE]+)\s*\)',
                         cpp_text):
        out[int(m.group(1))] = (float(m.group(3)), float(m.group(2)))   # (w, h)
    return out


FIELD_SIZE = {'uint32_t': 4, 'int32_t': 4, 'float': 4, 'uint16_t': 2,
              'uint64_t': 8, 'int64_t': 8, 'double': 8}


def parse_blur_offsets(cpp_text):
    """Data offsets of every variable the ruiFunc sets to -4 (SCREENBLUR).

    A material widget's image slots are data offsets, so this is the
    name-free discriminator between a blur plate and an art quad."""
    m = re.search(r'struct\s+\w+\s*\{(.*?)\};', cpp_text, re.S)
    off, offsets = 0, {}
    for decl in m.group(1).split(';'):
        decl = decl.strip()
        if not decl:
            continue
        pm = re.match(r'_BYTE\s+\w+\[(\d+)\]', decl)
        if pm:
            off += int(pm.group(1))
            continue
        dm = re.match(r'(?:const\s+)?(\w+)\s*(\*?)\s*(\w+)', decl)
        size = 8 if dm.group(2) else FIELD_SIZE.get(dm.group(1), 4)
        off = (off + size - 1) & ~(size - 1)
        offsets[dm.group(3)] = off
        off += size
    blur = set()
    for am in re.finditer(r'data->(\w+)\s*=\s*-4\b', cpp_text):
        if am.group(1) in offsets:
            blur.add(offsets[am.group(1)])
    return blur


def build_transforms(b, h, sizes):
    """Walk the transform stream. Returns {index: Xf}."""
    W, H = h['elementWidth'], h['elementHeight']
    dvo = h['defaultValuesOffset']
    to, ts = h['transformDataOffset'], h['transformDataSize']

    # 0,1,2 are engine built-ins; 2 is the identity the graph roots on.
    xf = {0: Xf((0.0, 0.0), (1.0, 0.0, 0.0, 1.0)),
          1: Xf((0.0, 0.0), (1.0, 0.0, 0.0, 1.0)),
          2: Xf((0.0, 0.0), (1.0, 0.0, 0.0, 1.0))}
    nxt = 3
    off = 0
    while off < ts:
        op = b[to + off]
        if op == 4:
            _, cnt, parent, v0x, v0y, v3x, v3y, _pad = struct.unpack_from('<BBHHHHHH', b, to + off)
            idx = nxt
            nxt += 1
            w, hh = sizes.get(idx, (0.0, 0.0))
            grad = (w / W, 0.0, 0.0, hh / H)
            p = xf[parent]
            a0 = (f32(b, dvo, v0x), f32(b, dvo, v0y))
            a3 = (f32(b, dvo, v3x), f32(b, dvo, v3y))
            # pos = parent.pos + parentGrad . val0 - val3 (x) ownGrad
            px = p.pos[0] + a0[0] * p.grad[0] + a0[1] * p.grad[2] - a3[0] * grad[0]
            py = p.pos[1] + a0[0] * p.grad[1] + a0[1] * p.grad[3] - a3[1] * grad[3]
            xf[idx] = Xf((px, py), grad)
            off += 14
        elif op == 1:
            (_, cnt, src, op2, cnt2, tgt, rotOff,
             cx_off, cy_off) = struct.unpack_from('<BBHBBHHHH', b, to + off)
            if op2 != 12:
                raise SystemExit('clone at +%d not followed by opcode 12' % off)
            idx = nxt
            nxt += 1
            if idx != tgt:
                raise SystemExit('clone target %d but next index is %d' % (tgt, idx))
            src_xf = xf[src]
            g = src_xf.grad
            rot = f32(b, dvo, rotOff)
            cx, cy = f32(b, dvo, cx_off), f32(b, dvo, cy_off)
            import math
            c, s = math.cos(2 * math.pi * rot), math.sin(2 * math.pi * rot)
            ar = (-(H / W), W / H, -(H / W), W / H)
            sh = (g[1], g[0], g[3], g[2])           # shuffle(grad, 177)
            g2 = tuple(sh[i] * s * ar[i] + c * g[i] for i in range(4))
            px = src_xf.pos[0] + cx * (g[0] - g2[0]) + cy * (g[2] - g2[2])
            py = src_xf.pos[1] + cx * (g[1] - g2[1]) + cy * (g[3] - g2[3])
            xf[idx] = Xf((px, py), g2)
            off += 14
        else:
            raise SystemExit('unhandled transform opcode %d at +%d' % (op, off))
    return xf


def clip_poly(poly, quad):
    """Sutherland-Hodgman against a convex quad given in order."""
    def inside(p, a, bb):
        return (bb[0] - a[0]) * (p[1] - a[1]) - (bb[1] - a[1]) * (p[0] - a[0]) >= 0

    def isect(p, q, a, bb):
        x1, y1, x2, y2 = p[0], p[1], q[0], q[1]
        x3, y3, x4, y4 = a[0], a[1], bb[0], bb[1]
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(den) < 1e-12:
            return q
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

    # normalise winding so `inside` means the quad's interior
    area = 0.0
    for i in range(len(quad)):
        x1, y1 = quad[i]
        x2, y2 = quad[(i + 1) % len(quad)]
        area += x1 * y2 - x2 * y1
    q = quad if area >= 0 else quad[::-1]

    out = list(poly)
    for i in range(len(q)):
        a, bb = q[i], q[(i + 1) % len(q)]
        if not out:
            break
        src, out = out, []
        for j in range(len(src)):
            cur, prv = src[j], src[j - 1]
            if inside(cur, a, bb):
                if not inside(prv, a, bb):
                    out.append(isect(prv, cur, a, bb))
                out.append(cur)
            elif inside(prv, a, bb):
                out.append(isect(prv, cur, a, bb))
    return out


def raster(poly, W, H):
    """Coverage mask at SS x SS supersampling, collapsed to a boolean per pixel."""
    m = np.zeros((H * SS, W * SS), dtype=bool)
    if len(poly) < 3:
        return np.zeros((H, W), dtype=bool)
    px = np.array([p[0] * W * SS for p in poly])
    py = np.array([p[1] * H * SS for p in poly])
    y0 = max(0, int(np.floor(py.min())))
    y1 = min(H * SS, int(np.ceil(py.max())) + 1)
    for y in range(y0, y1):
        yc = y + 0.5
        xs = []
        n = len(poly)
        for i in range(n):
            ax, ay = px[i], py[i]
            bx, by = px[(i + 1) % n], py[(i + 1) % n]
            if (ay <= yc < by) or (by <= yc < ay):
                xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            a = max(0, int(np.ceil(xs[i] - 0.5)))
            bb = min(W * SS, int(np.floor(xs[i + 1] - 0.5)) + 1)
            if bb > a:
                m[y, a:bb] = True
    return m.reshape(H, SS, W, SS).any(axis=(1, 3))


def main():
    ruip = sys.argv[1]
    cpp = sys.argv[2]
    maskPath = sys.argv[3] if len(sys.argv) > 3 else None

    b = open(ruip, 'rb').read()
    h = read_header(b)
    W, H = int(round(h['elementWidth'])), int(round(h['elementHeight']))
    cpp_text = open(cpp, encoding='utf-8', errors='replace').read()
    sizes = parse_sizes(cpp_text)
    blurOffsets = parse_blur_offsets(cpp_text)
    xf = build_transforms(b, h, sizes)
    print('element %dx%d  transforms=%d' % (W, H, len(xf)))

    ro, rs = h['renderJobOffset'], h['renderJobSize']
    off = 0
    cov = np.zeros((H, W), dtype=bool)
    plates = 0
    while off < rs:
        t = struct.unpack_from('<H', b, ro + off)[0]
        if t not in WIDGET_SIZE:
            break
        if t == 1:
            _, _df, xi, ci, i0, _i1 = struct.unpack_from('<6H', b, ro + off)
            poly = xf[xi].corners()
            if ci:
                poly = clip_poly(poly, xf[ci].corners())
            pts = [(round(p[0] * W, 1), round(p[1] * H, 1)) for p in poly]
            isBlur = i0 in blurOffsets
            print('  material xfrm=%-3d clip=%-3d %-4s %s'
                  % (xi, ci, 'BLUR' if isBlur else 'ART', pts))
            if isBlur:
                cov |= raster(poly, W, H)
                plates += 1
        off += WIDGET_SIZE[t]

    print('\nblur plates rasterised: %d   pixels blurred: %d' % (plates, cov.sum()))
    out = os.path.join(os.path.dirname(os.path.abspath(ruip)), 'blur_actual.png')
    if maskPath:
        M = np.array(Image.open(maskPath).convert('RGBA'))
        mask = (M[..., 3] > 127) & (M[..., 0] > 127)
        spill = int((cov & ~mask).sum())
        miss = int((mask & ~cov).sum())
        print('mask=%d  covered=%d  SPILL=%d (%.3f%%)  miss=%d (%.3f%%)'
              % (mask.sum(), int((cov & mask).sum()), spill, 100.0 * spill / mask.sum(),
                 miss, 100.0 * miss / mask.sum()))
        rgb = np.dstack([(cov & ~mask) * 255, (cov & mask) * 180, (mask & ~cov) * 255])
        Image.fromarray(rgb.astype(np.uint8)).save(out)
        print('overlay -> %s   (red = spill, green = correct, blue = missed)' % out)
        return 1 if spill else 0
    Image.fromarray((cov * 255).astype(np.uint8)).save(out)
    print('coverage -> %s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
