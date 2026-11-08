import json
import urllib.request
import urllib.error

packages = [
    'typesafe-sdk',
    'typesafe',
    'jev',
    'strands',
    'strands-agents',
    'strands-ai',
    'strands-agentic',
    'semantic-router',
    'rerankers',
    'chonkie',
    'flashrank',
]

for pkg in packages:
    url = f"https://pypi.org/pypi/{pkg}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            info = data.get("info", {})
            print(f"[FOUND] {pkg}: version={info.get('version')} | summary={info.get('summary')} | home={info.get('home_page') or info.get('project_url')}")
    except urllib.error.HTTPError as e:
        print(f"[NOT FOUND] {pkg}: HTTP {e.code}")
    except Exception as e:
        print(f"[ERROR] {pkg}: {e}")
