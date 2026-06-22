"""
engine.py — Dynamic shared graph engine.

The story graph GROWS as players make choices.
- Every node expansion creates 2 outgoing links with variable config
  (2 new / 1 new + 1 cross / 2 cross) chosen randomly.
- All players share the same graph.
- Collisions: if player B arrives at a node where player A is already
  present, every player at that node gets a collision scene (each with
  path-seeded overlay text). When only one player remains, collision clears.
"""

import json
import queue
import random
import re
import threading
import time
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

LLM_COALESCE_SEC = 3.0  # batch node polishes before one background API call
IDLE_SPAWN_SEC = 12 * 60  # gallery mode: force spawn if none for this long


# ---------------------------------------------------------------------------
# Markov Chain  (sentence-aware, backoff, temperature, repetition penalty)
# ---------------------------------------------------------------------------

class MarkovChain:
    """
    Improvements over a naive chain:

    - Sentence-aware training: each line/sentence is a unit.
      Sentence-start keys are recorded so generation always begins
      at a real sentence boundary.
    - Backoff: if an order-N key has no continuation, try order N-1
      down to order 1 before doing a random restart.
    - Temperature: scale continuation weights so low temp = pick the
      most common continuation, high temp = more random.
    - Repetition penalty: recently used keys are down-weighted so the
      output doesn't loop on the same phrase.
    - Generation ends at a sentence boundary when possible.
    """

    SENT_END = re.compile(r'[.!?]$')

    def __init__(self, order: int = 3, temperature: float = 1.1):
        self.order       = order
        self.temperature = temperature   # 0.7 = conservative, 1.5 = chaotic
        self.chain: dict[tuple, list] = {}
        self.starts: list[tuple]      = []   # sentence-start keys

    def reset(self):
        self.chain  = {}
        self.starts = []

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def _sentences(self, text: str) -> list[list[str]]:
        """Split text into sentence word-lists. Each line = one sentence."""
        sentences = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            words = line.split()
            if len(words) >= self.order + 1:
                sentences.append(words)
        return sentences

    def train(self, text: str):
        for words in self._sentences(text):
            key = tuple(words[: self.order])
            if key not in self.starts:
                self.starts.append(key)
            for i in range(len(words) - self.order):
                k = tuple(words[i : i + self.order])
                self.chain.setdefault(k, []).append(words[i + self.order])

    def train_from_dir(self, directory: Path) -> int:
        self.reset()
        files = [
            f for f in Path(directory).glob("*.txt")
            if f.name.upper() not in ("README.TXT", "README.MD")
        ]
        for f in files:
            try:
                self.train(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        return len(files)

    # ------------------------------------------------------------------
    # Sampling helpers
    # ------------------------------------------------------------------

    def _weighted_choice(self, options: list[str], recent: set) -> str:
        """
        Choose from options applying temperature and repetition penalty.
        recent: set of recently used words to down-weight.
        """
        if len(options) == 1:
            return options[0]

        # Count frequencies
        freq: dict[str, int] = {}
        for w in options:
            freq[w] = freq.get(w, 0) + 1

        words   = list(freq.keys())
        weights = []
        for w in words:
            w_freq = freq[w]
            # Temperature: raise to 1/temp — flattens (>1) or sharpens (<1)
            w_t = w_freq ** (1.0 / max(self.temperature, 0.1))
            # Repetition penalty
            if w in recent:
                w_t *= 0.25
            weights.append(w_t)

        total = sum(weights)
        if total == 0:
            return random.choice(words)
        r = random.uniform(0, total)
        cumul = 0.0
        for w, wt in zip(words, weights):
            cumul += wt
            if r <= cumul:
                return w
        return words[-1]

    def _backoff_key(self, key: tuple) -> str | None:
        """Try key, then shorter suffixes, return next word or None."""
        for length in range(len(key), 0, -1):
            short = key[-length:]
            if short in self.chain:
                return short
        return None

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(self, length: int = 40) -> str:
        """
        Generate text of approximately `length` words.
        Starts at a sentence boundary.
        Tries to end at a sentence boundary (word ending in . ! ?).
        Uses backoff + temperature + repetition penalty.
        """
        if not self.chain:
            return "the city continues in all directions from here"

        # Start at a sentence boundary if possible
        if self.starts:
            key = random.choice(self.starts)
        else:
            key = random.choice(list(self.chain.keys()))

        result  = list(key)
        recent: set = set(key)   # track last ~6 words for repetition penalty
        RECENT_WINDOW = 6

        for step in range(length * 2):   # allow extra steps to reach sentence end
            found = self._backoff_key(key)
            if found is None:
                # Hard dead end — restart from a sentence start
                if self.starts:
                    key = random.choice(self.starts)
                    result.extend(list(key))
                    recent.update(key)
                    if len(recent) > RECENT_WINDOW:
                        recent = set(list(recent)[-RECENT_WINDOW:])
                continue

            nxt = self._weighted_choice(self.chain[found], recent)
            result.append(nxt)
            recent.add(nxt)
            if len(recent) > RECENT_WINDOW:
                recent = set(list(recent)[-RECENT_WINDOW:])
            key = tuple(result[-self.order :])

            # After reaching minimum length, stop at sentence boundary
            if len(result) >= length and self.SENT_END.search(nxt):
                break

        # Hard truncate with a soft boundary: find last sentence end
        if len(result) > length + 15:
            for i in range(len(result) - 1, length - 1, -1):
                if self.SENT_END.search(result[i]):
                    result = result[: i + 1]
                    break
            else:
                result = result[:length]

        text = " ".join(result)
        # Capitalise first letter
        if text:
            text = text[0].upper() + text[1:]
        return text

    def generate_short(self, length: int = 5) -> str:
        """
        Generate a short label (for link buttons).
        Picks a random sentence-start and takes the first `length` words.
        Avoids terminal punctuation so it reads as a fragment/action.
        """
        if not self.chain:
            return "continue"
        if self.starts:
            key = random.choice(self.starts)
        else:
            key = random.choice(list(self.chain.keys()))

        result = list(key)
        recent: set = set(key)
        for _ in range(length * 3):
            found = self._backoff_key(key)
            if found is None:
                break
            nxt = self._weighted_choice(self.chain[found], recent)
            result.append(nxt)
            recent.add(nxt)
            key = tuple(result[-self.order :])
            if len(result) >= length:
                break

        words = result[:length]
        # Strip trailing punctuation for cleaner button labels
        if words:
            words[-1] = words[-1].rstrip(".!?,;:")
        label = " ".join(words)
        if label:
            label = label[0].upper() + label[1:]
        return label

    def generate_seeded(self, seed_words: list, length: int = 40) -> str:
        """
        Generate text seeded from specific words.
        Finds a sentence-start key that contains any of the seed words.
        Falls back to generate() if no seed match found.
        """
        if not self.chain:
            return self.generate(length)
        seed_lower = {w.lower() for w in seed_words if w}
        # Find sentence-start keys that contain a seed word
        matches = [
            k for k in self.starts
            if any(w.lower() in seed_lower for w in k)
        ]
        if matches:
            key = random.choice(matches)
        elif self.starts:
            key = random.choice(self.starts)
        else:
            key = random.choice(list(self.chain.keys()))

        result  = list(key)
        recent: set = set(key)
        RECENT_WINDOW = 6

        for step in range(length * 2):
            found = self._backoff_key(key)
            if found is None:
                if self.starts:
                    key = random.choice(self.starts)
                    result.extend(list(key))
                    recent.update(key)
                    if len(recent) > RECENT_WINDOW:
                        recent = set(list(recent)[-RECENT_WINDOW:])
                continue
            nxt = self._weighted_choice(self.chain[found], recent)
            result.append(nxt)
            recent.add(nxt)
            if len(recent) > RECENT_WINDOW:
                recent = set(list(recent)[-RECENT_WINDOW:])
            key = tuple(result[-self.order:])
            if len(result) >= length and self.SENT_END.search(nxt):
                break

        if len(result) > length + 15:
            for i in range(len(result) - 1, length - 1, -1):
                if self.SENT_END.search(result[i]):
                    result = result[:i + 1]
                    break
            else:
                result = result[:length]

        text = " ".join(result)
        if text:
            text = text[0].upper() + text[1:]
        return text

    def set_order(self, order: int):
        """Order change requires retraining."""
        self.order = max(1, min(5, int(order)))

    def set_temperature(self, t: float):
        self.temperature = max(0.3, min(3.0, t))


# ---------------------------------------------------------------------------
# Graph data structures
# ---------------------------------------------------------------------------

class Node:
    _counter = 0

    def __init__(self, text: str, node_id: str = None):
        Node._counter += 1
        self.id: str = node_id or f"n{Node._counter:04d}"
        self.text: str = text
        self.expanded: bool = False       # True once a player visited + links created
        self.links_out: list[str] = []    # link ids departing from this node
        self.visitors: set = set()        # player_ids who have been here

        # Mutation state
        self.is_mutated: bool = False
        self.mutations: list[str] = []          # texts applied so far (newest last)
        self.base_text: str = text              # preserved original text
        # Pre-computed mutation texts per link index, filled at expansion time
        self.link_mutation_texts: dict[int, str] = {}
        self.traversed_links: set[int] = set()  # link indices already first-traversed


class Link:
    _counter = 0

    def __init__(self, from_node: str, to_node: str, label: str, is_cross: bool = False):
        Link._counter += 1
        self.id: str = f"l{Link._counter:04d}"
        self.from_node: str = from_node
        self.to_node: str   = to_node
        self.label: str     = label
        self.is_cross: bool = is_cross   # True = points to pre-existing node


class DynamicGraph:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.links: dict[str, Link] = {}   # id → Link
        self._links_from: dict[str, list] = defaultdict(list)  # node_id → [Link]

    def add_node(self, node: Node):
        self.nodes[node.id] = node

    def add_link(self, link: Link):
        self.links[link.id] = link
        self._links_from[link.from_node].append(link)
        self.nodes[link.from_node].links_out.append(link.id)

    def get_links_from(self, node_id: str) -> list:
        return self._links_from.get(node_id, [])

    def nodes_visited_by_others(self, exclude_player: str, exclude_node: str) -> list:
        """All nodes visited by at least one other player, excluding given node."""
        return [
            n for n in self.nodes.values()
            if n.visitors - {exclude_player}  # someone else visited
            and n.id != exclude_node
            and not n.id.startswith("start")
        ]

    def candidate_cross_nodes(self, from_node: str, player_id: str) -> list:
        """
        Nodes suitable as cross-link targets:
        - visited by others, OR expanded (has content)
        - not already linked from from_node
        - not from_node itself
        """
        already_linked = {l.to_node for l in self.get_links_from(from_node)}
        already_linked.add(from_node)
        return [
            n for n in self.nodes.values()
            if n.id not in already_linked
            and (n.visitors - {player_id} or n.expanded)
        ]


# ---------------------------------------------------------------------------
# Player State
# ---------------------------------------------------------------------------

STATUS_ACTIVE    = "active"
STATUS_ENCOUNTER = "encounter"
STATUS_GAME_OVER = "game_over"


class PlayerState:
    def __init__(self, player_id: str, start_node: str):
        self.player_id    = player_id
        self.current_node = start_node
        self.status       = STATUS_ACTIVE
        self.history: list[str] = [start_node]
        # The choices currently presented to this player (exits or interactions)
        self.current_links: list = []
        # Per-player encounter state
        self.encounter_role: str | None = None   # "fled" or "witnessed"
        self.encounter_text: str | None = None
        # World mode: track which interactions have been taken at each node
        self.taken_interactions: dict = {}  # node_id → set of choice labels
        # Inventory — world mode only, max 1 item at a time
        self.inventory: str | None       = None   # item_id of carried item
        self.inventory_label: str | None = None   # display label e.g. "the key"
        # Per-node exit rotation index (fair exposure when 3+ exits, item slot)
        self.exit_rotation: dict[str, int] = {}
        # One-line confirmation after a choice (wall one-press UX)
        self.choice_beat: str | None = None


# ---------------------------------------------------------------------------
# World graph data structures  (static authored world)
# ---------------------------------------------------------------------------

class ExitLink:
    """Pre-authored exit from a WorldNode to another WorldNode."""

    def __init__(self, from_node: str, to_node: str, label: str):
        self.id          = f"exit_{from_node}__{to_node}"
        self.from_node   = from_node
        self.to_node     = to_node
        self.label       = label
        self.is_cross    = False
        self.choice_type = "exit"


class InteractionChoice:
    """Generated in-node interaction — player stays at current node."""

    def __init__(self, label: str):
        self.label       = label
        self.is_cross    = False
        self.choice_type = "interact"
        self.to_node     = None
        self.id          = f"interact__{label[:12].replace(' ', '_')}"


class ItemChoice:
    """Stateful item interaction — take, leave, or use a carried item."""

    def __init__(self, action: str, item_id: str, item_label: str,
                 travel_exit: "ExitLink | None" = None):
        self.choice_type  = "item"
        self.action       = action        # "take" | "leave" | "use"
        self.item_id      = item_id
        self.label        = item_label
        self.is_cross     = False
        self.to_node      = None
        self.travel_exit  = travel_exit   # exit bundled with this item action
        self.id           = f"item_{action}_{item_id[:12].replace(' ', '_')}"


class WorldNode:
    """A static authored node in the world graph."""

    def __init__(self, node_id: str, title: str, description: str,
                 exits: list, tags: list):
        self.id                  = node_id
        self.title               = title
        self.base_text           = description          # never overwritten
        self.current_text        = description          # drifts over time
        self.text                = description          # alias kept for GraphCanvas compat
        self.exits               = exits                # list[ExitLink]
        self.tags                = tags
        self.drift: float        = 0.0                  # increments each player departure
        self.traces: list[str]   = []                   # rolling window max 5
        self.visitors: set       = set()
        self.interaction_count   = 0
        self.pregenerated_choices: list = []
        # Stateful items on this node  {item_id: {"label": str, "present": bool}}
        self.items: dict[str, dict]       = {}
        self._items_base: dict[str, dict] = {}   # snapshot for reset
        # Duck-type compat with Node for GraphCanvas
        self.is_mutated          = False
        self.expanded            = True

    @property
    def mutations(self) -> list:
        return self.traces

    def _sync_text_alias(self):
        """Keep .text in sync with .current_text for GraphCanvas compatibility."""
        self.text = self.current_text
        self.is_mutated = self.drift > 0


class WorldGraph:
    """Loads and holds the static authored world graph."""

    def __init__(self):
        self.nodes: dict[str, WorldNode] = {}
        self.start_nodes: list[str] = []   # eligible spawn points

    @property
    def links(self) -> dict:
        """Duck-type compatible with DynamicGraph.links for GraphCanvas."""
        result = {}
        for node in self.nodes.values():
            for ex in node.exits:
                result[ex.id] = ex
        return result

    def load(self, path) -> "WorldGraph":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        # Support both "start_nodes" list and legacy "start" single string
        if "start_nodes" in data:
            self.start_nodes = data["start_nodes"]
        elif "start" in data:
            self.start_nodes = [data["start"]]
        for nd in data.get("nodes", []):
            exits = [
                ExitLink(from_node=nd["id"], to_node=e["to"], label=e["label"])
                for e in nd.get("exits", [])
            ]
            # Accept both "text" and legacy "description"
            desc = nd.get("text", nd.get("description", ""))
            node = WorldNode(
                node_id     = nd["id"],
                title       = nd.get("title", nd["id"]),
                description = desc,
                exits       = exits,
                tags        = nd.get("tags", []),
            )
            for item_name in nd.get("items", []):
                label = (item_name if item_name.lower().startswith(("the ", "a ", "an "))
                         else f"the {item_name}")
                node.items[item_name] = {"label": label, "present": True}
            node._items_base = {k: dict(v) for k, v in node.items.items()}
            self.nodes[node.id] = node
        if not self.start_nodes and self.nodes:
            self.start_nodes = [next(iter(self.nodes))]

        all_ids = list(self.nodes.keys())
        adj = self._build_adjacency()
        from world_generator import select_spread_start_nodes
        # Always spread spawn points across the full graph — authored start_nodes
        # that cover only a subset (e.g. nodes.json's 3 of 6) cluster players.
        if all_ids:
            self.start_nodes = select_spread_start_nodes(
                all_ids, adj, k=min(20, len(all_ids))
            )
        return self

    def _build_adjacency(self) -> dict[str, list[str]]:
        """Undirected adjacency from world exit links."""
        adj = {nid: [] for nid in self.nodes}
        for node in self.nodes.values():
            for ex in node.exits:
                dest = ex.to_node
                if dest not in self.nodes:
                    continue
                if dest not in adj[node.id]:
                    adj[node.id].append(dest)
                if node.id not in adj[dest]:
                    adj[dest].append(node.id)
        return adj

    def pregenerate(self, engine) -> "WorldGraph":
        """Pre-generate all interaction choices for every node using Markov."""
        for node_id in self.nodes:
            self.nodes[node_id].pregenerated_choices = (
                engine.generate_interaction_choices(node_id)
            )
        return self


# ---------------------------------------------------------------------------
# Story Engine
# ---------------------------------------------------------------------------

DISPLAY_TEXT_MAX_PARAS = 2


class StoryEngine:
    def __init__(self, training_dir: Path):
        self.training_dir = Path(training_dir)
        self.markov       = MarkovChain(order=3, temperature=1.1)
        self.text_len     = 35
        self.choice_len   = 5

        self.graph   = DynamicGraph()
        self.players: dict[str, PlayerState] = {}
        # node_id → set of player_ids currently at that node
        self._at_node: dict[str, set] = defaultdict(set)

        # World mode (static authored graph) — None means dynamic mode
        self.world: WorldGraph | None       = None
        self._world_at_node: dict[str, set] = defaultdict(set)
        self.max_interactions_per_node      = 3
        self._start_node_index: int         = 0   # round-robin spawn counter
        self._drift_rate: int               = 1   # visits per sentence rewrite (1=every)
        self._world_adj: dict[str, list[str]] | None = None
        self._spawn_order: list[str]        = []

        # Callbacks — UI registers these to be notified of graph changes
        self.on_graph_change    = None   # callable(moved_player: str | None = None)
        self.on_encounter_start = None   # callable(node_id: str)

        # On-demand world growth (always on in world mode)
        self._latent_nodes: list = []
        self._corpus_text: str         = ""
        self._corpus_locations: list   = []
        self._corpus_items: list       = []
        self._fresh_node_counter: int  = 0

        # Spawn new nodes after N live node text changes (drift / items)
        self.spawn_every_node_changes: int = 5
        self.gallery_pace: bool = True
        self.max_world_nodes: int = 300
        self._node_changes_since_spawn: int = 0
        self._last_spawn_time: float = time.time()
        self._play_changed_nodes: dict[str, list[str]] = {}
        self._recent_item_events: list[str] = []

        # Session log (player actions, drift, items, LLM, discovery)
        from world_log import WorldLog
        self.world_log = WorldLog()
        self._last_review_had_changes: bool = False

        # LLM world review (off / openai / ollama) — play-time calls run in background
        self.llm_mode: str = "off"
        self.llm_model: str | None = None
        self.llm_ollama_url: str = "http://localhost:11434"
        self.on_world_progress = None  # callable(str) for UI status
        self.on_schedule_main = None   # callable(fn) — marshal results onto UI thread

        self._llm_job_queue: queue.Queue = queue.Queue()
        self._llm_pending: dict[str, dict] = {}  # node_id → {dict, reasons}
        self._llm_lock = threading.Lock()
        self._llm_timer: threading.Timer | None = None
        self._llm_worker = threading.Thread(
            target=self._llm_worker_loop, name="llm-worker", daemon=True,
        )
        self._llm_worker.start()

        self._init_start_node()
        self.train()

    def _emit_graph_change(
        self, moved_player: str | None = None, canvas_only: bool = False,
    ):
        if self.on_graph_change:
            self.on_graph_change(moved_player=moved_player, canvas_only=canvas_only)

    def _schedule_main(self, fn):
        """Run fn on the UI thread (via control_window root.after)."""
        if self.on_schedule_main:
            self.on_schedule_main(fn)
        else:
            fn()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _init_start_node(self):
        Node._counter = 0
        Link._counter = 0
        # No shared start node — each player gets their own on spawn

    def train(self) -> int:
        n = self.markov.train_from_dir(self.training_dir)
        return n

    def retrain(self, order: int = None) -> int:
        if order is not None:
            self.markov.set_order(order)
        return self.train()

    def _feed_back(self, text: str):
        """Feed newly generated node text back into the Markov chain.
        This keeps the world consistent: new locations echo the vocabulary
        of places already discovered."""
        self.markov.train(text)

    # ------------------------------------------------------------------
    # World mode — static authored graph
    # ------------------------------------------------------------------

    @property
    def _is_world_mode(self) -> bool:
        return self.world is not None

    @property
    def active_graph(self):
        """The graph used for rendering — world or dynamic."""
        return self.world if self._is_world_mode else self.graph

    def load_world(self, path) -> "StoryEngine":
        """Load a static authored world from a JSON file and pre-generate choices."""
        self.world = WorldGraph().load(Path(path))
        self._world_at_node = defaultdict(set)
        self._start_node_index = 0
        self._world_adj = self.world._build_adjacency()
        self._spawn_order = self._compute_spawn_order()
        if self.markov.chain:          # only pregenerate if training data is loaded
            self.world.pregenerate(self)
        self._ensure_discovery_pool()
        self._play_changed_nodes.clear()
        self._node_changes_since_spawn = 0
        self._last_spawn_time = time.time()
        self._cancel_llm_coalesce_timer()
        with self._llm_lock:
            self._llm_pending.clear()
        if self.on_graph_change:
            self.on_graph_change()
        return self

    def _ensure_discovery_pool(self):
        """Seed location corpus for on-demand node generation (cached JSON loads)."""
        if not self.world:
            return
        if not self._corpus_locations:
            self._corpus_locations = [
                n.title for n in self.world.nodes.values() if n.title
            ]
        self.world_log.add(
            "world",
            f"loaded {len(self.world.nodes)} nodes, "
            f"{len(self._latent_nodes)} latent pool, "
            f"spawn every {self.spawn_every_node_changes} node changes",
        )

    def _compute_spawn_order(self) -> list[str]:
        """Spread-ordered spawn candidates for the loaded world graph."""
        if not self.world:
            return []
        from world_generator import select_spread_start_nodes
        pool = list(self.world.nodes.keys())
        if not pool:
            return []
        adj = self._world_adj or self.world._build_adjacency()
        return select_spread_start_nodes(pool, adj, k=min(20, len(pool)))

    def _pick_world_spawn_node(self) -> str:
        """Pick a spawn node maximally distant from players already in the world."""
        pool = list(self.world.nodes.keys())
        if not pool:
            return next(iter(self.world.nodes))

        adj = self._world_adj or self.world._build_adjacency()
        occupied = {nid for nid, pids in self._world_at_node.items() if pids}

        from world_generator import bfs_distances, min_graph_distance

        if not occupied:
            def eccentricity(nid: str) -> int:
                dists = bfs_distances(nid, adj)
                return max(dists.values()) if dists else 0

            start_id = max(pool, key=eccentricity)
            self._start_node_index += 1
            return start_id

        best_score = -1
        best_nodes: list[str] = []
        for cand in pool:
            if cand in occupied:
                continue
            score = min_graph_distance(cand, occupied, adj)
            if score > best_score:
                best_score = score
                best_nodes = [cand]
            elif score == best_score:
                best_nodes.append(cand)

        if not best_nodes:
            start_id = pool[self._start_node_index % len(pool)]
            self._start_node_index += 1
            return start_id

        order_rank = {nid: i for i, nid in enumerate(self._spawn_order)}
        best_nodes.sort(key=lambda n: order_rank.get(n, 999))
        start_id = best_nodes[self._start_node_index % len(best_nodes)]
        self._start_node_index += 1
        return start_id

    def load_from_text(self, txt_path) -> tuple:
        """Load a world from a .txt file.

        Auto-detects the format:
        - Structured format (paragraphs with nav verb exits) → existing parser
        - Free prose corpus → corpus generator (world_generator.py)

        Returns (json_path_or_None, node_count).
        """
        from world_generator import is_structured_format
        txt_path = Path(txt_path)
        src_text = txt_path.read_text(encoding="utf-8")

        if is_structured_format(src_text):
            # --- Original structured parser path ---
            from world_text_parser import convert_file as _cvt
            json_path = _cvt(txt_path)
            self.markov.train(src_text)
            self.world = None
            self._world_at_node = defaultdict(set)
            self.players = {}
            self._start_node_index = 0
            self._apply_world_quality(json_path)
            self.load_world(json_path)
            node_count = len(self.world.nodes) if self.world else 0
            return json_path, node_count
        else:
            # --- Corpus generator path ---
            return self.generate_from_corpus(txt_path, src_text=src_text)

    def generate_from_corpus(
        self,
        txt_path,
        src_text: str = None,
        node_count: int = 150,
    ) -> tuple:
        """Generate a world from a free-prose corpus file.

        Extracts locations, items and connections automatically.
        Stores a pool of latent nodes for on-demand discovery.
        Returns (json_path, node_count).
        """
        from world_generator import generate_world, extract_locations, extract_items
        import json as _json

        txt_path = Path(txt_path)
        if src_text is None:
            src_text = txt_path.read_text(encoding="utf-8")

        # Train Markov first so generate_world can use it
        # Reset chain so node text draws purely from the corpus vocabulary
        self.markov.reset()
        self.markov.train(src_text)

        world_dict, latent_nodes = generate_world(
            src_text, self.markov, node_count=node_count
        )

        self._report_progress("Sanity check…")
        from world_sanity import sanitize_world, sanitize_node_dict
        from world_log import diff_node_dicts
        before_gen = deepcopy(world_dict)
        world_dict = sanitize_world(world_dict)
        sanity_changes = diff_node_dicts(before_gen.get("nodes", []), world_dict.get("nodes", []))
        if sanity_changes:
            self.world_log.add_block("sanity", f"{len(sanity_changes)} rule fix(es)", sanity_changes)
        latent_nodes = [sanitize_node_dict(n) for n in latent_nodes]

        client = self._get_llm_client()
        llm_changes: list[str] = []
        if client.enabled:
            before_llm = deepcopy(world_dict)
            world_dict, llm_changes = client.review_world(
                world_dict, on_progress=self._report_progress,
            )
            if not llm_changes:
                llm_changes = diff_node_dicts(
                    before_llm.get("nodes", []), world_dict.get("nodes", []),
                )
            if llm_changes:
                self.world_log.add_block("llm", f"{len(llm_changes)} AI edit(s) on rebuild", llm_changes)
        self._last_review_had_changes = bool(sanity_changes or llm_changes)

        # Keep corpus pools for infinite, on-demand node generation
        self._corpus_text      = src_text
        self._corpus_locations = extract_locations(src_text, n=node_count + 40)
        self._corpus_items     = extract_items(src_text, self._corpus_locations)

        # Write generated JSON as a sidecar file
        json_path = txt_path.parent / (txt_path.stem + "_generated.json")
        json_path.write_text(
            _json.dumps(world_dict, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Clear state and load
        self.world = None
        self._world_at_node = defaultdict(set)
        self.players = {}
        self._start_node_index = 0
        self._latent_nodes: list = latent_nodes
        self._play_changed_nodes.clear()
        self._node_changes_since_spawn = 0
        self.load_world(json_path)

        node_count_actual = len(self.world.nodes) if self.world else 0
        return json_path, node_count_actual

    def _apply_world_quality(self, json_path) -> None:
        """Run sanity (+ optional LLM) on an on-disk world JSON before load."""
        import json as _json
        from world_sanity import sanitize_world

        path = Path(json_path)
        data = _json.loads(path.read_text(encoding="utf-8"))
        self._report_progress("Sanity check…")
        before = deepcopy(data)
        data = sanitize_world(data)
        from world_log import diff_node_dicts
        sanity_changes = diff_node_dicts(before.get("nodes", []), data.get("nodes", []))
        if sanity_changes:
            self.world_log.add_block("sanity", f"{len(sanity_changes)} rule fix(es)", sanity_changes)

        client = self._get_llm_client()
        llm_changes: list[str] = []
        if client.enabled:
            before_llm = deepcopy(data)
            data, llm_changes = client.review_world(
                data, on_progress=self._report_progress,
            )
            if not llm_changes:
                from world_log import diff_node_dicts
                llm_changes = diff_node_dicts(
                    before_llm.get("nodes", []), data.get("nodes", []),
                )
        self._last_review_had_changes = bool(sanity_changes or llm_changes)
        if llm_changes:
            self.world_log.add_block("llm", f"{len(llm_changes)} AI edit(s)", llm_changes)
        elif client.enabled:
            self.world_log.add("llm", "review complete — no changes")
        path.write_text(
            _json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _world_spawn_player(self, player_id: str) -> "PlayerState":
        start_id = self._pick_world_spawn_node()
        if start_id not in self.world.nodes:
            start_id = next(iter(self.world.nodes))
        self.world.nodes[start_id].visitors.add(player_id)
        state = PlayerState(player_id, start_id)
        self.players[player_id] = state
        self._world_at_node[start_id].add(player_id)
        # No encounter on spawn — give normal choices regardless of occupants
        self._build_world_choices(player_id)
        self._emit_graph_change(moved_player=player_id)
        return state

    def _world_reset_player(self, player_id: str) -> "PlayerState":
        if player_id in self.players:
            old = self.players[player_id].current_node
            self._world_at_node[old].discard(player_id)
            del self.players[player_id]
        return self._world_spawn_player(player_id)

    def _refresh_choices_for_world_player(self, player_id: str):
        """Show up to 2 ranked exits — best navigation pair for this visit."""
        state = self.players[player_id]
        node  = self.world.nodes[state.current_node]
        exits = [e for e in node.exits if e.to_node != state.current_node]
        if not exits:
            exits = list(node.exits)
        ranked = self._rank_exits_for_player(player_id, state.current_node, exits)
        state.current_links = [
            self._exit_for_display(ex) for ex in ranked[:2]
        ]

    def _title_words_in_label(self, title: str, label: str) -> bool:
        label_lower = label.lower()
        if title.replace("_", " ").lower() in label_lower:
            return True
        for w in title.split():
            if len(w) > 2 and w.lower() in label_lower:
                return True
        return False

    def _exit_navigation_score(
        self, player_id: str, from_node_id: str, exit: "ExitLink",
    ) -> tuple[int, int]:
        """Score an exit for sorting (higher = prefer showing first)."""
        state = self.players[player_id]
        hist = state.history
        dest = exit.to_node
        score = 0

        if dest not in hist:
            score += 3

        dest_node = self.world.nodes.get(dest) if self.world else None
        dest_title = dest_node.title if dest_node else dest.replace("_", " ")
        if self._title_words_in_label(dest_title, exit.label):
            score += 2

        came_from = None
        if len(hist) >= 2 and hist[-1] == from_node_id:
            came_from = hist[-2]

        if exit.label.strip().lower() == "return":
            score -= 2
        if came_from and dest == came_from:
            score -= 2

        recent = set(hist[-3:]) if len(hist) >= 3 else set(hist)
        if dest in recent and dest != from_node_id:
            score -= 1

        tie = hash((player_id, from_node_id, exit.to_node)) & 0xFFFF
        return score, tie

    def _rank_exits_for_player(
        self, player_id: str, from_node_id: str, exits: list,
    ) -> list:
        """History-aware exit order; rotates among ties on revisits."""
        if not exits:
            return exits
        state = self.players[player_id]
        scored = [
            (self._exit_navigation_score(player_id, from_node_id, ex), ex)
            for ex in exits
        ]
        scored.sort(key=lambda pair: (-pair[0][0], pair[0][1]))
        ranked = [ex for _, ex in scored]
        rot = state.exit_rotation.get(from_node_id, 0)
        if len(ranked) > 1 and rot:
            offset = rot % len(ranked)
            ranked = ranked[offset:] + ranked[:offset]
        return ranked

    def _display_exit_label(self, exit: "ExitLink") -> str:
        """Ensure the destination title is readable on the choice button."""
        if not self.world:
            return exit.label
        dest = self.world.nodes.get(exit.to_node)
        if not dest:
            return exit.label
        title = dest.title or exit.to_node.replace("_", " ")
        if self._title_words_in_label(title, exit.label):
            return exit.label
        return f"Go to {title}"

    def _exit_for_display(self, exit: "ExitLink") -> "ExitLink":
        label = self._display_exit_label(exit)
        if label == exit.label:
            return exit
        return ExitLink(exit.from_node, exit.to_node, label)

    def _choice_for_display(self, choice):
        """Apply display-only exit labels without mutating the world graph."""
        if getattr(choice, "choice_type", None) == "exit":
            return self._exit_for_display(choice)
        if getattr(choice, "choice_type", None) == "item":
            travel = getattr(choice, "travel_exit", None)
            if travel is not None:
                return ItemChoice(
                    choice.action, choice.item_id, choice.label,
                    travel_exit=self._exit_for_display(travel),
                )
        return choice

    def get_player_trace_text(self, player_id: str) -> str:
        """Trace strip: inventory or breadcrumb from previous location."""
        state = self.players.get(player_id)
        if not state:
            return ""
        if state.inventory:
            label = state.inventory_label or state.inventory
            return f"[carrying: {label}]"
        if self.world and len(state.history) >= 2:
            prev_id = state.history[-2]
            prev = self.world.nodes.get(prev_id)
            title = prev.title if prev else prev_id.replace("_", " ")
            return f"from: {title}"
        node_trace = self.get_trace(state.current_node)
        return node_trace or ""

    def _effective_spawn_every(self) -> int:
        """Gallery pace lowers threshold as more players join."""
        if not self.gallery_pace:
            return self.spawn_every_node_changes
        n = max(1, len(self.players))
        return max(3, self.spawn_every_node_changes - (n - 1))

    def _effective_drift_rate(self) -> int:
        """Gallery pace: faster drift when 4+ players and slider is above 1."""
        if self.gallery_pace and len(self.players) >= 4 and self._drift_rate > 1:
            return 1
        return self._drift_rate

    def gallery_idle_seconds_remaining(self) -> int:
        """Seconds until an idle gallery spawn may fire."""
        if not self.gallery_pace:
            return IDLE_SPAWN_SEC
        elapsed = time.time() - self._last_spawn_time
        return max(0, int(IDLE_SPAWN_SEC - elapsed))

    def tick_gallery_idle(self) -> int:
        """Periodic check for idle gallery spawn (call from UI timer)."""
        return self._maybe_gallery_idle_spawn()

    def _maybe_gallery_idle_spawn(self) -> int:
        if not self.gallery_pace or not self.world or not self.players:
            return 0
        if time.time() - self._last_spawn_time < IDLE_SPAWN_SEC:
            return 0
        occupied = [
            p.current_node for p in self.players.values()
            if p.current_node in self.world.nodes
        ]
        if not occupied:
            return 0
        from_node = random.choice(occupied)
        self.world_log.add("spawn", "idle gallery spawn")
        return self._spawn_from_play(from_node_id=from_node)

    def _title_mentioned_in_text(self, title: str, body: str) -> bool:
        body_lower = body.lower()
        for w in title.split():
            if len(w) > 2 and w.lower() in body_lower:
                return True
        return title.replace("_", " ").lower() in body_lower

    def _neighbor_titles_for_node(self, node_id: str) -> list[str]:
        if not self.world or node_id not in self.world.nodes:
            return []
        titles: list[str] = []
        for ex in self.world.nodes[node_id].exits:
            if ex.to_node == node_id:
                continue
            dest = self.world.nodes.get(ex.to_node)
            titles.append(dest.title if dest else ex.to_node.replace("_", " "))
        return titles

    def _visible_destination_titles(self, player_id: str) -> list[str]:
        """Destination titles matching the player's current choice buttons."""
        state = self.players.get(player_id)
        if not state or not self.world:
            return []
        titles: list[str] = []
        seen: set[str] = set()
        for c in state.current_links[:2]:
            dest_id = None
            if getattr(c, "choice_type", None) == "exit":
                dest_id = c.to_node
            elif getattr(c, "choice_type", None) == "item":
                travel = getattr(c, "travel_exit", None)
                if travel is not None:
                    dest_id = travel.to_node
            if not dest_id or dest_id in seen:
                continue
            seen.add(dest_id)
            dest = self.world.nodes.get(dest_id)
            titles.append(dest.title if dest else dest_id.replace("_", " "))
        if titles:
            return titles[:2]
        node_id = state.current_node
        exits = [
            e for e in self.world.nodes[node_id].exits
            if e.to_node != node_id
        ]
        if not exits:
            exits = list(self.world.nodes[node_id].exits)
        ranked = self._rank_exits_for_player(player_id, node_id, exits)
        for ex in ranked[:2]:
            dest = self.world.nodes.get(ex.to_node)
            titles.append(dest.title if dest else ex.to_node.replace("_", " "))
        return titles[:2]

    def get_orientation_hint(self, player_id: str) -> str | None:
        """One-line display hint naming where current choices lead."""
        state = self.players.get(player_id)
        if not state or not self.world:
            return None
        node = self.world.nodes.get(state.current_node)
        if not node:
            return None
        dest_titles = self._visible_destination_titles(player_id)
        if not dest_titles:
            return None
        body = node.current_text
        if all(self._title_mentioned_in_text(t, body) for t in dest_titles):
            return None
        if len(dest_titles) == 1:
            return f"Paths: {dest_titles[0]}."
        return f"Paths: {dest_titles[0]} · {dest_titles[1]}."

    def get_display_text_for_player(self, player_id: str) -> str:
        """Node body plus optional beat line and orientation hint (display-only)."""
        state = self.players.get(player_id)
        if not state:
            return ""
        base = self.get_display_text(state.current_node)
        parts = base.split("\n\n")
        if len(parts) > DISPLAY_TEXT_MAX_PARAS:
            base = "\n\n".join(parts[:DISPLAY_TEXT_MAX_PARAS])

        if state.choice_beat:
            beat = state.choice_beat
            state.choice_beat = None
            body = f"{beat}\n\n{base.rstrip()}"
        else:
            body = base.rstrip()

        if not self.world:
            return body
        hint = self.get_orientation_hint(player_id)
        if hint:
            return f"{body}\n\n{hint}"
        return body

    def _build_world_choices(self, player_id: str):
        """Build exactly 2 choices for a world-mode player.

        Priority: item interactions first, exits as fill.
          - Present items in the node  → "Take …"
          - Carried item               → "Use … here"  (when item words overlap
                                         node text/tags) or "Leave … here"
          - Exits                      → fallback filler
        """
        state = self.players[player_id]
        node  = self.world.nodes[state.current_node]

        item_pool: list = []

        # Take choices — for each item currently present in this node
        for item_id, info in node.items.items():
            if info["present"] and state.inventory is None:
                item_pool.append(ItemChoice("take", item_id, f"Take {info['label']}"))

        # Inventory choice — player is carrying something
        if state.inventory is not None:
            inv_id    = state.inventory
            inv_label = state.inventory_label or f"the {inv_id}"
            # Use if item words appear in node text/tags; otherwise leave
            inv_words  = set(inv_id.lower().split())
            node_words = set(
                w.lower().rstrip(".,!?") for w in
                (node.current_text + " " + " ".join(node.tags)).split()
            ) - {"the", "a", "an", "of", "in", "on", "is", "at"}
            if inv_words & node_words:
                action, label = "use",   f"Use {inv_label} here"
            else:
                action, label = "leave", f"Drop {inv_label} and go"
            item_pool.append(ItemChoice(action, inv_id, label))

        # Exit choices (exclude exact self-loops unless no other exits exist)
        exits = [e for e in node.exits if e.to_node != state.current_node]
        if not exits:
            exits = list(node.exits)
        ranked = self._rank_exits_for_player(player_id, state.current_node, exits)

        # Selection: always 2 — prefer 1 item + 1 exit when both are available.
        chosen: list = []
        if item_pool and ranked:
            chosen = [item_pool[0], ranked[0]]
        elif item_pool:
            chosen.append(item_pool[0])
        else:
            chosen = ranked[:2]

        # Pad with exits — never offer two item-only slots when navigation exists
        if ranked:
            for ex in ranked:
                if len(chosen) >= 2:
                    break
                if ex not in chosen:
                    chosen.append(ex)
            if not any(getattr(c, "choice_type", None) == "exit" for c in chosen):
                chosen = ranked[:2]
            elif len(chosen) == 2 and getattr(chosen[1], "choice_type", None) == "item":
                for ex in ranked:
                    if ex not in chosen:
                        chosen[1] = ex
                        break

        # If stuck with one choice, spawn a new exit immediately
        if len(chosen) < 2:
            self._maybe_spawn_from_play(from_node_id=state.current_node, force=True)
            node = self.world.nodes[state.current_node]
            exits = [e for e in node.exits if e.to_node != state.current_node]
            if not exits:
                exits = list(node.exits)
            ranked = self._rank_exits_for_player(player_id, state.current_node, exits)
            for ex in ranked:
                if len(chosen) >= 2:
                    break
                if ex not in chosen:
                    chosen.append(ex)

        chosen = self._finalize_item_travel(chosen, ranked, state.current_node)
        state.current_links = [
            self._choice_for_display(c) for c in chosen[:2]
        ]

    def _finalize_item_travel(self, chosen: list, exits: list, node_id: str) -> list:
        """Ensure every ItemChoice has a valid travel_exit paired with an exit choice."""
        chosen = list(chosen[:2])

        has_item = any(getattr(c, "choice_type", None) == "item" for c in chosen)
        exit_in_chosen = [
            c for c in chosen if getattr(c, "choice_type", None) == "exit"
        ]

        if has_item and not exit_in_chosen:
            for ex in exits:
                if ex not in chosen:
                    if len(chosen) < 2:
                        chosen.append(ex)
                    else:
                        chosen[1] = ex
                    break

        if has_item and not any(getattr(c, "choice_type", None) == "exit" for c in chosen):
            fallback = self._synthesize_fallback_exit(node_id)
            if fallback:
                if len(chosen) < 2:
                    chosen.append(fallback)
                else:
                    chosen[1] = fallback

        for i, c in enumerate(chosen):
            if getattr(c, "choice_type", None) != "item":
                continue
            companion = None
            for j, other in enumerate(chosen):
                if j != i and getattr(other, "choice_type", None) == "exit":
                    companion = other
                    break
            if companion is None:
                for ex in exits:
                    if ex not in chosen or ex is c:
                        companion = ex
                        break
            c.travel_exit = companion

        return chosen[:2]

    def _synthesize_fallback_exit(self, node_id: str) -> "ExitLink | None":
        """Last-resort exit when a node has no usable exits (item travel fail-safe)."""
        if not self.world:
            return None
        node = self.world.nodes.get(node_id)
        if node:
            candidates = [e for e in node.exits if e.to_node in self.world.nodes]
            if candidates:
                return random.choice(candidates)
        others = [nid for nid in self.world.nodes if nid != node_id]
        if not others:
            return None
        dest = random.choice(others)
        return ExitLink(from_node=node_id, to_node=dest, label=f"Go to {dest.replace('_', ' ')}")

    def _node_to_review_dict(self, node: "WorldNode") -> dict:
        """Export a live world node as JSON for sanity/LLM review."""
        return {
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
        }

    def _apply_reviewed_node_dict(self, nd: dict):
        """Apply LLM/sanity edits back onto a live world node."""
        node = self.world.nodes.get(nd.get("id", ""))
        if not node:
            return
        text = (nd.get("text") or nd.get("description") or "").strip()
        if text and text != node.current_text.strip():
            node.current_text = text
            node._sync_text_alias()
        exit_by_dest = {e.to_node: e for e in node.exits}
        for ex in nd.get("exits", []):
            dest = ex.get("to")
            if dest in exit_by_dest and ex.get("label"):
                exit_by_dest[dest].label = ex["label"]

    def _next_latent_node(self) -> dict | None:
        """Next node to add: latent pool first, then Markov-generated."""
        from world_sanity import sanitize_node_dict
        if self._latent_nodes:
            return sanitize_node_dict(self._latent_nodes.pop(0))
        latent = self._generate_fresh_latent()
        return sanitize_node_dict(latent) if latent else None

    def _on_play_node_changed(self, node_id: str, reason: str):
        """Track drift/item rewrites; spawn when threshold reached."""
        if not self.world or node_id not in self.world.nodes:
            return
        reasons = self._play_changed_nodes.setdefault(node_id, [])
        if reason not in reasons:
            reasons.append(reason)
        self._node_changes_since_spawn += 1
        self._mark_node_for_llm_polish(node_id, reason)
        self._maybe_spawn_from_play()

    def _maybe_spawn_from_play(
        self, from_node_id: str | None = None, force: bool = False,
    ) -> int:
        """After enough node changes, add a Markov location immediately (LLM later)."""
        if not self.world:
            return 0
        threshold = self._effective_spawn_every()
        if not force and self._node_changes_since_spawn < threshold:
            if self.gallery_pace:
                return self._maybe_gallery_idle_spawn()
            return 0
        return self._spawn_from_play(from_node_id=from_node_id)

    def _cancel_llm_coalesce_timer(self):
        with self._llm_lock:
            if self._llm_timer:
                self._llm_timer.cancel()
                self._llm_timer = None

    def _mark_node_for_llm_polish(self, node_id: str, reason: str):
        """Debounce: queue node text for a background LLM fix (does not block play)."""
        if not self._get_llm_client().enabled or not self.world:
            return
        if node_id not in self.world.nodes:
            return
        snap = deepcopy(self._node_to_review_dict(self.world.nodes[node_id]))
        with self._llm_lock:
            entry = self._llm_pending.setdefault(node_id, {"reasons": []})
            entry["dict"] = snap
            if reason not in entry["reasons"]:
                entry["reasons"].append(reason)
            if self._llm_timer:
                self._llm_timer.cancel()
            self._llm_timer = threading.Timer(
                LLM_COALESCE_SEC, self._flush_llm_coalesce,
            )
            self._llm_timer.daemon = True
            self._llm_timer.start()

    def _flush_llm_coalesce(self):
        """Fire a background polish for all nodes touched since last flush."""
        with self._llm_lock:
            pending = dict(self._llm_pending)
            self._llm_pending.clear()
            self._llm_timer = None
        if not pending:
            return
        node_dicts = [e["dict"] for e in pending.values()]
        change_reasons = {nid: e["reasons"] for nid, e in pending.items()}
        neighbor_titles = {
            nid: self._neighbor_titles_for_node(nid) for nid in pending.keys()
        }
        self._submit_llm_job(
            node_dicts,
            {
                "play_session": True,
                "fix_markov_only": True,
                "change_reasons": change_reasons,
                "recent_item_events": list(self._recent_item_events[-15:]),
                "neighbor_titles": neighbor_titles,
            },
            label=f"polish {len(node_dicts)} node(s)",
        )

    def _submit_llm_job(
        self, node_dicts: list[dict], context: dict, label: str,
        refresh_from: str | None = None, new_node_ids: list[str] | None = None,
    ):
        """Enqueue an LLM review; results applied on the main thread when ready."""
        client = self._get_llm_client()
        if not client.enabled:
            return
        provider = "OpenAI" if client.mode == "openai" else client.mode.title()
        self.world_log.add("llm", f"{provider} queued — {label} (background)")
        self._report_progress(f"{provider} queued — {label}")
        self._llm_job_queue.put({
            "node_dicts": deepcopy(node_dicts),
            "context": deepcopy(context),
            "label": label,
            "refresh_from": refresh_from,
            "new_node_ids": new_node_ids or [],
            "llm_mode": self.llm_mode,
            "llm_model": self.llm_model,
            "llm_ollama_url": self.llm_ollama_url,
            "provider": provider,
        })

    def _llm_worker_loop(self):
        while True:
            job = self._llm_job_queue.get()
            if job is None:
                return
            self._run_llm_job(job)

    def _run_llm_job(self, job: dict):
        from llm_client import LLMClient
        client = LLMClient(
            mode=job["llm_mode"],
            model=job["llm_model"],
            ollama_url=job["llm_ollama_url"],
        )
        t0 = time.perf_counter()
        try:
            reviewed, changes = client.review_nodes(job["node_dicts"], job["context"])
            elapsed = time.perf_counter() - t0
            self._schedule_main(lambda: self._apply_llm_job_result(
                reviewed, changes, job, elapsed, error=None,
            ))
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            self._schedule_main(lambda: self._apply_llm_job_result(
                job["node_dicts"], [], job, elapsed, error=str(exc),
            ))

    def _apply_llm_job_result(
        self,
        node_dicts: list[dict],
        llm_changes: list[str],
        job: dict,
        elapsed: float,
        error: str | None,
    ):
        provider = job.get("provider", "LLM")
        label = job.get("label", "review")
        if error:
            self.world_log.add("llm", f"{provider} failed ({elapsed:.1f}s): {error}")
            self._report_progress(f"{provider} failed")
            return

        self.world_log.add("llm", f"{provider} done in {elapsed:.1f}s — {label}")
        self._report_progress(f"{provider} done ({elapsed:.1f}s)")

        if not self.world:
            return

        graph_dirty = False
        players_on_changed: set[str] = set()
        for nd in node_dicts:
            nid = nd.get("id")
            if not nid or nid not in self.world.nodes:
                continue
            before = self.world.nodes[nid].current_text
            self._apply_reviewed_node_dict(nd)
            if self.world.nodes[nid].current_text.strip() != before.strip():
                graph_dirty = True
                for pid, pstate in self.players.items():
                    if pstate.current_node == nid:
                        players_on_changed.add(pid)

        if llm_changes:
            self.world_log.add_block(
                "llm", f"{label} — {len(llm_changes)} edit(s)", llm_changes,
            )
        elif node_dicts:
            from world_log import diff_node_dicts
            before_snap = job.get("node_dicts", [])
            diff = diff_node_dicts(before_snap, node_dicts)
            if diff:
                self.world_log.add_block(
                    "llm", f"{label} — {len(diff)} edit(s)", diff,
                )

        refresh_from = job.get("refresh_from")
        if refresh_from:
            for pid, pstate in list(self.players.items()):
                if pstate.current_node == refresh_from:
                    self._build_world_choices(pid)
                    players_on_changed.add(pid)

        for pid in players_on_changed:
            self._emit_graph_change(moved_player=pid)
        if graph_dirty and not players_on_changed:
            self._emit_graph_change(canvas_only=True)

    def _pick_spawn_from_node(self) -> str:
        """Bias new locations toward nodes players occupy or recently changed."""
        if not self.world:
            return ""
        occupied = {nid for nid, pids in self._world_at_node.items() if pids}
        if self._play_changed_nodes:
            changed = [nid for nid in self._play_changed_nodes if nid in occupied]
            if changed:
                return random.choice(changed)
            return next(reversed(self._play_changed_nodes))
        if occupied:
            return random.choice(list(occupied))
        if self.players:
            return next(iter(self.players.values())).current_node
        return random.choice(list(self.world.nodes.keys()))

    def _spawn_from_play(self, from_node_id: str | None = None) -> int:
        """Add a Markov location immediately; LLM polishes text in the background."""
        if not self.world:
            return 0

        if len(self.world.nodes) >= self.max_world_nodes:
            self.world_log.add(
                "spawn",
                f"skipped — node cap ({self.max_world_nodes})",
            )
            return 0

        if from_node_id is None or from_node_id not in self.world.nodes:
            from_node_id = self._pick_spawn_from_node()

        if from_node_id not in self.world.nodes:
            from_node_id = random.choice(list(self.world.nodes.keys()))

        new_latent = self._next_latent_node()
        if new_latent is None:
            self.world_log.add("spawn", "skipped — no corpus for new nodes")
            return 0

        changed_ids = list(self._play_changed_nodes.keys()) or [from_node_id]
        change_reasons = {
            nid: list(self._play_changed_nodes.get(nid, []))
            for nid in changed_ids
        }
        changes_at_spawn = self._node_changes_since_spawn

        from world_sanity import sanitize_node_list
        nodes_by_id = {n.id: n for n in self.world.nodes.values()}
        new_latent = sanitize_node_list(
            [new_latent],
            nodes_by_id={
                nid: {"id": nid, "title": n.title}
                for nid, n in self.world.nodes.items()
            },
        )[0]

        promoted_id = new_latent["id"]
        added = self._promote_latent_node(new_latent, from_node_id)
        if not added:
            return 0

        self._last_spawn_time = time.time()

        self.world_log.add(
            "spawn",
            f"new location «{new_latent.get('title', promoted_id)}» "
            f"← exit from {from_node_id} (after {changes_at_spawn} text changes, Markov text)",
        )

        self._play_changed_nodes.clear()
        self._node_changes_since_spawn = 0

        for pid, pstate in list(self.players.items()):
            if pstate.current_node == from_node_id:
                self._build_world_choices(pid)

        self._emit_graph_change()

        # Background LLM: polish changed nodes + the new location (players need not wait)
        with self._llm_lock:
            self._llm_pending.clear()
            if self._llm_timer:
                self._llm_timer.cancel()
                self._llm_timer = None

        llm_nodes: list[dict] = []
        llm_reasons: dict[str, list[str]] = {}
        for nid in changed_ids:
            if nid not in self.world.nodes:
                continue
            llm_nodes.append(deepcopy(self._node_to_review_dict(self.world.nodes[nid])))
            llm_reasons[nid] = change_reasons.get(nid, [])
        if promoted_id in self.world.nodes:
            llm_nodes.append(deepcopy(self._node_to_review_dict(self.world.nodes[promoted_id])))
            llm_reasons[promoted_id] = ["new location"]

        neighbor_titles = {
            nd.get("id", ""): self._neighbor_titles_for_node(nd.get("id", ""))
            for nd in llm_nodes if nd.get("id")
        }

        if llm_nodes:
            self._submit_llm_job(
                llm_nodes,
                {
                    "play_session": True,
                    "fix_markov_only": True,
                    "change_reasons": llm_reasons,
                    "recent_item_events": list(self._recent_item_events[-15:]),
                    "spawn_from": from_node_id,
                    "new_node_id": promoted_id,
                    "neighbor_titles": neighbor_titles,
                },
                label=f"spawn polish ({len(llm_nodes)} node(s))",
                refresh_from=from_node_id,
                new_node_ids=[promoted_id],
            )

        try:
            from world_archive import save_session
            save_session(self)
        except Exception:
            pass

        return added

    def _promote_latent_node(self, latent_data: dict, from_node_id: str) -> int:
        """Add one reviewed latent node to the world and wire an exit from from_node_id."""
        if not self.world or from_node_id not in self.world.nodes:
            return 0

        node_id = latent_data["id"]
        if node_id in self.world.nodes:
            node_id = f"{node_id}_d{self._fresh_node_counter}"
            latent_data = dict(latent_data)
            latent_data["id"] = node_id
            self._fresh_node_counter += 1

        label_dest = latent_data.get("title", node_id).replace("_", " ")
        label = f"Go to {label_dest}"

        back_label = "Return"
        exits_back = [ExitLink(from_node=node_id, to_node=from_node_id, label=back_label)]
        existing = [
            nid for nid in self.world.nodes
            if nid != from_node_id and nid != node_id
        ]
        if existing:
            second_dest = random.choice(existing)
            exits_back.append(ExitLink(
                from_node=node_id,
                to_node=second_dest,
                label=f"Go to {second_dest.replace('_', ' ')}",
            ))

        desc = latent_data.get("text", latent_data.get("description", ""))
        new_node = WorldNode(
            node_id=node_id,
            title=latent_data.get("title", node_id),
            description=desc,
            exits=exits_back,
            tags=latent_data.get("tags", []),
        )
        from world_sanity import filter_carryable_items
        for item_name in filter_carryable_items(latent_data.get("items", [])):
            lbl = (item_name if item_name.lower().startswith(("the ", "a ", "an "))
                   else f"the {item_name}")
            new_node.items[item_name] = {"label": lbl, "present": True}
        new_node._items_base = {k: dict(v) for k, v in new_node.items.items()}
        self.world.nodes[node_id] = new_node
        new_node.pregenerated_choices = self.generate_interaction_choices(node_id)

        from_node = self.world.nodes[from_node_id]
        from_node.exits.append(
            ExitLink(from_node=from_node_id, to_node=node_id, label=label)
        )
        return 1

    def _get_llm_client(self):
        from llm_client import LLMClient
        return LLMClient(
            mode=self.llm_mode,
            model=self.llm_model,
            ollama_url=self.llm_ollama_url,
        )

    def _report_progress(self, msg: str):
        if self.on_world_progress:
            self.on_world_progress(msg)

    def spawn_now(self) -> int:
        """Manual spawn from control panel (ignores change counter)."""
        if not self.world:
            self.world_log.add("discovery", "spawn requested — no world loaded")
            return 0
        return self._spawn_from_play()

    def _generate_fresh_latent(self) -> dict | None:
        """Synthesize a brand-new node dict from the corpus."""
        if not self._corpus_locations:
            return None
        from world_generator import generate_node_text, _slugify

        loc_name = random.choice(self._corpus_locations)
        self._fresh_node_counter += 1
        base_id = _slugify(loc_name)
        node_id = f"{base_id}_{self._fresh_node_counter}"
        body = generate_node_text(self.markov, loc_name, n_sentences=3)
        items = []
        if self._corpus_items and random.random() < 0.5:
            from world_sanity import is_carryable
            pool = [(i, l) for i, l in self._corpus_items if is_carryable(i)]
            if pool:
                items = [random.choice(pool)[0]]
        return {
            "id":          node_id,
            "title":       loc_name.title(),
            "text":        body,
            "description": body,
            "tags":        [w for w in loc_name.split() if len(w) > 2][:4],
            "exits":       [],
            "items":       items,
        }

    def generate_interaction_choices(self, node_id: str) -> list:
        """Generate 2 interaction choices seeded from node text and tags."""
        node = self.world.nodes[node_id]
        choices = []
        used = ""
        for _ in range(2):
            label = self._gen_label_from_node(node.text, exclude_phrase=used)
            if node.tags:
                seeded = self._markov_seeded_generate(
                    node.tags[:3] + label.split(), length=self.choice_len
                )
                words = seeded.split()[:self.choice_len]
                if words:
                    words[-1] = words[-1].rstrip(".!?,;:")
                seeded_label = " ".join(words)
                if seeded_label:
                    seeded_label = seeded_label[0].upper() + seeded_label[1:]
                label = seeded_label or label
            used = label
            choices.append(InteractionChoice(label=label))
        return choices

    def apply_interaction(self, player_id: str, choice: "InteractionChoice") -> "PlayerState":
        """Player acts on something in the current node — generates and appends reaction text."""
        state = self.players[player_id]
        node  = self.world.nodes[state.current_node]
        seed_words = node.tags + choice.label.split()
        reaction   = self._markov_seeded_generate(
            seed_words, length=max(10, self.text_len // 2)
        )
        if reaction:
            reaction = reaction[0].upper() + reaction[1:]
            node.traces.append(reaction)
            if len(node.traces) > 5:
                node.traces.pop(0)
            self.world_log.add(
                "interact",
                f"{player_id} @ {state.current_node}: «{choice.label}» → {reaction[:120]}",
            )
        node.interaction_count += 1
        node_id = state.current_node
        if node_id not in state.taken_interactions:
            state.taken_interactions[node_id] = set()
        state.taken_interactions[node_id].add(choice.label)
        self._build_world_choices(player_id)
        self._emit_graph_change(moved_player=player_id)
        return state

    def take_item(self, player_id: str, item_id: str, *, rebuild: bool = True) -> "PlayerState":
        """Player picks up an item from the current node."""
        state = self.players[player_id]
        node  = self.world.nodes[state.current_node]
        if item_id not in node.items:
            return state
        node.items[item_id]["present"] = False
        state.inventory       = item_id
        state.inventory_label = node.items[item_id]["label"]
        self._item_absent_rewrite(node, item_id, state.inventory_label)
        self._record_item_event(state.current_node, f"took {item_id}")
        if rebuild:
            self._build_world_choices(player_id)
            self._emit_graph_change(moved_player=player_id)
        return state

    def leave_item(self, player_id: str, *, rebuild: bool = True) -> "PlayerState":
        """Player leaves their carried item at the current node."""
        state     = self.players[player_id]
        item_id   = state.inventory
        item_label = state.inventory_label
        if item_id is None:
            return state
        node = self.world.nodes[state.current_node]
        # Place item in current node (may be a node that didn't originally have it)
        if item_id in node.items:
            node.items[item_id]["present"] = True
        else:
            node.items[item_id] = {"label": item_label, "present": True}
        state.inventory       = None
        state.inventory_label = None
        self._item_present_rewrite(node, item_id, item_label)
        self._record_item_event(state.current_node, f"left {item_id}")
        if rebuild:
            self._build_world_choices(player_id)
            self._emit_graph_change(moved_player=player_id)
        return state

    def _use_item(self, player_id: str, item_id: str, *, rebuild: bool = True) -> "PlayerState":
        """Use a carried item at this node — clears inventory and rewrites node text."""
        state = self.players[player_id]
        if state.inventory != item_id:
            return state
        node = self.world.nodes[state.current_node]
        item_label = state.inventory_label or f"the {item_id}"
        state.inventory = None
        state.inventory_label = None
        seed_words = item_id.split() + node.tags + ["used", "here"]
        reaction = self._markov_seeded_generate(
            seed_words, length=max(10, self.text_len // 2)
        )
        if reaction:
            reaction = reaction[0].upper() + reaction[1:]
            node.traces.append(reaction)
            if len(node.traces) > 5:
                node.traces.pop(0)
            node._sync_text_alias()
        if rebuild:
            self._build_world_choices(player_id)
            self._emit_graph_change(moved_player=player_id)
        return state

    def _record_item_event(self, node_id: str, action: str):
        msg = f"{node_id}: {action}"
        self._recent_item_events.append(msg)
        if len(self._recent_item_events) > 20:
            self._recent_item_events.pop(0)
        self.world_log.add("item", msg)

    def _log_node_text_change(self, node_id: str, reason: str, before: str, after: str):
        if before.strip() == after.strip():
            return
        self.world_log.add_block(
            f"node/{node_id}",
            f"{reason} — text updated",
            [f"− {before.strip()[:400]}", f"+ {after.strip()[:400]}"],
        )
        self._on_play_node_changed(node_id, reason)

    def _companion_exit(self, choices: list, chosen) -> "ExitLink | None":
        """The navigation choice shown alongside an item button."""
        travel = getattr(chosen, "travel_exit", None)
        if travel is not None and travel.to_node in self.world.nodes:
            return travel
        for c in choices:
            if c is chosen:
                continue
            if getattr(c, "choice_type", None) == "exit" and c.to_node in self.world.nodes:
                return c
        return None

    def _world_travel(self, player_id: str, target_id: str) -> "PlayerState":
        """Move a world-mode player to target_id (drift, encounters, new choices)."""
        state = self.players[player_id]
        if target_id not in self.world.nodes:
            return state
        from_id = state.current_node
        if from_id == target_id:
            self._build_world_choices(player_id)
            self._emit_graph_change(moved_player=player_id)
            return state

        self.world_log.add(
            "travel", f"{player_id}: {from_id} → {target_id}",
        )

        from_node = self.world.nodes.get(from_id)
        if from_node:
            n_exits = len([
                e for e in from_node.exits if e.to_node != from_id
            ])
            if n_exits >= 3:
                state.exit_rotation[from_id] = state.exit_rotation.get(from_id, 0) + 1

        self.on_player_leave(from_id, player_id)
        self._world_at_node[from_id].discard(player_id)
        target_node = self.world.nodes[target_id]
        target_node.visitors.add(player_id)
        others_here = self._world_at_node[target_id] - {player_id}
        is_encounter = bool(others_here)
        self._world_at_node[target_id].add(player_id)
        state.current_node = target_id
        state.history.append(target_id)
        dest = self.world.nodes[target_id]
        title = (dest.title or target_id).replace("_", " ")
        state.choice_beat = f"Toward {title}."
        if is_encounter:
            self._apply_encounter(target_id, player_id, others_here)
        else:
            state.status = STATUS_ACTIVE
            self._build_world_choices(player_id)
            self._emit_graph_change(moved_player=player_id)
        return state

    def _resolve_item_choice(self, player_id: str, chosen: "ItemChoice",
                             choices: list) -> "PlayerState":
        """Apply take/leave/use, then travel so item picks always advance the story."""
        if chosen.action == "take":
            self.take_item(player_id, chosen.item_id, rebuild=False)
        elif chosen.action == "use":
            self._use_item(player_id, chosen.item_id, rebuild=False)
        else:
            self.leave_item(player_id, rebuild=False)

        exit_c = self._companion_exit(choices, chosen)
        if exit_c is not None and exit_c.to_node in self.world.nodes:
            return self._world_travel(player_id, exit_c.to_node)

        state = self.players[player_id]
        node = self.world.nodes[state.current_node]
        for c in choices:
            if getattr(c, "choice_type", None) == "exit" and c.to_node in self.world.nodes:
                return self._world_travel(player_id, c.to_node)

        fallback = [
            e for e in node.exits
            if e.to_node in self.world.nodes and e.to_node != state.current_node
        ]
        if not fallback:
            fallback = [e for e in node.exits if e.to_node in self.world.nodes]
        if fallback:
            return self._world_travel(player_id, random.choice(fallback).to_node)

        synth = self._synthesize_fallback_exit(state.current_node)
        if synth and synth.to_node in self.world.nodes:
            return self._world_travel(player_id, synth.to_node)

        self._build_world_choices(player_id)
        self._emit_graph_change(moved_player=player_id)
        return state

    def _world_make_choice(self, player_id: str, choice_index: int) -> "PlayerState":
        state   = self.players[player_id]
        choices = state.current_links
        if not choices or choice_index >= len(choices):
            return state
        # Block move if locked in an encounter
        if state.status == STATUS_ENCOUNTER:
            return state
        chosen = choices[choice_index]
        if hasattr(chosen, 'choice_type') and chosen.choice_type == "interact":
            return self.apply_interaction(player_id, chosen)
        # Item interaction (take / leave / use) — always travel afterward when possible
        if getattr(chosen, 'choice_type', None) == "item":
            return self._resolve_item_choice(player_id, chosen, choices)
        # Navigation (exit choice)
        target_id = chosen.to_node
        if target_id not in self.world.nodes:
            return state
        return self._world_travel(player_id, target_id)

    # ------------------------------------------------------------------
    # Drift, traces, co-presence
    # ------------------------------------------------------------------

    _SENT_SPLIT = re.compile(r'(?<=[.!?])\s+|\n\n+')

    def on_player_leave(self, node_id: str, player_id: str):
        """Called every time a player departs a node. Triggers drift + trace."""
        node = self.world.nodes.get(node_id)
        if node is None:
            return
        node.drift += 1
        drift_rate = self._effective_drift_rate()
        if int(node.drift) % drift_rate == 0:
            self._drift_rewrite(node)
        self._generate_trace(node)

    def _drift_rewrite(self, node: "WorldNode"):
        """Replace one sentence in current_text with a Markov variation."""
        sentences = self._SENT_SPLIT.split(node.current_text.strip())
        if not sentences:
            return
        # Weight: avoid first and last sentence changing too fast
        n = len(sentences)
        if n == 1:
            weights = [1.0]
        else:
            weights = [0.5] + [1.0] * max(0, n - 2) + [0.5]
        total = sum(weights)
        r = random.uniform(0, total)
        cumul = 0.0
        idx = 0
        for i, w in enumerate(weights):
            cumul += w
            if r <= cumul:
                idx = i
                break

        chosen = sentences[idx]
        chosen_words = chosen.split()
        target_len = max(6, len(chosen_words))

        # Seed: tail of chosen sentence + start of next + node tags + traces
        seed_words = chosen_words[-4:]
        if idx + 1 < len(sentences):
            seed_words += sentences[idx + 1].split()[:2]
        seed_words += node.tags
        if node.traces:
            seed_words += node.traces[-1].split()[:3]

        variation = self._markov_seeded_generate(seed_words, length=target_len)
        if not variation:
            return
        # Trim to first sentence only — prevents text from growing on each visit
        variation = self._SENT_SPLIT.split(variation)[0].strip()
        if not variation:
            return
        if variation[-1] not in '.!?':
            variation = variation.rstrip('.!?, ') + '.'

        sentences[idx] = variation
        before = node.current_text
        node.current_text = '\n\n'.join(sentences)
        node._sync_text_alias()
        self._log_node_text_change(node.id, f"drift (visit {int(node.drift)})", before, node.current_text)
        # Feed rewritten sentence back into chain
        self._feed_back(variation)

    def _generate_trace(self, node: "WorldNode"):
        """Generate a short fragment from the departing node and store it."""
        sentences = self._SENT_SPLIT.split(node.current_text.strip())
        seed_words = sentences[-1].split() if sentences else []
        seed_words += random.sample(
            self._ENCOUNTER_WORDS, min(2, len(self._ENCOUNTER_WORDS))
        )
        fragment = self._markov_seeded_generate(seed_words, length=10)
        if not fragment:
            return
        if not fragment[-1] in '.!?':
            fragment = fragment.rstrip('.!?, ') + '.'
        node.traces.append(fragment)
        if len(node.traces) > 5:
            node.traces.pop(0)

    def get_trace(self, node_id: str) -> str | None:
        """Return the most recent trace fragment for a node, or None."""
        node = self.world.nodes.get(node_id) if self.world else None
        if node and node.traces:
            return node.traces[-1]
        return None

    def _item_absent_rewrite(self, node: "WorldNode", item_id: str, item_label: str):
        """Rewrite node text to reflect that an item has been taken away."""
        item_words = (
            set(item_id.lower().split()) |
            {w.lower() for w in item_label.split() if w.lower() not in {"the", "a", "an"}}
        )
        sentences = self._SENT_SPLIT.split(node.current_text.strip())
        # Find the first sentence that mentions the item
        target_idx = None
        for i, s in enumerate(sentences):
            s_words = {w.lower().rstrip(".,!?;:") for w in s.split()}
            if item_words & s_words:
                target_idx = i
                break
        # Only rewrite if the item is actually mentioned — never append
        if target_idx is None:
            return
        absent_seeds = list(item_words) + ["gone", "missing", "taken", "no", "longer"]
        variation = self._markov_seeded_generate(absent_seeds, length=8)
        if not variation:
            variation = f"The {item_label} is gone."
        else:
            variation = self._SENT_SPLIT.split(variation)[0].strip()
            if not variation:
                variation = f"The {item_label} is gone."
            if variation[-1] not in ".!?":
                variation = variation.rstrip(".!?, ") + "."
        sentences[target_idx] = variation
        before = node.current_text
        node.current_text = "\n\n".join(sentences)
        node._sync_text_alias()
        self._log_node_text_change(node.id, f"item taken ({item_label})", before, node.current_text)
        self._feed_back(variation)

    def _item_present_rewrite(self, node: "WorldNode", item_id: str, item_label: str):
        """Rewrite a sentence in node text to reflect that an item has been left here."""
        item_words = (
            set(item_id.lower().split()) |
            {w.lower() for w in item_label.split() if w.lower() not in {"the", "a", "an"}}
        )
        # Skip if the item is already mentioned — no change needed
        text_words = {w.lower().rstrip(".,!?;:") for w in node.current_text.split()}
        if item_words & text_words:
            return
        present_seeds = list(item_words) + node.tags[:3] + ["left", "placed", "here", "rests"]
        variation = self._markov_seeded_generate(present_seeds, length=10)
        if not variation:
            variation = f"Someone has left {item_label} here."
        else:
            variation = self._SENT_SPLIT.split(variation)[0].strip()
            if not variation:
                variation = f"Someone has left {item_label} here."
            if variation[-1] not in ".!?":
                variation = variation.rstrip(".!?, ") + "."
        # Replace the last sentence instead of appending
        sentences = self._SENT_SPLIT.split(node.current_text.strip())
        if sentences:
            sentences[-1] = variation
        else:
            sentences = [variation]
        before = node.current_text
        node.current_text = "\n\n".join(sentences)
        node._sync_text_alias()
        self._log_node_text_change(node.id, f"item left ({item_label})", before, node.current_text)
        self._feed_back(variation)

    def get_display_text(self, node_id: str) -> str:
        """Return current_text (drifted) for display."""
        if self.world:
            node = self.world.nodes.get(node_id)
            if node:
                return node.current_text
        node = self.graph.nodes.get(node_id)
        return node.text if node else ""

    def reset_node_drift(self, node_id: str):
        """Reset a node's drift, current_text, and traces to original."""
        node = self.world.nodes.get(node_id) if self.world else None
        if node:
            node.current_text = node.base_text
            node.drift = 0.0
            node.traces = []
            node._sync_text_alias()
            if self.on_graph_change:
                self.on_graph_change()

    # ------------------------------------------------------------------
    # Encounter system
    # ------------------------------------------------------------------

    _ENCOUNTER_FLEE_TEXT = (
        "Something arrives at the threshold. Before thought can form you are already "
        "moving\u2014through the nearest door, down the first corridor that opens. "
        "The space falls away behind you."
    )

    _ENCOUNTER_WITNESS_TEXT = (
        "Something was here. You feel the residue of a recent departure\u2014"
        "a shape that moved like a figure, slipping through the door just before you arrived. "
        "The space is yours now."
    )

    @staticmethod
    def _clear_encounter_state(state: "PlayerState"):
        state.encounter_role = None
        state.encounter_text = None
        state.status = STATUS_ACTIVE

    def _find_empty_node(self, exclude_node_id: str | None = None) -> str | None:
        """Return a random node with no occupants. Falls back to least-occupied."""
        if self._is_world_mode:
            at_node   = self._world_at_node
            all_nodes = list(self.world.nodes.keys())
        else:
            at_node   = self._at_node
            all_nodes = list(self.graph.nodes.keys())

        empty = [
            nid for nid in all_nodes
            if nid != exclude_node_id and len(at_node.get(nid, set())) == 0
        ]
        if empty:
            return random.choice(empty)
        # Fallback: least-occupied node excluding the current one
        candidates = [nid for nid in all_nodes if nid != exclude_node_id]
        if not candidates:
            return None
        return min(candidates, key=lambda nid: len(at_node.get(nid, set())))

    def _apply_encounter(
        self, node_id: str, arriving_player_id: str, others_here: set
    ):
        """Lock existing occupants (P1, 'fled') and arriving player (P2, 'witnessed')."""
        for pid in list(others_here):
            if pid not in self.players:
                continue
            state = self.players[pid]
            state.status         = STATUS_ENCOUNTER
            state.encounter_role = "fled"
            state.encounter_text = self._ENCOUNTER_FLEE_TEXT
            state.current_links  = []
        if arriving_player_id not in self.players:
            return
        p2 = self.players[arriving_player_id]
        p2.status         = STATUS_ENCOUNTER
        p2.encounter_role = "witnessed"
        p2.encounter_text = self._ENCOUNTER_WITNESS_TEXT
        p2.current_links  = []
        # In dynamic mode ensure the node is expanded so exits exist after the encounter
        if not self._is_world_mode:
            self._ensure_expanded(node_id, arriving_player_id)
        if self.on_encounter_start:
            self.on_encounter_start(node_id)

    def resolve_encounter(self, node_id: str):
        """Called by the 15-second timer: teleport fled players, restore choices."""
        at_node = self._world_at_node if self._is_world_mode else self._at_node
        occupants = [p for p in list(at_node.get(node_id, set()))
                     if p in self.players]

        fled_pids      = [p for p in occupants
                          if self.players[p].encounter_role == "fled"]
        witnessed_pids = [p for p in occupants
                          if self.players[p].encounter_role == "witnessed"]

        # Teleport each P1 to a random empty node
        for pid in fled_pids:
            if pid not in self.players:
                continue
            state = self.players[pid]
            dest  = self._find_empty_node(exclude_node_id=node_id)
            if dest is None:
                dest = node_id  # nowhere else to go
            at_node[node_id].discard(pid)
            at_node[dest].add(pid)
            state.current_node = dest
            state.history.append(dest)
            if self._is_world_mode:
                self._build_world_choices(pid)
            else:
                self._ensure_expanded(dest, pid)
                state.current_links = self.graph.get_links_from(dest)
            self._clear_encounter_state(state)

        # Restore choices for P2s (still at node_id)
        for pid in witnessed_pids:
            if pid not in self.players:
                continue
            state = self.players[pid]
            if self._is_world_mode:
                self._build_world_choices(pid)
            else:
                state.current_links = self.graph.get_links_from(node_id)
            self._clear_encounter_state(state)

        if self.on_graph_change:
            self.on_graph_change()

    # ------------------------------------------------------------------
    # Text generation
    # ------------------------------------------------------------------

    def _gen_text(self) -> str:
        return self.markov.generate(self.text_len)

    def _gen_label(self) -> str:
        return self.markov.generate_short(self.choice_len)

    def _make_new_node(self) -> "Node":
        """Create a new node, generate its text, and feed it back into the chain."""
        text = self._gen_text()
        node = Node(text=text)
        self._feed_back(text)   # online learning — new places shape future places
        return node

    # ------------------------------------------------------------------
    # Mutation text generation
    # ------------------------------------------------------------------

    # Word-pair substitutions: city-state changes.
    # Each entry is (regex_pattern, replacement_string).
    _MUTATION_PAIRS = [
        (re.compile(r'\bkeys are on\b',      re.I), "keys are off"),
        (re.compile(r'\bkeys are off\b',     re.I), "keys are on"),
        (re.compile(r'\blights? are on\b',   re.I), "lights are off"),
        (re.compile(r'\blights? are off\b',  re.I), "lights are on"),
        (re.compile(r'\bdoor is (open|ajar)\b', re.I), "door is closed"),
        (re.compile(r'\bdoor is closed\b',   re.I), "door is open"),
        (re.compile(r'\bwindow is open\b',   re.I), "window is closed"),
        (re.compile(r'\bwindow is closed\b', re.I), "window is open"),
        (re.compile(r'\bthere (?:are|is) (\w+)\b', re.I), "there are no"),
        (re.compile(r'\bstill here\b',       re.I), "no longer here"),
        (re.compile(r'\bno one\b',           re.I), "someone"),
        (re.compile(r'\bempty\b',            re.I), "changed"),
        (re.compile(r'\bfull\b',             re.I), "empty"),
        (re.compile(r'\bclosed\b',           re.I), "open"),
        (re.compile(r'\blocked\b',           re.I), "unlocked"),
    ]

    def _gen_mutation_text(self, node_text: str, choice_label: str) -> str:
        """
        Generate the mutated version of node_text after a player leaves via
        the link whose label is choice_label.

        Method 1: try word-pair substitution on node_text.
        Method 2 (fallback): Markov re-seed using tail of node_text +
                             words from choice_label, blended with city_traces
                             vocabulary already in the chain.
        """
        # --- Method 1: word-pair substitution ---
        for pattern, replacement in self._MUTATION_PAIRS:
            if pattern.search(node_text):
                mutated = pattern.sub(replacement, node_text, count=1)
                # Append a short trace phrase to signal change
                trace = self._gen_traces_phrase()
                return mutated.rstrip() + " " + trace
        # --- Method 2: Markov re-seed ---
        # Build seed words from last ~4 words of node_text + choice_label words
        tail_words = node_text.split()[-4:]
        label_words = choice_label.split()[:3]
        seed_words  = tail_words + label_words
        # Try to start generation from a key containing any seed word
        seed_text = self._markov_seeded_generate(seed_words, length=self.text_len)
        return seed_text

    def _gen_traces_phrase(self) -> str:
        """
        Generate a single short sentence (~8 words) in the style of city_traces:
        something that signals presence/change, without naming the other player.
        """
        return self.markov.generate(8)

    _ENCOUNTER_WORDS = (
        "footsteps", "shadow", "voice", "breath", "presence", "someone",
        "brush", "stumble", "whisper", "passing", "warmth", "scent",
    )

    def _gen_collision_text(self, node: "Node", player_id: str) -> str:
        """Encounter scene for the arriving player — seeded from place and path."""
        state = self.players[player_id]
        seed_words: list[str] = []

        seed_words.extend(node.text.split()[-6:])
        for nid in state.history[-3:]:
            hist_node = self.graph.nodes.get(nid)
            if hist_node:
                seed_words.extend(hist_node.text.split()[-4:])

        seed_words.extend(
            random.sample(self._ENCOUNTER_WORDS, min(3, len(self._ENCOUNTER_WORDS)))
        )

        base = node.text
        for pattern, replacement in self._MUTATION_PAIRS:
            if pattern.search(base):
                base = pattern.sub(replacement, base, count=1)
                seed_words.extend(base.split()[-4:])
                break

        return self._markov_seeded_generate(seed_words, length=self.text_len)

    def _markov_seeded_generate(self, seed_words: list[str], length: int) -> str:
        """
        Generate text seeded from any chain key that contains a word from seed_words.
        Falls back to normal generate() if no match found.
        """
        seed_set = {w.lower() for w in seed_words}
        # Find all starts that contain at least one seed word
        matching = [
            k for k in self.markov.starts
            if any(w.lower() in seed_set for w in k)
        ]
        if not matching:
            # Broaden: any chain key containing a seed word
            matching = [
                k for k in self.markov.chain
                if any(w.lower() in seed_set for w in k)
            ]
        if matching:
            # Temporarily hijack generate by injecting our chosen start
            original_starts = self.markov.starts
            self.markov.starts = matching
            result = self.markov.generate(length)
            self.markov.starts = original_starts
            return result
        return self.markov.generate(length)

    # ------------------------------------------------------------------
    # Label extraction from node text
    # ------------------------------------------------------------------

    _ARTICLE_NOUN = re.compile(
        r'\b(the|a|an)\s+(\w+(?:\s+\w+)?)\b', re.I
    )

    # Words too generic/common to make distinctive button labels
    _LABEL_STOP = {
        "the", "a", "an", "is", "of", "in", "on", "at", "it", "its",
        "that", "this", "which", "who", "with", "from", "all", "no",
        "door", "doors", "window", "windows", "building", "buildings",
        "street", "streets", "room", "rooms", "wall", "walls",
        "floor", "floors", "light", "lights", "place", "thing", "things",
    }

    def _gen_label_from_node(self, node_text: str, exclude_phrase: str = "") -> str:
        """
        Extract a noun phrase from node_text (article + 1-2 words),
        then append a short Markov-generated continuation.
        Falls back to plain _gen_label() if nothing useful is found.
        exclude_phrase: first word of a phrase already used (for deduplication).
        """
        matches = self._ARTICLE_NOUN.findall(node_text)
        candidates = []
        for article, rest in matches:
            words = rest.split()
            first = words[0].lower() if words else ""
            if first and first not in self._LABEL_STOP:
                phrase = f"{article} {rest}".strip()
                candidates.append(phrase)

        # Deduplicate: exclude any candidate whose first content word
        # matches the already-used phrase's first content word
        if exclude_phrase:
            excl_first = exclude_phrase.split()[1].lower() if len(exclude_phrase.split()) > 1 else ""
            filtered = [c for c in candidates
                        if c.split()[1].lower() != excl_first] if excl_first else candidates
            if filtered:
                candidates = filtered

        if not candidates:
            return self._gen_label()

        base = random.choice(candidates[:6])
        continuation = self._markov_seeded_generate(
            base.split(), length=self.choice_len
        )
        cont_words = continuation.split()[: self.choice_len]
        if cont_words:
            cont_words[-1] = cont_words[-1].rstrip(".!?,;:")
        label = " ".join(cont_words)
        if label:
            label = label[0].upper() + label[1:]
        return label or self._gen_label()

    # ------------------------------------------------------------------
    # Player management
    # ------------------------------------------------------------------

    def _make_player_start(self, player_id: str) -> str:
        """Create a fresh starting node for this player, pre-expanded with 2 links."""
        node = self._make_new_node()
        node.id = f"start_{player_id}"
        self.graph.add_node(node)
        node.visitors.add(player_id)
        # Always give 2 fresh new nodes at the start — player hasn't met anyone yet
        for _ in range(2):
            child = self._make_new_node()
            self.graph.add_node(child)
            self.graph.add_link(Link(
                from_node=node.id,
                to_node=child.id,
                label=self._gen_label(),
                is_cross=False,
            ))
        node.expanded = True
        # Pre-compute mutation texts (same as _ensure_expanded does)
        for idx, link in enumerate(self.graph.get_links_from(node.id)):
            node.link_mutation_texts[idx] = self._gen_mutation_text(
                node.text, link.label
            )
        return node.id

    def _next_player_id(self) -> str:
        n = 1
        while f"P{n:02d}" in self.players:
            n += 1
        return f"P{n:02d}"

    def spawn_player(self, player_id: str | None = None) -> PlayerState:
        if player_id and player_id in self.players:
            state = self.players[player_id]
            if self._is_world_mode:
                self._build_world_choices(player_id)
            else:
                state.current_links = self.graph.get_links_from(state.current_node)
            self._emit_graph_change(moved_player=player_id)
            return state
        if player_id is None:
            player_id = self._next_player_id()
        if self._is_world_mode:
            return self._world_spawn_player(player_id)
        node_id = self._make_player_start(player_id)
        state = PlayerState(player_id, node_id)
        self.players[player_id] = state
        self._at_node[node_id].add(player_id)
        state.current_links = self.graph.get_links_from(node_id)
        self._emit_graph_change(moved_player=player_id)
        return state

    def reset_player(self, player_id: str) -> PlayerState:
        if self._is_world_mode:
            return self._world_reset_player(player_id)
        if player_id in self.players:
            old = self.players[player_id].current_node
            self._at_node[old].discard(player_id)
        node_id = self._make_player_start(player_id)
        state = PlayerState(player_id, node_id)
        self.players[player_id] = state
        self._at_node[node_id].add(player_id)
        state.current_links = self.graph.get_links_from(node_id)
        self._emit_graph_change(moved_player=player_id)
        return state

    def remove_player(self, player_id: str):
        if player_id in self.players:
            node = self.players[player_id].current_node
            self._at_node[node].discard(player_id)
            del self.players[player_id]

    # ------------------------------------------------------------------
    # Node expansion — the core of the dynamic graph
    # ------------------------------------------------------------------

    def _link_config(self, node_id: str, player_id: str) -> tuple:
        """
        Decide how many new vs cross links to spawn.
        Returns (n_new, n_cross).

        Possible outcomes:
          (2, 0) — both links go to brand new nodes
          (1, 1) — one new, one cross
          (0, 2) — both links go back to existing nodes

        Only options with enough cross candidates are offered.
        """
        candidates = self.graph.candidate_cross_nodes(node_id, player_id)
        n_avail = len(candidates)

        if n_avail == 0:
            return (2, 0)
        elif n_avail == 1:
            return random.choices([(2, 0), (1, 1)], weights=[0.35, 0.65])[0]
        else:
            return random.choices(
                [(2, 0), (1, 1), (0, 2)],
                weights=[0.25, 0.45, 0.30],
            )[0]

    def _ensure_expanded(
        self, node_id: str, player_id: str, label_source: str | None = None
    ):
        """
        If node has not been expanded yet, create 2 outgoing links.
        The mix of new vs cross links is random — see _link_config.
        New node text is fed back into the Markov chain (online learning)
        so the world stays consistent and grows its own vocabulary.
        Link labels are extracted from label_source or the node's own text.
        After creating links, pre-compute one mutation text per link index.
        """
        node = self.graph.nodes[node_id]
        if node.expanded:
            return

        label_text = label_source or node.text
        n_new, n_cross = self._link_config(node_id, player_id)

        candidates = self.graph.candidate_cross_nodes(node_id, player_id)
        preferred = [c for c in candidates if c.visitors - {player_id}]
        cross_pool = preferred if preferred else candidates

        links_to_add = []

        # Spawn fresh nodes — generate labels with deduplication
        used_label = ""
        for _ in range(n_new):
            new_node = self._make_new_node()
            self.graph.add_node(new_node)
            lbl = self._gen_label_from_node(label_text, exclude_phrase=used_label)
            used_label = lbl
            links_to_add.append(Link(
                from_node=node_id,
                to_node=new_node.id,
                label=lbl,
                is_cross=False,
            ))

        # Attach cross links (to existing nodes)
        used = set()
        for _ in range(n_cross):
            available = [c for c in cross_pool if c.id not in used]
            if not available:
                new_node = self._make_new_node()
                self.graph.add_node(new_node)
                lbl = self._gen_label_from_node(label_text, exclude_phrase=used_label)
                used_label = lbl
                links_to_add.append(Link(
                    from_node=node_id,
                    to_node=new_node.id,
                    label=lbl,
                    is_cross=False,
                ))
            else:
                target = random.choice(available)
                used.add(target.id)
                lbl = self._gen_label_from_node(label_text, exclude_phrase=used_label)
                used_label = lbl
                links_to_add.append(Link(
                    from_node=node_id,
                    to_node=target.id,
                    label=lbl,
                    is_cross=True,
                ))

        # Shuffle so button order isn't predictably new/cross
        random.shuffle(links_to_add)
        for link in links_to_add:
            self.graph.add_link(link)

        node.expanded = True

        # Pre-compute mutation texts for each link index
        for idx, link in enumerate(self.graph.get_links_from(node_id)):
            node.link_mutation_texts[idx] = self._gen_mutation_text(
                node.text, link.label
            )

    # ------------------------------------------------------------------
    # Choice resolution
    # ------------------------------------------------------------------

    def make_choice(self, player_id: str, link_index: int) -> PlayerState | None:
        """Player selects a choice by index. Returns updated PlayerState."""
        if player_id not in self.players:
            return None
        if self._is_world_mode:
            return self._world_make_choice(player_id, link_index)
        return self._make_choice_dynamic(player_id, link_index)

    def _make_choice_dynamic(self, player_id: str, link_index: int) -> PlayerState | None:
        """Dynamic graph choice resolution (non-world mode)."""
        state = self.players[player_id]

        if state.status == STATUS_GAME_OVER:
            return state

        if state.status == STATUS_ENCOUNTER:
            return state

        links = state.current_links
        if not links or link_index >= len(links):
            return state

        chosen_link = links[link_index]
        target_node_id = chosen_link.to_node
        from_node_id   = state.current_node

        # --- Mutation: first traversal of this link on the FROM node ---
        from_node = self.graph.nodes[from_node_id]
        if link_index not in from_node.traversed_links:
            from_node.traversed_links.add(link_index)
            if link_index in from_node.link_mutation_texts:
                mutated_text = from_node.link_mutation_texts[link_index]
                from_node.mutations.append(mutated_text)
                from_node.text       = mutated_text
                from_node.is_mutated = True
                # NOTE: do NOT call on_graph_change here — state is mid-update.
                # The single call at the end of make_choice covers this.

        # Leave current node
        self._at_node[from_node_id].discard(player_id)

        # Arrive at target.  A node with an active encounter is NOT blocked —
        # the arriving player joins as a witness.  (Silently rejecting felt
        # like input lag / unclickable choices.)
        target_node = self.graph.nodes[target_node_id]
        target_node.visitors.add(player_id)

        # Encounter check — is someone else already here?
        others_here  = self._at_node[target_node_id] - {player_id}
        is_encounter = bool(others_here)

        self._at_node[target_node_id].add(player_id)
        state.current_node = target_node_id
        state.history.append(target_node_id)

        if is_encounter:
            self._apply_encounter(target_node_id, player_id, others_here)
            # on_encounter_start already called _push_all; skip on_graph_change
        else:
            state.status = STATUS_ACTIVE
            self._ensure_expanded(target_node_id, player_id)
            state.current_links = self.graph.get_links_from(target_node_id)
            self._emit_graph_change(moved_player=player_id)

        return state

    # ------------------------------------------------------------------
    # Weight / settings for sliders
    # ------------------------------------------------------------------

    def set_text_len(self, v: int):
        self.text_len = int(v)

    def set_choice_len(self, v: int):
        self.choice_len = int(v)

    def set_temperature(self, v: float):
        self.markov.set_temperature(float(v))

    def set_drift_rate(self, v: int):
        """Drift rate: how many visits before a sentence rewrite. 1 = every visit."""
        self._drift_rate = max(1, int(v))

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_all_states(self) -> list:
        return list(self.players.values())

    def reset_graph(self):
        """Full reset — clear graph/world state and all players."""
        if self._is_world_mode:
            for node in self.world.nodes.values():
                node.current_text = node.base_text
                node.drift = 0.0
                node.traces = []
                node.visitors = set()
                node.interaction_count = 0
                node.items = {k: dict(v) for k, v in node._items_base.items()}
                node._sync_text_alias()
            self.players = {}
            self._world_at_node = defaultdict(set)
            self._start_node_index = 0
            if self.on_graph_change:
                self.on_graph_change()
            return
        self.graph = DynamicGraph()
        self.players = {}
        self._at_node = defaultdict(set)
        Node._counter = 0
        Link._counter = 0
        if self.on_graph_change:
            self.on_graph_change()
