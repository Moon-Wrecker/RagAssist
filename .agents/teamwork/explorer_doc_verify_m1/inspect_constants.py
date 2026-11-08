import zipfile
import io
import urllib.request

wheel_url = "https://files.pythonhosted.org/packages/1c/f6/bee4c3b49570c2d312057c9e37c1446cf37eb1b86bf5872f7a797e803326/typesafe_sdk-0.7.5-py3-none-any.whl"
req_whl = urllib.request.Request(wheel_url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req_whl, timeout=15) as resp:
    content = resp.read()

with zipfile.ZipFile(io.BytesIO(content)) as z:
    for f in ["typesafe_sdk/_core/constants.py", "typesafe_sdk/_core/question_types.py"]:
        print(f"=== {f} ===")
        print(z.read(f).decode("utf-8", errors="replace")[:1500])
