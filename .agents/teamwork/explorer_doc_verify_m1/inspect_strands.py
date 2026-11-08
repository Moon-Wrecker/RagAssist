import json
import urllib.request
import zipfile
import io

def inspect_strands_decider():
    url = "https://pypi.org/pypi/strands-decider/json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    
    wheel_url = data["urls"][0]["url"]
    print(f"Fetching strands-decider wheel from {wheel_url}...")
    req_whl = urllib.request.Request(wheel_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req_whl, timeout=15) as resp:
        content = resp.read()

    with zipfile.ZipFile(io.BytesIO(content)) as z:
        print("Files in strands-decider wheel:")
        for name in z.namelist()[:20]:
            print(f"  {name}")
        for target in ["strands_decider/__init__.py", "strands_decider/serve.py"]:
            if target in z.namelist():
                print(f"\n--- {target} ---")
                text = z.read(target).decode("utf-8", errors="replace")
                print(text[:1500])

inspect_strands_decider()
