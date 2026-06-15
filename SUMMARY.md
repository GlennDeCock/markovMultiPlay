# MultiMarkovPlay — Project Summary

## What It Is

A multiplayer interactive narrative game for up to **20 players** sharing one story graph. Each player sees branching Markov-generated text and picks one of two choices. The tone is nonsensical, abstract, old-school RPG humor. No violence.

**Current form:** a **desktop prototype** on one PC — one control window plus up to 20 player windows styled like E-Ink screens (Tkinter). This simulates the shared-space experience before any physical hardware.

---

## How to Run

```powershell
cd prototype
python main.py
python test_image_gen.py
```

Requires **Python 3** with **Tkinter** (included on most Windows Python installs).

---

## Collision Mechanic

Collisions affect **every player at the node**:

- Player A is already at a node
- Player B arrives at the same node
- **Both** windows switch to an encounter scene (context-seeded Markov text per player’s path)
- Shared node text is **not** overwritten (per-player overlay only)
- Choice buttons are phrases derived from each player’s encounter text
- When only one player remains at the node, collision UI clears and normal play resumes

---

## Software Stack (prototype)

| Component | Role |
|-----------|------|
| `main.py` | Entry point |
| `engine.py` | Markov chain, dynamic shared graph, collisions, mutations |
| `control_window.py` | Spawn players, sliders, graph view, retrain |
| `player_window.py` | Per-player E-Ink-style UI |
| `graph_canvas.py` | Force-directed graph visualization |
| `image_gen.py` | Procedural scene silhouettes |
| `training_texts/` | `.txt` files used to train the Markov model |

The graph **grows at runtime** as players explore. There is no static JSON scene file in use.

---

## Folder Structure

```
MultiMarkovPlay/
└── prototype/
    ├── main.py
    ├── engine.py
    ├── control_window.py
    ├── player_window.py
    ├── graph_canvas.py
    ├── image_gen.py
    ├── test_image_gen.py
    ├── SUMMARY.md
    ├── references.txt          ← design notes (ergodic / encounter ideas)
    └── training_texts/
        └── *.txt
```

---

## Training Text

Add `.txt` files under `training_texts/`. Use the control panel **Retrain** after changes. See `training_texts/README.txt` for notes on Markov order.

---

## Design Notes

`references.txt` captures literary framing (ergodic / psychogeography) and ideas for richer encounters. Collision scenes already use context seeding and per-player overlay text so shared nodes stay stable for other players.

---

## World Authoring System

### Writing → Nodes

You write a plain `.txt` file. When loaded, the engine **auto-detects** which of two pipelines to use:

**Pipeline 1 — Structured format** (hand-authored, deterministic):
The file contains navigation-verb sentences (`Enter`, `Go`, `Climb`, etc.). One paragraph = one node. Nav-verb sentences at the end of each paragraph become exits; the parser links them to other nodes by keyword overlap. An optional `items:` line declares objects. The JSON produced is exactly what you wrote — no generation.

```
room with a desk
There is a desk in the corner. A brass key rests on the surface. The door is locked.
items: key
Enter the corridor. Check the locked door.

corridor
The corridor stretches ahead. A door at the far end.
Go back to the desk room.
```

**Pipeline 2 — Free prose corpus** (generative, probabilistic):
The file is narrative prose with no nav-verb sentences. The engine extracts location names and items via heuristics, then uses the **Markov chain** to *generate* node body text seeded from each location name. Connections are auto-created. Leftover locations become "latent nodes" discovered during play. The resulting JSON will differ on each load.

The generated JSON is saved as a sidecar `_generated.json` next to your `.txt`. Editing the `.txt` and reloading regenerates it; editing the JSON directly works for quick experiments but is overwritten on next reload.

### Training → Markov

When you click **"Load from Text…"** in the control panel, three things happen in sequence:

1. **Parse/Generate** — your `.txt` → `.json` via the appropriate pipeline above
2. **Train** — the Markov chain reads your `.txt` directly. Your own vocabulary (the words and sentence patterns you wrote) are what generate choice labels and text drift
3. **Load** — the world goes live

The Markov chain does **not** retrain as players play. It is trained once from your text, then used throughout the session.

### What changes during play (live, no retraining)

| Event | What happens |
|---|---|
| Player takes an item | Node text rewrites to reflect item gone (Markov variation seeded from item words) |
| Player leaves an item at a new node | Short sentence appended to that node's text |
| Player leaves a node | One sentence in the node text is replaced with a Markov variation (drift) |
| Player leaves a node | A short "trace" fragment is generated and stored (signals recent presence) |

