"""
world_generator.py — Generates a world graph from a free-prose corpus.

No structured authoring format required.  The author writes normal prose;
this module extracts location names, items, and connectivity automatically,
then uses the Markov chain to generate node body text seeded from each
location name.

Entry point
-----------
    generate_world(text, markov, node_count=50) -> dict

Returns a world dict matching the existing JSON schema:
    { "start_nodes": [...], "nodes": [ {id, title, text, tags, exits, items} ] }

Also returns a list of "latent" nodes (not yet in the graph) via:
    generate_world(...) -> (world_dict, latent_nodes_list)

The latent list is stored on StoryEngine._latent_nodes for on-demand discovery.
"""

import re
import random
from collections import Counter, deque

# ---------------------------------------------------------------------------
# Stopwords
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
    "only", "even", "about", "after", "before", "between", "these",
    "those", "where", "while", "might", "could", "would", "should",
    "does", "did", "its", "than", "into", "just", "now", "like", "get",
    "got", "gets", "make", "made", "see", "seen", "come", "came", "way",
    "say", "said", "know", "known", "well", "much", "many", "long",
    "little", "own", "old", "new", "first", "last", "another", "off",
    "side", "seem", "seemed", "around", "place", "something", "nothing",
    "anything", "everything", "someone", "anyone", "everyone",
}

# Navigation verb prefixes for exit labels
_NAV_VERBS = [
    "Enter", "Descend", "Climb", "Cross", "Push", "Follow",
    "Step", "Pass", "Proceed", "Return",
]

# Action verbs that signal nearby items (active and passive forms)
_ITEM_VERBS = re.compile(
    r'\b(take|took|taken|carry|carried|hold|holds|held|leave|left|leaves|'
    r'pick|picks|picked|drop|drops|dropped|place|placed|places|placing|'
    r'find|finds|found|grab|grabs|grabbed|lift|lifts|lifted|'
    r'slip|slips|slipped|put|puts|assembled|assembly|arranged|arrange|'
    r'attached|attach|fixed|fix|bound|bind|built|build|made|make|'
    r'hung|hang|hangs|hanging|resting|rests|rest|sitting|sits|sit|'
    r'standing|stands|stand|leaning|leans|lean)\b',
    re.I,
)

# Detect structured-format nav verb sentences (for auto-mode detection)
# Matches nav verbs at start of line OR after sentence-ending punctuation
_STRUCTURED_NAV = re.compile(
    r'(?:^|(?<=[.!?])\s+)(Enter|Go|Cross|Climb|Return|Back|Push|Slip|Descend|Emerge|'
    r'Head|Walk|Move|Follow|Step|Proceed|Continue|Leave|Exit|Pass|Turn|'
    r'Open|Through|Into|Up|Down|Out|Away|Toward|Towards|Reach)\b',
    re.I | re.MULTILINE,
)


def _slugify(text: str, max_words: int = 4) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    words = [w for w in text.split() if w not in _STOP and len(w) > 1]
    return "_".join(words[:max_words]) or "node"


def _extract_tags(text: str, n: int = 6) -> list:
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    seen, tags = set(), []
    for w in words:
        if w not in _STOP and w not in seen:
            seen.add(w)
            tags.append(w)
        if len(tags) >= n:
            break
    return tags


# ---------------------------------------------------------------------------
# Location extraction
# ---------------------------------------------------------------------------

