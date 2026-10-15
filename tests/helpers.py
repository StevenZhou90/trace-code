"""One small dataset shared by the test modules, built once into a fresh temporary folder."""
import atexit
import shutil
import tempfile

from stc.build import build

_cache = {}


def read(path, mode="r"):
    with open(path, mode) as f:
        return f.read()


def small_dataset():
    if "dir" not in _cache:
        root = tempfile.mkdtemp(prefix="stc-test-")
        atexit.register(shutil.rmtree, root, True)
        _cache["dir"] = root + "/ds"
        _cache["summary"] = build(_cache["dir"], seed=0, small=True)
    return _cache["dir"], _cache["summary"]
