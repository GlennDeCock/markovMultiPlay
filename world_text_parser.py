"""
world_text_parser.py — Converts plain-text world notes to world JSON.

Authoring format
----------------
Paragraphs separated by one or more blank lines (double Enter).

Optional: first line of a paragraph with no trailing period = node title/ID.
If present, the title line becomes the node's ID (slugified) and display title.
If absent, the ID is slugified from the first few significant words of the body.

Last 2 sentences of each paragraph = exit choice labels (stripped from body text).
Everything else = the node description shown to players, verbatim.

Example
-------
    city square
    Pigeons crowd the cracked pavement. A lamppost leans at a permanent
    angle. The fountain has been dry for years. Enter the market hall.
    Slip into the narrow alley.

    market hall
    Stalls crowd together under a vaulted iron ceiling. The smell of old
    cheese mingles freely. Back out to the square. Climb to the rooftop.

CLI
---
    python world_text_parser.py data/worlds/my_world.txt [output.json]
"""

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Stopwords used for slugification and tag extraction
# ---------------------------------------------------------------------------
_STOP = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "it", "its", "that", "this",
    "was", "are", "be", "has", "have", "had", "he", "she", "they", "we",
    "you", "i", "into", "through", "onto", "back", "out", "up", "down",
    "all", "both", "some", "such", "no", "not", "so", "very", "just",
    "will", "can", "do", "if", "there", "here", "then", "when", "which",
    "who", "what", "how", "been", "being", "were", "their", "them", "us",
    "my", "your", "our", "his", "her", "one", "two", "three", "still",
    "also", "each", "every", "more", "most", "other", "same", "than",
    "too", "under", "over", "near", "left", "right", "always", "never",
    "only", "even",
}


def _slugify(text: str, max_words: int = 4) -> str:
    """Turn a short phrase into a snake_case identifier."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    words = [w for w in text.split() if w not in _STOP and len(w) > 1]
    return "_".join(words[:max_words]) or "node"


_NAV_VERBS = {
    "enter", "go", "cross", "climb", "return", "back", "push", "slip",
    "descend", "emerge", "head", "walk", "move", "take", "follow", "step",
    "proceed", "continue", "leave", "exit", "access", "pass", "turn",
    "open", "through", "into", "up", "down", "out", "away", "toward",
    "towards", "reach",
}


def _is_exit_sentence(sentence: str) -> bool:
    """Return True if the sentence reads like a navigation/action choice."""
    first = sentence.split()[0].lower().rstrip(".!?,;:") if sentence.split() else ""
    return first in _NAV_VERBS


def _split_sentences(text: str) -> list:
    """Split text into individual sentences on .!? boundaries."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _token_set(text: str) -> set:
    """Return non-stopword tokens from text for overlap scoring."""
    words = re.findall(r"\b[a-z]{2,}\b", text.lower())
    return {w for w in words if w not in _STOP}


def _best_match(exit_label: str, stubs: list, self_id: str) -> str | None:
    """Find the node whose title/body best matches the exit label text."""
    exit_tokens = _token_set(exit_label)
    best_id = None
    best_score = 0
    for stub in stubs:
        if stub["id"] == self_id:
            continue
        # Score = token overlap with node's title + full body text
        candidate_tokens = _token_set(stub["title"] + " " + stub["body"])
        score = len(exit_tokens & candidate_tokens)
        if score > best_score:
            best_score = score
            best_id = stub["id"]
    return best_id if best_score > 0 else None