def extract_locations(text: str, n: int = 50) -> list[str]:
    """
    Extract candidate location names from free prose.

    Strategy:
    - Find "the X", "a X", "an X" where X is 1-3 significant words
    - Also find standalone multi-word noun phrases in sentence positions
    - Count frequency; return top N by count, minimum 2 occurrences
    - Prefer multi-word phrases (more specific = better location names)
    """
    text_lower = text.lower()

    # Pattern 1: "the/a/an <word>" — captures the head noun
    article_pattern = re.compile(
        r'\b(?:the|a|an)\s+([a-z][a-z\-]{2,}(?:\s+[a-z][a-z\-]{2,}){0,2})\b'
    )
    candidates: Counter = Counter()
    for m in article_pattern.finditer(text_lower):
        phrase = m.group(1).strip()
        words = phrase.split()
        # Filter: no stopwords as head, minimum 3 chars
        head = words[-1]
        if head in _STOP or len(head) < 3:
            continue
        if all(w in _STOP for w in words):
            continue
        # Use only the meaningful part
        clean = " ".join(w for w in words if w not in _STOP or len(words) == 1)
        if clean and len(clean) >= 3:
            candidates[clean] += 1

    # Pattern 2: capitalized phrases mid-sentence (proper place names)
    cap_pattern = re.compile(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,2})\b')
    for m in cap_pattern.finditer(text):
        phrase = m.group(1)
        # Skip sentence-start (first word of sentence) — too generic
        start = m.start()
        preceding = text[max(0, start-2):start]
        if preceding in ('', '. ', '! ', '? ', '\n\n'):
            continue
        phrase_lower = phrase.lower()
        if phrase_lower not in _STOP and len(phrase) >= 4:
            candidates[phrase_lower] += 1

    # Filter by minimum frequency and stopword head
    filtered = [
        (phrase, count) for phrase, count in candidates.most_common()
        if count >= 2
        and not all(w in _STOP for w in phrase.split())
        and len(phrase) >= 3
    ]

    # Prefer multi-word, then by frequency
    filtered.sort(key=lambda x: (-len(x[0].split()), -x[1]))

    seen_heads: set = set()
    result: list = []
    for phrase, _ in filtered:
        head = phrase.split()[-1]
        if head not in seen_heads:
            seen_heads.add(head)
            result.append(phrase)
        if len(result) >= n:
            break

    # If we got fewer than 8, relax the frequency requirement
    if len(result) < 8:
        extras = [
            phrase for phrase, count in candidates.most_common()
            if count >= 1
            and not all(w in _STOP for w in phrase.split())
            and len(phrase) >= 3
            and phrase.split()[-1] not in seen_heads
        ]
        for phrase in extras:
            seen_heads.add(phrase.split()[-1])
            result.append(phrase)
            if len(result) >= max(8, n // 2):
                break

    return result[:n]


# ---------------------------------------------------------------------------
# Item extraction
# ---------------------------------------------------------------------------

def extract_items(text: str, locations: list[str]) -> list[tuple[str, str]]:
    """
    Find likely item names from the corpus.

    Looks for nouns within a 6-word window of action verbs.
    Returns list of (item_id, item_label) tuples.
    """
    location_words = set()
    for loc in locations:
        location_words.update(loc.lower().split())

    item_candidates: Counter = Counter()
    sentences = re.split(r'[.!?]\s+', text)

    # Words that are themselves verb forms — exclude from item candidates
    _VERB_FORMS = {
        'placed', 'stands', 'standing', 'leaning', 'leans', 'assembled',
        'arranged', 'attached', 'fixed', 'bound', 'built', 'hung', 'hanging',
        'resting', 'rests', 'sitting', 'sits', 'lifted', 'carry', 'carried',
        'take', 'took', 'taken', 'hold', 'holds', 'held', 'leave', 'left',
        'pick', 'picked', 'drop', 'dropped', 'find', 'found', 'grab', 'grabbed',
        'put', 'puts', 'slip', 'slipped', 'made', 'make', 'built', 'build',
    }

    for sent in sentences:
        if not _ITEM_VERBS.search(sent):
            continue
        words = re.findall(r'\b[a-z][a-z\-]{2,}\b', sent.lower())
        for i, w in enumerate(words):
            if w in _STOP or w in location_words or len(w) < 3:
                continue
            # Check if any item verb is within 6 words
            window = words[max(0, i-6):i+6]
            if any(_ITEM_VERBS.match(v) for v in window):
                item_candidates[w] += 1

    # Filter: min 1 occurrence, not a stopword, not a location head
    loc_heads = {loc.split()[-1] for loc in locations}
    result = []
    seen = set()
    for word, _ in item_candidates.most_common(20):
        if word in seen or word in loc_heads or word in _STOP or word in _VERB_FORMS:
            continue
        seen.add(word)
        label = f"the {word}"
        result.append((word, label))
        if len(result) >= 10:
            break

    return result


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_connected_graph(location_ids: list[str]) -> dict[str, list[str]]:
    """
    Build a connected graph where every node has exactly 2 exits.

    Strategy:
    - Arrange nodes in a ring (guarantees full connectivity)
    - Add random cross-edges so every node has exactly 2 distinct exits
    - Cross-edges are bidirectional where possible
    """
    n = len(location_ids)
    if n == 0:
        return {}
    if n == 1:
        return {location_ids[0]: [location_ids[0], location_ids[0]]}
    if n == 2:
        return {
            location_ids[0]: [location_ids[1], location_ids[1]],
            location_ids[1]: [location_ids[0], location_ids[0]],
        }

    # Start with ring
    adj: dict[str, list[str]] = {nid: [] for nid in location_ids}
    for i in range(n):
        a = location_ids[i]
        b = location_ids[(i + 1) % n]
        adj[a].append(b)
        adj[b].append(a)

    # Fill nodes that still need a second exit with cross-edges
    ids = list(location_ids)
    random.shuffle(ids)
    for node_id in ids:
        if len(adj[node_id]) >= 2:
            continue
        # Pick a random target that is not already adjacent and not self
        candidates = [
            x for x in location_ids
            if x != node_id and x not in adj[node_id]
        ]
        if not candidates:
            # All already adjacent — just reuse an existing neighbour
            adj[node_id].append(adj[node_id][0])
            continue
        target = random.choice(candidates)
        adj[node_id].append(target)
        # Add reverse if target also needs an exit
        if len(adj[target]) < 2:
            adj[target].append(node_id)

    # Trim to exactly 2 exits per node
    for node_id in location_ids:
        seen = []
        for x in adj[node_id]:
            if x not in seen:
                seen.append(x)
        adj[node_id] = seen[:2]
        # Pad if somehow only 1
        while len(adj[node_id]) < 2:
            other = random.choice([x for x in location_ids if x != node_id])
            adj[node_id].append(other)

    return adj


def bfs_distances(source: str, adj: dict[str, list[str]]) -> dict[str, int]:
    """Shortest-hop distances from source to all reachable nodes."""
    dist = {source: 0}
    q = deque([source])
    while q:
        n = q.popleft()
        for nb in adj.get(n, []):
            if nb not in dist:
                dist[nb] = dist[n] + 1
                q.append(nb)
    return dist


def min_graph_distance(node_id: str, targets: set[str], adj: dict[str, list[str]]) -> int:
    """Minimum BFS distance from node_id to any node in targets."""
    if not targets:
        return 999
    if node_id in targets:
        return 0
    best = 999
    for t in targets:
        d = bfs_distances(t, adj).get(node_id, 999)
        if d < best:
            best = d
    return best


def select_spread_start_nodes(
    node_ids: list[str],
    adj: dict[str, list[str]],
    k: int = 20,
) -> list[str]:
    """Farthest-point sampling — pick spawn nodes maximally spread on the graph."""
    if not node_ids:
        return []
    k = min(k, len(node_ids))
    first = max(node_ids, key=lambda nid: len(adj.get(nid, [])))
    selected = [first]
    selected_set = {first}
    while len(selected) < k:
        best_node = None
        best_score = -1
        for cand in node_ids:
            if cand in selected_set:
                continue
            score = min_graph_distance(cand, selected_set, adj)
            if score > best_score:
                best_score = score
                best_node = cand
        if best_node is None:
            break
        selected.append(best_node)
        selected_set.add(best_node)
    return selected


# ---------------------------------------------------------------------------
# Text generation helpers
# ---------------------------------------------------------------------------

_SENT_END_RE = re.compile(r'[.!?]')


def _first_sentence(text: str) -> str:
    """Return only the first sentence of a generated chunk."""
    text = text.strip()
    m = _SENT_END_RE.search(text)
    if m:
        text = text[: m.end()].strip()
    if text and text[-1] not in ".!?":
        text = text.rstrip(".!?, ") + "."
    return text


def generate_node_text(markov, location_name: str, n_sentences: int = 3) -> str:
    """Generate body text: N distinct single-sentence paragraphs.

    Each paragraph is trimmed to a single sentence and deduplicated so the
    node text stays short and never repeats the same line.
    """
    seed_words = [w for w in location_name.split() if w.lower() not in _STOP]
    if not seed_words:
        seed_words = location_name.split()

    sentences: list = []
    seen: set = set()
    attempts = 0
    max_attempts = n_sentences * 5
    while len(sentences) < n_sentences and attempts < max_attempts:
        attempts += 1
        if not sentences:
            seeds = seed_words
        else:
            seeds = [random.choice(seed_words)] if seed_words else seed_words
        raw = markov.generate_seeded(seeds, length=10)
        sent = _first_sentence(raw)
        if not sent or len(sent.split()) < 4:
            continue
        key = sent.lower()
        if key in seen:
            continue
        seen.add(key)
        sentences.append(sent)

    return "\n\n".join(sentences)


def generate_exit_label(markov, from_name: str, to_name: str) -> str:
    """
    Generate a short exit label like "Follow the corridor toward the precinct".

    Seeds from to_name words, prepends a nav verb if not already present.
    """
    seed_words = [w for w in to_name.split() if w.lower() not in _STOP]
    if not seed_words:
        seed_words = to_name.split()

    phrase = markov.generate_short(length=6)

    # Check if phrase starts with a nav verb already
    first_word = phrase.split()[0].lower() if phrase.split() else ""
    nav_lower = {v.lower() for v in _NAV_VERBS}

    if first_word not in nav_lower:
        verb = random.choice(_NAV_VERBS)
        # Try to include the destination name
        dest_words = [w for w in to_name.split() if w.lower() not in _STOP]
        if dest_words:
            phrase = f"{verb} the {dest_words[0]}"
        else:
            phrase = f"{verb} {phrase.lower()}"
    else:
        # Capitalise first letter
        phrase = phrase[0].upper() + phrase[1:]

    return phrase.rstrip(".!?,;:")


# ---------------------------------------------------------------------------
# Item assignment
# ---------------------------------------------------------------------------

def assign_items(
    location_ids: list[str],
    item_candidates: list[tuple[str, str]],
    n_items: int = 3,
) -> dict[str, list[str]]:
    """
    Place items across nodes, max 1 per node.
    Items are reused (cycled) so roughly half of all nodes get an item.
    Returns {node_id: [item_id, ...]}
    """
    from world_sanity import is_carryable

    if not item_candidates or not location_ids:
        return {}

    item_candidates = [(i, l) for i, l in item_candidates if is_carryable(i)]
    if not item_candidates:
        return {}

    result: dict[str, list[str]] = {}
    candidate_nodes = list(location_ids)
    random.shuffle(candidate_nodes)

    # How many nodes should receive an item (clamped to available nodes)
    target = min(len(candidate_nodes), max(n_items, len(candidate_nodes) // 2))

    item_ids = [iid for iid, _ in item_candidates]
    for idx in range(target):
        node_id = candidate_nodes[idx]
        item_id = item_ids[idx % len(item_ids)]
        if not is_carryable(item_id):
            continue
        result[node_id] = [item_id]

    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_world(
    text: str,
    markov,
    node_count: int = 50,
    latent_count: int = 20,
) -> tuple[dict, list]:
    """
    Generate a world dict and a list of latent (undiscovered) node dicts
    from a free-prose corpus.

    Returns (world_dict, latent_nodes)
    """
    # 1. Extract all location candidates (node_count + latent_count)
    all_locations = extract_locations(text, n=node_count + latent_count)

    # Cap to what was actually found
    total_found = len(all_locations)
    actual_main = min(node_count, max(1, total_found - min(latent_count, total_found // 4)))
    actual_latent = total_found - actual_main

    main_locations   = all_locations[:actual_main]
    latent_locations = all_locations[actual_main:]

    # 2. Extract items
    item_candidates = extract_items(text, main_locations)

    # 3. Build graph for main locations
    main_ids = [_slugify(loc) for loc in main_locations]
    # Deduplicate slugs
    seen_ids: dict = {}
    deduped_ids = []
    for sid in main_ids:
        if sid in seen_ids:
            seen_ids[sid] += 1
            deduped_ids.append(f"{sid}_{seen_ids[sid]}")
        else:
            seen_ids[sid] = 1
            deduped_ids.append(sid)
    main_ids = deduped_ids

    loc_id_map = {loc: sid for loc, sid in zip(main_locations, main_ids)}
    adj = build_connected_graph(main_ids)

    # 4. Assign items to nodes
    item_assignments = assign_items(main_ids, item_candidates, n_items=max(2, node_count // 15))

    # 5. Generate node dicts
    nodes = []
    for loc_name, node_id in zip(main_locations, main_ids):
        body_text = generate_node_text(markov, loc_name, n_sentences=3)

        exits = []
        for dest_id in adj.get(node_id, []):
            # Find the destination location name for label seeding
            dest_name = next(
                (loc for loc, sid in zip(main_locations, main_ids) if sid == dest_id),
                dest_id,
            )
            label = generate_exit_label(markov, loc_name, dest_name)
            exits.append({"to": dest_id, "label": label})

        nodes.append({
            "id":          node_id,
            "title":       loc_name.title(),
            "text":        body_text,
            "description": body_text,
            "tags":        _extract_tags(loc_name + " " + body_text),
            "exits":       exits,
            "items":       item_assignments.get(node_id, []),
        })

    world_dict = {
        "start_nodes": select_spread_start_nodes(
            main_ids, adj, k=min(20, len(main_ids))
        ),
        "nodes": nodes,
    }

    # 6. Build latent node dicts (no exits yet — assigned on discovery)
    latent_nodes = []
    latent_item_candidates = extract_items(text, latent_locations) if latent_locations else []
    for loc_name in latent_locations:
        lid = _slugify(loc_name)
        body_text = generate_node_text(markov, loc_name, n_sentences=3)
        latent_nodes.append({
            "id":          lid,
            "title":       loc_name.title(),
            "text":        body_text,
            "description": body_text,
            "tags":        _extract_tags(loc_name + " " + body_text),
            "exits":       [],   # filled at discovery time
            "items":       [],
        })

    return world_dict, latent_nodes


def is_structured_format(text: str) -> bool:
    """
    Return True if text looks like the structured authoring format
    (paragraphs ending with nav verb sentences).
    Heuristic: at least 2 nav-verb sentences found.
    """
    matches = _STRUCTURED_NAV.findall(text)
    return len(matches) >= 2
