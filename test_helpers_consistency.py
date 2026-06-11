"""Test the new helper functions for consistency."""
from __future__ import annotations

import tempfile
import os

from fava.core import FavaLedger
from fava.beans.helpers import (
    is_system_generated_transaction,
    is_actual_transaction,
    filter_actual_transactions,
    slice_entry_dates,
)
from fava.beans.abc import Transaction

TEST_DATA = '''
option "title" "Helper Test"
option "operating_currency" "USD"

2024-01-01 open Assets:Cash USD
2024-01-01 open Expenses:Food USD
2024-01-01 open Income:Salary USD

2024-01-10 * "Jan 10 - Salary"
  Assets:Cash                                            1000 USD
  Income:Salary                                         -1000 USD

2024-01-20 * "Jan 20 - Food"
  Expenses:Food                                           100 USD
  Assets:Cash                                            -100 USD
'''

def test_helper_functions():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.beancount', delete=False) as f:
        f.write(TEST_DATA)
        temp_path = f.name
    
    try:
        ledger = FavaLedger(temp_path)
        filtered = ledger.get_filtered(time='2024-01-15 to 2024-01-25')
        begin, end = filtered.date_range.begin, filtered.date_range.end
        
        print("=" * 70)
        print("Testing helper functions")
        print("=" * 70)
        print(f'DateRange: [{begin}, {end})')
        print()
        
        print("All entries in filtered.entries:")
        for i, entry in enumerate(filtered.entries):
            is_txn = isinstance(entry, Transaction)
            is_system = is_system_generated_transaction(entry)
            is_actual = is_actual_transaction(entry)
            print(f'  [{i}] {type(entry).__name__}: {entry.date} - {getattr(entry, "narration", "N/A")}')
            print(f'       is_txn={is_txn}, is_system={is_system}, is_actual={is_actual}')
            print()
        
        print("-" * 70)
        print("filter_actual_transactions result:")
        actual = filter_actual_transactions(filtered.entries)
        print(f'  Count: {len(actual)}')
        for entry in actual:
            print(f'    {entry.date} - {entry.narration}')
        
        print()
        print("-" * 70)
        print("slice_entry_dates result:")
        sliced = slice_entry_dates(filtered.entries, begin, end)
        print(f'  Count: {len(sliced)}')
        for entry in sliced:
            print(f'    {entry.date} - {getattr(entry, "narration", "N/A")}')
        
        print()
        print("-" * 70)
        print("Consistency check:")
        actual_from_filtered = filter_actual_transactions(filtered.entries)
        actual_from_sliced = filter_actual_transactions(slice_entry_dates(filtered.entries, begin, end))
        actual_from_all = filter_actual_transactions(slice_entry_dates(ledger.all_entries, begin, end))
        
        narrations_filtered = sorted([e.narration for e in actual_from_filtered])
        narrations_sliced = sorted([e.narration for e in actual_from_sliced])
        narrations_all = sorted([e.narration for e in actual_from_all])
        
        print(f'  From filtered.entries: {narrations_filtered}')
        print(f'  From sliced filtered:  {narrations_sliced}')
        print(f'  From sliced all:      {narrations_all}')
        print()
        
        if narrations_filtered == narrations_sliced == narrations_all:
            print("✓ All methods return consistent actual transactions")
        else:
            print("✗ Inconsistent results!")
        
        return narrations_filtered == narrations_sliced == narrations_all
        
    finally:
        os.unlink(temp_path)

if __name__ == '__main__':
    success = test_helper_functions()
    exit(0 if success else 1)
