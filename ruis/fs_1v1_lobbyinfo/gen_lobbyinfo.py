import json
import math
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

def strarg(argname, x, y):
    return node("String Arg", "Argument", x, y, ArgName=argname)

# ---------------------------------------------------------------- layout ----
# One frosted plate: header band, then the queue readout that only exists while
# the player is searching. Height is the state: 43 idle, 97 searching, 121
# with the input-lock grace countdown running.
CANVAS_W, CANVAS_H = 1920.0, 1080.0
PLATE_X, PLATE_Y, PLATE_W = 28.0, 56.0, 342.0
HEADER_H, BODY_BASE, GRACE_H = 43.0, 58.0, 28.0
CHAMFER, RAIL_W = 14.0, 3.0
PAD_L, PAD_R = 16.0, 14.0

TEXT_X = PLATE_X + PAD_L
RIGHT_X = PLATE_X + PLATE_W - PAD_R
BODY_Y = PLATE_Y + HEADER_H

LOGO = 40.0
ICON_H = 20.0
LOCK_W = 16.0
DEV_W = 26.0
ROW_Y = BODY_Y + 40.0
BAR_W, BAR_H = 312.0, 3.0

# solid fill: the plate silhouette comes from the widget quad and its clip,
# never from the art
BG_ASSET = "white"
CARD_ASSET = "rui/flowstate_custom/queue_card"

