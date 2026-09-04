"""Machine-local path resolution for the ui_fs build tools.

Order: environment variable, then sere_paths.json beside this file, then the
built-in default. Copy sere_paths.example.json to sere_paths.json and edit it.
"""

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_CONFIG = os.path.join(_HERE, 'sere_paths.json')

_DEFAULTS = {
    "sereRoot": os.path.dirname(_HERE),
    "repakExe": "",
    "deployDir": "",
    "artRoot": "",
    "bridge": "http://127.0.0.1:8790/rpc",
    "vcvars": "",
}

_ENV = {
    "sereRoot": "SERE_ROOT",
    "repakExe": "SERE_REPAK_EXE",
    "deployDir": "SERE_DEPLOY_DIR",
    "artRoot": "SERE_ART_ROOT",
    "bridge": "SERE_BRIDGE",
    "vcvars": "SERE_VCVARS",
}

_file = {}
if os.path.isfile(_CONFIG):
    with open(_CONFIG, 'rb') as f:
        _file = json.loads(f.read().decode('utf-8'))


def get(key, required=False):
    v = os.environ.get(_ENV[key]) or _file.get(key) or _DEFAULTS[key]
    if required and not v:
        raise SystemExit(
            "path '%s' is not set: set %s or add it to %s"
            % (key, _ENV[key], _CONFIG))
    return v


def art(*parts):
    """A file under the local art root; '' when the root is not configured."""
    root = get('artRoot')
    return os.path.join(root, *parts) if root else ''
