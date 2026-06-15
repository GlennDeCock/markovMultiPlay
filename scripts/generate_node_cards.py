#!/usr/bin/env python3
"""
generate_node_cards.py

Generate printable HTML node cards.
Modes:
  blank  -- generate N blank cards (default 12)
  prefill <world.json> -- generate a card per node prefilled from a world JSON

Writes files to the project root:
  node_cards_blank.html
  node_cards_prefilled.html

Usage examples:
  python scripts/generate_node_cards.py blank --count 12
  python scripts/generate_node_cards.py prefill data/world/example_world.json
"""

import argparse
import json
from pathlib import Path
import html as _html

OUT_BLANK = Path(__file__).parents[0].parent / "node_cards_blank.html"
OUT_PREF  = Path(__file__).parents[0].parent / "node_cards_prefilled.html"
# JSON-style variants (handy for writing directly in JSON format)
OUT_BLANK_JSON = Path(__file__).parents[0].parent / "node_cards_blank_json.html"
OUT_PREF_JSON  = Path(__file__).parents[0].parent / "node_cards_prefilled_json.html"

HEADER = """<!doctype html>
<html lang=\"en\"> 
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Node Cards</title>
<style>
@page { size: A4; margin: 12mm; }
body { margin:0; font-family: "Courier New", Courier, monospace; color:#0f0f0c; background:#fff }
.container { padding:12mm }
.page { box-sizing:border-box; width:100%; height:287mm; page-break-after:always }
.card { border:1px solid #111; padding:12mm; height:100%; display:flex; flex-direction:column }
.header { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px }
.h1 { font-size:18px; font-weight:bold }
.field { margin-bottom:10px }
.label { font-size:11px; color:#111; margin-bottom:4px }
.small-line { height:1.3em; border-bottom:1px dashed #999; display:block }
.lines { flex:1; background-image: linear-gradient(transparent calc(100% - 1px), #e5e5e5 1px); background-size: 100% 1.2em; padding:8px 6px }
.exit-row { display:flex; gap:10px; margin-bottom:6px }
.exit-label { width:65% }
.exit-to { width:35% }
.checkbox { display:inline-block; width:12px; height:12px; border:1px solid #000; vertical-align:middle; margin-right:6px }
.note-lines { height:48px; background-image: linear-gradient(transparent calc(100% - 1px), #e5e5e5 1px); background-size: 100% 1.2em; padding:6px }
.small-muted { font-size:10px; color:#444 }
</style>
</head>
<body>
<div class=\"container\">"""

FOOTER = """
</div>
</body>
</html>
"""


def esc(s):
    return _html.escape(str(s)) if s is not None else ""


def render_blank_card(card_number=None):
    card = []
    card.append('<div class="page">')
    card.append('<div class="card">')
    card.append('<div class="header"><div class="h1">Node Card</div><div class="small-muted">Card #: {}</div></div>'.format(esc(card_number) if card_number else '____'))
    card.append('<div class="field"><div class="label">Node ID</div><div class="small-line"></div></div>')
    card.append('<div class="field"><div class="label">Title</div><div class="small-line"></div></div>')
    card.append('<div class="field" style="flex:0 0 36%;"><div class="label">Description / Text</div><div class="lines"></div></div>')
    card.append('<div class="field" style="flex:0 0 auto;"><div class="label">Exits (label → target node)</div>')
    for _ in range(6):
        card.append('<div class="exit-row"><div class="exit-label"><div class="small-line"></div></div><div class="exit-to"><div class="small-line"></div></div></div>')
    card.append('</div>')
    card.append('<div class="footer"><div><span class="checkbox"></span> Start node</div><div><span class="checkbox"></span> Mutated</div><div>Drift: ______ visits</div></div>')
    card.append('<div class="field" style="margin-top:8px;"><div class="label">Tags (comma-separated)</div><div class="small-line"></div></div>')
    card.append('<div class="field" style="margin-top:6px;"><div class="label">Notes</div><div class="note-lines"></div></div>')
    card.append('</div>')
    card.append('</div>')
    return '\n'.join(card)


