# ui_fs ( R5Flowstate / S21 )

Source for `ui_fs.rpak` and `ui_fs.dll`.

Agents view included: CLAUDE.md

## What is in here

| Path | What it is |
|---|---|
| `ruis/<name>/<name>.json` | the SERE graph, the actual source of a RUI |
| `ruis/<name>/gen_*.py` | generator that writes that graph, where one exists |
| `tools/build_ui_fs.py` | drives SERE, compiles the module, packs and deploys |
| `tools/gen_fs_frame.py` | one generator for every board frame (`FRAMES` table) |
| `tools/fit_blur_exact.py` | fits screen-blur widgets to a painted mask |
| `tools/verify_blur_from_ruip.py` | rasterises an exported `.ruip` and scores it |

A graph is the source. The `.cpp` and `.ruip` are build output and are not
checked in.

## Building

Needs [SERE](https://github.com/R5Flowstate/SERE),
[RePak](https://github.com/R5Flowstate/RePak), and MSVC.

```
copy tools\sere_paths.example.json tools\sere_paths.json   :: then edit it
python tools\build_ui_fs.py                                 :: --no-deploy to skip the copy
```

Start SERE first and leave the window **restored**. Minimised, its main
thread stops pumping and every bridge request times out.
