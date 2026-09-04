import os
import json, math, os
import sere_paths

W, H = 1005.0, 138.0
BLUR_PREVIEW = os.environ.get('BLUR_PREVIEW', '')   # non-empty -> plates draw art, not blur
PANEL_W, PANEL_H = 676.0, 92.72          # FS_1v1_UI_BG in flowstate_customhudvgui.res
SCALE = H / PANEL_H                      # panel units -> authored RUI units

def srgb(hexcode):
    """Style colors are linear floats; encode an sRGB hex so the rendered
    pixel matches the swatch."""
    c = [int(hexcode[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
                 for x in c)


ORANGE = srgb('f77d04')
CYAN = srgb('88d0e6')

nodes, links = [], []
_next = [1000]


def nid():
    _next[0] += 1
    return _next[0]


def node(**kw):
    # SERE keys nodes by Id in one map; a repeat silently replaces the earlier
    # node and every link into it then resolves against the wrong node type.
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


# ---- frame ---------------------------------------------------------------
size(1, W, H, -2400, 0, mx=2000.0)
vec2(2, 0.5, 0.5, -2400, 80)                      # shared centre anchor / pivot
node(Name="Transform 2", Category="Transform", PosX=-2100, PosY=0, Id=3)
node(Name="Image Arg", Category="Argument", ArgName="basicImage", PosX=-2400, PosY=180, Id=4)
node(Name="Screen Blur", Category="Constant", PosX=-2400, PosY=280, Id=5)
color(6, (1.0, 1.0, 1.0), -2400, 380)

node(Name="Render Image Image Mask", Category="Image Render", Layer=1, PosX=-1750, PosY=460, Id=8)
link(2, "Value", 3, "Val_0")
link(2, "Value", 3, "Val_3")
link(1, "Value", 3, "Size")
link(4, "Value", 8, "Main Asset")
link(6, "Value", 8, "Main Color")
link(3, "Out", 8, "Transform")

# ---- frosted plates ------------------------------------------------------
# Blur is image index -4 and the engine hard-sets uv/clip to the widget's own
# quad, so art cannot shape it: the WIDGET is the shape, and the draw path
# intersects each widget quad with its clip transform's quad. Each plate is
# seven axis-aligned rects, each cut by one rotated clip quad along the mask
# edge segment it owns (both tab chamfers come from one 45-degree diamond).
# fit_blur_exact.py fits the segments to the painted mask at zero spill.
GEOM = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   'fs_1v1_vs_blur_geom.json'), encoding='utf-8'))

blurAsset = 4 if BLUR_PREVIEW else 5
py = [900]


def transform2(cx, cy, w_, h_):
    a, b, c = nid(), nid(), nid()
    vec2(a, round(cx / W, 6), round(cy / H, 6), -2100, py[0])
    size(b, round(w_, 2), round(h_, 2), -2100, py[0] + 60)
    node(Name="Transform 2", Category="Transform", PosX=-1750, PosY=py[0], Id=c)
    link(3, "Out", c, "Parent")
    link(a, "Value", c, "Val_0")
    link(2, "Value", c, "Val_3")
    link(b, "Value", c, "Size")
    py[0] += 200
    return c, b


def rotated_clip(cx, cy, w_, h_, rot):
    c, b = transform2(cx, cy, w_, h_)
    r, rc = nid(), nid()
    node(Name="Float Constant", Category="Constant", Min=-1.0, Max=1.0,
         Value=round(rot, 7), PosX=-2100, PosY=py[0], Id=r)
    node(Name="Rotate Transform", Category="Transform", PosX=-1400, PosY=py[0], Id=rc)
    link(c, "Out", rc, "Parent")
    link(b, "Value", rc, "Size")
    link(2, "Value", rc, "Rotation Origin")
    link(r, "Value", rc, "Rotation")
    py[0] += 200
    return rc


