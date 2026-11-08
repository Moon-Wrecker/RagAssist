import os

brain_dir = r'C:\Users\ASUS\.gemini\antigravity\brain'
if os.path.exists(brain_dir):
    for root, dirs, files in os.walk(brain_dir):
        if files:
            for f in files:
                full = os.path.join(root, f)
                print(full, os.path.getsize(full))
