import ast
import re
from pathlib import Path

src = Path("src/ragassist")

patterns = [
    ("test_conditional", re.compile(r"if\s+.*(?:test|pytest|mock).*", re.IGNORECASE)),
    ("canned_mock_return", re.compile(r"return\s+['\"](?:test|fake|mock|dummy)['\"]", re.IGNORECASE)),
    ("test_attribute", re.compile(r"__test__\s*=")),
    ("sys_modules_pytest", re.compile(r"sys\.modules\[['\"]pytest")),
    ("hardcoded_jwt_secret", re.compile(r"jwt\.decode\(.*verify_signature\s*=\s*False")),
    ("hardcoded_pass_fail", re.compile(r"return\s+['\"](?:PASS|FAIL|SUCCESS|ERROR)['\"]")),
]

matches = []
for p in src.rglob("*.py"):
    text = p.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), start=1):
        # ignore comments
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for name, pat in patterns:
            if pat.search(stripped):
                matches.append((name, p.as_posix(), i, stripped))

print(f"Total pattern matches: {len(matches)}")
for name, path, line_no, content in matches:
    print(f"[{name}] {path}:{line_no} -> {content}")
