"""Build every custom RUI into ONE pak + ONE module: ui_fs.rpak / ui_fs.dll.

The engine resolves a RUI's code with Pak_GetProcAddress(pak, ui->name), so one
module can serve any number of RUIs as long as each exports a function named
after its asset. One pak also means one HAS_MODULE allowlist entry instead of
one per RUI.

SERE stays a single-graph editor: it is driven over its control bridge to emit
the per-graph .ruip + .cpp, and this script does the combine, pack and deploy.
Turn AutoDeploy off in SERE so it does not also ship a per-graph pak.

  python build_ui_fs.py            build + deploy
  python build_ui_fs.py --no-deploy
"""

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import sere_paths

BRIDGE = sere_paths.get('bridge')
SERE_ROOT = sere_paths.get('sereRoot')
REPAK = sere_paths.get('repakExe', required=True)
DEPLOY = sere_paths.get('deployDir')
WORK = os.path.join(SERE_ROOT, 'work', 'ui_fs')
PAK_NAME = 'ui_fs'

VCVARS_CANDIDATES = [
    sere_paths.get('vcvars'),
    r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat',
    r'C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat',
]

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def graph_of(name):
    """A RUI's graph: this repo's ruis/ first, then a SERE examples/ tree."""
    local = os.path.join(_REPO, 'ruis', name, name + '.json')
    if os.path.exists(local):
        return local
    return os.path.join(SERE_ROOT, 'examples', name, name + '.json')


# Every RUI that ships inside ui_fs. `defaults` are baked as the asset's initial
# values; script overrides them at runtime with RuiSet*.
RUIS = [
    {
        "name": "fs_1v1_lobbyinfo",
        "graph": graph_of('fs_1v1_lobbyinfo'),
        "blurMask": sere_paths.art('shipped', '1v1_lobbyinfo_blur_mask.png'),
        # cardImage cannot be baked: SERE's image picker only holds names in
        # its local registry and rewrites anything else to "missing". The
        # client script sets it right after RuiCreate, like logoImage.
        "defaults": {"headerText": "", "countText": "",
                     "logoImage": "rui/flowstatecustom/1v1",
                     "queueTitle": "", "queueFilter": "",
                     "queueFilterAny": "", "graceText": "",
                     "lockClosedImage": "rui/menu/buttons/large_lock",
                     "lockOpenImage": "rui/menu/buttons/unlocked",
                     "queueInputIcon": "rui/menu/crossplatform/controller",
                     "queuePadIcon": "rui/menu/crossplatform/controller"},
    },
    {
        # FSLeaderboard frame: blur, dark fill, header band and edge bar with a
        # chamfered corner. Widget quads are the shape, so no mask gate.
        "name": "fs_lb_frame",
        "graph": graph_of('fs_lb_frame'),
        "defaults": {},
    },
    {
        # 1v1 settings board: same frame at 980x560 (tools/gen_fs_frame.py).
        "name": "fs_1v1_settings_frame",
        "graph": graph_of('fs_1v1_settings_frame'),
        "defaults": {},
    },
    {
        # Prebuilt RSX ui export. Data offsets are baked, so asset and ruiFunc must move together.
        "name": "mantle_boost",
        "prebuilt": {
            "json": os.path.join(SERE_ROOT, 'prebuilt', 'mantle_boost', 'mantle_boost.json'),
            "cpp": os.path.join(SERE_ROOT, 'prebuilt', 'mantle_boost', 'mantle_boost.cpp'),
        },
    },
    {
        "name": "fs_1v1_vs",
        "graph": graph_of('fs_1v1_vs'),
        # Blur is shaped by widget quads, so a geometry change can silently put
        # blur outside the panel. Gate every build against the painted mask.
        "blurMask": sere_paths.art('shipped', '1v1_bg_blur_mask_cafe.png'),
        "defaults": {
            "basicImage": "rui/flowstate_custom/1v1_bg",
            "enemyPosition": "", "playerPosition": "",
            "enemyName": "", "playerName": "",
            "enemyKills": "0", "enemyDeaths": "0",
            "enemyDamage": "0", "enemyLatency": "0",
            "playerKills": "0", "playerDeaths": "0",
            "playerDamage": "0", "playerLatency": "0",
            "lockLocked": "", "lockAny": "",
            "playerInputIcon": "rui/menu/crossplatform/pc",
            "enemyInputIcon": "rui/menu/crossplatform/pc",
            "lockIcon": "rui/menu/buttons/unlocked",
        },
    },
]


# Art a prebuilt RUI needs that S21 does not already carry. GUID is StringToGuid of ui_image/<path>.rpak.
IMAGES = [
    {
        "path": "rui/hud/crosshairs/superglide_hud_bracket",
        "uiia": os.path.join(SERE_ROOT, 'prebuilt', 'mantle_boost', 'images',
                             'superglide_hud_bracket.uiia'),
        "guid": "0xA74A654ECAE97BF5",
    },
    {
        "path": "rui/hud/crosshairs/superglide_hud_ring",
        "uiia": os.path.join(SERE_ROOT, 'prebuilt', 'mantle_boost', 'images',
                             'superglide_hud_ring.uiia'),
        "guid": "0x58813072CE39F74D",
    },
]


