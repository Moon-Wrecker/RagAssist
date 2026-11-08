import json
import urllib.request
import zipfile
import io

def inspect_jev():
    url = "https://pypi.org/pypi/jev/json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    
    wheel_url = data["urls"][0]["url"]
    print(f"Fetching jev wheel from {wheel_url}...")
    req_whl = urllib.request.Request(wheel_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req_whl, timeout=15) as resp:
        content = resp.read()

    with zipfile.ZipFile(io.BytesIO(content)) as z:
        print("Files in jev wheel:")
        for name in z.namelist():
            print(f"  {name}")
        for target in ["jev/__init__.py"]:
            if target in z.namelist():
                print(f"\n--- {target} ---")
                text = z.read(target).decode("utf-8", errors="replace")
                print(text[:1500])

inspect_jev()