def line_clip(ln):
    """A long rotated band whose edge lies on x = a + s*(y - y0), covering the
    keep side of the line."""
    s, keep = ln['s'], ln['keep']
    r = math.hypot(s, 1.0)
    d = (s / r, 1.0 / r)
    n = (keep / r, -keep * s / r)
    L, T = 2600.0, 900.0
    cx = ln['a'] + n[0] * T / 2.0
    cy = ln['y0'] + n[1] * T / 2.0
    # recentre along the edge so the clip transform stays in vec2 range
    u = (H / 2.0 - cy) / d[1]
    return rotated_clip(cx + d[0] * u, cy + d[1] * u, L, T,
                        math.atan2(1.0, s) / (2.0 * math.pi))


def diamond_clip(dm):
    """One 45-degree square whose two upper edges are the chamfer lines
    x + y = c1 and x - y = c2."""
    L = 300.0
    cx = (dm['c1'] + dm['c2']) / 2.0
    cy = (dm['c1'] - dm['c2']) / 2.0 + L
    return rotated_clip(cx, cy, L * math.sqrt(2.0), L * math.sqrt(2.0), 0.125)


for sideName in ('left', 'right'):
    for wdg in GEOM['sides'][sideName].values():
        x0, y0, x1, y1 = wdg['rect']
        c, _ = transform2((x0 + x1) / 2.0, (y0 + y1) / 2.0, x1 - x0, y1 - y0)
        dW = nid()
        node(Name="Render Image Image Mask", Category="Image Render", Layer=0,
             PosX=-1050, PosY=py[0], Id=dW)
        link(blurAsset, "Value", dW, "Main Asset")
        link(6, "Value", dW, "Main Color")
        link(c, "Out", dW, "Transform")
        clip = line_clip(wdg['line']) if 'line' in wdg else diamond_clip(wdg['diamond'])
        link(clip, "Out", dW, "Clip")

# ---- text styles ---------------------------------------------------------
node(Name="Float Constant", Category="Constant", Min=0.0, Max=200.0,
     Value=round(22 * SCALE, 1), PosX=-2400, PosY=560, Id=9)     # fontHeight 22
node(Name="Float Constant", Category="Constant", Min=0.0, Max=200.0,
     Value=round(14 * SCALE, 1), PosX=-2400, PosY=640, Id=10)    # fontHeight 14
color(11, ORANGE, -2400, 720)
color(12, CYAN, -2400, 800)

node(Name="Float Constant", Category="Constant", Min=0.0, Max=200.0,
     Value=round(10 * SCALE, 1), PosX=-2400, PosY=860, Id=17)     # fontHeight 10
color(18, srgb('79818c'), -2400, 940)                             # hud dim grey

# name styles use the mixed-case title face; ArameMono is caps-only
for sid, (fsize, col, pos, face) in {
        13: (9, 11, 600, "TitanfallBold"), 14: (9, 12, 760, "TitanfallBold"),
        15: (10, 11, 920, "ArameMono"), 16: (10, 12, 1080, "ArameMono"),
        900: (17, 11, 1240, "ArameMono"), 901: (17, 12, 1400, "ArameMono"),
        902: (17, 18, 1560, "ArameMono")}.items():
    node(Name="Text Style", Category="Text Render", FontName=face,
         PosX=-2100, PosY=pos, Id=sid)
    link(fsize, "Value", sid, "Size")
    link(col, "Value", sid, "mainColor")

# ---- the twelve script-settable values -----------------------------------
# centre, in element-normalised coords, derived from each Label's pin+xpos+wide
def left_cx(xpos, wide):
    return (-xpos + wide / 2.0) / PANEL_W


def right_cx(xpos, wide):
    return (PANEL_W + xpos - wide / 2.0) / PANEL_W


def cy(ypos):
    return (PANEL_H / 2.0 + ypos) / PANEL_H


NAME_Y, VAL_Y, POS_Y = cy(-5), cy(37), cy(-33)
LOCK_Y = cy(-26)