def rpc(method, params=None):
    body = json.dumps({"method": method, "params": params or {}}).encode()
    req = urllib.request.Request(BRIDGE, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        out = json.loads(r.read().decode())
    if not out.get("ok"):
        raise SystemExit("SERE bridge error on %s: %s" % (method, out.get("error")))
    return out


def export_one(rui):
    graph = json.load(open(rui["graph"], encoding='utf-8'))
    rpc("graph.set", {"graph": graph})
    live = rpc("health")["nodes"]
    if live != len(graph["Nodes"]):
        raise SystemExit("%s: SERE holds %d nodes, file has %d"
                         % (rui["name"], live, len(graph["Nodes"])))
    rpc("args.set", {"args": rui["defaults"]})
    started = time.time()
    msg = rpc("export", {"name": rui["name"]})["message"]
    print('  export:', msg)

    # Take the path SERE reports. Guessing a directory picks up a stale .ruip
    # from an earlier export and silently bakes its defaults into the pak.
    m = re.search(r'Exported:\s*(.+?\.ruip)', msg)
    if not m:
        raise SystemExit("%s: could not read the .ruip path out of %r"
                         % (rui["name"], msg))
    ruip = m.group(1).strip()
    base = os.path.dirname(ruip)
    if os.path.basename(base).lower() == 'ui':
        base = os.path.dirname(base)
    cpp = os.path.join(base, rui["name"] + '.cpp')
    for p in (ruip, cpp):
        if not os.path.exists(p):
            raise SystemExit("%s: %s missing" % (rui["name"], p))
        if os.path.getmtime(p) < started - 5:
            raise SystemExit("%s: %s is stale (not rewritten by this export)"
                             % (rui["name"], p))

    # The element size is baked into the asset. If the graph declares a canvas,
    # the package must carry exactly that, otherwise the editor's last canvas
    # was used and every normalised position still looks right while the aspect
    # is silently wrong.
    want = (graph.get("RuiWidth"), graph.get("RuiHeight"))
    if want[0] and want[1]:
        import struct
        got = struct.unpack_from('<ff', open(ruip, 'rb').read(), 16)
        if abs(got[0] - want[0]) > 0.5 or abs(got[1] - want[1]) > 0.5:
            raise SystemExit("%s: baked element %gx%g but the graph declares %gx%g"
                             % (rui["name"], got[0], got[1], want[0], want[1]))
        print('  element: %g x %g' % got)
    else:
        print('  WARNING: %s declares no RuiWidth/RuiHeight, element size is '
              'whatever the editor last had' % rui["name"])
    return base, ruip, cpp


def prepare_prebuilt(rui):
    """Package an RSX ui JSON export + hand-written ruiFunc into a .ruip."""
    src = rui["prebuilt"]
    base = os.path.dirname(src["json"])
    ruip = os.path.join(base, rui["name"] + '.ruip')
    conv = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'ui_json_to_ruip.py')
    r = subprocess.run([sys.executable, conv, src["json"], ruip],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(ruip):
        raise SystemExit("%s: ruip conversion failed: %s"
                         % (rui["name"], (r.stderr or r.stdout)[-2000:]))
    print('  ' + r.stdout.strip())

    import struct
    js = json.load(open(src["json"], encoding='utf-8'))
    got = struct.unpack_from('<ff', open(ruip, 'rb').read(), 16)
    want = (js["elementWidth"], js["elementHeight"])
    if abs(got[0] - want[0]) > 0.5 or abs(got[1] - want[1]) > 0.5:
        raise SystemExit("%s: baked element %gx%g but the export declares %gx%g"
                         % (rui["name"], got[0], got[1], want[0], want[1]))
    print('  element: %g x %g' % got)
    return base, ruip, src["cpp"]


def find_vcvars():
    for c in VCVARS_CANDIDATES:
        if os.path.exists(c):
            return c
    raise SystemExit("vcvars64.bat not found")


def sources_present(rui):
    if rui.get("prebuilt"):
        return all(os.path.exists(v) for v in rui["prebuilt"].values())
    return os.path.exists(rui["graph"])


def main():
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    os.makedirs(os.path.join(WORK, 'ui'))
    os.makedirs(os.path.join(WORK, 'build'))

    headers = None
    cpps = []
    for rui in RUIS:
        if not sources_present(rui):
            print('[%s] skipped, source not in this tree' % rui["name"])
            continue
        print('[%s]' % rui["name"])
        if rui.get("prebuilt"):
            base, ruip, cpp = prepare_prebuilt(rui)
        else:
            base, ruip, cpp = export_one(rui)
        shutil.copy2(ruip, os.path.join(WORK, 'ui', os.path.basename(ruip)))
        shutil.copy2(cpp, os.path.join(WORK, os.path.basename(cpp)))
        cpps.append(os.path.basename(cpp))
        if rui.get("blurMask"):
            gate = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'verify_blur_from_ruip.py')
            g = subprocess.run([sys.executable, gate, ruip, cpp, rui["blurMask"]],
                               capture_output=True, text=True)
            for line in g.stdout.strip().splitlines():
                print('  ' + line)
            if g.returncode != 0:
                if 'SPILL=' not in g.stdout:
                    raise SystemExit("%s: blur gate failed to run: %s"
                                     % (rui["name"], g.stderr[-2000:]))
                raise SystemExit("%s: blur spills outside the painted mask, "
                                 "refit with fit_blur_geom.py" % rui["name"])
        # Prebuilt entries must not contribute RuiHeaders.h; a stale copy shadows the live ABI.
        h = os.path.join(base, 'RuiHeaders.h')
        if not rui.get("prebuilt") and os.path.exists(h):
            headers = h
    for img in IMAGES:
        if not os.path.exists(img["uiia"]):
            print('[image] %s skipped, not in this tree' % img["path"])
            continue
        dst = os.path.join(WORK, 'ui_image', img["path"] + '.uiia')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(img["uiia"], dst)
        print('[image] %s -> %s' % (img["path"], img["guid"]))

    if not headers:
        raise SystemExit("RuiHeaders.h not produced by any export")
    shutil.copy2(headers, os.path.join(WORK, 'RuiHeaders.h'))

    print('\ncompiling %s.dll from %d translation unit(s)' % (PAK_NAME, len(cpps)))
    log = os.path.join(WORK, 'cl_output.txt')
    batPath = os.path.join(WORK, '_build_dll.bat')
    with open(batPath, 'w', encoding='utf-8') as f:
        f.write('@echo off\r\n')
        f.write('call "%s" >nul 2>&1\r\n' % find_vcvars())
        f.write('cd /d "%s"\r\n' % WORK)
        f.write('cl /LD /O2 /EHsc /std:c++17 %s /Fe:%s.dll > "%s" 2>&1\r\n'
                % (' '.join(cpps), PAK_NAME, log))
    subprocess.run(['cmd', '/c', batPath], capture_output=True, text=True)
    dll = os.path.join(WORK, PAK_NAME + '.dll')
    if not os.path.exists(dll):
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise SystemExit("compile failed, see " + log)
    print('  ->', dll, os.path.getsize(dll), 'bytes')

    manifest = {
        "version": 8,
        "hasDynamicLibrary": True,
        # 0x20 is required by the S21 native loader or the pak is rejected.
        "headerFlags": 32,
        "name": PAK_NAME,
        "assetsDir": WORK.replace('\\', '/') + '/',
        "outputDir": os.path.join(WORK, 'build').replace('\\', '/') + '/',
        "buildDate": int(time.time()),
        "files": [{"_type": "ui", "_path": "ui/%s.rpak" % r["name"]}
                  for r in RUIS if sources_present(r)]
               + [{"_type": "uiia", "_path": "ui_image/%s.uiia" % i["path"],
                   "$guid": i["guid"]}
                  for i in IMAGES if os.path.exists(i["uiia"])],
    }
    mpath = os.path.join(WORK, PAK_NAME + '_repak.json')
    open(mpath, 'wb').write(json.dumps(manifest, indent=4).encode('utf-8'))

    print('packing')
    r = subprocess.run([REPAK, mpath], capture_output=True, text=True)
    pak = os.path.join(WORK, 'build', PAK_NAME + '.rpak')
    if not os.path.exists(pak):
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise SystemExit("repak failed")

    import struct
    b = open(pak, 'rb').read()
    flags = struct.unpack_from('<H', b, 6)[0]
    headPage = struct.unpack_from('<I', b, 0x88)[0]
    print("  -> %s %d bytes  flags=0x%04X  headPage=%d"
          % (pak, len(b), flags, headPage))
    if not flags & 0x20:
        raise SystemExit("pak header flag 0x20 missing, S21 will reject it")
    # SF_HEAD is 112B per RUI plus 64B per uiia. A 104-byte RUI stride means repak.exe is stale.
    nUi = sum(1 for r in RUIS if sources_present(r))
    nImg = sum(1 for i in IMAGES if os.path.exists(i["uiia"]))
    wantHead = 112 * nUi + 64 * nImg
    if headPage != wantHead:
        raise SystemExit("head page is %d, expected %d (%d ui x 112 + %d uiia x 64)"
                         % (headPage, wantHead, nUi, nImg))

    if '--no-deploy' in sys.argv:
        print('\nnot deploying (--no-deploy)')
        return
    shutil.copy2(pak, os.path.join(DEPLOY, PAK_NAME + '.rpak'))
    shutil.copy2(dll, os.path.join(DEPLOY, PAK_NAME + '.dll'))
    print('\ndeployed %s.rpak + %s.dll -> %s' % (PAK_NAME, PAK_NAME, DEPLOY))
    for r in RUIS:
        if sources_present(r):
            print('  contains ui/%s.rpak  (module export "%s")' % (r["name"], r["name"]))


if __name__ == '__main__':
    main()
