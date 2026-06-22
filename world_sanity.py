"""
world_sanity.py — Rule-based checks for generated world JSON (works offline).
"""

from __future__ import annotations

import re

# Nouns that should not be portable inventory items
NON_CARRYABLE = frozenset({
    "car", "cars", "vehicle", "vehicles", "truck", "bus", "train",
    "building", "buildings", "room", "rooms", "floor", "floors",
    "wall", "walls", "ceiling", "bridge", "bridges", "road", "roads",
    "street", "streets", "city", "tower", "towers", "block", "blocks",
    "corridor", "corridors", "hallway", "hallways", "station", "platform",
    "roof", "basement", "elevator", "escalator", "stairs", "staircase",
    "doorway", "archway", "tunnel", "tunnels", "park", "lot", "garage",
    "warehouse", "factory", "plant", "complex", "structure", "monolith",
    "precinct", "district", "zone", "sector", "grid", "network",
})

_STOP = frozenset({
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "of", "is",
})


def is_carryable(item_id: str) -> bool:
    """Return False for immovable / oversized item candidates."""
    words = re.findall(r"[a-z]+", item_id.lower())
    if not words:
        return False
    if any(w in NON_CARRYABLE for w in words):
        return False
    if len(words) > 3:
        return False
    return True


def filter_carryable_items(items: list[str]) -> list[str]:
    return [i for i in items if is_carryable(i)]


def _dest_words(node_id: str, title: str = "") -> set[str]:
    words = set(re.findall(r"[a-z]{3,}", node_id.lower().replace("_", " ")))
    words |= set(re.findall(r"[a-z]{3,}", title.lower()))
    return words - _STOP


def _label_matches_dest(label: str, dest_id: str, dest_title: str = "") -> bool:
    label_words = set(re.findall(r"[a-z]{3,}", label.lower())) - _STOP
    dest = _dest_words(dest_id, dest_title)
    return bool(label_words & dest)


def fix_exit_labels(world_dict: dict) -> dict:
    """Ensure exit labels mention their destination or use a clear fallback."""
    nodes_by_id = {n["id"]: n for n in world_dict.get("nodes", [])}
    for node in world_dict.get("nodes", []):
        for ex in node.get("exits", []):
            dest = nodes_by_id.get(ex.get("to", ""))
            dest_title = dest.get("title", ex.get("to", "")) if dest else ex.get("to", "")
            label = ex.get("label", "")
            if not _label_matches_dest(label, ex.get("to", ""), dest_title):
                title = dest_title if dest else ex.get("to", "somewhere").replace("_", " ")
                ex["label"] = f"Go to {title}"
    return world_dict


def ensure_items_in_text(node: dict) -> dict:
    """Append a short sentence if an item is not mentioned in the body."""
    body = node.get("text") or node.get("description") or ""
    items = node.get("items") or []
    if not items or not body:
        return node
    body_lower = body.lower()
    additions = []
    for item_id in items:
        if not is_carryable(item_id):
            continue
        words = [w for w in re.findall(r"[a-z]+", item_id.lower()) if w not in _STOP]
        if not words:
            continue
        if not any(w in body_lower for w in words):
            label = item_id if item_id.lower().startswith(("the ", "a ", "an ")) else f"the {item_id}"
            additions.append(f"{label.capitalize()} rests here.")
    if additions:
        node = dict(node)
        node["text"] = body.rstrip() + "\n\n" + " ".join(additions)
        node["description"] = node["text"]
    return node


def sanitize_node_dict(node: dict) -> dict:
    """Apply per-node sanity rules."""
    node = dict(node)
    raw_items = node.get("items") or []
    node["items"] = filter_carryable_items(raw_items)
    node = ensure_items_in_text(node)
    return node


def sanitize_world(world_dict: dict) -> dict:
    """Apply all offline sanity rules to a world dict."""
    world_dict = dict(world_dict)
    nodes = [sanitize_node_dict(n) for n in world_dict.get("nodes", [])]
    world_dict["nodes"] = nodes
    return fix_exit_labels(world_dict)


def sanitize_node_list(nodes: list[dict], nodes_by_id: dict | None = None) -> list[dict]:
    """Sanitize a batch of node dicts (discovery flush)."""
    result = [sanitize_node_dict(n) for n in nodes]
    if nodes_by_id:
        combined = dict(nodes_by_id)
        for n in result:
            combined[n["id"]] = n
        mini = {"nodes": list(combined.values())}
        mini = fix_exit_labels(mini)
        by_id = {n["id"]: n for n in mini["nodes"]}
        result = [by_id.get(n["id"], n) for n in result]
    else:
        mini = fix_exit_labels({"nodes": result})
        by_id = {n["id"]: n for n in mini["nodes"]}
        result = [by_id[n["id"]] for n in result]
    return result
