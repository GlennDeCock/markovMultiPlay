"""Tests for history-aware exit ranking and display labels."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import StoryEngine, ExitLink, WorldNode, WorldGraph, PlayerState


def _mini_world():
    """Three-node line: a -> b -> c with a return link on c."""
    wg = WorldGraph()
    wg.nodes = {
        "a": WorldNode("a", "Alpha", "Alpha room.", [
            ExitLink("a", "b", "Proceed east"),
        ], ["alpha"]),
        "b": WorldNode("b", "Bravo", "Bravo hall.", [
            ExitLink("b", "a", "Return"),
            ExitLink("b", "c", "Cross north"),
            ExitLink("b", "d", "Follow west"),
        ], ["bravo"]),
        "c": WorldNode("c", "Charlie", "Charlie yard.", [
            ExitLink("c", "b", "Return"),
        ], ["charlie"]),
        "d": WorldNode("d", "Delta", "Delta lot.", [
            ExitLink("d", "b", "Return"),
        ], ["delta"]),
    }
    wg.start_nodes = ["a"]
    return wg


class TestExitRanking(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parent.parent / "training_texts"
        self.engine = StoryEngine(training_dir=base)
        self.engine.world = _mini_world()
        self.engine.players["P01"] = PlayerState("P01", "b")
        self.engine.players["P01"].history = ["a", "b"]

    def test_unvisited_beats_return(self):
        exits = list(self.engine.world.nodes["b"].exits)
        ranked = self.engine._rank_exits_for_player("P01", "b", exits)
        self.assertNotIn(ranked[0].to_node, ("a",))
        self.assertNotEqual(ranked[0].label.strip().lower(), "return")
        self.assertIn(ranked[0].to_node, ("c", "d"))

    def test_deprioritize_backtrack(self):
        state = self.engine.players["P01"]
        state.history = ["a", "b", "c", "b"]
        exits = list(self.engine.world.nodes["b"].exits)
        ranked = self.engine._rank_exits_for_player("P01", "b", exits)
        # Came from c — c should not be first
        self.assertNotEqual(ranked[0].to_node, "c")

    def test_display_exit_label_adds_destination(self):
        ex = ExitLink("b", "d", "Follow west")
        label = self.engine._display_exit_label(ex)
        self.assertIn("Delta", label)

    def test_exit_rotation_cycles_order(self):
        state = self.engine.players["P01"]
        exits = [
            e for e in self.engine.world.nodes["b"].exits
            if e.to_node != "b"
        ]
        first = self.engine._rank_exits_for_player("P01", "b", exits)
        state.exit_rotation["b"] = 1
        second = self.engine._rank_exits_for_player("P01", "b", exits)
        if len(first) >= 2:
            self.assertNotEqual(
                [e.to_node for e in first],
                [e.to_node for e in second],
            )

    def test_breadcrumb_from_history(self):
        trace = self.engine.get_player_trace_text("P01")
        self.assertIn("from:", trace.lower())
        self.assertIn("Alpha", trace)


if __name__ == "__main__":
    unittest.main()
