# ui_fs (agent notes)

Human overview: `README.md`. The editor and its own notes live in
[SERE](https://github.com/R5Flowstate/SERE).

## The shape, and why it is one pak

A RUI's drawing code is resolved by the engine with
`Pak_GetProcAddress( pak, ui->name )`, so **one module serves any number of
RUIs** as long as each exports a function named after its asset:

```cpp
extern "C" __declspec(dllexport)
void <assetName>( RuiFunctions_t*, RuiGlobals*, RuiInstance*, <assetName>_data* );
```

That is why everything here ships as one pak plus one module rather than a pair
per RUI: a pak that carries a module is loaded by name, so a single first-party
name is the only thing the client has to trust.

**The pak and the module are a matched pair.** Data-struct offsets and the
header's code CRC move together; shipping one without the other is undefined
behaviour. Never deploy half of a build.

## Paths

Nothing machine-specific is hardcoded. `tools/sere_paths.py` resolves each key
from an environment variable, then `tools/sere_paths.json` (gitignored), then a
default:

| Key | Env | What it is |
|---|---|---|
| `sereRoot` | `SERE_ROOT` | SERE tree, for `examples/` fallback and prebuilt assets |
| `repakExe` | `SERE_REPAK_EXE` | RePak binary; required |
| `deployDir` | `SERE_DEPLOY_DIR` | game `paks/Win64`; empty means build only |
| `artRoot` | `SERE_ART_ROOT` | local art root for blur masks; empty skips the gate |
| `vcvars` | `SERE_VCVARS` | `vcvars64.bat`, tried before the stock VS locations |
| `bridge` | `SERE_BRIDGE` | SERE's control bridge URL |

`graph_of()` takes a RUI's graph from `<repo>/ruis/<name>/` and falls back to
`<sereRoot>/examples/<name>/`, so the same script runs here and in a SERE tree.

## Adding a RUI

Put the graph at `ruis/<name>/<name>.json`, append an entry to `RUIS` in
`build_ui_fs.py`, and build. An entry whose sources are absent is skipped,
and it drops out of the repak manifest and the head-page gate with it, so a
partial tree still packs.

## What bites

- **A minimised SERE answers nothing.** Its bridge handlers run on the editor
  main thread from `Pump()`; minimise the window and every RPC, `health`
  included, blocks until the server-side timeout and returns
  `timed out waiting for the editor main thread`. It reads exactly like a hung
  editor. Restore the window.
- **SERE holds the game paks open**, and so does the running game. Close both
  before deploying, and verify BOTH files landed. A copy that fails on the
  `.dll` while succeeding on the `.rpak` leaves a mismatched pair.
- **Export defaults are baked.** Whatever argument values are set at export time
  become the asset's defaults, so leave names empty and counters at `"0"` rather
  than shipping test data.
- **The asset name is not the pak name.** `ui/<name>.rpak` is the path *inside*
  `ui_fs.rpak`, and that is what a `.res` `rui` field or a script's
  `GetKeyValueAsAsset` asks for. Adding a RUI never moves those paths.
- **Screen blur is a negative image index, not artwork**, and it cannot be
  masked by art: it is shaped by the widget quad and its clip transform. That
  is why the fit and verify tools exist: the shaping is checked against a
  painted mask and scored for spill, not eyeballed.
- **Two pak gates** run after packing. Header flags must carry `0x20` or the
  loader rejects the pak, and the SF_HEAD page at `+0x88` must equal
  `112 * numRuis + 64 * numImages`. A 104-byte RUI stride means the RePak build
  is stale. Rebuild RePak, never hex-patch the pak.
