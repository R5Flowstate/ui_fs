import json
import os

nodes, links = [], []
_id = [0]


def nid():
    _id[0] += 1
    return _id[0]


def node(name, category, x, y, **kw):
    n = {"Name": name, "Category": category, "PosX": float(x), "PosY": float(y), "Id": nid()}
    n.update(kw)
    nodes.append(n)
    return n["Id"]


def link(ln, lp, rn, rp):
    links.append({"LeftNode": ln, "LeftPin": lp, "RightNode": rn, "RightPin": rp})


def fconst(v, x, y, mn=0.0, mx=2000.0):
    return node("Float Constant", "Constant", x, y, Min=mn, Max=mx, Value=float(v))


def v2const(vx, vy, x, y):
    return node("Vector2 Constant", "Constant", x, y, Min=-2.0, Max=2.0,
                Value_X=float(vx), Value_Y=float(vy))


def sizeconst(w, h, x, y):
    return node("Size Constant", "Constant", x, y, Min=0.0, Max=2000.0,
                Value_0=float(w), Value_1=0.0, Value_2=0.0, Value_3=float(h))


def color(r, g, b, a, x, y):
    return node("Color Constant", "Constant", x, y,
                Value_Red=float(r), Value_Green=float(g), Value_Blue=float(b), Value_Alpha=float(a))


CANVAS_W, CANVAS_H = 1920.0, 1080.0
SLOTS = 64
DOT = 8.0
ORIGIN = 10.0
RING = 12.0
PLATE_X, PLATE_Y, PLATE_W, PLATE_H = 24.0, 24.0, 360.0, 196.0

anchor_c = v2const(0.5, 0.5, -1900, -800)
anchor_tl = v2const(0.0, 0.0, -1900, -720)
white = node("Asset Constant", "Constant", -1900, -640, AssetName="white")

c_plate = color(0.04, 0.05, 0.06, 0.82, -1900, -560)
c_ref = color(0.32, 0.55, 1.0, 1.0, -1900, -480)
c_live = color(1.0, 1.0, 1.0, 1.0, -1900, -400)
c_origin = color(0.18, 0.92, 0.42, 1.0, -1900, -320)
c_ring = color(1.0, 1.0, 1.0, 0.70, -1900, -240)
c_title = color(0.96, 0.97, 0.98, 1.0, -1900, -160)
c_pat = color(0.72, 0.76, 0.80, 1.0, -1900, -80)
c_score = color(1.0, 0.47, 0.125, 1.0, -1900, 0)
c_hint = color(0.82, 0.84, 0.88, 1.0, -1900, 80)

sz_title = fconst(18.0, -1700, -160, 0, 200)
sz_pat = fconst(16.0, -1700, -80, 0, 200)
sz_score = fconst(36.0, -1700, 0, 0, 200)
sz_hint = fconst(14.0, -1700, 80, 0, 200)

style_title = node("Text Style", "Text Render", -1450, -160, FontName="TitanfallBold")
link(sz_title, "Value", style_title, "Size")
link(c_title, "Value", style_title, "mainColor")

style_pat = node("Text Style", "Text Render", -1450, -80, FontName="TitanfallBold")
link(sz_pat, "Value", style_pat, "Size")
link(c_pat, "Value", style_pat, "mainColor")

style_score = node("Text Style", "Text Render", -1450, 0, FontName="TitanfallBold")
link(sz_score, "Value", style_score, "Size")
link(c_score, "Value", style_score, "mainColor")

style_hint = node("Text Style", "Text Render", -1450, 80, FontName="TitanfallBold")
link(sz_hint, "Value", style_hint, "Size")
link(c_hint, "Value", style_hint, "mainColor")

sz_dot = sizeconst(DOT, DOT, -1700, 160)
sz_origin = sizeconst(ORIGIN, ORIGIN, -1700, 240)
sz_ring = sizeconst(RING, RING, -1700, 320)
sz_plate = sizeconst(PLATE_W, PLATE_H, -1700, 400)

