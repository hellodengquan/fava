"""Final verification test for boundary date consistency across all modules."""
from __future__ import annotations

import tempfile
import os
from decimal import Decimal

from fava.core import FavaLedger
from fava.beans.helpers import (
    slice_entry_dates,
    filter_actual_transactions,
    is_actual_transaction,
)
from fava.beans.abc import Transaction
from fava.util.date import Month, Quarter

TEST_DATA = '''
option "title" "Final Verification Test"
option "operating_currency" "USD"

2024-01-01 open Assets:Cash USD
2024-01-01 open Assets:Bank USD
2024-01-01 open Expenses:Food USD
2024-01-01 open Expenses:Rent USD
2024-01-01 open Income:Salary USD

; Boundary date tests
2024-01-31 * "Jan 31 - Before Feb"
  Expenses:Food                                           100 USD
  Assets:Cash                                            -100 USD

; Multiple entries on Feb 1 (begin date)
2024-02-01 * "Feb 1 - Entry 1"
  Expenses:Food                                            10 USD
  Assets:Cash                                             -10 USD

2024-02-01 * "Feb 1 - Entry 2"
  Expenses:Rent                                          1000 USD
  Assets:Cash                                           -1000 USD

2024-02-15 * "Feb 15 - Mid Month"
  Expenses:Food                                            50 USD
  Assets:Cash                                             -50 USD

; Entry on Feb 29 (end date - 1 day)
2024-02-29 * "Feb 29 - End of Month"
  Expenses:Food                                            70 USD
  Assets:Cash                                             -70 USD

; Entry on Mar 1 (end date, should be excluded)
2024-03-01 * "Mar 1 - After Feb"
  Expenses:Food                                            20 USD
  Assets:Cash                                             -20 USD

; Quarter boundary tests
2024-03-31 * "Mar 31 - Before Q2"
  Expenses:Rent                                          1000 USD
  Assets:Cash                                           -1000 USD

2024-04-01 * "Apr 1 - Q2 Begin"
  Expenses:Food                                            30 USD
  Assets:Cash                                             -30 USD

; Budget
2024-01-01 custom "budget" Expenses:Food "monthly" 500.00 USD
2024-01-01 custom "budget" Expenses:Rent "monthly" 1000.00 USD
'''

def get_txn_narrations(entries):
    """Get narrations of actual transactions."""
    return sorted([e.narration for e in filter_actual_transactions(entries)])

def get_txn_total(entries, account):
    """Get total amount for actual transactions on account."""
    total = Decimal('0')
    for entry in filter_actual_transactions(entries):
        for posting in entry.postings:
            if posting.account == account:
                total += posting.units.number
    return total

