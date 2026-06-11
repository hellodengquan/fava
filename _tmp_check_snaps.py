import json
from pathlib import Path

snap_dir = Path('tests/__snapshots__')
files = sorted(snap_dir.glob('test_json_api-test_api-account_report_budget*.json'))
for f in files:
    name = f.name
    d = json.loads(f.read_text())
    print('=======', name, '=======')
    print('TOP-LEVEL KEYS:', list(d.keys()))
    if 'budget_categories' in d:
        print('budget_categories:', d['budget_categories'])
    if 'budgets' in d:
        budgets = d['budgets']
        for acct in sorted(budgets.keys())[:8]:
            arr = budgets[acct]
            if arr:
                first = arr[0]
                print(f'  {acct}: keys={list(first.keys())}')
                print(f'    budget={first.get("budget")}')
                print(f'    status={first.get("status")}')
                print(f'    ratio ={first.get("ratio")}')
                print(f'    cat   ={first.get("category")}')
        for k, v in list(d['budgets'].items())[:3]:
            print(f'  intervals for {k}: {len(v)}')
    print()
