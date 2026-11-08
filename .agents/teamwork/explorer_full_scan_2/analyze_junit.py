import xml.etree.ElementTree as ET
from collections import defaultdict
import os

tree = ET.parse(r'.agents/teamwork/explorer_full_scan_2/junit.xml')
root = tree.getroot()

suites = defaultdict(lambda: {'passed': 0, 'failed': 0, 'skipped': 0, 'xfailed': 0, 'total': 0})
failures_list = []
xfails_list = []
skipped_list = []

for ts in root.iter('testsuite'):
    for tc in ts.iter('testcase'):
        classname = tc.attrib.get('classname', '')
        name = tc.attrib.get('name', '')
        # determine category from classname: tests.unit, tests.integration, tests.security, tests.e2e, etc.
        parts = classname.split('.')
        category = parts[1] if len(parts) > 1 and parts[0] == 'tests' else 'other'
        
        suites[category]['total'] += 1
        
        failures = tc.findall('failure')
        skipped = tc.findall('skipped')
        
        if failures:
            suites[category]['failed'] += 1
            failures_list.append((classname, name, failures[0].attrib.get('message', ''), failures[0].text))
        elif skipped:
            msg = skipped[0].attrib.get('message', '')
            skip_type = skipped[0].attrib.get('type', '')
            if 'xfail' in skip_type.lower() or 'defect' in msg.lower():
                suites[category]['xfailed'] += 1
                xfails_list.append((classname, name, msg))
            else:
                suites[category]['skipped'] += 1
                skipped_list.append((classname, name, msg))
        else:
            suites[category]['passed'] += 1

print(f"{'CATEGORY':15} | {'TOTAL':5} | {'PASSED':6} | {'FAILED':6} | {'SKIPPED':7} | {'XFAILED':7}")
print("-" * 60)
total_all = defaultdict(int)
for cat, counts in sorted(suites.items()):
    print(f"{cat:15} | {counts['total']:5} | {counts['passed']:6} | {counts['failed']:6} | {counts['skipped']:7} | {counts['xfailed']:7}")
    for k in ['total', 'passed', 'failed', 'skipped', 'xfailed']:
        total_all[k] += counts[k]
print("-" * 60)
print(f"{'TOTAL':15} | {total_all['total']:5} | {total_all['passed']:6} | {total_all['failed']:6} | {total_all['skipped']:7} | {total_all['xfailed']:7}")

print("\n--- FAILURES ---")
for c, n, m, t in failures_list:
    print(f"\nFAIL: {c}::{n}")
    print(f"Message: {m}")
    if t:
        print(f"Trace:\n{t[:500]}...")

print(f"\n--- SKIPPED COUNT: {len(skipped_list)} ---")
# summarize skipped reasons
skip_reasons = defaultdict(int)
for c, n, m in skipped_list:
    short_reason = m.split(':')[0] if ':' in m else m
    skip_reasons[short_reason] += 1
for r, cnt in skip_reasons.items():
    print(f"  {r}: {cnt}")

print(f"\n--- XFAILED COUNT: {len(xfails_list)} ---")
defect_counts = defaultdict(int)
for c, n, m in xfails_list:
    defect_id = m.split(':')[0] if ':' in m else m
    defect_counts[defect_id] += 1
for d, cnt in sorted(defect_counts.items()):
    print(f"  {d}: {cnt}")