def render_prefilled_card(node, start_nodes=None):
    nid = esc(node.get('id') or node.get('node_id') or '')
    title = esc(node.get('title',''))
    description = esc(node.get('description') or node.get('base_text') or node.get('text') or '')
    tags = esc(', '.join(node.get('tags',[]) if isinstance(node.get('tags',[]), list) else [str(node.get('tags'))] if node.get('tags') else ''))
    exits = node.get('exits', []) or []
    traces = node.get('traces', []) or []

    card = []
    card.append('<div class="page">')
    card.append('<div class="card">')
    card.append('<div class="header"><div class="h1">Node Card</div><div class="small-muted">Node: {}</div></div>'.format(nid))
    card.append('<div class="field"><div class="label">Node ID</div><div class="small-line">{}</div></div>'.format(nid))
    card.append('<div class="field"><div class="label">Title</div><div class="small-line">{}</div></div>'.format(title))
    # description - preserve simple newlines
    desc_html = description.replace('\n','<br>')
    card.append('<div class="field" style="flex:0 0 36%;"><div class="label">Description / Text</div><div class="lines">{}</div></div>'.format(desc_html))

    card.append('<div class="field" style="flex:0 0 auto;"><div class="label">Exits (label → target node)</div>')
    for i in range(6):
        if i < len(exits):
            ex = exits[i]
            # exits may be like {"to":"node_id", "label":"go north"}
            lab = esc(ex.get('label') or ex.get('text') or '')
            to  = esc(ex.get('to') or ex.get('node') or '')
            card.append('<div class="exit-row"><div class="exit-label"><div class="small-line">{}</div></div><div class="exit-to"><div class="small-line">{}</div></div></div>'.format(lab, to))
        else:
            card.append('<div class="exit-row"><div class="exit-label"><div class="small-line"></div></div><div class="exit-to"><div class="small-line"></div></div></div>')
    card.append('</div>')

    is_start = (start_nodes and nid in start_nodes)
    card.append('<div class="footer"><div><span class="checkbox">{}</span> Start node</div><div><span class="checkbox">{}</span> Mutated</div><div>Drift: {} visits</div></div>'.format('X' if is_start else '&nbsp;', '&nbsp;', esc(node.get('drift', ''))))
    card.append('<div class="field" style="margin-top:8px;"><div class="label">Tags (comma-separated)</div><div class="small-line">{}</div></div>'.format(tags))
    # traces (show up to 3)
    if traces:
        tshow = '\n'.join(esc(t) for t in (traces[-3:]))
        tshow = tshow.replace('\n','<br>')
        card.append('<div class="field"><div class="label">Recent traces</div><div class="small-line">{}</div></div>'.format(tshow))

    card.append('<div class="field" style="margin-top:6px;"><div class="label">Notes</div><div class="note-lines"></div></div>')
    card.append('</div>')
    card.append('</div>')
    return '\n'.join(card)


