import os

def walk_error(err):
    print("Walk error:", err)

brain_dir = r'C:\Users\ASUS\.gemini\antigravity\brain'
for root, dirs, files in os.walk(brain_dir, onerror=walk_error):
    for d in dirs:
        full = os.path.join(root, d)
        print("DIR:", full)
    for f in files:
        full = os.path.join(root, f)
        print("FILE:", full)
