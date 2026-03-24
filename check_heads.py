import os
import re

path = '/Users/fghjkl/Documents/Project/MyProject/menu-zen/menu_zen_back/alembic/versions'
nodes = {}
revisions = {}

for f in os.listdir(path):
    if f.endswith('.py'):
        with open(os.path.join(path, f), 'r') as file:
            content = file.read()
            rev_match = re.search(r'revision: str = [\'"]([^\'\"]*)[\'\"]', content)
            down_match = re.search(r'down_revision: Union\[str, Sequence\[str\], None\] = [\'"]([^\'\"]*)[\'\"]', content)
            if rev_match:
                rev = rev_match.group(1)
                down = down_match.group(1) if down_match and down_match.group(1) != 'None' else None
                nodes[rev] = down
                revisions[rev] = f

heads = set(revisions.keys()) - set(nodes.values())
print(f"Heads ({len(heads)}):")
for h in heads:
    print(f"- {h} ({revisions[h]}) -> Parent: {nodes[h]}")

# Print other things to see the tree
print("\nDown revisions mapping:")
for rev, down in nodes.items():
    print(f"{rev} -> {down}")

def find_children(parent):
    return [k for k, v in nodes.items() if v == parent]

print("\nTree Structure:")
for h in heads:
    curr = h
    path_len = 0
    while curr:
        path_len += 1
        curr = nodes[curr]
    print(f"Path from {h} has length {path_len}")