# input device icons at the outer ends of the name row; padlock over the VS
def icon_widget(argName, colId, cx_px, cy_px, w_, h_):
    ia = nid()
    node(Name="Image Arg", Category="Argument", ArgName=argName,
         PosX=-800, PosY=py[0], Id=ia)
    c, _ = transform2(cx_px, cy_px, w_, h_)
    dI = nid()
    node(Name="Render Image Image Mask", Category="Image Render", Layer=2,
         PosX=-400, PosY=py[0], Id=dI)
    link(ia, "Value", dI, "Main Asset")
    link(colId, "Value", dI, "Main Color")
    link(c, "Out", dI, "Transform")


icon_widget("enemyInputIcon", 11, left_cx(-8, 55) * W, NAME_Y * H, 26.0, 20.0)
icon_widget("playerInputIcon", 12, right_cx(-8, 55) * W, NAME_Y * H, 26.0, 20.0)
icon_widget("lockIcon", 6, 0.5 * W, 12.0, 16.0, 20.0)

FIELDS = [
    # lock state text above the VS wedge
    ("lockLocked",    0.5,                  LOCK_Y, 900),
    ("lockAny",       0.5,                  LOCK_Y, 902),
    ("enemyPosition", left_cx(-30, 30),     POS_Y,  15),
    ("playerPosition", right_cx(-30, 30),   POS_Y,  16),
    ("enemyName",     left_cx(0, 300),      NAME_Y, 13),
    ("enemyKills",    left_cx(-23, 55),     VAL_Y,  15),
    ("enemyDeaths",   left_cx(-75, 55),     VAL_Y,  15),
    ("enemyDamage",   left_cx(-135, 100),   VAL_Y,  15),
    ("enemyLatency",  left_cx(-245, 55),    VAL_Y,  15),
    ("playerName",    right_cx(0, 300),     NAME_Y, 14),
    ("playerKills",   right_cx(-255, 55),   VAL_Y,  16),
    ("playerDeaths",  right_cx(-200, 55),   VAL_Y,  16),
    ("playerDamage",  right_cx(-90, 100),   VAL_Y,  16),
    ("playerLatency", right_cx(-28, 55),    VAL_Y,  16),
]

for i, (arg, x, y, style) in enumerate(FIELDS):
    b = 20 + i * 5
    ty = i * 220
    node(Name="String Arg", Category="Argument", ArgName=arg, PosX=-1400, PosY=ty, Id=b)
    node(Name="Text Size", Category="Text Render", PosX=-1100, PosY=ty, Id=b + 1)
    vec2(b + 2, round(x, 4), round(y, 4), -1400, ty + 100)
    node(Name="Transform 2", Category="Transform", PosX=-800, PosY=ty, Id=b + 3)
    node(Name="Text Render", Category="Text Render", Layer=2, PosX=-500, PosY=ty, Id=b + 4)

    link(b, "Value", b + 1, "text")
    link(style, "Style", b + 1, "Style_0")
    link(3, "Out", b + 3, "Parent")
    link(b + 2, "Value", b + 3, "Val_0")
    link(2, "Value", b + 3, "Val_3")
    link(b + 1, "Size", b + 3, "Size")
    link(b + 1, "Text Data", b + 4, "Data")
    link(b + 3, "Out", b + 4, "Parent")

out = os.path.join(sere_paths.get('sereRoot'), 'examples', 'fs_1v1_vs', 'fs_1v1_vs.json')
os.makedirs(os.path.dirname(out), exist_ok=True)
# The canvas MUST travel with the graph. Without these the editor keeps whatever
# it last had and the export bakes that instead, which silently changes the
# element aspect while every normalised position still looks correct.
doc = {"Nodes": nodes, "Links": links, "RuiWidth": W, "RuiHeight": H}
with open(out, 'wb') as f:
    f.write(json.dumps(doc, indent=2).encode('utf-8'))
print('wrote', out, len(nodes), 'nodes', len(links), 'links, canvas %gx%g' % (W, H))
nWidgets = sum(len(s) for s in GEOM['sides'].values())
print('blur widgets: %d (rect + rotated clip per mask edge segment)' % nWidgets)