def render_json_blank_card(card_number=None):
    """Render a card page that shows labeled, fillable JSON fields for handwriting.

    This layout mirrors the JSON keys you will paste into `nodes.json` later:
    `id`, `title`, `text`, `exits` (array of {label,to,hidden}), `tags`.
    """
    card = []
    card.append('<div class="page">')
    card.append('<div class="card">')
    card.append('<div class="header"><div class="h1">Node Card — JSON</div><div class="small-muted">Card #: {}</div></div>'.format(esc(card_number) if card_number else '____'))

    # ID / Title
    card.append('<div class="field"><div class="label">id (use_lower_snake_case)</div><div class="small-line"></div></div>')
    card.append('<div class="field"><div class="label">title</div><div class="small-line"></div></div>')

    # Text
    card.append('<div class="field"><div class="label">text (full description)</div><div class="lines" style="height:88px;"></div></div>')

    # Exits table
    card.append('<div class="field"><div class="label">exits — each row: label → to (node_id). Mark hidden with X</div>')
    card.append('<table style="width:100%; border-collapse:collapse; font-family:monospace; font-size:12px;">')
    card.append('<tr style="font-weight:bold;"><td style="width:60%;">label</td><td style="width:33%;">to (node_id)</td><td style="width:7%;">hidden</td></tr>')
    for _ in range(6):
        card.append('<tr><td style="border-bottom:1px dashed #999;"><div class="small-line"></div></td><td style="border-bottom:1px dashed #999;"><div class="small-line"></div></td><td style="text-align:center; vertical-align:middle; border-bottom:1px dashed #999;"><div class="checkbox"></div></td></tr>')
    card.append('</table></div>')

    # Tags
    card.append('<div class="field"><div class="label">tags (comma-separated)</div><div class="small-line"></div></div>')

    # Small JSON skeleton to guide copy-paste when transcribing
    skeleton = {
        "id": "your_node_id",
        "title": "Your title",
        "text": "Full description...",
        "exits": [{"label": "go north", "to": "other_node", "hidden": False}],
        "tags": ["tag1", "tag2"]
    }
    pre = _html.escape(json.dumps(skeleton, ensure_ascii=False, indent=2))
    card.append('<div class="field"><div class="label">Quick JSON skeleton (copy this and replace values)</div>')
    card.append('<pre style="white-space:pre-wrap; font-family:monospace; font-size:12px; padding:8px; border:1px dashed #999;">')
    card.append(pre)
    card.append('</pre></div>')

    card.append('<div class="footer"><div><span class="checkbox"></span> Start node</div><div><span class="checkbox"></span> Mutated</div><div>Drift: ______ visits</div></div>')
    card.append('</div>')
    card.append('</div>')
    return '\n'.join(card)


def render_json_prefilled_card(node, start_nodes=None):
    """Render a structured, prefilled JSON-style card (editable fields and JSON block).

    Shows the node fields in labeled blanks and includes a pretty JSON block below
    to make transcription back into `nodes.json` straightforward.
    """
    nid = esc(node.get('id') or node.get('node_id') or '')
    title = esc(node.get('title',''))
    text = esc(node.get('text') or node.get('description') or node.get('base_text') or '')
    tags = node.get('tags', []) or []
    exits = node.get('exits', []) or []

    card = []
    card.append('<div class="page">')
    card.append('<div class="card">')
    card.append('<div class="header"><div class="h1">Node Card — JSON</div><div class="small-muted">Node: {}</div></div>'.format(nid))

    # ID / Title
    card.append('<div class="field"><div class="label">id</div><div class="small-line">{}</div></div>'.format(nid))
    card.append('<div class="field"><div class="label">title</div><div class="small-line">{}</div></div>'.format(title))

    # Text
    card.append('<div class="field"><div class="label">text</div><div class="lines" style="height:88px;">{}</div></div>'.format(text.replace('\n','<br>')))

    # Exits
    card.append('<div class="field"><div class="label">exits — label → to (node_id). Mark hidden with X</div>')
    card.append('<table style="width:100%; border-collapse:collapse; font-family:monospace; font-size:12px;">')
    card.append('<tr style="font-weight:bold;"><td style="width:60%;">label</td><td style="width:33%;">to (node_id)</td><td style="width:7%;">hidden</td></tr>')
    for i in range(6):
        if i < len(exits):
            ex = exits[i]
            lab = esc(ex.get('label') or ex.get('text') or '')
            to = esc(ex.get('to') or ex.get('node') or '')
            hidden = 'X' if ex.get('hidden') else '&nbsp;'
            card.append('<tr><td style="border-bottom:1px dashed #999;">{}</td><td style="border-bottom:1px dashed #999;">{}</td><td style="text-align:center; vertical-align:middle; border-bottom:1px dashed #999;">{}</td></tr>'.format(lab, to, hidden))
        else:
            card.append('<tr><td style="border-bottom:1px dashed #999;"><div class="small-line"></div></td><td style="border-bottom:1px dashed #999;"><div class="small-line"></div></td><td style="text-align:center; vertical-align:middle; border-bottom:1px dashed #999;"><div class="checkbox"></div></td></tr>')
    card.append('</table></div>')

    card.append('<div class="field"><div class="label">tags (comma-separated)</div><div class="small-line">{}</div></div>'.format(esc(', '.join(tags))))

    # Pretty JSON block
    obj = {
        'id': node.get('id') or '',
        'title': node.get('title') or '',
        'text': node.get('text') or node.get('description') or node.get('base_text') or '',
        'exits': [ {'label': ex.get('label',''), 'to': ex.get('to',''), 'hidden': ex.get('hidden', False)} for ex in exits ],
        'tags': tags,
    }
    pre = _html.escape(json.dumps(obj, ensure_ascii=False, indent=2))
    card.append('<div class="field"><div class="label">JSON (copy/paste into nodes.json)</div>')
    card.append('<pre style="white-space:pre-wrap; font-family:monospace; font-size:12px; padding:8px; border:1px dashed #999;">')
    card.append(pre)
    card.append('</pre></div>')

    card.append('<div class="footer"><div><span class="checkbox">{}</span> Start node</div><div><span class="checkbox">{}</span> Mutated</div><div>Drift: {} visits</div></div>'.format('X' if start_nodes and (node.get('id') or '') in start_nodes else '&nbsp;', '&nbsp;', esc(node.get('drift', ''))))
    card.append('</div>')
    card.append('</div>')
    return '\n'.join(card)