def test_monthly_consistency():
    """Test monthly boundary consistency."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.beancount', delete=False) as f:
        f.write(TEST_DATA)
        temp_path = f.name
    
    try:
        ledger = FavaLedger(temp_path)
        
        print("=" * 80)
        print("TEST 1: Monthly boundary consistency (2024-02)")
        print("=" * 80)
        
        filtered = ledger.get_filtered(time='2024-02')
        begin, end = filtered.date_range.begin, filtered.date_range.end
        
        print(f"DateRange: [{begin}, {end})")
        print(f"Expected entries: Feb 1 (2 entries), Feb 15, Feb 29")
        print(f"Expected to exclude: Jan 31, Mar 1")
        print()
        
        # 1. Journal - using new actual_transactions property
        print("1. Journal (actual_transactions property):")
        journal_txns = filtered.actual_transactions
        journal_narrations = get_txn_narrations(journal_txns)
        journal_food_total = get_txn_total(journal_txns, 'Expenses:Food')
        journal_rent_total = get_txn_total(journal_txns, 'Expenses:Rent')
        print(f"   Count: {len(journal_txns)}")
        print(f"   Narrations: {journal_narrations}")
        print(f"   Expenses:Food total: {journal_food_total}")
        print(f"   Expenses:Rent total: {journal_rent_total}")
        print()
        
        # 2. Charts (interval_totals approach with is_actual_transaction)
        print("2. Charts (slice_entry_dates + is_actual_transaction):")
        sliced = slice_entry_dates(filtered.entries, begin, end)
        actual_sliced = [e for e in sliced if is_actual_transaction(e)]
        sliced_narrations = get_txn_narrations(actual_sliced)
        sliced_food_total = get_txn_total(actual_sliced, 'Expenses:Food')
        sliced_rent_total = get_txn_total(actual_sliced, 'Expenses:Rent')
        print(f"   Count: {len(actual_sliced)}")
        print(f"   Narrations: {sliced_narrations}")
        print(f"   Expenses:Food total: {sliced_food_total}")
        print(f"   Expenses:Rent total: {sliced_rent_total}")
        print()
        
        # 3. Manual filtering (begin <= date < end)
        print("3. Manual filtering (begin <= date < end):")
        manual = [e for e in ledger.all_entries 
                  if isinstance(e, Transaction) and is_actual_transaction(e)
                  and begin <= e.date < end]
        manual_narrations = sorted([e.narration for e in manual])
        manual_food_total = get_txn_total(manual, 'Expenses:Food')
        manual_rent_total = get_txn_total(manual, 'Expenses:Rent')
        print(f"   Count: {len(manual)}")
        print(f"   Narrations: {manual_narrations}")
        print(f"   Expenses:Food total: {manual_food_total}")
        print(f"   Expenses:Rent total: {manual_rent_total}")
        print()
        
        # 4. Budget calculation
        print("4. Budget calculation:")
        budget_food = ledger.budgets.calculate('Expenses:Food', begin, end)
        budget_rent = ledger.budgets.calculate('Expenses:Rent', begin, end)
        print(f"   Budget Expenses:Food: {budget_food}")
        print(f"   Budget Expenses:Rent: {budget_rent}")
        print()
        
        # Verify consistency
        print("-" * 80)
        print("CONSISTENCY CHECK:")
        print("-" * 80)
        
        all_checks_pass = True
        
        # Check 1: Journal actual == slice
        check1 = journal_narrations == sliced_narrations
        print(f"  Journal actual == slice filtered: {'✓ PASS' if check1 else '✗ FAIL'}")
        if not check1:
            all_checks_pass = False
        
        # Check 2: Journal actual == manual
        check2 = journal_narrations == manual_narrations
        print(f"  Journal actual == manual: {'✓ PASS' if check2 else '✗ FAIL'}")
        if not check2:
            all_checks_pass = False
        
        # Check 3: Food totals match
        check3 = journal_food_total == sliced_food_total == manual_food_total
        print(f"  Food totals match: {'✓ PASS' if check3 else '✗ FAIL'}")
        if not check3:
            print(f"    Journal: {journal_food_total}, Slice: {sliced_food_total}, Manual: {manual_food_total}")
            all_checks_pass = False
        
        # Check 4: Rent totals match
        check4 = journal_rent_total == sliced_rent_total == manual_rent_total
        print(f"  Rent totals match: {'✓ PASS' if check4 else '✗ FAIL'}")
        if not check4:
            print(f"    Journal: {journal_rent_total}, Slice: {sliced_rent_total}, Manual: {manual_rent_total}")
            all_checks_pass = False
        
        # Check 5: Begin date entries included (both Feb 1 entries)
        feb1_entries = [n for n in journal_narrations if n.startswith("Feb 1 -")]
        check5 = len(feb1_entries) == 2
        print(f"  Begin date (Feb 1) entries (2) included: {'✓ PASS' if check5 else '✗ FAIL'}")
        if not check5:
            print(f"    Found {len(feb1_entries)} entries: {feb1_entries}")
            all_checks_pass = False
        
        # Check 6: End date entries excluded
        check6 = all("Mar 1" not in n for n in journal_narrations)
        print(f"  End date (Mar 1) entries excluded: {'✓ PASS' if check6 else '✗ FAIL'}")
        if not check6:
            all_checks_pass = False
        
        # Check 7: Before begin date entries excluded
        check7 = all("Jan 31" not in n for n in journal_narrations)
        print(f"  Before begin date (Jan 31) entries excluded: {'✓ PASS' if check7 else '✗ FAIL'}")
        if not check7:
            all_checks_pass = False
        
        print()
        print(f"MONTHLY TEST: {'✓ ALL CHECKS PASS' if all_checks_pass else '✗ SOME CHECKS FAILED'}")
        print()
        
        return all_checks_pass
        
    finally:
        os.unlink(temp_path)

def test_quarterly_consistency():
    """Test quarterly boundary consistency."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.beancount', delete=False) as f:
        f.write(TEST_DATA)
        temp_path = f.name
    
    try:
        ledger = FavaLedger(temp_path)
        
        print("=" * 80)
        print("TEST 2: Quarterly boundary consistency (2024-Q2)")
        print("=" * 80)
        
        filtered = ledger.get_filtered(time='2024-Q2')
        begin, end = filtered.date_range.begin, filtered.date_range.end
        
        print(f"DateRange: [{begin}, {end})")
        print(f"Expected: include Apr 1, exclude Mar 31")
        print()
        
        # Check actual transactions
        journal_txns = filtered.actual_transactions
        journal_narrations = get_txn_narrations(journal_txns)
        
        print("Journal actual transactions:")
        print(f"   Narrations: {journal_narrations}")
        print()
        
        # Manual check
        manual = [e for e in ledger.all_entries 
                  if isinstance(e, Transaction) and is_actual_transaction(e)
                  and begin <= e.date < end]
        manual_narrations = sorted([e.narration for e in manual])
        
        check1 = journal_narrations == manual_narrations
        check2 = all("Apr 1" in n for n in journal_narrations)
        check3 = all("Mar 31" not in n for n in journal_narrations)
        
        print("CONSISTENCY CHECK:")
        print(f"  Journal == manual: {'✓ PASS' if check1 else '✗ FAIL'}")
        print(f"  Apr 1 included: {'✓ PASS' if check2 else '✗ FAIL'}")
        print(f"  Mar 31 excluded: {'✓ PASS' if check3 else '✗ FAIL'}")
        
        all_checks_pass = check1 and check2 and check3
        print()
        print(f"QUARTERLY TEST: {'✓ ALL CHECKS PASS' if all_checks_pass else '✗ SOME CHECKS FAILED'}")
        print()
        
        return all_checks_pass
        
    finally:
        os.unlink(temp_path)