All changes are **shared** — every player sees the same mutated world state in real time.

### Authoring flow

```
1. Write my_world.txt      (full story: all nodes, exits, items)
2. Load from Text…         (parse + train Markov + load world — one button)
3. Players play            (world drifts organically from your vocabulary)
4. Edit my_world.txt       (add/change nodes or items)
5. Rebuild World           (reset + retrain from updated text)
```

The longer and richer your source text, the more atmospheric the Markov-generated choice labels and drift sentences will feel — because they draw vocabulary directly from what you wrote.

### Item rules

- Max **1 item** carried at a time — forces a take/leave decision at every node
- Items that overlap the destination node's vocabulary show a **"Use"** choice; otherwise **"Leave"**
- Item state is in-memory — restarting the server resets all item positions to their authored defaults
2) 4-5 short descriptive sentences
3) optional line exactly: items: itemname
4) exactly 2 navigation sentences that start with one of:
Enter, Descend, Climb, Cross, Push, Follow, Step, Pass, Proceed
Leave one blank line between nodes.
Never explain rules. Never output markdown.Output must look exactly like this example — copy the items: line format literally:

transit corridor
The floor plates are uneven. Conduit runs along the ceiling, most of it cut. A pressure door at the far end is jammed open with a length of pipe. The air tastes of oxidised metal.
items: pipe
Descend to the lower access shaft. Follow the conduit toward the relay room.

relay room
Banks of equipment line the walls. Most panels are dark. One screen still cycles through a readout no one has checked in a long time.
Proceed back to the transit corridor. Pass through the sealed bulkhead.
You write location descriptions for a text adventure game. Format rules you always follow:
- Each location: title line (no period), then body sentences, then exactly 2 exit sentences starting with a nav verb
- Nav verbs: Enter, Descend, Climb, Cross, Push, Follow, Step, Pass, Proceed
- If a location has an item, add a line that reads exactly: items: itemname
- Blank line between locations
- Terse. Cold. Present tense. Short sentences. No magic. No torches. Industrial decay.

