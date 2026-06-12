import sys
import os
import shutil
import tempfile

sys.path.insert(0, "src")

from fava.core import FavaLedger
from fava.beans.funcs import hash_entry
from fava.beans.abc import Transaction
from fava.util.date import Month

# 复制测试文件到临时目录
src = os.path.abspath("tests/data/example.beancount")
dst = os.path.join(tempfile.gettempdir(), "test_suspicious.beancount")
shutil.copy(src, dst)
print(f"Copied test file to: {dst}")

# 加载账本
ledger = FavaLedger(dst)
print(f"Loaded {len(ledger.all_entries)} entries")

# 找到第一个交易
first_tx = None
for entry in ledger.all_entries:
    if isinstance(entry, Transaction):
        first_tx = entry
        break

if first_tx:
    entry_hash = hash_entry(first_tx)
    print(f"\nFirst transaction: {first_tx.date} - {first_tx.payee}")
    print(f"Entry hash: {entry_hash}")

    # 测试标记可疑
    print("\n--- Testing mark_suspicious ---")
    ledger.suspicious.mark_suspicious(entry_hash, "test reason")

    # 重新加载
    ledger.load_file()

    # 检查是否标记成功
    all_suspicious = ledger.suspicious.all_suspicious_transactions
    print(f"Suspicious transactions after mark: {len(all_suspicious)}")
    if all_suspicious:
        print(f"  - {all_suspicious[0].payee}: {all_suspicious[0].suspicious_reason}")

    # 测试按账户聚合
    by_account = ledger.suspicious.by_account()
    print(f"\nSuspicious by account groups: {len(by_account)}")
    for group in by_account:
        print(f"  {group.account}: {group.count}")

    # 测试按时间聚合
    by_time = ledger.suspicious.by_time(Month)
    print(f"\nSuspicious by time groups: {len(by_time)}")
    for period in by_time:
        print(f"  {period.period}: {period.count} transactions")
        for acc in period.by_account:
            print(f"    {acc.account}: {acc.count}")

    # 测试取消标记
    print("\n--- Testing unmark_suspicious ---")
    # 重新加载后，找到可疑交易的新哈希
    all_suspicious = ledger.suspicious.all_suspicious_transactions
    if all_suspicious:
        current_hash = all_suspicious[0].entry_hash
        print(f"Current suspicious entry hash: {current_hash}")
        result = ledger.suspicious.unmark_suspicious(current_hash)
        print(f"Unmark result: {result}")

        # 重新加载
        ledger.load_file()

        all_suspicious = ledger.suspicious.all_suspicious_transactions
        print(f"Suspicious transactions after unmark: {len(all_suspicious)}")
    else:
        print("No suspicious entries found to unmark")

    # 清理
    os.unlink(dst)
    print("\n✅ Test completed successfully!")
else:
    print("No transaction found")
