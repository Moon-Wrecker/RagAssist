import json
import urllib.request

packages = ['typesafe-sdk', 'jev', 'strands-decider', 'strands-agents', 'openai']
for pkg in packages:
    url = f"https://pypi.org/pypi/{pkg}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            info = data.get("info", {})
            print(f"=== {pkg} ===")
            print(f"Version: {info.get('version')}")
            print(f"Author: {info.get('author')}")
            print(f"Homepage: {info.get('home_page')}")
            print(f"Project URLs: {info.get('project_urls')}")
            print(f"Summary: {info.get('summary')}")
            print(f"Requires Python: {info.get('requires_python')}")
            print(f"Requires Dist: {info.get('requires_dist')[:5] if info.get('requires_dist') else None}")
    except Exception as e:
        print(f"=== {pkg} === ERROR: {e}")
