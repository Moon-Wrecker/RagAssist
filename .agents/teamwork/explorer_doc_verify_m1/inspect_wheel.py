import json
import urllib.request
import zipfile
import io

def inspect_wheel(pkg_name):
    url = f"https://pypi.org/pypi/{pkg_name}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    
    releases = data.get("urls", [])
    wheel_url = None
    for r in releases:
        if r.get("packagetype") == "bdist_wheel":
            wheel_url = r.get("url")
            break
    if not wheel_url:
        print(f"No wheel found for {pkg_name}")
        return

    print(f"Fetching wheel for {pkg_name} from {wheel_url}...")
    req_whl = urllib.request.Request(wheel_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req_whl, timeout=15) as resp:
        content = resp.read()

    with zipfile.ZipFile(io.BytesIO(content)) as z:
        namelist = z.namelist()
        print(f"Files in {pkg_name} wheel ({len(namelist)} total):")
        for name in namelist[:25]:
            print(f"  {name}")
        if len(namelist) > 25:
            print(f"  ... and {len(namelist)-25} more")
        
        # Read __init__.py or client.py if available
        for target in ["typesafe_sdk/__init__.py", "typesafe_sdk/client.py"]:
            if target in namelist:
                print(f"\n--- {target} ---")
                text = z.read(target).decode("utf-8", errors="replace")
                print(text[:1000])

inspect_wheel("typesafe-sdk")
