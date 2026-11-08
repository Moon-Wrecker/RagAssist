import zipfile
import io
import urllib.request

wheel_url = "https://files.pythonhosted.org/packages/99/f1/fbe8f6c316936f7694cba5af8b65c3c7b925988e5280a91dfbce0b98281b/jev-0.3.0-py3-none-any.whl"
req_whl = urllib.request.Request(wheel_url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req_whl, timeout=15) as resp:
    content = resp.read()

with zipfile.ZipFile(io.BytesIO(content)) as z:
    print(z.read("jev.py").decode("utf-8", errors="replace")[:2000])
