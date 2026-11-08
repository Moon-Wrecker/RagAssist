import os

root_dir = r'd:\Coding\RagAssist-1'
for dirpath, dirnames, filenames in os.walk(root_dir):
    if any(p in dirpath for p in ['.venv', '.pytest_cache', '.git']):
        continue
    for f in filenames:
        rel = os.path.relpath(os.path.join(dirpath, f), root_dir)
        print(rel)