def test_custom_range_consistency():
    """Test custom date range consistency."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.beancount', delete=False) as f:
        f.write(TEST_DATA)
        temp_path = f.name
    
    try:
        ledger = FavaLedger(temp_path)
        
        print("=" * 80)
        print("TEST 3: Custom range consistency (2024-02-15 to 2024-03-15)")
        print("=" * 80)
        
        filtered = ledger.get_filtered(time='2024-02-15 to 2024-03-15')
        begin, end = filtered.date_range.begin, filtered.date_range.end
        
        print(f"DateRange: [{begin}, {end})")
        print(f"Expected: include Feb 15, Feb 29, Mar 1; exclude Mar 31")
        print()
        
        # Check actual transactions
        journal_txns = filtered.actual_transactions
        journal_narrations = get_txn_narrations(journal_txns)
        
        print("Journal actual transactions:")
        print(f"   Narrations: {journal_narrations}")
        print()
        
        # Manual check
        manual = [e for e in ledger.all_entries 
                  if isinstance(e, Transaction) and is_actual_transaction(e)
                  and begin <= e.date < end]
        manual_narrations = sorted([e.narration for e in manual])
        
        check1 = journal_narrations == manual_narrations
        check2 = all("Feb 15" in n or "Feb 29" in n or "Mar 1" in n for n in journal_narrations)
        check3 = all("Mar 31" not in n for n in journal_narrations)
        
        print("CONSISTENCY CHECK:")
        print(f"  Journal == manual: {'✓ PASS' if check1 else '✗ FAIL'}")
        print(f"  Range entries included: {'✓ PASS' if check2 else '✗ FAIL'}")
        print(f"  Outside entries excluded: {'✓ PASS' if check3 else '✗ FAIL'}")
        
        all_checks_pass = check1 and check2 and check3
        print()
        print(f"CUSTOM RANGE TEST: {'✓ ALL CHECKS PASS' if all_checks_pass else '✗ SOME CHECKS FAILED'}")
        print()
        
        return all_checks_pass
        
    finally:
        os.unlink(temp_path)

if __name__ == '__main__':
    success1 = test_monthly_consistency()
    success2 = test_quarterly_consistency()
    success3 = test_custom_range_consistency()
    
    print("=" * 80)
    print("FINAL RESULT")
    print("=" * 80)
    all_success = success1 and success2 and success3
    print(f"Overall: {'✓ ALL TESTS PASS' if all_success else '✗ SOME TESTS FAILED'}")
    exit(0 if all_success else 1)