def generate_blank(count=12, out=None, fmt='plain'):
    """Generate blank cards. Use fmt='json' to produce JSON-skeleton pages."""
    out = out or (OUT_BLANK_JSON if fmt == 'json' else OUT_BLANK)
    parts = [HEADER]
    for i in range(1, count+1):
        if fmt == 'json':
            parts.append(render_json_blank_card(card_number=i))
        else:
            parts.append(render_blank_card(card_number=i))
    parts.append(FOOTER)
    out.write_text('\n'.join(parts), encoding='utf-8')
    print('Wrote', out)


def generate_prefill(world_file, out=None, fmt='plain'):
    out = out or (OUT_PREF_JSON if fmt == 'json' else OUT_PREF)
    p = Path(world_file)
    if not p.exists():
        raise SystemExit(f"World file not found: {p}")
    data = json.loads(p.read_text(encoding='utf-8'))
    nodes = data.get('nodes') if isinstance(data, dict) else data
    if nodes is None:
        # if the file itself is an array
        if isinstance(data, list):
            nodes = data
        else:
            raise SystemExit('No nodes found in world JSON')
    start_nodes = data.get('start_nodes', []) if isinstance(data, dict) else []
    parts = [HEADER]
    for node in nodes:
        if fmt == 'json':
            parts.append(render_json_prefilled_card(node, start_nodes=start_nodes))
        else:
            parts.append(render_prefilled_card(node, start_nodes=start_nodes))
    parts.append(FOOTER)
    out.write_text('\n'.join(parts), encoding='utf-8')
    print('Wrote', out)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Generate node card HTML (blank or prefilled)')
    sub = ap.add_subparsers(dest='mode')

    b = sub.add_parser('blank', help='Generate blank cards')
    b.add_argument('--count', '-n', type=int, default=12, help='Number of blank cards')
    b.add_argument('--format', '-f', choices=['plain', 'json'], default='plain',
                   help='Output layout format: plain (hand-fill) or json (JSON skeleton)')

    p = sub.add_parser('prefill', help='Generate prefilled cards from world JSON')
    p.add_argument('world', help='Path to world JSON (example: data/world/example_world.json)')
    p.add_argument('--format', '-f', choices=['plain', 'json'], default='plain',
                   help='Output layout format: plain (hand-fill) or json (JSON block)')

    args = ap.parse_args()
    if args.mode == 'blank':
        generate_blank(count=args.count, fmt=args.format)
    elif args.mode == 'prefill':
        generate_prefill(args.world, fmt=args.format)
    else:
        ap.print_help()
