import zipfile
import io
import urllib.request

wheel_url = "https://files.pythonhosted.org/packages/58/73/c9527f45530d77411f6a2fa0a576909299f4738373966c880b99e73474af/strands_decider-0.3.0-py3-none-any.whl"
req_whl = urllib.request.Request(wheel_url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req_whl, timeout=15) as resp:
    content = resp.read()

with zipfile.ZipFile(io.BytesIO(content)) as z:
    for f in ["strands_decider/schema.py", "strands_decider/server.py"]:
        print(f"=== {f} ===")
        print(z.read(f).decode("utf-8", errors="replace")[:1500])
