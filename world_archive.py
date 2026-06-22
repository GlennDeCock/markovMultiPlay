"""
world_archive.py — Auto-save and export the live gallery world + session log.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def world_to_dict(engine) -> dict:
    """Serialize the live world graph to JSON schema (includes drifted text)."""
    if not engine.world:
        return {"start_nodes": [], "nodes": [], "players": {}}

    nodes = []
    for node in engine.world.nodes.values():
        nodes.append({
            "id": node.id,
            "title": node.title,
            "text": node.current_text,
            "description": node.current_text,
            "tags": list(node.tags),
            "exits": [
                {"to": ex.to_node, "label": ex.label}
                for ex in node.exits
            ],
            "items": [
                meta["label"].replace("the ", "").replace("The ", "").strip()
                for meta in node.items.values()
                if meta.get("present")
            ],
        })

    players = {}
    for pid, state in engine.players.items():
        players[pid] = {
            "current_node": state.current_node,
            "history_len": len(state.history),
            "inventory": state.inventory,
        }

    return {
        "start_nodes": list(engine.world.start_nodes),
        "nodes": nodes,
        "session": {
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "node_count": len(nodes),
            "player_count": len(players),
            "players": players,
        },
    }


def save_session(engine, base_dir: Path | None = None, *, snapshot: bool = False) -> Path | None:
    """Write live world JSON under data/sessions/. Returns path or None."""
    if not engine.world:
        return None
    base_dir = base_dir or Path(__file__).parent / "data" / "sessions"
    base_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d")
    live_path = base_dir / f"{stamp}_live.json"
    live_path.write_text(
        json.dumps(world_to_dict(engine), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if snapshot:
        snap = base_dir / f"{datetime.now().strftime('%Y-%m-%d_%H%M')}_snap.json"
        snap.write_text(live_path.read_text(encoding="utf-8"), encoding="utf-8")
        return snap
    return live_path


def export_day(engine, log_text: str, base_dir: Path | None = None) -> tuple[Path, Path]:
    """Export final world JSON + world log text. Returns (json_path, log_path)."""
    base_dir = base_dir or Path(__file__).parent / "data" / "sessions"
    base_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    json_path = base_dir / f"{stamp}_export.json"
    log_path = base_dir / f"{stamp}_world_log.txt"

    json_path.write_text(
        json.dumps(world_to_dict(engine), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    node_count = len(engine.world.nodes) if engine.world else 0
    header = (
        f"MultiMarkovPlay — day export {stamp}\n"
        f"Nodes: {node_count}  Players: {len(engine.players)}\n"
        f"{'=' * 60}\n\n"
    )
    log_path.write_text(header + log_text, encoding="utf-8")
    return json_path, log_path
