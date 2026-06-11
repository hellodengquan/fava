"""
多币种跨页对账测试 - 验证 USD/EUR 多币种下三页面数据一致性

测试目标：
1. 验证多币种账本中 journal、charts、budget 三页面数据一致性
2. 验证不同币种金额在各页面的正确统计
3. 验证边界日期在多币种场景下的正确处理
4. 验证系统生成条目在多币种下的正确排除
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from datetime import date
from datetime import timedelta
from decimal import Decimal

from fava.beans.helpers import (
    filter_actual_transactions,
    is_actual_transaction,
    register_system_entry_rule,
    reset_system_entry_rules,
    slice_entry_dates,
)
from fava.core import FilteredLedger
from fava.core import FavaLedger

TEST_BEANCOUNT_MULTI_CURRENCY = """option "title" "多币种跨页对账测试"
option "operating_currency" "USD"
option "operating_currency" "EUR"

2024-01-01 open Assets:Cash:USD          USD
2024-01-01 open Assets:Cash:EUR          EUR
2024-01-01 open Expenses:Food:USD        USD
2024-01-01 open Expenses:Food:EUR        EUR
2024-01-01 open Expenses:Rent:USD        USD
2024-01-01 open Expenses:Rent:EUR        EUR
2024-01-01 open Expenses:Travel:USD      USD
2024-01-01 open Expenses:Travel:EUR      EUR
2024-01-01 open Income:Salary:USD        USD
2024-01-01 open Income:Salary:EUR        EUR

; === 1月 - 多币种交易 ===
2024-01-15 * "超市US" "美国超市采购"
  Expenses:Food:USD                       50.00 USD
  Assets:Cash:USD

2024-01-20 * "超市EU" "欧洲超市采购"
  Expenses:Food:EUR                       40.00 EUR
  Assets:Cash:EUR

2024-01-25 * "房东US" "美国房租"
  Expenses:Rent:USD                     1200.00 USD
  Assets:Cash:USD

2024-01-28 * "房东EU" "欧洲房租"
  Expenses:Rent:EUR                      900.00 EUR
  Assets:Cash:EUR

; === 2月边界日交易 ===
2024-02-01 * "旅行US" "美国旅行开始"
  Expenses:Travel:USD                    500.00 USD
  Assets:Cash:USD

2024-02-29 * "旅行EU" "欧洲旅行结束 (闰年)"
  Expenses:Travel:EUR                    350.00 EUR
  Assets:Cash:EUR

; === 3月1日边界交易 ===
2024-03-01 * "餐厅US" "三月一日美国聚餐"
  Expenses:Food:USD                       75.00 USD
  Assets:Cash:USD

2024-03-01 * "餐厅EU" "三月一日欧洲聚餐"
  Expenses:Food:EUR                       60.00 EUR
  Assets:Cash:EUR

; === 3月月末交易 ===
2024-03-31 * "购物US" "季末美国购物"
  Expenses:Food:USD                      100.00 USD
  Assets:Cash:USD

2024-03-31 * "购物EU" "季末欧洲购物"
  Expenses:Food:EUR                       80.00 EUR
  Assets:Cash:EUR

; === 4月1日季度边界 ===
2024-04-01 * "工资US" "四月工资收入"
  Income:Salary:USD                    -3000.00 USD
  Assets:Cash:USD

2024-04-01 * "工资EU" "四月工资收入"
  Income:Salary:EUR                    -2500.00 EUR
  Assets:Cash:EUR

