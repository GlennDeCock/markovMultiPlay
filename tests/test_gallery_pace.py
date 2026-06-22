"""Tests for orientation hints and gallery self-pace."""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import (
    StoryEngine, ExitLink, WorldNode, WorldGraph, PlayerState, IDLE_SPAWN_SEC,
)
from tests.test_navigation import _mini_world


class TestOrientationHint(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parent.parent / "training_texts"
        self.engine = StoryEngine(training_dir=base)
        self.engine.world = _mini_world()
        self.engine.players["P01"] = PlayerState("P01", "b")
        state = self.engine.players["P01"]
        state.history = ["a", "b"]
        state.current_links = [
            ExitLink("b", "c", "Go to Charlie"),
            ExitLink("b", "d", "Go to Delta"),
        ]

    def test_hint_lists_visible_destinations(self):
        hint = self.engine.get_orientation_hint("P01")
        self.assertIsNotNone(hint)
        self.assertIn("Charlie", hint)
        self.assertIn("Delta", hint)

    def test_hint_omitted_when_titles_in_body(self):
        node = self.engine.world.nodes["b"]
        node.current_text = "Charlie hall. Delta wing. Bravo hall."
        self.assertIsNone(self.engine.get_orientation_hint("P01"))

    def test_display_text_appends_hint(self):
        text = self.engine.get_display_text_for_player("P01")
        self.assertIn("Paths:", text)
        self.assertIn("Charlie", text)


class TestGalleryPace(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parent.parent / "training_texts"
        self.engine = StoryEngine(training_dir=base)
        self.engine.world = _mini_world()
        self.engine.spawn_every_node_changes = 5
        self.engine.gallery_pace = True

    def test_effective_spawn_every_scales_with_players(self):
        self.assertEqual(self.engine._effective_spawn_every(), 5)
        for i in range(4):
            pid = f"P{i:02d}"
            self.engine.players[pid] = PlayerState(pid, "a")
        self.assertEqual(self.engine._effective_spawn_every(), 3)

    def test_effective_spawn_floor_at_three(self):
        for i in range(10):
            self.engine.players[f"P{i:02d}"] = PlayerState(f"P{i:02d}", "a")
        self.assertEqual(self.engine._effective_spawn_every(), 3)

    def test_effective_drift_rate_with_many_players(self):
        self.engine._drift_rate = 3
        for i in range(4):
            self.engine.players[f"P{i:02d}"] = PlayerState(f"P{i:02d}", "a")
        self.assertEqual(self.engine._effective_drift_rate(), 1)

    def test_idle_spawn_when_stale(self):
        self.engine.players["P01"] = PlayerState("P01", "b")
        self.engine._last_spawn_time = time.time() - IDLE_SPAWN_SEC - 1
        self.engine._corpus_locations = ["warehouse", "yard"]
        with patch.object(self.engine, "_next_latent_node", return_value={
            "id": "new_spot",
            "title": "New Spot",
            "text": "A new spot.",
            "description": "A new spot.",
            "tags": ["new"],
            "exits": [],
            "items": [],
        }):
            n = self.engine.tick_gallery_idle()
        self.assertEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
