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

import random
import re
from collections import defaultdict
from pathlib import Path


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
STATUS_COLLISION = "collision"
STATUS_GAME_OVER = "game_over"


class PlayerState:
    def __init__(self, player_id: str, start_node: str):
        self.player_id    = player_id
        self.current_node = start_node
        self.status       = STATUS_ACTIVE
        self.history: list[str] = [start_node]
        # The two link choices currently presented to this player
        self.current_links: list[Link] = []
        # Per-player collision scene (does not overwrite shared node text)
        self.collision_overlay_text: str | None = None
        self.collision_choice_labels: list[str] | None = None


# ---------------------------------------------------------------------------
# Story Engine
# ---------------------------------------------------------------------------

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

        # Callbacks — UI registers these to be notified of graph changes
        self.on_graph_change = None   # callable()

        self._init_start_node()
        self.train()

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

    def _collision_display_labels(self, collision_text: str, n: int = 2) -> list[str]:
        """Button labels derived from the collision scene text."""
        labels = []
        used = ""
        for _ in range(n):
            lbl = self._gen_label_from_node(collision_text, exclude_phrase=used)
            used = lbl
            labels.append(lbl)
        return labels

    @staticmethod
    def _clear_collision_display(state: PlayerState):
        state.collision_overlay_text = None
        state.collision_choice_labels = None

    def _sync_collision_at_node(self, node_id: str):
        """Clear collision UI when fewer than two players share a node."""
        occupants = self._at_node.get(node_id, set())
        if len(occupants) > 1:
            return
        for pid in occupants:
            state = self.players.get(pid)
            if state is None or state.status != STATUS_COLLISION:
                continue
            self._clear_collision_display(state)
            state.status = STATUS_ACTIVE
            state.current_links = self.graph.get_links_from(node_id)

    def _apply_collision_at_node(
        self, node_id: str, arriving_player_id: str, others_here: set[str]
    ):
        """Collision scene for every player currently at this node."""
        target_node = self.graph.nodes[node_id]
        all_here = others_here | {arriving_player_id}
        arriving_overlay = self._gen_collision_text(target_node, arriving_player_id)
        self._ensure_expanded(
            node_id, arriving_player_id, label_source=arriving_overlay
        )
        links = self.graph.get_links_from(node_id)
        for pid in all_here:
            state = self.players[pid]
            overlay = self._gen_collision_text(target_node, pid)
            state.status = STATUS_COLLISION
            state.collision_overlay_text = overlay
            state.current_links = links
            n_labels = min(2, len(links))
            if n_labels:
                state.collision_choice_labels = self._collision_display_labels(
                    overlay, n=n_labels
                )

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

    def spawn_player(self, player_id: str) -> PlayerState:
        node_id = self._make_player_start(player_id)
        state = PlayerState(player_id, node_id)
        self.players[player_id] = state
        self._at_node[node_id].add(player_id)
        state.current_links = self.graph.get_links_from(node_id)
        if self.on_graph_change:
            self.on_graph_change()
        return state

    def reset_player(self, player_id: str) -> PlayerState:
        if player_id in self.players:
            old = self.players[player_id].current_node
            self._at_node[old].discard(player_id)
        node_id = self._make_player_start(player_id)
        state = PlayerState(player_id, node_id)
        self.players[player_id] = state
        self._at_node[node_id].add(player_id)
        state.current_links = self.graph.get_links_from(node_id)
        if self.on_graph_change:
            self.on_graph_change()
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

        if self.on_graph_change:
            self.on_graph_change()

    # ------------------------------------------------------------------
    # Choice resolution
    # ------------------------------------------------------------------

    def make_choice(self, player_id: str, link_index: int) -> PlayerState:
        """Player selects link 0 or 1. Returns updated PlayerState."""
        state = self.players[player_id]

        if state.status == STATUS_GAME_OVER:
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
        self._sync_collision_at_node(from_node_id)

        # Arrive at target
        target_node = self.graph.nodes[target_node_id]
        target_node.visitors.add(player_id)

        # Collision check — is someone else already here?
        others_here  = self._at_node[target_node_id] - {player_id}
        is_collision = bool(others_here)

        self._at_node[target_node_id].add(player_id)
        state.current_node = target_node_id
        state.history.append(target_node_id)

        if is_collision:
            self._apply_collision_at_node(
                target_node_id, player_id, others_here
            )
        else:
            self._clear_collision_display(state)
            state.status = STATUS_ACTIVE
            self._ensure_expanded(target_node_id, player_id)
            state.current_links = self.graph.get_links_from(target_node_id)

        if self.on_graph_change:
            self.on_graph_change()

        return state

    def resolve_collision_choice(self, player_id: str, link_index: int) -> PlayerState:
        """After collision scene, player picks a link — same as normal choice."""
        state = self.players[player_id]
        self._clear_collision_display(state)
        state.status = STATUS_ACTIVE
        return self.make_choice(player_id, link_index)

    # ------------------------------------------------------------------
    # Weight / settings for sliders
    # ------------------------------------------------------------------

    def set_text_len(self, v: int):
        self.text_len = int(v)

    def set_choice_len(self, v: int):
        self.choice_len = int(v)

    def set_temperature(self, v: float):
        self.markov.set_temperature(float(v))

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_all_states(self) -> list:
        return list(self.players.values())

    def reset_graph(self):
        """Full reset — clear graph and all players."""
        self.graph = DynamicGraph()
        self.players = {}
        self._at_node = defaultdict(set)
        Node._counter = 0
        Link._counter = 0
        if self.on_graph_change:
            self.on_graph_change()
