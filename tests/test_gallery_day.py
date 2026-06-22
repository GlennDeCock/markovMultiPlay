"""Tests for gallery-day features: spawn bias, caps, display beats, archive."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import StoryEngine, PlayerState, DISPLAY_TEXT_MAX_PARAS
from tests.test_navigation import _mini_world
from world_archive import world_to_dict, save_session, export_day


class TestSpawnBiasAndCap(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parent.parent / "training_texts"
        self.engine = StoryEngine(training_dir=base)
        self.engine.world = _mini_world()
        self.engine.players["P01"] = PlayerState("P01", "a")
        self.engine._world_at_node["a"].add("P01")

    def test_pick_spawn_from_occupied_node(self):
        picked = {self.engine._pick_spawn_from_node() for _ in range(20)}
        self.assertIn("a", picked)

    def test_spawn_respects_node_cap(self):
        self.engine.max_world_nodes = len(self.engine.world.nodes)
        n = self.engine._spawn_from_play()
        self.assertEqual(n, 0)

    def test_reconnect_spawn_returns_existing_player(self):
        first = self.engine.spawn_player("P01")
        first.history.append("extra")
        again = self.engine.spawn_player("P01")
        self.assertIs(first, again)
        self.assertIn("extra", again.history)


class TestDisplayBeat(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parent.parent / "training_texts"
        self.engine = StoryEngine(training_dir=base)
        self.engine.world = _mini_world()
        node = self.engine.world.nodes["b"]
        node.current_text = "Para one.\n\nPara two.\n\nPara three.\n\nPara four."
        self.engine.players["P01"] = PlayerState("P01", "b")
        self.engine.players["P01"].choice_beat = "Toward Bravo Hall."

    def test_truncates_body_and_shows_beat_once(self):
        text = self.engine.get_display_text_for_player("P01")
        self.assertIn("Toward Bravo Hall.", text)
        self.assertNotIn("Para four.", text)
        parts = [p for p in text.split("\n\n") if p and not p.startswith("Paths:")]
        self.assertLessEqual(len(parts), DISPLAY_TEXT_MAX_PARAS + 1)

        again = self.engine.get_display_text_for_player("P01")
        self.assertNotIn("Toward Bravo Hall.", again)


class TestWorldArchive(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parent.parent / "training_texts"
        self.engine = StoryEngine(training_dir=base)
        self.engine.world = _mini_world()
        self.engine.players["P01"] = PlayerState("P01", "a")

    def test_world_to_dict_includes_players(self):
        data = world_to_dict(self.engine)
        self.assertEqual(data["session"]["player_count"], 1)
        self.assertIn("P01", data["session"]["players"])

    def test_save_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            live = save_session(self.engine, base)
            self.assertTrue(live.exists())
            data = json.loads(live.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(data["nodes"]), 1)

            self.engine.world_log.add("travel", "P01 moved")
            jpath, lpath = export_day(self.engine, self.engine.world_log.text(), base)
            self.assertTrue(jpath.exists())
            self.assertTrue(lpath.exists())
            self.assertIn("P01 moved", lpath.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