def _extract_tags(text: str, n: int = 6) -> list:
    """Return the first N unique non-stopword words from text as tags."""
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    seen = set()
    tags = []
    for w in words:
        if w not in _STOP and w not in seen:
            seen.add(w)
            tags.append(w)
        if len(tags) >= n:
            break
    return tags


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def parse_world_text(text: str) -> dict:
    """
    Parse a plain-text world authoring file into a world dict.

    Returns a dict matching the world JSON schema:
      { "start": str, "nodes": [ { id, title, description, tags, exits } ] }
    """
    paragraphs = [p.strip() for p in re.split(r"\n\n+", text.strip()) if p.strip()]
    if not paragraphs:
        raise ValueError("No content found — check that paragraphs are separated by blank lines.")

    # ------------------------------------------------------------------
    # Pass 1: build node stubs (id, title, body, exit_sentences)
    # ------------------------------------------------------------------
    stubs = []
    for para in paragraphs:
        lines = para.splitlines()

        # Detect optional title line: first line has no sentence-ending punctuation
        if len(lines) > 1 and not re.search(r"[.!?]\s*$", lines[0]):
            title_raw = lines[0].strip()
            body_raw  = " ".join(l.strip() for l in lines[1:])
        else:
            title_raw = None
            body_raw  = " ".join(l.strip() for l in lines)

        sentences = _split_sentences(body_raw)

        # Detect exit sentences from the end: scan backward while sentences
        # look like navigation/action imperatives.  Cap at 3 exits.
        split_idx = len(sentences)
        for j in range(len(sentences) - 1, max(len(sentences) - 4, -1), -1):
            if _is_exit_sentence(sentences[j]):
                split_idx = j
            else:
                break

        body_sentences = sentences[:split_idx]
        exit_sentences = sentences[split_idx:]

        # Fallback: if nothing detected as exit and there are ≥ 2 sentences,
        # treat the last sentence as the single exit.
        if not exit_sentences and len(sentences) >= 2:
            body_sentences = sentences[:-1]
            exit_sentences = sentences[-1:]

        body_text = " ".join(body_sentences)

        if title_raw:
            node_id = _slugify(title_raw)
            title   = title_raw.title()
        else:
            node_id = _slugify(body_sentences[0] if body_sentences else body_raw)
            title   = (body_sentences[0].rstrip(".!?") if body_sentences
                       else body_raw[:40])

        stubs.append({
            "id":             node_id,
            "title":          title,
            "body":           body_text,
            "exit_sentences": exit_sentences,
        })

    # Deduplicate node IDs (append _2, _3, … if collision)
    seen: dict = {}
    for stub in stubs:
        base = stub["id"]
        if base in seen:
            seen[base] += 1
            stub["id"] = f"{base}_{seen[base]}"
        else:
            seen[base] = 1

    # ------------------------------------------------------------------
    # Pass 2: link exits
    # ------------------------------------------------------------------
    nodes = []
    for i, stub in enumerate(stubs):
        exits = []
        for exit_sent in stub["exit_sentences"]:
            dest_id = _best_match(exit_sent, stubs, stub["id"])
            if dest_id is None:
                # Fallback: next node in document order (wrap around)
                dest_id = stubs[(i + 1) % len(stubs)]["id"]
            exits.append({
                "to":    dest_id,
                "label": exit_sent.rstrip(".!?"),
            })

        nodes.append({
            "id":          stub["id"],
            "title":       stub["title"],
            "description": stub["body"],
            "tags":        _extract_tags(stub["body"]),
            "exits":       exits,
        })

    return {
        "start": nodes[0]["id"] if nodes else "",
        "nodes": nodes,
    }


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def convert_file(txt_path, json_path=None) -> Path:
    """Parse a .txt world file and write the resulting JSON.

    Parameters
    ----------
    txt_path  : path to the source .txt file
    json_path : output path (default: same name, .json extension,
                placed next to the .txt file)

    Returns the Path of the written JSON file.
    """
    txt_path = Path(txt_path)
    if json_path is None:
        json_path = txt_path.parent / (txt_path.stem + ".json")
    else:
        json_path = Path(json_path)

    raw   = txt_path.read_text(encoding="utf-8")
    world = parse_world_text(raw)

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(world, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Parsed {len(world['nodes'])} nodes  →  {json_path}")
    return json_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python world_text_parser.py <world.txt> [output.json]")
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else None
    convert_file(sys.argv[1], out)
