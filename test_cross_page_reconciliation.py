"""
跨页对账测试 - 确保 journal、图表、预算页三页面对边界日期上的交易统计口径一致

测试目标：
1. 验证同一区间内，journal 页面的实际交易与图表的 interval_totals 数据一致
2. 验证预算页面的实际支出与其他两页的数据一致
3. 验证边界日期（开始日、结束日）的条目在三个页面中被一致地包含或排除
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from datetime import date
from datetime import timedelta
from decimal import Decimal

from fava.beans.abc import Transaction
from fava.beans.helpers import filter_actual_transactions
from fava.beans.helpers import is_actual_transaction
from fava.beans.helpers import slice_entry_dates
from fava.core import FilteredLedger
from fava.core import FavaLedger
from fava.util.date import DateRange


TEST_BEANCOUNT = """
option "title" "跨页对账测试"
option "operating_currency" "CNY"

2024-01-01 open Assets:Cash
2024-01-01 open Expenses:Food
2024-01-01 open Expenses:Rent
2024-01-01 open Expenses:Entertainment
2024-01-01 open Liabilities:CreditCard

2024-02-01 * "超市" "月初采购"
  Expenses:Food                          200.00 CNY
  Assets:Cash

2024-02-01 * "房东" "2月房租"
  Expenses:Rent                         3000.00 CNY
  Assets:Cash

2024-02-15 * "餐厅" "情人节晚餐"
  Expenses:Food                          350.00 CNY
  Assets:Cash

2024-02-29 * "超市" "月末采购"
  Expenses:Food                          180.00 CNY
  Assets:Cash

2024-03-01 * "电影院" "3月1日电影"
  Expenses:Entertainment                 120.00 CNY
  Assets:Cash

2024-03-10 * "餐厅" "3月聚餐"
  Expenses:Food                          450.00 CNY
  Assets:Cash

2024-03-31 * "超市" "3月末采购"
  Expenses:Food                          220.00 CNY
  Assets:Cash

2024-04-01 * "房东" "4月房租"
  Expenses:Rent                         3000.00 CNY
  Assets:Cash

