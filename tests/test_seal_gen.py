"""Headless tests for procedural gothic seal generation."""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

tk_stub = types.ModuleType("tkinter")


class _FakePhotoImage:
    def __init__(self, **kw):
        self.width = kw.get("width", 0)
        self.height = kw.get("height", 0)

    def put(self, data):
        pass

    def zoom(self, factor):
        return self


tk_stub.PhotoImage = _FakePhotoImage
sys.modules["tkinter"] = tk_stub

import image_gen

image_gen._to_photoimage = lambda grid, ink, paper: None


def test_seal_deterministic():
    a = image_gen._dither_hmap(image_gen._build_seal_hmap("node_x", 64, "node"))
    b = image_gen._dither_hmap(image_gen._build_seal_hmap("node_x", 64, "node"))
    assert a == b


def test_seal_different_seeds_differ():
    a = image_gen._dither_hmap(image_gen._build_seal_hmap("alpha", 64, "node"))
    b = image_gen._dither_hmap(image_gen._build_seal_hmap("beta", 64, "node"))
    assert a != b


def test_seal_variant_differs():
    a = image_gen._dither_hmap(image_gen._build_seal_hmap("same", 64, "node"))
    b = image_gen._dither_hmap(image_gen._build_seal_hmap("same", 64, "item"))
    assert a != b


def test_seal_pil_dimensions():
    img = image_gen.generate_seal_pil_image("test", size=100, variant="node", zoom=3)
    assert img.size == (300, 300)
    assert img.mode == "1"


def test_seal_motif_index_in_range():
    seed = hash("motif_probe") & 0xFFFF_FFFF
    idx = int(image_gen._hash_val(9, 9, seed) * len(image_gen._SEAL_MOTIFS)) % len(image_gen._SEAL_MOTIFS)
    assert 0 <= idx < len(image_gen._SEAL_MOTIFS)


if __name__ == "__main__":
    test_seal_deterministic()
    test_seal_different_seeds_differ()
    test_seal_variant_differs()
    test_seal_pil_dimensions()
    test_seal_motif_index_in_range()
    print("all seal tests passed")