{
  "title": "Vermis Descent",
  "author": "Glenn",
  "description": "A vast civic megastructure of uncertain age. Stone precincts, sealed halls, flooded walkways. The style of Vermis and Ursula Le Guin — plain, specific, mundane objects in wrong contexts. No heroes, no destiny.",
  "tags": ["fantasy", "megastructure", "vermis", "weird", "exploration", "civic", "le guin"],
  "prompt": "You descend a stair that does not appear on the district plan. The stone is older than the precinct above it. A corridor opens left toward the PERMIT HALL. A low arch ahead leads into the WATER PRECINCT. The air does not move. Describe your first action.",
  "memory": "Style rules: terse, plain, present tense, second person. Tone: Vermis + Ursula Le Guin. World is a megastructure city of impossible scale — precincts, vaulted halls, bridges, sealed districts, aqueducts, civic corridors. Stone, plaster, cord, water, pigment, worn thresholds, ledger marks. No bones or remains. No machinery. No electric light. Magic is not dramatic — it is wrongness in the weight of a room, in a door that should not open, in a record that should not exist. No heroic framing. No quests. Format rules for location blocks: 1) title line (no period), 2) 4-5 short descriptive sentences, 3) optional line exactly: items: itemname, 4) exactly 2 navigation sentences starting with Enter, Descend, Climb, Cross, Push, Follow, Step, Pass, Proceed, Return. IMPORTANT: if a location has an items: line, at least one of the two navigation sentences must refer to the item or where it is used. At least two locations must include a literal items: line.",
  "authorsnote": "Write in plain, specific prose. Present tense. Short declarative sentences. Name ordinary things precisely: the cord, the ledger stamp, the transit permit, the plaster seal, the measuring weight. No bones. No adjectives like dark, ancient, eerie — describe the surface and let the reader feel it. Items must be mundane objects that are wrong in context or useful in unexpected ways. When a location has an item, one navigation sentence must reference the item or the place it opens.\n\nOutput world nodes in this exact format:\n1) location title line (no period)\n2) 4-5 short descriptive sentences\n3) optional line exactly: items: itemname\n4) exactly 2 navigation sentences starting with: Enter, Descend, Climb, Cross, Push, Follow, Step, Pass, Proceed, Return\n\nLeave one blank line between nodes. Never explain rules. Never output markdown.\n\nExample:\n\npermit hall\nThe counter runs the full length of the room. The windows behind it are sealed with plaster. A stack of transit permits sits on the counter, each stamped but not filled. The floor is worn in a path from the door to the counter and nowhere else.\nitems: transit permit\nPresent the permit at the district gate and proceed through. Cross the hall toward the water precinct.\n\nwater precinct\nThe channel runs through the centre of the floor under iron gratings. The water is slow and carries a fine grey sediment. Marks on the wall record water levels in a notation no longer standard. The last mark is recent.\nFollow the channel toward the lower aqueduct. Climb the steps back toward the permit hall.",
  "worldinfo": [
    {
      "key": "transit permit,permit",
      "keysecondary": "",
      "content": "A transit permit is a rectangle of pressed fibre stamped with a district seal. This one is stamped but the name field is blank. Most gate wardens accept a stamped permit without reading it closely. The stamp belongs to a district that was sealed two administrations ago.",
      "comment": "Item lore — opens the district gate",
      "constant": false,
      "selective": true
    },
    {
      "key": "measuring cord,cord",
      "keysecondary": "",
      "content": "A measuring cord of knotted flax, twenty spans long, used by district surveyors to mark boundaries. The knots are tied in the old system. Someone has tied a single additional knot at the midpoint that is not part of any system.",
      "comment": "Item lore — used at the survey marker",
      "constant": false,
      "selective": true
    },
    {
      "key": "permit hall,counter,permits",
      "keysecondary": "",
      "content": "The permit hall has a long counter and sealed windows behind it. A stack of transit permits sits on the counter, stamped but not filled. The floor is worn in a single path from the door to the counter. There is no path worn to the door on the far side.",
      "comment": "Location lore — transit permit found here",
      "constant": false,
      "selective": true
    },
    {
      "key": "water precinct,channel,aqueduct,sediment",
      "keysecondary": "",
      "content": "The water precinct has a channel running under iron gratings through the centre of the floor. The water moves slowly and carries grey sediment. Waterline marks on the walls use a notation no longer standard. The most recent mark is fresh.",
      "comment": "Location lore",
      "constant": false,
      "selective": true
    },
    {
      "key": "district gate,gate,sealed arch",
      "keysecondary": "",
      "content": "The district gate is a wide stone arch with a warden's window set into the right pillar. The window shutter is closed. A slot at the base of the shutter is the width of a permit. The gate has a counterweight mechanism that still functions.",
      "comment": "Location lore — opened by transit permit",
      "constant": false,
      "selective": true
    },
    {
      "key": "survey passage,survey marker,boundary marks",
      "keysecondary": "",
      "content": "Survey passage has boundary marks cut into both walls at regular intervals. The intervals do not match any standard measure. A brass pin is set into the floor at the midpoint — the kind used to anchor a measuring cord. The passage continues further than the district plan shows.",
      "comment": "Location lore — measuring cord used here",
      "constant": false,
      "selective": true
    }
  ]
}Write in plain, specific prose. Present tense. Short declarative sentences. Name ordinary things precisely: the cord, the ledger stamp, the transit permit, the plaster seal, the measuring weight. No bones. No adjectives like dark, ancient, eerie — describe the surface and let the reader feel it. Items must be mundane objects that are wrong in context or useful in unexpected ways. When a location has an item, one navigation sentence must reference the item or the place it opens.

Output world nodes in this exact format:
1) location title line (no period)
2) 4-5 short descriptive sentences
3) optional line exactly: items: itemname
4) exactly 2 navigation sentences starting with: Enter, Descend, Climb, Cross, Push, Follow, Step, Pass, Proceed, Return

Leave one blank line between nodes. Never explain rules. Never output markdown.

Example:

permit hall
The counter runs the full length of the room. The windows behind it are sealed with plaster. A stack of transit permits sits on the counter, each stamped but not filled. The floor is worn in a path from the door to the counter and nowhere else.
items: transit permit
Present the permit at the district gate and proceed through. Cross the hall toward the water precinct.

water precinct
The channel runs through the centre of the floor under iron gratings. The water is slow and carries a fine grey sediment. Marks on the wall record water levels in a notation no longer standard. The last mark is recent.
Follow the channel toward the lower aqueduct. Climb the steps back toward the permit hall.