#!/usr/bin/env python3
"""
validate_world.py

Simple validator for a world JSON used by MultiMarkovPlay.
Checks:
 - exit targets exist
 - lists unreachable nodes from start nodes
 - optional: require reciprocals (bidirectional links)

Usage:
  python scripts/validate_world.py data/world/example_world.json
  python scripts/validate_world.py nodes.json --require-reciprocals
"""
import argparse
import json
from pathlib import Path
from collections import deque


def main():
    ap = argparse.ArgumentParser(description='Validate world JSON')
    ap.add_argument('world', help='Path to world JSON')
    ap.add_argument('--require-reciprocals', action='store_true', help='Warn if reciprocal exits are missing')
    args = ap.parse_args()

    p = Path(args.world)
    if not p.exists():
        raise SystemExit(f'File not found: {p}')

    data = json.loads(p.read_text(encoding='utf-8'))
    nodes = data.get('nodes') if isinstance(data, dict) else data
    if nodes is None:
        if isinstance(data, list):
            nodes = data
        else:
            raise SystemExit('No nodes array found in JSON')

    id_map = {n['id']: n for n in nodes}

    # 1) Missing targets
    missing = []
    for n in nodes:
        for ex in n.get('exits', []) or []:
            to = ex.get('to')
            if to and to not in id_map:
                missing.append((n['id'], to))
    if missing:
        print('ERROR: Missing exit targets:')
        for src, tgt in missing:
            print(f'  {src} -> {tgt} (target not found)')
    else:
        print('All exit targets exist.')

    # 2) Reachability
    start_nodes = data.get('start_nodes', []) if isinstance(data, dict) else []
    if not start_nodes and nodes:
        start_nodes = [nodes[0]['id']]
    visited = set()
    dq = deque(start_nodes)
    while dq:
        cur = dq.popleft()
        if cur in visited or cur not in id_map:
            continue
        visited.add(cur)
        for ex in id_map[cur].get('exits', []) or []:
            to = ex.get('to')
            if to in id_map and to not in visited:
                dq.append(to)
    unreachable = set(id_map.keys()) - visited
    if unreachable:
        print('\nWARNING: Unreachable nodes from start nodes:')
        for n in sorted(unreachable):
            print(' ', n)
    else:
        print('\nAll nodes are reachable from start nodes.')

    # 3) Reciprocal check (optional)
    if args.require_reciprocals:
        missing_recip = []
        for n in nodes:
            for ex in n.get('exits', []) or []:
                to = ex.get('to')
                if to in id_map:
                    back_found = False
                    for ex2 in id_map[to].get('exits', []) or []:
                        if ex2.get('to') == n['id']:
                            back_found = True
                            break
                    if not back_found:
                        missing_recip.append((n['id'], to))
        if missing_recip:
            print('\nReciprocal exits missing for:')
            for a,b in missing_recip:
                print(f'  {a} -> {b}  (no {b} -> {a})')
        else:
            print('\nAll reciprocals present.')

if __name__ == '__main__':
    main()
