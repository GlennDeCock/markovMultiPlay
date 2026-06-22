"""
llm_client.py — Optional LLM review for world JSON (OpenAI, Ollama, or off).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from copy import deepcopy
from typing import Callable

log = logging.getLogger(__name__)

MODES = ("off", "openai", "ollama")
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_OLLAMA_URL = "http://localhost:11434"

SYSTEM_PROMPT = """You improve text-adventure world JSON. Rules:
- Exit labels must match destination node titles/descriptions (no "enter the car" to a bookstore).
- Items must be small and portable (no cars, buildings, rooms as items).
- Items must be mentioned in the node body text.
- Keep all existing node IDs unchanged. Only the new location node may be added.
- Preserve graph connectivity: every exit "to" must reference an existing node id.
- Return ONLY valid JSON: same schema as input (nodes with id, title, text, exits, items, tags).
- Terse cold present-tense prose. No markdown.
- During play review: fix only broken or nonsensical Markov drift/item sentences.
- Do NOT rewrite coherent text. Keep length and tone. Minimal edits only.
- Polish the new location node so it fits recent player actions."""

ProgressCallback = Callable[[str], None] | None


class LLMClient:
    def __init__(
        self,
        mode: str = "off",
        model: str | None = None,
        ollama_url: str = DEFAULT_OLLAMA_URL,
        batch_size: int = 10,
    ):
        self.mode = mode if mode in MODES else "off"
        self.model = model or (
            DEFAULT_OPENAI_MODEL if self.mode == "openai" else DEFAULT_OLLAMA_MODEL
        )
        self.ollama_url = ollama_url.rstrip("/")
        self.batch_size = max(1, batch_size)

    @classmethod
    def from_env(cls) -> "LLMClient":
        mode = os.environ.get("MMP_LLM_MODE", "off").lower()
        model = os.environ.get("MMP_LLM_MODEL")
        url = os.environ.get("MMP_OLLAMA_URL", DEFAULT_OLLAMA_URL)
        return cls(mode=mode, model=model, ollama_url=url)

    @property
    def enabled(self) -> bool:
        return self.mode != "off"

    def test_connection(self) -> tuple[bool, str]:
        if self.mode == "off":
            return True, "LLM disabled (Markov + sanity only)"
        try:
            if self.mode == "openai":
                key = os.environ.get("OPENAI_API_KEY", "")
                if not key:
                    return False, "OPENAI_API_KEY not set"
                self._openai_chat("Reply with OK.", "ping")
                return True, f"OpenAI OK ({self.model})"
            if self.mode == "ollama":
                self._ollama_chat("Reply with OK.", "ping")
                return True, f"Ollama OK ({self.model})"
        except Exception as exc:
            return False, str(exc)
        return False, f"Unknown mode: {self.mode}"

    def review_world(
        self,
        world_dict: dict,
        on_progress: ProgressCallback = None,
    ) -> tuple[dict, list[str]]:
        if not self.enabled:
            return world_dict, []
        nodes = world_dict.get("nodes", [])
        if not nodes:
            return world_dict, []
        reviewed = []
        all_changes: list[str] = []
        total = len(nodes)
        for start in range(0, total, self.batch_size):
            batch = nodes[start : start + self.batch_size]
            if on_progress:
                on_progress(f"LLM review nodes {start + 1}–{min(start + len(batch), total)}/{total}")
            context = {
                "start_nodes": world_dict.get("start_nodes", []),
                "all_ids": [n["id"] for n in nodes],
            }
            fixed, changes = self.review_nodes(batch, context)
            reviewed.extend(fixed)
            all_changes.extend(changes)
        out = deepcopy(world_dict)
        out["nodes"] = reviewed
        return out, all_changes

    def review_nodes(
        self, nodes: list[dict], context: dict | None = None,
    ) -> tuple[list[dict], list[str]]:
        if not self.enabled or not nodes:
            return nodes, []
        before = deepcopy(nodes)
        context = context or {}
        payload = {"nodes": nodes, "context": context}
        if context.get("play_session"):
            if context.get("fix_markov_only"):
                intro = (
                    "Live play: Markov chains rewrote these nodes (see change_reasons). "
                    "Fix ONLY nonsensical or ungrammatical sentences from drift/items. "
                    "Leave good sentences unchanged. Minimal edits. "
                    "If neighbor_titles is provided, weave one short in-world orientation "
                    "clause naming reachable neighbors when not already in the text. "
                    "Do not use UI labels like 'Paths:'. "
                    "Return JSON with key 'nodes' only.\n\n"
                )
            else:
                intro = (
                    "Players changed these locations during live play (see change_reasons and "
                    "recent_item_events). Polish the changed nodes and the one NEW location node. "
                    "Return JSON with key 'nodes' only.\n\n"
                )
        else:
            intro = "Review and fix these world nodes. Return JSON with key 'nodes' only.\n\n"
        compact = context.get("play_session", False)
        prompt = intro + json.dumps(
            payload, ensure_ascii=False,
            separators=(",", ":") if compact else None,
            indent=None if compact else 2,
        )
        try:
            raw = self._chat(SYSTEM_PROMPT, prompt, json_mode=True)
            parsed = _extract_json(raw)
            if isinstance(parsed, dict) and "nodes" in parsed:
                fixed = parsed["nodes"]
            elif isinstance(parsed, list):
                fixed = parsed
            else:
                log.warning("LLM returned unexpected shape; keeping originals")
                return nodes, []
            if not _validate_nodes(fixed, nodes):
                log.warning("LLM output failed validation; keeping originals")
                return nodes, []
            from world_log import diff_node_dicts
            changes = diff_node_dicts(before, fixed)
            return fixed, changes
        except Exception as exc:
            log.warning("LLM review failed: %s", exc)
            return nodes, [f"LLM error: {exc}"]

    def _chat(self, system: str, user: str, json_mode: bool = False) -> str:
        if self.mode == "openai":
            return self._openai_chat(system, user, json_mode=json_mode)
        if self.mode == "ollama":
            return self._ollama_chat(system, user)
        return user

    def _openai_chat(self, system: str, user: str, json_mode: bool = False) -> str:
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set")
        body_dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
        }
        if json_mode:
            body_dict["response_format"] = {"type": "json_object"}
        body = json.dumps(body_dict).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    def _ollama_chat(self, system: str, user: str) -> str:
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
        }).encode("utf-8")
        url = f"{self.ollama_url}/api/chat"
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama not reachable at {self.ollama_url}: {exc}") from exc
        return data.get("message", {}).get("content", "")


def _extract_json(text: str):
    """Parse LLM output as JSON; tolerate fences and unescaped newlines in strings."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()

    candidates = [text]
    start = text.find("{")
    if start > 0:
        candidates.append(text[start:])
    end = text.rfind("}")
    if end > start >= 0:
        candidates.append(text[start : end + 1])

    last_err = None
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        for attempt in (candidate, _repair_json_strings(candidate)):
            try:
                return json.loads(attempt)
            except json.JSONDecodeError as exc:
                last_err = exc
    if last_err:
        raise last_err
    raise json.JSONDecodeError("No JSON object found", text, 0)


def _repair_json_strings(text: str) -> str:
    """Escape raw newlines/tabs inside JSON string values (common LLM mistake)."""
    out: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if escape:
            out.append(ch)
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            out.append(ch)
            continue
        if ch == '"':
            in_string = not in_string
            out.append(ch)
            continue
        if in_string and ch == "\n":
            out.append("\\n")
            continue
        if in_string and ch == "\r":
            continue
        if in_string and ch == "\t":
            out.append("\\t")
            continue
        out.append(ch)
    return "".join(out)


def _validate_nodes(fixed: list, original: list) -> bool:
    if len(fixed) != len(original):
        return False
    orig_ids = {n["id"] for n in original}
    for n in fixed:
        if not isinstance(n, dict) or "id" not in n:
            return False
        if n["id"] not in orig_ids and len(original) == len(fixed):
            pass  # discovery batch may add ids — caller handles
    return True