2024-06-30 custom "budget" Expenses:Food "monthly" 1000.00 CNY
2024-06-30 custom "budget" Expenses:Rent "monthly" 3000.00 CNY
2024-06-30 custom "budget" Expenses:Entertainment "monthly" 500.00 CNY
"""


def write_test_file():
    """写入测试文件"""
    test_file = Path(__file__).parent / "test_cross_page.beancount"
    test_file.write_text(TEST_BEANCOUNT)
    return test_file


def load_ledger(test_file: Path) -> FavaLedger:
    """加载测试账本"""
    return FavaLedger(str(test_file))


def create_filtered_ledger(
    ledger: FavaLedger, begin: date, end: date
) -> FilteredLedger:
    """创建带日期过滤的账本"""
    # 为了得到 [begin, end)，我们需要将结束日期设为 end-1 天
    # 因为 parse_date 会将单个日期解析为 [date, date+1)
    end_minus_1 = end - timedelta(days=1)
    time_str = f'{begin.isoformat()} - {end_minus_1.isoformat()}'
    filtered = FilteredLedger(
        ledger=ledger,
        time=time_str,
    )
    return filtered


def calculate_account_total(entries, account_name):
    """计算指定账户的总金额"""
    total = Decimal("0")
    for entry in entries:
        if not is_actual_transaction(entry):
            continue
        for posting in entry.postings:
            if posting.account == account_name:
                total += posting.units.number
    return total


def test_monthly_reconciliation():
    """测试月度区间的跨页对账"""
    print("\n" + "=" * 60)
    print("测试 1: 月度区间跨页对账 (2024年2月)")
    print("=" * 60)

    test_file = write_test_file()
    ledger = load_ledger(test_file)

    begin = date(2024, 2, 1)
    end = date(2024, 3, 1)
    filtered = create_filtered_ledger(ledger, begin, end)

    # 预期：2月1日(2笔), 2月15日(1笔), 2月29日(1笔) = 4笔
    expected_transactions = 4
    expected_food_total = Decimal("730.00")  # 200 + 350 + 180
    expected_rent_total = Decimal("3000.00")

    # 1. Journal 页面数据
    journal_entries = [
        e for e in filtered.journal_entries if is_actual_transaction(e)
    ]
    journal_transaction_count = len(journal_entries)
    journal_food_total = calculate_account_total(
        journal_entries, "Expenses:Food"
    )
    journal_rent_total = calculate_account_total(
        journal_entries, "Expenses:Rent"
    )

    print(f"\nJournal 页面:")
    print(f"  交易数量: {journal_transaction_count} (预期: {expected_transactions})")
    print(f"  食品支出: {journal_food_total} CNY (预期: {expected_food_total})")
    print(f"  房租支出: {journal_rent_total} CNY (预期: {expected_rent_total})")

    # 2. actual_transactions (应该与 journal 一致)
    actual = filtered.actual_transactions
    actual_transaction_count = len(actual)
    actual_food_total = calculate_account_total(actual, "Expenses:Food")
    actual_rent_total = calculate_account_total(actual, "Expenses:Rent")

    print(f"\nActual Transactions:")
    print(f"  交易数量: {actual_transaction_count} (预期: {expected_transactions})")
    print(f"  食品支出: {actual_food_total} CNY (预期: {expected_food_total})")
    print(f"  房租支出: {actual_rent_total} CNY (预期: {expected_rent_total})")

    # 3. Charts 页面 - 使用与 interval_totals 相同的过滤逻辑
    # interval_totals 内部使用 filter_actual_transactions + slice_entry_dates
    chart_entries = filter_actual_transactions(filtered.entries)
    chart_entries = slice_entry_dates(chart_entries, begin, end)
    chart_transaction_count = len(chart_entries)
    chart_food_total = calculate_account_total(chart_entries, "Expenses:Food")
    chart_rent_total = calculate_account_total(chart_entries, "Expenses:Rent")

    print(f"\nCharts 页面:")
    print(f"  交易数量: {chart_transaction_count} (预期: {expected_transactions})")
    print(f"  食品支出: {chart_food_total} CNY (预期: {expected_food_total})")
    print(f"  房租支出: {chart_rent_total} CNY (预期: {expected_rent_total})")

    # 4. 预算页面 - interval_balances
    from fava.core.tree import Tree

    budget_entries = filtered.entries_without_system_generated
    budget_entries = slice_entry_dates(budget_entries, begin, end)
    budget_tree = Tree(budget_entries, ["Expenses:Food", "Expenses:Rent"])

    budget_food_node = budget_tree.get("Expenses:Food")
    budget_rent_node = budget_tree.get("Expenses:Rent")

    # 从 tree 中提取金额
    budget_food_total = Decimal("0")
    budget_rent_total = Decimal("0")

    # 计算预算页面的实际交易数量
    budget_transactions = [
        e for e in budget_entries if is_actual_transaction(e)
    ]
    budget_transaction_count = len(budget_transactions)
    budget_food_total = calculate_account_total(
        budget_transactions, "Expenses:Food"
    )
    budget_rent_total = calculate_account_total(
        budget_transactions, "Expenses:Rent"
    )

    print(f"\n预算页面:")
    print(f"  交易数量: {budget_transaction_count} (预期: {expected_transactions})")
    print(f"  食品支出: {budget_food_total} CNY (预期: {expected_food_total})")
    print(f"  房租支出: {budget_rent_total} CNY (预期: {expected_rent_total})")

    # 验证结果
    all_pass = True

    print("\n" + "-" * 60)
    print("对账结果:")

    try:
        assert (
            journal_transaction_count == expected_transactions
        ), f"Journal 交易数量不匹配: {journal_transaction_count} != {expected_transactions}"
        assert (
            actual_transaction_count == expected_transactions
        ), f"Actual 交易数量不匹配: {actual_transaction_count} != {expected_transactions}"
        assert (
            chart_transaction_count == expected_transactions
        ), f"Charts 交易数量不匹配: {chart_transaction_count} != {expected_transactions}"
        assert (
            budget_transaction_count == expected_transactions
        ), f"Budget 交易数量不匹配: {budget_transaction_count} != {expected_transactions}"
        print("✓ 交易数量: 所有页面一致")
    except AssertionError as e:
        print(f"✗ 交易数量: {e}")
        all_pass = False

    try:
        assert (
            journal_food_total == expected_food_total
        ), f"Journal 食品支出不匹配: {journal_food_total} != {expected_food_total}"
        assert (
            actual_food_total == expected_food_total
        ), f"Actual 食品支出不匹配: {actual_food_total} != {expected_food_total}"
        assert (
            chart_food_total == expected_food_total
        ), f"Charts 食品支出不匹配: {chart_food_total} != {expected_food_total}"
        assert (
            budget_food_total == expected_food_total
        ), f"Budget 食品支出不匹配: {budget_food_total} != {expected_food_total}"
        print("✓ 食品支出: 所有页面一致")
    except AssertionError as e:
        print(f"✗ 食品支出: {e}")
        all_pass = False

    try:
        assert (
            journal_rent_total == expected_rent_total
        ), f"Journal 房租支出不匹配: {journal_rent_total} != {expected_rent_total}"
        assert (
            actual_rent_total == expected_rent_total
        ), f"Actual 房租支出不匹配: {actual_rent_total} != {expected_rent_total}"
        assert (
            chart_rent_total == expected_rent_total
        ), f"Charts 房租支出不匹配: {chart_rent_total} != {expected_rent_total}"
        assert (
            budget_rent_total == expected_rent_total
        ), f"Budget 房租支出不匹配: {budget_rent_total} != {expected_rent_total}"
        print("✓ 房租支出: 所有页面一致")
    except AssertionError as e:
        print(f"✗ 房租支出: {e}")
        all_pass = False

    # 检查三页互相一致
    try:
        assert (
            journal_transaction_count
            == actual_transaction_count
            == chart_transaction_count
            == budget_transaction_count
        ), "三页面交易数量不一致"
        assert (
            journal_food_total
            == actual_food_total
            == chart_food_total
            == budget_food_total
        ), "三页面食品支出不一致"
        assert (
            journal_rent_total
            == actual_rent_total
            == chart_rent_total
            == budget_rent_total
        ), "三页面房租支出不一致"
        print("✓ 三页面数据完全一致")
    except AssertionError as e:
        print(f"✗ 三页面数据不一致: {e}")
        all_pass = False

    return all_pass


def test_boundary_date_reconciliation():
    """测试边界日期的跨页对账"""
    print("\n" + "=" * 60)
    print("测试 2: 边界日期跨页对账 (2024-02-15 至 2024-03-15)")
    print("=" * 60)

    test_file = write_test_file()
    ledger = load_ledger(test_file)

    begin = date(2024, 2, 15)
    end = date(2024, 3, 15)
    filtered = create_filtered_ledger(ledger, begin, end)

    # 预期：2月15日(1笔), 2月29日(1笔), 3月1日(1笔) = 3笔
    # 3月10日不包含（3月10日 < 3月15日？是的，3月10日 < 3月15日，所以应该包含
    # 重新计算：2月15日(1), 2月29日(1), 3月1日(1), 3月10日(1) = 4笔
    expected_transactions = 4
    expected_food_total = Decimal("980.00")  # 350 + 180 + 450
    expected_entertainment_total = Decimal("120.00")

    print(f"日期区间: {begin} 至 {end}")
    print(f"规则: [begin, end) - 包含 begin，不包含 end")
    print(f"预期交易数量: {expected_transactions}")

    # Journal 页面
    journal_entries = [
        e for e in filtered.journal_entries if is_actual_transaction(e)
    ]
    journal_count = len(journal_entries)
    journal_food = calculate_account_total(journal_entries, "Expenses:Food")
    journal_entertainment = calculate_account_total(
        journal_entries, "Expenses:Entertainment"
    )

    # Actual transactions
    actual = filtered.actual_transactions
    actual_count = len(actual)
    actual_food = calculate_account_total(actual, "Expenses:Food")
    actual_entertainment = calculate_account_total(
        actual, "Expenses:Entertainment"
    )

    # Charts 页面
    chart_entries = filter_actual_transactions(filtered.entries)
    chart_entries = slice_entry_dates(chart_entries, begin, end)
    chart_count = len(chart_entries)
    chart_food = calculate_account_total(chart_entries, "Expenses:Food")
    chart_entertainment = calculate_account_total(
        chart_entries, "Expenses:Entertainment"
    )

    # 预算页面
    budget_entries = filtered.entries_without_system_generated
    budget_entries = slice_entry_dates(budget_entries, begin, end)
    budget_transactions = [
        e for e in budget_entries if is_actual_transaction(e)
    ]
    budget_count = len(budget_transactions)
    budget_food = calculate_account_total(
        budget_transactions, "Expenses:Food"
    )
    budget_entertainment = calculate_account_total(
        budget_transactions, "Expenses:Entertainment"
    )

    print("\n各页面数据:")
    print(
        f"  Journal: {journal_count} 笔, 食品: {journal_food}, 娱乐: {journal_entertainment}"
    )
    print(
        f"  Actual:  {actual_count} 笔, 食品: {actual_food}, 娱乐: {actual_entertainment}"
    )
    print(
        f"  Charts:  {chart_count} 笔, 食品: {chart_food}, 娱乐: {chart_entertainment}"
    )
    print(
        f"  Budget:  {budget_count} 笔, 食品: {budget_food}, 娱乐: {budget_entertainment}"
    )

    all_pass = True

    try:
        assert (
            journal_count
            == actual_count
            == chart_count
            == budget_count
            == expected_transactions
        ), f"交易数量不匹配: {journal_count}, {actual_count}, {chart_count}, {budget_count} != {expected_transactions}"
        print("\n✓ 交易数量: 所有页面一致")
    except AssertionError as e:
        print(f"\n✗ 交易数量: {e}")
        all_pass = False

    try:
        assert (
            journal_food
            == actual_food
            == chart_food
            == budget_food
            == expected_food_total
        ), f"食品支出不匹配"
        print("✓ 食品支出: 所有页面一致")
    except AssertionError as e:
        print(f"✗ 食品支出: {e}")
        all_pass = False

    try:
        assert (
            journal_entertainment
            == actual_entertainment
            == chart_entertainment
            == budget_entertainment
            == expected_entertainment_total
        ), f"娱乐支出不匹配"
        print("✓ 娱乐支出: 所有页面一致")
    except AssertionError as e:
        print(f"✗ 娱乐支出: {e}")
        all_pass = False

    # 验证边界日期条目
    print("\n边界日期验证:")
    feb_15_entries = [e for e in actual if e.date == date(2024, 2, 15)]
    mar_1_entries = [e for e in actual if e.date == date(2024, 3, 1)]
    mar_10_entries = [e for e in actual if e.date == date(2024, 3, 10)]
    mar_15_entries = [e for e in actual if e.date == date(2024, 3, 15)]

    print(f"  2月15日 (开始日): {len(feb_15_entries)} 笔 - 应该包含 ✓")
    print(f"  3月1日: {len(mar_1_entries)} 笔 - 应该包含 ✓")
    print(f"  3月10日: {len(mar_10_entries)} 笔 - 应该包含 ✓")
    print(f"  3月15日 (结束日): {len(mar_15_entries)} 笔 - 应该排除 ✓")

    try:
        assert len(feb_15_entries) == 1, "2月15日条目应该被包含"
        assert len(mar_1_entries) == 1, "3月1日条目应该被包含"
        assert len(mar_10_entries) == 1, "3月10日条目应该被包含"
        assert len(mar_15_entries) == 0, "3月15日条目应该被排除"
        print("✓ 边界日期处理正确")
    except AssertionError as e:
        print(f"✗ 边界日期处理错误: {e}")
        all_pass = False

    return all_pass


def test_quarterly_reconciliation():
    """测试季度区间的跨页对账"""
    print("\n" + "=" * 60)
    print("测试 3: 季度区间跨页对账 (2024年Q2)")
    print("=" * 60)

    test_file = write_test_file()
    ledger = load_ledger(test_file)

    # Q2: 4月1日 - 7月1日
    begin = date(2024, 4, 1)
    end = date(2024, 7, 1)
    filtered = create_filtered_ledger(ledger, begin, end)

    # 预期：4月1日(1笔房租) = 1笔
    expected_transactions = 1
    expected_rent_total = Decimal("3000.00")

    print(f"日期区间: {begin} 至 {end}")
    print(f"预期交易数量: {expected_transactions}")

    # 各页面数据
    journal_entries = [
        e for e in filtered.journal_entries if is_actual_transaction(e)
    ]
    actual = filtered.actual_transactions
    chart_entries = filter_actual_transactions(filtered.entries)
    chart_entries = slice_entry_dates(chart_entries, begin, end)
    budget_entries = filtered.entries_without_system_generated
    budget_entries = slice_entry_dates(budget_entries, begin, end)
    budget_transactions = [
        e for e in budget_entries if is_actual_transaction(e)
    ]

    print("\n各页面交易数量:")
    print(f"  Journal: {len(journal_entries)}")
    print(f"  Actual:  {len(actual)}")
    print(f"  Charts:  {len(chart_entries)}")
    print(f"  Budget:  {len(budget_transactions)}")

    all_pass = True
    try:
        assert (
            len(journal_entries)
            == len(actual)
            == len(chart_entries)
            == len(budget_transactions)
            == expected_transactions
        ), "交易数量不匹配"
        print("\n✓ 所有页面交易数量一致")
    except AssertionError as e:
        print(f"\n✗ 交易数量不一致: {e}")
        all_pass = False

    # 验证3月31日被排除，4月1日被包含
    mar_31_entries = [e for e in actual if e.date == date(2024, 3, 31)]
    apr_1_entries = [e for e in actual if e.date == date(2024, 4, 1)]

    print("\n季度边界验证:")
    print(f"  3月31日 (Q1末尾): {len(mar_31_entries)} 笔 - 应该排除 ✓")
    print(f"  4月1日 (Q2开始): {len(apr_1_entries)} 笔 - 应该包含 ✓")

    try:
        assert len(mar_31_entries) == 0, "3月31日应该被排除"
        assert len(apr_1_entries) == 1, "4月1日应该被包含"
        print("✓ 季度边界处理正确")
    except AssertionError as e:
        print(f"✗ 季度边界处理错误: {e}")
        all_pass = False

    return all_pass


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("跨页对账测试 - Journal / Charts / Budget")
    print("=" * 60)

    results = []
    results.append(("月度区间对账", test_monthly_reconciliation()))
    results.append(("边界日期对账", test_boundary_date_reconciliation()))
    results.append(("季度区间对账", test_quarterly_reconciliation()))

    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)

    all_pass = True
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {name}: {status}")
        if not result:
            all_pass = False

    print("-" * 60)
    if all_pass:
        print("Overall: ✓ ALL TESTS PASS")
        return 0
    else:
        print("Overall: ✗ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
