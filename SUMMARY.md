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