def _srgb(hexcode, a=1.0):
    c = [int(hexcode[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return (lin[0], lin[1], lin[2], a)


COL_HEADER_TX = (1.0, 1.0, 1.0, 1.0)
COL_COUNT_TX  = _srgb('3DDA8A')
COL_ROW_TX    = (0.88, 0.90, 0.94, 1.0)
COL_DIM_TX    = (0.62, 0.65, 0.70, 1.0)
COL_ORANGE    = (1.0, 0.47, 0.125, 1.0)
COL_DARK      = _srgb('0A0F0C', 0.84)
COL_BAND      = _srgb('18211C', 0.60)

# shared style feeds
sz_header = fconst(20.0, -1900, -600, 0, 200)
sz_count  = fconst(22.0, -1900, -520, 0, 200)
sz_row    = fconst(18.0, -1900, -440, 0, 200)
sz_filter = fconst(16.0, -1900, -360, 0, 200)
sz_small  = fconst(13.0, -1900, -280, 0, 200)

c_header_tx = color(*COL_HEADER_TX, -1900, -200)
c_count_tx  = color(*COL_COUNT_TX,  -1900, -120)
c_row_tx    = color(*COL_ROW_TX,    -1900, -40)
c_dim_tx    = color(*COL_DIM_TX,    -1900, 40)


def style(size_id, color_id, y):
    s = node("Text Style", "Text Render", -1650, y, FontName="ArameMono")
    link(size_id, "Value", s, "Size")
    link(color_id, "Value", s, "mainColor")
    return s


style_header    = style(sz_header, c_header_tx, -600)
style_count     = style(sz_count,  c_count_tx,  -450)
style_row       = style(sz_row,    c_row_tx,    -300)
style_filter    = style(sz_filter, c_count_tx,  -150)
style_filter_dim = style(sz_filter, c_dim_tx,   0)
style_small     = style(sz_small,  c_dim_tx,    150)

bg_asset   = node("Asset Constant", "Constant", -1900, 240, AssetName=BG_ASSET)
blur_asset = node("Screen Blur", "Constant", -1900, 320)

c_white     = color(1.0, 1.0, 1.0, 1.0, -1900, 400)
c_backing   = color(*COL_DARK, -1900, 440)
c_band      = color(*COL_BAND, -1900, 480)
c_divider   = color(COL_COUNT_TX[0], COL_COUNT_TX[1], COL_COUNT_TX[2], 0.4, -1900, 560)
c_rail      = color(*COL_COUNT_TX, -1900, 640)
c_orange    = color(*COL_ORANGE, -1900, 720)
c_dim_icon  = color(*COL_DIM_TX, -1900, 800)
c_bar_track = color(1.0, 1.0, 1.0, 0.15, -1900, 880)

anchor_tl = v2const(0.0, 0.0, -1900, 960)
anchor_ml = v2const(0.0, 0.5, -1900, 1040)
anchor_mr = v2const(1.0, 0.5, -1900, 1120)
anchor_c  = v2const(0.5, 0.5, -1900, 1200)

_y = [1400]

# ------------------------------------------------------------------ args ----
queue_vis  = node("Float Arg", "Argument", -1900, 1280, ArgName="queueVis")
grace_vis  = node("Float Arg", "Argument", -1900, 1330, ArgName="graceVis")
locked_vis = node("Float Arg", "Argument", -1900, 1380, ArgName="lockedVis")
open_vis   = node("Float Arg", "Argument", -1900, 1430, ArgName="openVis")
grace_end  = node("Gametime Arg", "Argument", -1900, 1480, ArgName="graceEnd")
grace_dur  = node("Float Arg", "Argument", -1900, 1530, ArgName="graceDur")

# Image Arg, not Asset Constant: SERE nulls asset names missing from its local
# registry, and its picker rewrites them to "missing" on export.
logo_arg = node("Image Arg", "Argument", -1900, 1580, ArgName="logoImage")
card_arg = node("Image Arg", "Argument", -1900, 1630, ArgName="cardImage")
lock_closed_arg = node("Image Arg", "Argument", -1900, 1680, ArgName="lockClosedImage")
lock_open_arg = node("Image Arg", "Argument", -1900, 1730, ArgName="lockOpenImage")
input_arg = node("Image Arg", "Argument", -1900, 1780, ArgName="queueInputIcon")
mouse_arg = node("Image Arg", "Argument", -1900, 1830, ArgName="queueMouseIcon")
pad_arg = node("Image Arg", "Argument", -1900, 1880, ArgName="queuePadIcon")

# --------------------------------------------------------------- helpers ----
def blur_tr(cx, cy, w, h):
    pos = v2const(round(cx / CANVAS_W, 6), round(cy / CANVAS_H, 6), -1900, _y[0])
    size = sizeconst(round(w, 2), round(h, 2), -1900, _y[0] + 50)
    tr = node("Transform 2", "Transform", -1650, _y[0])
    link(pos, "Value", tr, "Val_0")
    link(anchor_c, "Value", tr, "Val_3")
    link(size, "Value", tr, "Size")
    _y[0] += 150
    return tr, size


def line_clip(ln):
    """Half-plane clip quad along y = s*(x-a) + y0, keeping one side."""
    s, keep = ln['s'], ln['keep']
    r = math.hypot(s, 1.0)
    d = (s / r, 1.0 / r)
    n = (keep / r, -keep * s / r)
    L, T = 1900.0, 900.0
    cx = ln['a'] + n[0] * T / 2.0
    cy = ln['y0'] + n[1] * T / 2.0
    u = (CANVAS_H / 2.0 - cy) / d[1]
    tr, size = blur_tr(cx + d[0] * u, cy + d[1] * u, L, T)
    rot = node("Float Constant", "Constant", -1900, _y[0], Min=-1.0, Max=1.0,
               Value=round(math.atan2(1.0, s) / (2.0 * math.pi), 7))
    rc = node("Rotate Transform", "Transform", -1400, _y[0])
    link(tr, "Out", rc, "Parent")
    link(size, "Value", rc, "Size")
    link(anchor_c, "Value", rc, "Rotation Origin")
    link(rot, "Value", rc, "Rotation")
    _y[0] += 150
    return rc


def dyn_size(w, h_pin=None, h_const=None, w_gate=None, w_scale=None):
    """Merge Size whose width is w * w_gate [* w_scale]; height fixed or piped.
    A packed RUI cannot hide one widget, so gating collapses the width to 0."""
    wq = fconst(w, -1900, _y[0], 0, 2000)
    src = wq
    src_pin = "Value"
    if w_gate is not None:
        mul = node("Multiply", "Math", -1650, _y[0])
        link(w_gate, "Value", mul, "A")
        link(wq, "Value", mul, "B")
        src, src_pin = mul, "Res"
    if w_scale is not None:
        mul2 = node("Multiply", "Math", -1500, _y[0])
        link(src, src_pin, mul2, "A")
        link(w_scale, "Res", mul2, "B")
        src, src_pin = mul2, "Res"
    mrg = node("Merge Size", "Split Merge", -1350, _y[0])
    link(src, src_pin, mrg, "X")
    if h_pin is not None:
        link(h_pin, "Res", mrg, "W")
    else:
        hq = fconst(h_const, -1900, _y[0] + 50, 0, 2000)
        link(hq, "Value", mrg, "W")
    _y[0] += 150
    return mrg


def image(asset_id, color_id, x, y, anchor, size_mrg=None, size_const=None,
          layer=2, clip=None):
    pos = v2const(round(x / CANVAS_W, 6), round(y / CANVAS_H, 6), -1200, _y[0])
    tr = node("Transform 2", "Transform", -1050, _y[0])
    link(pos, "Value", tr, "Val_0")
    link(anchor, "Value", tr, "Val_3")
    if size_mrg is not None:
        link(size_mrg, "Out", tr, "Size")
    else:
        link(size_const, "Value", tr, "Size")
    img = node("Render Image Image Mask", "Image Render", -900, _y[0], Layer=layer)
    link(asset_id, "Value", img, "Main Asset")
    link(color_id, "Value", img, "Main Color")
    link(tr, "Out", img, "Transform")
    if clip is not None:
        link(clip, "Out", img, "Clip")
    _y[0] += 150
    return tr


def text(arg_name, style_id, x, y, anchor, layer=4):
    txt = strarg(arg_name, -700, _y[0])
    ts = node("Text Size", "Text Render", -550, _y[0])
    link(txt, "Value", ts, "text")
    link(style_id, "Style", ts, "Style_0")
    pos = v2const(round(x / CANVAS_W, 6), round(y / CANVAS_H, 6), -700, _y[0] + 50)
    tr = node("Transform 2", "Transform", -400, _y[0])
    link(pos, "Value", tr, "Val_0")
    link(anchor, "Value", tr, "Val_3")
    link(ts, "Size", tr, "Size")
    tn = node("Text Render", "Text Render", -250, _y[0], Layer=layer)
    link(ts, "Text Data", tn, "Data")
    link(tr, "Out", tn, "Parent")
    _y[0] += 150


# ----------------------------------------------------------------- plate ----
# height = 43 + queueVis*54 + graceVis*24
h_head = fconst(HEADER_H, -1900, _y[0], 0, 200)
h_body = fconst(BODY_BASE, -1900, _y[0] + 50, 0, 200)
h_grace = fconst(GRACE_H, -1900, _y[0] + 100, 0, 200)
mul_body = node("Multiply", "Math", -1650, _y[0])
link(queue_vis, "Value", mul_body, "A")
link(h_body, "Value", mul_body, "B")
mul_grace = node("Multiply", "Math", -1650, _y[0] + 100)
link(grace_vis, "Value", mul_grace, "A")
link(h_grace, "Value", mul_grace, "B")
add1 = node("Add", "Math", -1500, _y[0])
link(mul_body, "Res", add1, "A")
link(h_head, "Value", add1, "B")
plate_h = node("Add", "Math", -1350, _y[0])
link(add1, "Res", plate_h, "A")
link(mul_grace, "Res", plate_h, "B")
_y[0] += 200

# top-right chamfer, shared by the blur backing, the body art and the header band
chamfer = line_clip({'s': 1.0, 'keep': -1.0,
                     'a': PLATE_X + PLATE_W - CHAMFER, 'y0': PLATE_Y})

plate_size = dyn_size(PLATE_W, h_pin=plate_h)
image(blur_asset, c_white, PLATE_X, PLATE_Y, anchor_tl,
      size_mrg=plate_size, layer=0, clip=chamfer)
# solid backing: the card art does not reach the plate edge, and bare blur there
# reads as a bright rim
image(bg_asset, c_backing, PLATE_X, PLATE_Y, anchor_tl,
      size_mrg=plate_size, layer=1, clip=chamfer)
image(card_arg, c_white, PLATE_X, PLATE_Y, anchor_tl,
      size_mrg=plate_size, layer=2, clip=chamfer)

# header band: same plate, darkened so the cap still reads as a cap
image(bg_asset, c_band, PLATE_X, PLATE_Y, anchor_tl,
      size_const=sizeconst(PLATE_W, HEADER_H, -1350, _y[0]), layer=3, clip=chamfer)

# cyan rail down the full left edge
rail_size = dyn_size(RAIL_W, h_pin=plate_h)
image(bg_asset, c_rail, PLATE_X, PLATE_Y, anchor_tl, size_mrg=rail_size, layer=3)

# hairline under the header, only while there is a body below it
image(bg_asset, c_divider, PLATE_X + RAIL_W, PLATE_Y + HEADER_H, anchor_tl,
      size_mrg=dyn_size(PLATE_W - RAIL_W, h_const=1.0, w_gate=queue_vis), layer=3)

# ---------------------------------------------------------------- header ----
image(logo_arg, c_white, PLATE_X + RAIL_W + 6.0 + LOGO / 2.0, PLATE_Y + HEADER_H / 2.0,
      anchor_c, size_const=sizeconst(LOGO, LOGO, -1350, _y[0]), layer=4)
text("headerText", style_header, PLATE_X + RAIL_W + 52.0, PLATE_Y + HEADER_H / 2.0, anchor_ml)
text("countText", style_count, RIGHT_X, PLATE_Y + HEADER_H / 2.0, anchor_mr)

# ------------------------------------------------------------ queue block ----
text("queueTitle", style_row, TEXT_X, BODY_Y + 17.0, anchor_ml)

# input filter: padlock + the device(s) the queue accepts. Locked and open are
# separate widget sets because a widget's colour is fixed at pack time.
image(lock_closed_arg, c_orange, TEXT_X, ROW_Y, anchor_ml,
      size_mrg=dyn_size(LOCK_W, h_const=ICON_H, w_gate=locked_vis), layer=4)
image(input_arg, c_rail, TEXT_X + 22.0, ROW_Y, anchor_ml,
      size_mrg=dyn_size(DEV_W, h_const=ICON_H, w_gate=locked_vis), layer=4)

image(lock_open_arg, c_dim_icon, TEXT_X, ROW_Y, anchor_ml,
      size_mrg=dyn_size(LOCK_W, h_const=ICON_H, w_gate=open_vis), layer=4)
image(mouse_arg, c_dim_icon, TEXT_X + 22.0, ROW_Y, anchor_ml,
      size_mrg=dyn_size(DEV_W, h_const=ICON_H, w_gate=open_vis), layer=4)
image(pad_arg, c_dim_icon, TEXT_X + 52.0, ROW_Y, anchor_ml,
      size_mrg=dyn_size(DEV_W, h_const=ICON_H, w_gate=open_vis), layer=4)

text("queueFilter", style_filter, RIGHT_X, ROW_Y, anchor_mr)
text("queueFilterAny", style_filter_dim, RIGHT_X, ROW_Y, anchor_mr)
text("graceText", style_small, TEXT_X, BODY_Y + 64.0, anchor_ml)

# remaining fraction, clamped 0..1: (graceEnd - now) / graceDur
now = node("Current Time", "Globals", -1900, _y[0])
sub = node("Subtract", "Math", -1750, _y[0])
link(grace_end, "Value", sub, "A")
link(now, "Time", sub, "B")
zero = fconst(0.0, -1750, _y[0] + 50, -1.0, 1.0)
one = fconst(1.0, -1600, _y[0] + 50, 0.0, 1.0)
# Divide hard-errors the whole instance on 0, and graceDur defaults to 0.
dur_ok = node("Greater Than", "Conditionals", -1750, _y[0] + 100)
link(grace_dur, "Value", dur_ok, "A")
link(zero, "Value", dur_ok, "B")
safe_dur = node("Conditional (Float)", "Conditionals", -1650, _y[0] + 100)
link(dur_ok, "Res", safe_dur, "A")
link(grace_dur, "Value", safe_dur, "B")
link(one, "Value", safe_dur, "C")
div = node("Divide", "Math", -1600, _y[0])
link(sub, "Res", div, "A")
link(safe_dur, "Res", div, "B")
gt0 = node("Greater Than", "Conditionals", -1450, _y[0])
link(div, "Res", gt0, "A")
link(zero, "Value", gt0, "B")
pos_frac = node("Conditional (Float)", "Conditionals", -1300, _y[0])
link(gt0, "Res", pos_frac, "A")
link(div, "Res", pos_frac, "B")
link(zero, "Value", pos_frac, "C")
gt1 = node("Greater Than", "Conditionals", -1150, _y[0])
link(pos_frac, "Res", gt1, "A")
link(one, "Value", gt1, "B")
frac = node("Conditional (Float)", "Conditionals", -1000, _y[0])
link(gt1, "Res", frac, "A")
link(one, "Value", frac, "B")
link(pos_frac, "Res", frac, "C")
_y[0] += 200

BAR_Y = PLATE_Y + HEADER_H + BODY_BASE + GRACE_H - 9.0
image(bg_asset, c_bar_track, TEXT_X, BAR_Y, anchor_ml,
      size_mrg=dyn_size(BAR_W, h_const=BAR_H, w_gate=grace_vis), layer=4)
image(bg_asset, c_orange, TEXT_X, BAR_Y, anchor_ml,
      size_mrg=dyn_size(BAR_W, h_const=BAR_H, w_gate=grace_vis, w_scale=frac), layer=4)

out = {"Nodes": nodes, "Links": links,
       "RuiWidth": CANVAS_W, "RuiHeight": CANVAS_H}
dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fs_1v1_lobbyinfo.json")
with open(dest, "wb") as f:
    f.write(json.dumps(out, indent=2).encode("utf-8"))
print("nodes=%d links=%d" % (len(nodes), len(links)))
