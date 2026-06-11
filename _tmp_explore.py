import json
from pathlib import Path
import sys
sys.path.insert(0, 'src')

from fava.application import create_app

test_data_dir = Path('tests/data')
app = create_app([
    str(test_data_dir / "long-example.beancount"),
    str(test_data_dir / "edit-example.beancount"),
    str(test_data_dir / "example.beancount"),
    str(test_data_dir / "extension-report-example.beancount"),
    str(test_data_dir / "import.beancount"),
    str(test_data_dir / "query-example.beancount"),
    str(test_data_dir / "errors.beancount"),
    str(test_data_dir / "off-by-one.beancount"),
    str(test_data_dir / "invalid-unicode.beancount"),
], load=True)
client = app.test_client()

resp = client.get('/example/api/account_report?interval=month&a=Expenses:Food&r=changes')
data = resp.json['data']
print("Top-level:", list(data.keys()))
print("Charts count:", len(data['charts']))
for i, ch in enumerate(data['charts']):
    print(f"--- chart[{i}] ---")
    for k, v in ch.items():
        if isinstance(v, list):
            print(f"  {k}: list len={len(v)}, first={v[0] if v else None}")
        elif isinstance(v, dict):
            print(f"  {k}: dict keys={list(v.keys())[:10]}")
        else:
            print(f"  {k}: {v}")
print("dates:")
for d in data['dates']:
    print(" ", d)
