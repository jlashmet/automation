# -*- coding: utf-8 -*-
"""Oculix IDE bundle entrypoint for the automation coordinator."""
from __future__ import print_function

import os


def _bundle_dir():
    file_name = globals().get("__file__")
    if file_name:
        return os.path.dirname(os.path.abspath(file_name))
    get_bundle_path = globals().get("getBundlePath")
    if get_bundle_path:
        bundle_path = get_bundle_path()
        if bundle_path:
            return os.path.abspath(str(bundle_path))
    return os.getcwd()


# The real coordinator and all PNG assets live one directory above this .sikuli
# bundle. Pin the coordinator there so Oculix never falls back to a shared volume.
_AUTOMATION_DIR = os.path.dirname(_bundle_dir())
os.environ["AUTOMATION_DIR"] = _AUTOMATION_DIR
_set_bundle_path = globals().get("setBundlePath")
if _set_bundle_path:
    _set_bundle_path(_AUTOMATION_DIR)

_MAIN = os.path.join(_AUTOMATION_DIR, "auto.py")
with open(_MAIN, "rb") as _main_handle:
    _main_code = compile(_main_handle.read(), _MAIN, "exec")
eval(_main_code, globals(), globals())
