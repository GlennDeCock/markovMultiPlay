import json
from pathlib import Path

data = json.loads(Path('data/worlds/empty_city_generated.json').read_text(encoding='utf-8'))
nodes = data['nodes']
no_exits = [n for n in nodes if not n.get('exits')]
one_exit = [n for n in nodes if len(n.get('exits', [])) == 1]
print(f'Total nodes: {len(nodes)}')
print(f'No exits: {len(no_exits)}')
print(f'One exit: {len(one_exit)}')
for n in no_exits[:3]:
    print('  no-exit node:', n['id'])
for n in one_exit[:3]:
    print('  one-exit node:', n['id'], '->', [e['to'] for e in n['exits']])
print()
print('start_nodes:', data.get('start_nodes'))
print()
lengths = sorted([len(n.get('text','').split()) for n in nodes], reverse=True)
print('Text word counts (top 5):', lengths[:5])
print('Text word counts (min):', min(lengths) if lengths else 0)
print()
# Show a sample text
print('Sample node text:')
print(nodes[0]['text'][:300])