node("Float Arg", "Argument", -1900, 480, ArgName="refCount")
node("Float Arg", "Argument", -1900, 540, ArgName="liveCount")
node("Float Arg", "Argument", -1900, 600, ArgName="cursor")
node("Float Arg", "Argument", -1900, 660, ArgName="score")
node("Float Arg", "Argument", -1900, 720, ArgName="adsFrac")

plate_pos = v2const(round(PLATE_X / CANVAS_W, 6), round(PLATE_Y / CANVAS_H, 6), -1200, -40)
plate_tr = node("Transform 2", "Transform", -1050, -40)
link(plate_pos, "Value", plate_tr, "Val_0")
link(anchor_tl, "Value", plate_tr, "Val_3")
link(sz_plate, "Value", plate_tr, "Size")
plate = node("Render Image Image Mask", "Image Render", -900, -40, Layer=1)
link(white, "Value", plate, "Main Asset")
link(c_plate, "Value", plate, "Main Color")
link(plate_tr, "Out", plate, "Transform")


def text(arg_name, style_id, x, y, layer=8):
    txt = node("String Arg", "Argument", -700, _y[0], ArgName=arg_name)
    ts = node("Text Size", "Text Render", -550, _y[0])
    link(txt, "Value", ts, "text")
    link(style_id, "Style", ts, "Style_0")
    pos = v2const(round(x / CANVAS_W, 6), round(y / CANVAS_H, 6), -700, _y[0] + 40)
    tr = node("Transform 2", "Transform", -400, _y[0])
    link(pos, "Value", tr, "Val_0")
    link(anchor_tl, "Value", tr, "Val_3")
    link(ts, "Size", tr, "Size")
    tn = node("Text Render", "Text Render", -250, _y[0], Layer=layer)
    link(ts, "Text Data", tn, "Data")
    link(tr, "Out", tn, "Parent")
    _y[0] += 140


_y = [80]
text("title", style_title, 40.0, 36.0)
text("patternName", style_pat, 40.0, 64.0)
text("scoreText", style_score, 40.0, 100.0)
text("hint", style_hint, 40.0, 152.0)


def mark(arg_name, color_id, size_id, layer, col, row):
    px = -200 + col * 220
    py = 80 + row * 90
    pos = node("Vector2 Arg", "Argument", px, py, ArgName=arg_name)
    tr = node("Transform 2", "Transform", px + 80, py)
    link(pos, "Value", tr, "Val_0")
    link(anchor_c, "Value", tr, "Val_3")
    link(size_id, "Value", tr, "Size")
    img = node("Render Image Image Mask", "Image Render", px + 160, py, Layer=layer)
    link(white, "Value", img, "Main Asset")
    link(color_id, "Value", img, "Main Color")
    link(tr, "Out", img, "Transform")


def fixed_mark(nx, ny, color_id, size_id, layer, px, py):
    pos = v2const(nx, ny, px, py)
    tr = node("Transform 2", "Transform", px + 80, py)
    link(pos, "Value", tr, "Val_0")
    link(anchor_c, "Value", tr, "Val_3")
    link(size_id, "Value", tr, "Size")
    img = node("Render Image Image Mask", "Image Render", px + 160, py, Layer=layer)
    link(white, "Value", img, "Main Asset")
    link(color_id, "Value", img, "Main Color")
    link(tr, "Out", img, "Transform")


fixed_mark(0.5, 0.5, c_origin, sz_origin, 4, -200, 20)
mark("cursorPos", c_ring, sz_ring, 6, 0, 0)

for i in range(SLOTS):
    mark("ref%02d" % i, c_ref, sz_dot, 2, i % 8, 1 + i // 8)

for i in range(SLOTS):
    mark("live%02d" % i, c_live, sz_dot, 3, i % 8, 10 + i // 8)

out = {"Nodes": nodes, "Links": links,
       "RuiWidth": CANVAS_W, "RuiHeight": CANVAS_H}
dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fs_viewkick_practice.json")
with open(dest, "wb") as f:
    f.write(json.dumps(out, indent=2).encode("utf-8"))
print("nodes=%d links=%d dest=%s" % (len(nodes), len(links), dest))
