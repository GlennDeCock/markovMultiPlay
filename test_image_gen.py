"""
Headless smoke test for image_gen.py.
Stubs out tkinter so it runs without a display.
Run: python test_image_gen.py
"""

import sys
import types

# --- stub tkinter before importing image_gen ---
tk_stub = types.ModuleType("tkinter")

class _FakePhotoImage:
    def __init__(self, **kw): pass
    def put(self, data): pass
    def zoom(self, factor): return self

tk_stub.PhotoImage = _FakePhotoImage
sys.modules["tkinter"] = tk_stub
import tkinter as tk  # noqa: F401 — ensure stub is active

# Patch _to_photoimage to skip actual Tk calls
import image_gen
image_gen._to_photoimage = lambda grid, ink, paper: None

# --- test cases ---
SAMPLES = [
    "You stand at the corner of two empty streets.",
    "The building casts a long shadow across the pavement.",
    "A bicycle leans against the wall near the door.",
    "Clouds drift over the towers in the pale sky.",
    "A bench beside the fountain. Nobody sits there.",
    "The elevator doors are open. A sign says OUT OF ORDER.",
    "The clock on the wall shows a time you don't recognise.",
    "Traffic lights blink amber above an empty road.",
    "A phone box with a cracked window and no directory.",
    "The courtyard smells of rain and old stone.",
    "Fire escapes zig-zag down the building face.",
    "Vending machines hum quietly in the corridor.",
    "Trees line the avenue, their branches bare.",
    "A parking garage, levels marked by painted numbers.",
    "",  # empty text → fallback
    "zzz xyz aaa bbb",  # no keyword matches → fallback
]

passed = 0
failed = 0

for i, text in enumerate(SAMPLES):
    try:
        result = image_gen.generate_scene_image(text)
        assert result is None  # our stub returns None
        print(f"[OK] sample {i:2d}: {repr(text[:50])}")
        passed += 1
    except Exception as e:
        print(f"[FAIL] sample {i:2d}: {repr(text[:50])}")
        print(f"       {type(e).__name__}: {e}")
        import traceback; traceback.print_exc()
        failed += 1

print()
print(f"Results: {passed} passed, {failed} failed out of {len(SAMPLES)} samples.")
if failed:
    sys.exit(1)
