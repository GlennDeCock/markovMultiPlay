"""Tests for world sanity rules and item travel pairing."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_sanity import (
    is_carryable,
    sanitize_world,
    fix_exit_labels,
    filter_carryable_items,
)
from engine import StoryEngine, ItemChoice, ExitLink


class TestCarryable(unittest.TestCase):
    def test_car_not_carryable(self):
        self.assertFalse(is_carryable("car"))
        self.assertFalse(is_carryable("apartment building"))

    def test_key_carryable(self):
        self.assertTrue(is_carryable("key"))
        self.assertTrue(is_carryable("rusty pipe"))


class TestSanitizeWorld(unittest.TestCase):
    def test_fix_exit_label(self):
        world = {
            "nodes": [
                {"id": "a", "title": "Garage", "text": "A garage.", "exits": [
                    {"to": "b", "label": "enter the car"},
                ], "items": []},
                {"id": "b", "title": "Bookstore", "text": "Shelves.", "exits": [], "items": []},
            ],
        }
        out = fix_exit_labels(world)
        label = out["nodes"][0]["exits"][0]["label"]
        self.assertIn("Bookstore", label)

    def test_filters_car_item(self):
        world = {
            "nodes": [
                {"id": "lot", "title": "Lot", "text": "Empty lot.", "exits": [],
                 "items": ["car", "key"]},
            ],
        }
        out = sanitize_world(world)
        self.assertEqual(out["nodes"][0]["items"], ["key"])


class TestItemTravelFinalize(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parent.parent / "training_texts"
        self.engine = StoryEngine(training_dir=base)

    def test_item_gets_travel_exit_after_padding(self):
        ex_a = ExitLink("n1", "n2", "Go east")
        ex_b = ExitLink("n1", "n3", "Go west")
        item = ItemChoice("leave", "key", "Drop the key and go")
        chosen = [item, ex_a]
        # Simulate discovery replacing second slot
        chosen[1] = ex_b
        result = self.engine._finalize_item_travel(chosen, [ex_a, ex_b], "n1")
        self.assertEqual(result[0].travel_exit, ex_b)

    def test_item_only_gets_paired_exit(self):
        ex = ExitLink("n1", "n2", "Go on")
        item = ItemChoice("take", "pipe", "Take the pipe")
        result = self.engine._finalize_item_travel([item], [ex], "n1")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].travel_exit, ex)


if __name__ == "__main__":
    unittest.main()