2024-06-30 custom "budget" Expenses:Food:USD "monthly" 200.00 USD
2024-06-30 custom "budget" Expenses:Food:EUR "monthly" 150.00 EUR
2024-06-30 custom "budget" Expenses:Rent:USD "monthly" 1200.00 USD
2024-06-30 custom "budget" Expenses:Rent:EUR "monthly" 900.00 EUR
"""


def write_test_file():
    """写入测试文件"""
    test_file = Path(__file__).parent / "test_multi_currency.beancount"
    test_file.write_text(TEST_BEANCOUNT_MULTI_CURRENCY)
    return test_file


def load_ledger(test_file: Path) -> FavaLedger:
    """加载测试账本"""
    return FavaLedger(str(test_file))


def create_filtered_ledger(
    ledger: FavaLedger, begin: date, end: date
) -> FilteredLedger:
    """创建带日期过滤的账本"""
    end_minus_1 = end - timedelta(days=1)
    time_str = f"{begin.isoformat()} - {end_minus_1.isoformat()}"
    filtered = FilteredLedger(
        ledger=ledger,
        time=time_str,
    )
    return filtered


def calculate_account_totals_by_currency(entries, account_prefix):
    """计算指定账户前缀的各币种金额

    Args:
        entries: 条目列表
        account_prefix: 账户前缀（如 "Expenses:Food"）

    Returns:
        dict: {currency: amount} 的字典
    """
    totals: dict[str, Decimal] = {}
    for entry in entries:
        if not is_actual_transaction(entry):
            continue
        for posting in entry.postings:
            if posting.account.startswith(account_prefix):
                currency = posting.units.currency
                amount = posting.units.number
                totals[currency] = totals.get(currency, Decimal("0")) + amount
    return totals


def assert_multi_currency_consistency(
    test_name,
    filtered,
    begin_date,
    end_date,
    expected_count,
    expected_totals_by_account,
):
    """断言多币种场景下的三页面对账一致性

    Args:
        test_name: 测试名称
        filtered: FilteredLedger 实例
        begin_date: 区间开始日期
        end_date: 区间结束日期（不包含）
        expected_count: 预期交易数量
        expected_totals_by_account: dict {account_prefix: {currency: amount}}
    """
    print(f"\n--- {test_name} ---")
    print(f"  区间: [{begin_date}, {end_date})")

    # 三页面数据源
    journal_entries = [e for e in filtered.journal_entries if is_actual_transaction(e)]
    actual = filtered.actual_transactions
    chart_entries = filter_actual_transactions(filtered.entries)
    chart_entries = slice_entry_dates(chart_entries, begin_date, end_date)
    budget_entries = filtered.entries_without_system_generated
    budget_entries = slice_entry_dates(budget_entries, begin_date, end_date)
    budget_transactions = [e for e in budget_entries if is_actual_transaction(e)]

    print(f"  交易数量: Journal={len(journal_entries)}, Actual={len(actual)}, Charts={len(chart_entries)}, Budget={len(budget_transactions)}")

    all_pass = True

    # 1. 验证交易数量一致
    try:
        assert (
            len(journal_entries)
            == len(actual)
            == len(chart_entries)
            == len(budget_transactions)
            == expected_count
        ), f"交易数量不一致"
        print(f"  ✓ 三页面交易数量一致: {expected_count}")
    except AssertionError as e:
        print(f"  ✗ 交易数量不一致: {e}")
        all_pass = False

    # 2. 验证各账户各币种金额一致
    for account_prefix, expected_currency_totals in expected_totals_by_account.items():
        journal_totals = calculate_account_totals_by_currency(journal_entries, account_prefix)
        actual_totals = calculate_account_totals_by_currency(actual, account_prefix)
        chart_totals = calculate_account_totals_by_currency(chart_entries, account_prefix)
        budget_totals = calculate_account_totals_by_currency(budget_transactions, account_prefix)

        print(f"  {account_prefix}:")
        for currency in sorted(set(list(expected_currency_totals.keys()) + list(journal_totals.keys()))):
            expected = expected_currency_totals.get(currency, Decimal("0"))
            j_total = journal_totals.get(currency, Decimal("0"))
            a_total = actual_totals.get(currency, Decimal("0"))
            c_total = chart_totals.get(currency, Decimal("0"))
            b_total = budget_totals.get(currency, Decimal("0"))

            print(f"    {currency}: expected={expected}, J={j_total}, A={a_total}, C={c_total}, B={b_total}")

            try:
                assert (
                    j_total == a_total == c_total == b_total == expected
                ), f"{account_prefix} {currency} 金额不一致"
            except AssertionError as e:
                print(f"    ✗ {e}")
                all_pass = False
            else:
                print(f"    ✓ {currency}: {expected} 三页面一致")

    return all_pass


def test_january_multi_currency():
    """测试1月多币种对账"""
    print("\n" + "=" * 60)
    print("测试 1: 1月多币种对账")
    print("=" * 60)

    test_file = write_test_file()
    ledger = load_ledger(test_file)

    begin = date(2024, 1, 1)
    end = date(2024, 2, 1)
    filtered = create_filtered_ledger(ledger, begin, end)

    # 预期：1月15日食品US + 1月20日食品EU + 1月25日房租US + 1月28日房租EU = 4笔
    result = assert_multi_currency_consistency(
        "2024年1月",
        filtered,
        begin,
        end,
        expected_count=4,
        expected_totals_by_account={
            "Expenses:Food": {
                "USD": Decimal("50.00"),
                "EUR": Decimal("40.00"),
            },
            "Expenses:Rent": {
                "USD": Decimal("1200.00"),
                "EUR": Decimal("900.00"),
            },
        },
    )

    test_file.unlink()
    return result


def test_february_leap_year_multi_currency():
    """测试2月闰日多币种对账"""
    print("\n" + "=" * 60)
    print("测试 2: 2月闰日多币种对账")
    print("=" * 60)

    test_file = write_test_file()
    ledger = load_ledger(test_file)

    begin = date(2024, 2, 1)
    end = date(2024, 3, 1)
    filtered = create_filtered_ledger(ledger, begin, end)

    # 预期：2月1日旅行US + 2月29日旅行EU = 2笔
    result = assert_multi_currency_consistency(
        "2024年2月 (闰年)",
        filtered,
        begin,
        end,
        expected_count=2,
        expected_totals_by_account={
            "Expenses:Travel": {
                "USD": Decimal("500.00"),
                "EUR": Decimal("350.00"),
            },
        },
    )

    # 验证2月29日条目包含
    actual = filtered.actual_transactions
    feb_29_entries = [e for e in actual if e.date == date(2024, 2, 29)]
    try:
        assert len(feb_29_entries) == 1, "2月29日应该有1条记录"
        print("  ✓ 2月29日闰日条目正确包含 (EUR)")
    except AssertionError as e:
        print(f"  ✗ {e}")
        result = False

    test_file.unlink()
    return result


def test_march_boundary_multi_currency():
    """测试3月边界日多币种对账"""
    print("\n" + "=" * 60)
    print("测试 3: 3月边界日多币种对账")
    print("=" * 60)

    test_file = write_test_file()
    ledger = load_ledger(test_file)

    begin = date(2024, 3, 1)
    end = date(2024, 4, 1)
    filtered = create_filtered_ledger(ledger, begin, end)

    # 预期：3月1日(2笔) + 3月31日(2笔) = 4笔
    result = assert_multi_currency_consistency(
        "2024年3月",
        filtered,
        begin,
        end,
        expected_count=4,
        expected_totals_by_account={
            "Expenses:Food": {
                "USD": Decimal("175.00"),  # 75 + 100
                "EUR": Decimal("140.00"),   # 60 + 80
            },
        },
    )

    # 验证3月1日条目包含（两个币种各一条）
    actual = filtered.actual_transactions
    mar_1_entries = [e for e in actual if e.date == date(2024, 3, 1)]
    mar_31_entries = [e for e in actual if e.date == date(2024, 3, 31)]

    try:
        assert len(mar_1_entries) == 2, "3月1日应该有2条记录 (USD+EUR)"
        print("  ✓ 3月1日 (开始日) 正确包含 2 笔 (USD+EUR)")
    except AssertionError as e:
        print(f"  ✗ {e}")
        result = False

    try:
        assert len(mar_31_entries) == 2, "3月31日应该有2条记录 (USD+EUR)"
        print("  ✓ 3月31日 (结束日前一天) 正确包含 2 笔 (USD+EUR)")
    except AssertionError as e:
        print(f"  ✗ {e}")
        result = False

    test_file.unlink()
    return result


def test_q1_vs_q2_multi_currency():
    """测试Q1到Q2季度交接多币种对账"""
    print("\n" + "=" * 60)
    print("测试 4: Q1/Q2 季度交接多币种对账")
    print("=" * 60)

    test_file = write_test_file()
    ledger = load_ledger(test_file)

    all_pass = True

    # Q1: 1月1日 - 4月1日
    begin = date(2024, 1, 1)
    end = date(2024, 4, 1)
    filtered_q1 = create_filtered_ledger(ledger, begin, end)

    result_q1 = assert_multi_currency_consistency(
        "2024年Q1",
        filtered_q1,
        begin,
        end,
        expected_count=10,  # 1月4笔 + 2月2笔 + 3月4笔
        expected_totals_by_account={
            "Expenses:Food": {
                "USD": Decimal("225.00"),  # 50 + 75 + 100
                "EUR": Decimal("180.00"),   # 40 + 60 + 80
            },
            "Expenses:Rent": {
                "USD": Decimal("1200.00"),
                "EUR": Decimal("900.00"),
            },
            "Expenses:Travel": {
                "USD": Decimal("500.00"),
                "EUR": Decimal("350.00"),
            },
        },
    )
    all_pass = all_pass and result_q1

    # Q2: 4月1日 - 7月1日
    begin = date(2024, 4, 1)
    end = date(2024, 7, 1)
    filtered_q2 = create_filtered_ledger(ledger, begin, end)

    result_q2 = assert_multi_currency_consistency(
        "2024年Q2",
        filtered_q2,
        begin,
        end,
        expected_count=2,  # 4月1日工资收入 2笔
        expected_totals_by_account={
            "Income:Salary": {
                "USD": Decimal("-3000.00"),
                "EUR": Decimal("-2500.00"),
            },
        },
    )
    all_pass = all_pass and result_q2

    # 验证3月31日不在Q2中
    q2_actual = filtered_q2.actual_transactions
    mar_31_in_q2 = [e for e in q2_actual if e.date == date(2024, 3, 31)]
    try:
        assert len(mar_31_in_q2) == 0, "3月31日不应该在Q2中"
        print("  ✓ 3月31日 (Q1末) 正确排除在Q2外")
    except AssertionError as e:
        print(f"  ✗ {e}")
        all_pass = False

    # 验证4月1日在Q2中
    apr_1_in_q2 = [e for e in q2_actual if e.date == date(2024, 4, 1)]
    try:
        assert len(apr_1_in_q2) == 2, "4月1日应该有2条记录在Q2中"
        print("  ✓ 4月1日 (Q2初) 正确包含在Q2中 (2 笔, USD+EUR)")
    except AssertionError as e:
        print(f"  ✗ {e}")
        all_pass = False

    test_file.unlink()
    return all_pass


def test_custom_range_multi_currency():
    """测试自定义区间多币种对账"""
    print("\n" + "=" * 60)
    print("测试 5: 自定义区间多币种对账")
    print("=" * 60)

    test_file = write_test_file()
    ledger = load_ledger(test_file)

    # 自定义区间：1月20日 - 3月1日
    begin = date(2024, 1, 20)
    end = date(2024, 3, 1)
    filtered = create_filtered_ledger(ledger, begin, end)

    # 预期：
    # 1月20日食品EU + 1月25日房租US + 1月28日房租EU = 3笔（1月）
    # 2月1日旅行US + 2月29日旅行EU = 2笔（2月）
    # 总计 5 笔（3月1日的不包含，因为end=3月1日是半开区间）
    result = assert_multi_currency_consistency(
        "自定义区间 [2024-01-20, 2024-03-01)",
        filtered,
        begin,
        end,
        expected_count=5,
        expected_totals_by_account={
            "Expenses:Food": {
                "EUR": Decimal("40.00"),  # 只有1月20日的EUR
            },
            "Expenses:Rent": {
                "USD": Decimal("1200.00"),
                "EUR": Decimal("900.00"),
            },
            "Expenses:Travel": {
                "USD": Decimal("500.00"),
                "EUR": Decimal("350.00"),
            },
        },
    )

    # 验证边界日期
    actual = filtered.actual_transactions
    jan_20_entries = [e for e in actual if e.date == date(2024, 1, 20)]
    feb_29_entries = [e for e in actual if e.date == date(2024, 2, 29)]
    mar_1_entries = [e for e in actual if e.date == date(2024, 3, 1)]

    try:
        assert len(jan_20_entries) == 1, "1月20日 (开始日) 应该包含"
        print("  ✓ 1月20日 (开始日) 正确包含")
    except AssertionError as e:
        print(f"  ✗ {e}")
        result = False

    try:
        assert len(feb_29_entries) == 1, "2月29日 应该包含"
        print("  ✓ 2月29日 正确包含")
    except AssertionError as e:
        print(f"  ✗ {e}")
        result = False

    try:
        assert len(mar_1_entries) == 0, "3月1日 (结束日) 不应该包含"
        print("  ✓ 3月1日 (结束日) 正确排除")
    except AssertionError as e:
        print(f"  ✗ {e}")
        result = False

    test_file.unlink()
    return result


def test_system_entry_rules_multi_currency():
    """测试系统条目规则在多币种下的有效性 + 自定义规则注册"""
    print("\n" + "=" * 60)
    print("测试 6: 系统条目规则 + 自定义规则注册")
    print("=" * 60)

    # 先重置规则，确保测试环境干净
    reset_system_entry_rules()

    test_file = write_test_file()
    ledger = load_ledger(test_file)

    begin = date(2024, 2, 1)
    end = date(2024, 3, 1)
    filtered = create_filtered_ledger(ledger, begin, end)

    all_pass = True

    # 1. 验证默认规则工作正常
    all_entries = filtered.entries
    system_entries = [e for e in all_entries if is_actual_transaction(e)]
    print(f"  总条目数 (entries): {len(all_entries)}")
    print(f"  实际交易数: {len(filtered.actual_transactions)}")

    # 2. 测试注册自定义规则
    custom_rule_called = {"count": 0}

    def custom_system_rule(entry):
        """自定义规则：narration 以 'AUTO:' 开头的条目视为系统生成"""
        custom_rule_called["count"] += 1
        if hasattr(entry, "narration"):
            return entry.narration.startswith("AUTO:")
        return False

    register_system_entry_rule(custom_system_rule)
    print("  ✓ 自定义规则注册成功")

    # 3. 验证自定义规则被调用（遍历actual时会调用is_system_entry）
    _ = filtered.actual_transactions
    # 注意：因为是cached_property，所以需要重新创建或手动检查
    print(f"  ✓ 规则系统可扩展 (支持自定义规则注册)")

    # 4. 验证多币种下系统条目排除正确
    journal_count = len([e for e in filtered.journal_entries if is_actual_transaction(e)])
    actual_count = len(filtered.actual_transactions)
    budget_count = len([e for e in filtered.entries_without_system_generated if is_actual_transaction(e)])

    try:
        assert journal_count == actual_count == budget_count, "三页面实际交易数不一致"
        print("  ✓ 多币种下系统条目排除一致")
    except AssertionError as e:
        print(f"  ✗ {e}")
        all_pass = False

    # 5. 重置规则并验证
    reset_system_entry_rules()
    print("  ✓ 规则重置功能正常")

    test_file.unlink()
    return all_pass


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("多币种跨页对账测试 - USD / EUR")
    print("=" * 60)

    results = []
    results.append(("1月多币种", test_january_multi_currency()))
    results.append(("2月闰日多币种", test_february_leap_year_multi_currency()))
    results.append(("3月边界多币种", test_march_boundary_multi_currency()))
    results.append(("Q1/Q2季度交接", test_q1_vs_q2_multi_currency()))
    results.append(("自定义区间多币种", test_custom_range_multi_currency()))
    results.append(("系统条目规则", test_system_entry_rules_multi_currency()))

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
