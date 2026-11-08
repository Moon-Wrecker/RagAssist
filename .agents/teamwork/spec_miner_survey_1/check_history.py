import os

p = r'C:\Users\ASUS\.gemini\history'
if os.path.exists(p):
    for f in os.listdir(p):
        full = os.path.join(p, f)
        print(f, os.path.getsize(full))
