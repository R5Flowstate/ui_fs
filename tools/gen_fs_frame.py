"""Frosted board frames for the Flowstate menus: ui/<name>.rpak.

Each menu hosts its frame as the direct child named ScreenBlur (UpdateMenuBlur
keys on that name to composite the menu above the blur layer), sized to the
board. Blur, dark fill and header band share one 45-degree clip so the
top-right corner is a chamfer; every VGUI control the menu draws over it stays
inside the uncut area.

Usage: py gen_fs_frame.py [name ...]   (no args = every frame in FRAMES)
"""

import json
import math
import os
import sys
import sere_paths

FRAMES = {
    "fs_lb_frame": dict(W=980.0, H=692.0, HEADER_H=58.0),
    "fs_1v1_settings_frame": dict(W=1180.0, H=640.0, HEADER_H=64.0),
}

CHAMFER = 28.0
BAR_W = 4.0


def srgb(hexcode):
    c = [int(hexcode[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
                 for x in c)


GREEN = srgb('3DDA8A')
DARK = srgb('0A0F0C')
BAND = srgb('18211C')


def build(name, W, H, HEADER_H):
    nodes, links = [], []
    _next = [100]
    py = [0]

    def nid():
        _next[0] += 1
        return _next[0]

    def node(**kw):
        if any(n['Id'] == kw['Id'] for n in nodes):
            raise SystemExit('duplicate node Id %r' % kw['Id'])
        nodes.append(kw)
        return kw['Id']

    def link(ln, lp, rn, rp):
        links.append({"LeftNode": ln, "LeftPin": lp, "RightNode": rn, "RightPin": rp})

    def vec2(i, x, y, px, pyy):
        return node(Name="Vector2 Constant", Category="Constant", Min=-2.0, Max=2.0,
                    Value_X=x, Value_Y=y, PosX=px, PosY=pyy, Id=i)

    def size(i, w, h, px, pyy, mx=4000.0):
        return node(Name="Size Constant", Category="Constant", Min=0.0, Max=mx,
                    Value_0=w, Value_1=0.0, Value_2=0.0, Value_3=h, PosX=px, PosY=pyy, Id=i)

    def color(i, c, px, pyy, a=1.0):
        return node(Name="Color Constant", Category="Constant", Value_Red=c[0],
                    Value_Green=c[1], Value_Blue=c[2], Value_Alpha=a, PosX=px, PosY=pyy, Id=i)

    def transform2(cx, cy, w_, h_):
        a, b, c = nid(), nid(), nid()
        vec2(a, round(cx / W, 6), round(cy / H, 6), -1500, py[0])
        size(b, round(w_, 2), round(h_, 2), -1500, py[0] + 60)
        node(Name="Transform 2", Category="Transform", PosX=-1200, PosY=py[0], Id=c)
        link(ROOT, "Out", c, "Parent")
        link(a, "Value", c, "Val_0")
        link(PIVOT, "Value", c, "Val_3")
        link(b, "Value", c, "Size")
        py[0] += 160
        return c, b

    def fill(cx, cy, w_, h_, asset, col, layer, clip=None):
        t, _ = transform2(cx, cy, w_, h_)
        d = nid()
        node(Name="Render Image Image Mask", Category="Image Render", Layer=layer,
             PosX=-900, PosY=py[0] - 160, Id=d)
        link(asset, "Value", d, "Main Asset")
        link(col, "Value", d, "Main Color")
        link(t, "Out", d, "Transform")
        if clip is not None:
            link(clip, "Out", d, "Clip")
        return d

    # ---- root ------------------------------------------------------------
    size(1, W, H, -1800, 0, mx=2000.0)
    PIVOT = vec2(2, 0.5, 0.5, -1800, 80)
    ROOT = node(Name="Transform 2", Category="Transform", PosX=-1500, PosY=-200, Id=3)
    link(2, "Value", 3, "Val_0")
    link(2, "Value", 3, "Val_3")
    link(1, "Value", 3, "Size")

    BLUR = node(Name="Screen Blur", Category="Constant", PosX=-1800, PosY=180, Id=4)
    WHITE = node(Name="Asset Constant", Category="Constant", AssetName="white",
                 PosX=-1800, PosY=260, Id=5)
    C_WHITE = color(6, (1.0, 1.0, 1.0), -1800, 340)
    C_DARK = color(7, DARK, -1800, 420, a=0.84)
    C_BAND = color(8, BAND, -1800, 500, a=0.6)
    C_LINE = color(9, GREEN, -1800, 580, a=0.4)
    C_BAR = color(10, GREEN, -1800, 660)

    # ---- chamfer clip ----------------------------------------------------
    # The cut edge is the line x - y = W - CHAMFER. One 45-degree square whose
    # upper-right edge lies on that line clips everything to the keep side;
    # the square is big enough that its other three edges fall outside.
    L = 2000.0
    foot_t = ((W / 2.0) - (H / 2.0) - (W - CHAMFER)) / 2.0
    foot = (W / 2.0 - foot_t, H / 2.0 + foot_t)
    step = L / (2.0 * math.sqrt(2.0))
    clip_c = (foot[0] - step, foot[1] + step)
    ct, csz = transform2(clip_c[0], clip_c[1], L, L)
    ROT = nid()
    node(Name="Float Constant", Category="Constant", Min=-1.0, Max=1.0, Value=0.125,
         PosX=-1500, PosY=py[0], Id=ROT)
    CLIP = nid()
    node(Name="Rotate Transform", Category="Transform", PosX=-1200, PosY=py[0], Id=CLIP)
    link(ct, "Out", CLIP, "Parent")
    link(csz, "Value", CLIP, "Size")
    link(PIVOT, "Value", CLIP, "Rotation Origin")
    link(ROT, "Value", CLIP, "Rotation")
    py[0] += 160

    # ---- layers ----------------------------------------------------------
    fill(W / 2.0, H / 2.0, W, H, BLUR, C_WHITE, 0, CLIP)
    fill(W / 2.0, H / 2.0, W, H, WHITE, C_DARK, 1, CLIP)
    fill(W / 2.0, HEADER_H / 2.0, W, HEADER_H, WHITE, C_BAND, 2, CLIP)
    fill(W / 2.0, HEADER_H - 0.5, W, 1.0, WHITE, C_LINE, 3)
    fill(BAR_W / 2.0, H / 2.0, BAR_W, H, WHITE, C_BAR, 4)

    out = os.path.join(sere_paths.get('sereRoot'), 'examples', name, name + '.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    doc = {"Nodes": nodes, "Links": links, "RuiWidth": W, "RuiHeight": H}
    with open(out, 'wb') as f:
        f.write(json.dumps(doc, indent=2).encode('utf-8'))
    print('wrote', out, len(nodes), 'nodes', len(links), 'links, canvas %gx%g' % (W, H))
    print('chamfer clip centre', clip_c)


if __name__ == '__main__':
    names = sys.argv[1:] or list(FRAMES)
    for n in names:
        build(n, **FRAMES[n])
