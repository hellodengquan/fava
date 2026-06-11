"""
边界日回归测试 - 验证各类边界日期的交易统计口径一致性

覆盖场景：
1. 跨年边界：2023-12-31 与 2024-01-01
2. 月末边界：2024-04-30 与 2024-05-01
3. 季度交接：2024-03-31 (Q1末) 与 2024-04-01 (Q2初)
4. 闰年边界：2024-02-29 与 2024-03-01

验证规则：
- 半开区间 [begin, end)：开始日包含，结束日不包含
- 系统生成条目正确排除
- 三页面（journal、charts、budget）数据一致
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
    is_system_entry,
    slice_entry_dates,
)
from fava.core import FilteredLedger
from fava.core import FavaLedger

TEST_BEANCOUNT = """option "title" "边界日回归测试"
option "operating_currency" "CNY"

2023-01-01 open Assets:Cash
2023-01-01 open Expenses:Food
2023-01-01 open Expenses:Rent
2023-01-01 open Expenses:Travel
2023-01-01 open Expenses:Entertainment

; === 跨年边界 ===
2023-12-31 * "餐厅" "跨年晚餐"
  Expenses:Food                          500.00 CNY
  Assets:Cash

2024-01-01 * "超市" "元旦采购"
  Expenses:Food                          300.00 CNY
  Assets:Cash

; === 闰年边界 (2024是闰年) ===
2024-02-28 * "超市" "月末采购"
  Expenses:Food                          150.00 CNY
  Assets:Cash

2024-02-29 * "餐厅" "闰日聚餐"
  Expenses:Food                          280.00 CNY
  Assets:Cash

2024-03-01 * "电影院" "三月新片"
  Expenses:Entertainment                 100.00 CNY
  Assets:Cash

; === 季度交接 (Q1 -> Q2) ===
2024-03-31 * "超市" "季末采购"
  Expenses:Food                          220.00 CNY
  Assets:Cash

2024-04-01 * "房东" "4月房租"
  Expenses:Rent                         3000.00 CNY
  Assets:Cash

; === 月末边界 (4月 -> 5月) ===
2024-04-30 * "餐厅" "月末聚餐"
  Expenses:Food                          450.00 CNY
  Assets:Cash

2024-05-01 * "旅行" "五一旅行"
  Expenses:Travel                       2000.00 CNY
  Assets:Cash

2024-06-30 custom "budget" Expenses:Food "monthly" 1000.00 CNY
2024-06-30 custom "budget" Expenses:Rent "monthly" 3000.00 CNY
2024-06-30 custom "budget" Expenses:Travel "monthly" 5000.00 CNY
2024-06-30 custom "budget" Expenses:Entertainment "monthly" 500.00 CNY
"""


def write_test_file():
    """写入测试文件"""
    test_file = Path(__file__).parent / "test_boundary_dates.beancount"
    test_file.write_text(TEST_BEANCOUNT)
    return test_file


def load_ledger(test_file: Path) -> FavaLedger:
    """加载测试账本"""
    return FavaLedger(str(test_file))


def create_filtered_ledger(
    ledger: FavaLedger, begin: date, end: date
) -> FilteredLedger:
    """创建带日期过滤的账本
    
    为了得到 [begin, end)，将结束日期字符串设为 end-1 天
    因为 parse_date 会将单个日期解析为 [date, date+1)
    """
    end_minus_1 = end - timedelta(days=1)
    time_str = f"{begin.isoformat()} - {end_minus_1.isoformat()}"
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


def count_entries_on_date(entries, target_date):
    """统计指定日期的条目数量"""
    return sum(1 for e in entries if e.date == target_date and is_actual_transaction(e))


def assert_boundary_consistency(
    test_name,
    filtered,
    begin_date,
    end_date,
    expected_include_begin,
    expected_include_end_minus_1,
    expected_total_count,
    expected_totals=None,
):
    """断言边界一致性
    
    Args:
        test_name: 测试名称
        filtered: FilteredLedger 实例
        begin_date: 区间开始日期
        end_date: 区间结束日期（不包含）
        expected_include_begin: 开始日应包含的条目数
        expected_include_end_minus_1: 结束日前一天应包含的条目数
        expected_total_count: 预期总条目数
        expected_totals: 各账户预期金额 dict
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
    
    print(f"  Journal 条目数: {len(journal_entries)}")
    print(f"  Actual 条目数:  {len(actual)}")
    print(f"  Charts 条目数:  {len(chart_entries)}")
    print(f"  Budget 条目数:  {len(budget_transactions)}")
    
    all_pass = True
    
    # 1. 验证三页面数量一致
    try:
        assert (
            len(journal_entries)
            == len(actual)
            == len(chart_entries)
            == len(budget_transactions)
            == expected_total_count
        ), f"条目数量不一致: journal={len(journal_entries)}, actual={len(actual)}, charts={len(chart_entries)}, budget={len(budget_transactions)}, expected={expected_total_count}"
        print(f"  ✓ 三页面条目数量一致: {expected_total_count}")
    except AssertionError as e:
        print(f"  ✗ 条目数量不一致: {e}")
        all_pass = False
    
    # 2. 验证开始日条目包含
    begin_count = count_entries_on_date(actual, begin_date)
    try:
        assert begin_count == expected_include_begin, f"开始日 {begin_date} 条目数: {begin_count} != {expected_include_begin}"
        print(f"  ✓ 开始日 {begin_date} 包含: {begin_count} 条")
    except AssertionError as e:
        print(f"  ✗ 开始日 {begin_date} 包含错误: {e}")
        all_pass = False
    
    # 3. 验证结束日前一天条目包含
    end_minus_1 = end_date - timedelta(days=1)
    end_minus_1_count = count_entries_on_date(actual, end_minus_1)
    try:
        assert end_minus_1_count == expected_include_end_minus_1, f"结束日前一天 {end_minus_1} 条目数: {end_minus_1_count} != {expected_include_end_minus_1}"
        print(f"  ✓ 结束日前一天 {end_minus_1} 包含: {end_minus_1_count} 条")
    except AssertionError as e:
        print(f"  ✗ 结束日前一天 {end_minus_1} 包含错误: {e}")
        all_pass = False
    
    # 4. 验证结束日当天条目不包含
    end_day_count = count_entries_on_date(actual, end_date)
    try:
        assert end_day_count == 0, f"结束日 {end_date} 条目数: {end_day_count} != 0 (应该排除)"
        print(f"  ✓ 结束日 {end_date} 排除: {end_day_count} 条")
    except AssertionError as e:
        print(f"  ✗ 结束日 {end_date} 排除错误: {e}")
        all_pass = False
    
    # 5. 验证金额一致
    if expected_totals:
        for account, expected_amount in expected_totals.items():
            journal_amount = calculate_account_total(journal_entries, account)
            actual_amount = calculate_account_total(actual, account)
            chart_amount = calculate_account_total(chart_entries, account)
            budget_amount = calculate_account_total(budget_transactions, account)
            
            try:
                assert (
                    journal_amount
                    == actual_amount
                    == chart_amount
                    == budget_amount
                    == expected_amount
                ), f"{account} 金额不一致: journal={journal_amount}, actual={actual_amount}, charts={chart_amount}, budget={budget_amount}, expected={expected_amount}"
                print(f"  ✓ {account}: {expected_amount} CNY")
            except AssertionError as e:
                print(f"  ✗ {account} 金额不一致: {e}")
                all_pass = False
    
    return all_pass


def test_year_boundary():
    """测试跨年边界：2023-12-31 与 2024-01-01"""
    print("\n" + "=" * 60)
    print("测试 1: 跨年边界")
    print("=" * 60)
    
    test_file = write_test_file()
    ledger = load_ledger(test_file)
    
    all_pass = True
    
    # 1a: 2023年区间，应包含12月31日
    begin = date(2023, 1, 1)
    end = date(2024, 1, 1)
    filtered = create_filtered_ledger(ledger, begin, end)
    
    result = assert_boundary_consistency(
        "2023年全年",
        filtered,
        begin,
        end,
        expected_include_begin=0,  # 1月1日没有条目
        expected_include_end_minus_1=1,  # 12月31日有1条
        expected_total_count=1,
        expected_totals={"Expenses:Food": Decimal("500.00")},
    )
    all_pass = all_pass and result
    
    # 1b: 2024年区间，应包含1月1日，不包含去年12月31日
    begin = date(2024, 1, 1)
    end = date(2025, 1, 1)
    filtered = create_filtered_ledger(ledger, begin, end)
    
    result = assert_boundary_consistency(
        "2024年全年",
        filtered,
        begin,
        end,
        expected_include_begin=1,  # 1月1日有1条
        expected_include_end_minus_1=0,  # 12月31日没有条目
        expected_total_count=8,
        expected_totals={
            "Expenses:Food": Decimal("1400.00"),  # 300+150+280+220+450
            "Expenses:Rent": Decimal("3000.00"),
            "Expenses:Travel": Decimal("2000.00"),
            "Expenses:Entertainment": Decimal("100.00"),
        },
    )
    all_pass = all_pass and result
    
    # 1c: 跨年精确区间：2023-12-31 到 2024-01-02
    begin = date(2023, 12, 31)
    end = date(2024, 1, 2)
    filtered = create_filtered_ledger(ledger, begin, end)
    
    result = assert_boundary_consistency(
        "跨年精确区间 [2023-12-31, 2024-01-02)",
        filtered,
        begin,
        end,
        expected_include_begin=1,  # 12月31日有1条
        expected_include_end_minus_1=1,  # 1月1日有1条
        expected_total_count=2,
        expected_totals={"Expenses:Food": Decimal("800.00")},
    )
    all_pass = all_pass and result
    
    test_file.unlink()
    return all_pass


def test_leap_year_boundary():
    """测试闰年边界：2024-02-29 与 2024-03-01"""
    print("\n" + "=" * 60)
    print("测试 2: 闰年边界 (2024年是闰年)")
    print("=" * 60)
    
    test_file = write_test_file()
    ledger = load_ledger(test_file)
    
    all_pass = True
    
    # 2a: 2024年2月，应包含2月29日
    begin = date(2024, 2, 1)
    end = date(2024, 3, 1)
    filtered = create_filtered_ledger(ledger, begin, end)
    
    result = assert_boundary_consistency(
        "2024年2月 (闰年)",
        filtered,
        begin,
        end,
        expected_include_begin=0,  # 2月1日没有条目
        expected_include_end_minus_1=1,  # 2月29日有1条
        expected_total_count=2,  # 2月28日 + 2月29日
        expected_totals={"Expenses:Food": Decimal("430.00")},  # 150 + 280
    )
    all_pass = all_pass and result
    
    # 2b: 验证2月29日条目确实存在
    actual = filtered.actual_transactions
    feb_29_entries = [e for e in actual if e.date == date(2024, 2, 29)]
    try:
        assert len(feb_29_entries) == 1, "2月29日应该有1条记录"
        assert feb_29_entries[0].narration == "闰日聚餐", "2月29日条目描述不符"
        print("  ✓ 2月29日闰日条目正确包含")
    except AssertionError as e:
        print(f"  ✗ 2月29日条目错误: {e}")
        all_pass = False
    
    # 2c: 2024年3月，不应包含2月29日
    begin = date(2024, 3, 1)
    end = date(2024, 4, 1)
    filtered = create_filtered_ledger(ledger, begin, end)
    
    result = assert_boundary_consistency(
        "2024年3月",
        filtered,
        begin,
        end,
        expected_include_begin=1,  # 3月1日有1条
        expected_include_end_minus_1=1,  # 3月31日有1条
        expected_total_count=2,  # 3月1日娱乐 + 3月31日食品
        expected_totals={
            "Expenses:Entertainment": Decimal("100.00"),
            "Expenses:Food": Decimal("220.00"),
        },
    )
    all_pass = all_pass and result
    
    # 验证2月29日不在3月区间中
    actual = filtered.actual_transactions
    feb_29_in_mar = [e for e in actual if e.date == date(2024, 2, 29)]
    try:
        assert len(feb_29_in_mar) == 0, "2月29日不应该在3月区间中"
        print("  ✓ 2月29日条目正确排除在3月区间外")
    except AssertionError as e:
        print(f"  ✗ 2月29日条目错误: {e}")
        all_pass = False
    
    test_file.unlink()
    return all_pass


def test_quarter_boundary():
    """测试季度交接：Q1末(3月31日) 与 Q2初(4月1日)"""
    print("\n" + "=" * 60)
    print("测试 3: 季度交接边界 (Q1 -> Q2)")
    print("=" * 60)
    
    test_file = write_test_file()
    ledger = load_ledger(test_file)
    
    all_pass = True
    
    # 3a: Q1 (1月1日 - 4月1日)，应包含3月31日
    begin = date(2024, 1, 1)
    end = date(2024, 4, 1)
    filtered = create_filtered_ledger(ledger, begin, end)
    
    result = assert_boundary_consistency(
        "2024年Q1",
        filtered,
        begin,
        end,
        expected_include_begin=1,  # 1月1日有1条
        expected_include_end_minus_1=1,  # 3月31日有1条
        expected_total_count=5,  # 1.1 + 2.28 + 2.29 + 3.1 + 3.31
        expected_totals={
            "Expenses:Food": Decimal("950.00"),  # 300 + 150 + 280 + 220
            "Expenses:Entertainment": Decimal("100.00"),
        },
    )
    
    # 3b: Q2 (4月1日 - 7月1日)，应包含4月1日，不包含3月31日
    begin = date(2024, 4, 1)
    end = date(2024, 7, 1)
    filtered = create_filtered_ledger(ledger, begin, end)
    
    result = assert_boundary_consistency(
        "2024年Q2",
        filtered,
        begin,
        end,
        expected_include_begin=1,  # 4月1日有1条
        expected_include_end_minus_1=0,  # 6月30日没有条目
        expected_total_count=3,  # 4.1房租 + 4.30聚餐 + 5.1旅行
        expected_totals={
            "Expenses:Rent": Decimal("3000.00"),
            "Expenses:Food": Decimal("450.00"),
            "Expenses:Travel": Decimal("2000.00"),
        },
    )
    all_pass = all_pass and result
    
    # 3c: 验证3月31日不在Q2中
    mar_31_in_q2 = count_entries_on_date(filtered.actual_transactions, date(2024, 3, 31))
    try:
        assert mar_31_in_q2 == 0, "3月31日不应该在Q2中"
        print("  ✓ 3月31日 (Q1末) 正确排除在Q2外")
    except AssertionError as e:
        print(f"  ✗ 3月31日错误: {e}")
        all_pass = False
    
    # 3d: 验证4月1日在Q2中
    apr_1_in_q2 = count_entries_on_date(filtered.actual_transactions, date(2024, 4, 1))
    try:
        assert apr_1_in_q2 == 1, "4月1日应该在Q2中"
        print("  ✓ 4月1日 (Q2初) 正确包含在Q2中")
    except AssertionError as e:
        print(f"  ✗ 4月1日错误: {e}")
        all_pass = False
    
    test_file.unlink()
    return all_pass


def test_month_end_boundary():
    """测试月末边界：4月30日 与 5月1日"""
    print("\n" + "=" * 60)
    print("测试 4: 月末边界 (4月 -> 5月)")
    print("=" * 60)
    
    test_file = write_test_file()
    ledger = load_ledger(test_file)
    
    all_pass = True
    
    # 4a: 4月，应包含4月30日
    begin = date(2024, 4, 1)
    end = date(2024, 5, 1)
    filtered = create_filtered_ledger(ledger, begin, end)
    
    result = assert_boundary_consistency(
        "2024年4月",
        filtered,
        begin,
        end,
        expected_include_begin=1,  # 4月1日有1条
        expected_include_end_minus_1=1,  # 4月30日有1条
        expected_total_count=2,  # 房租 + 聚餐
        expected_totals={
            "Expenses:Rent": Decimal("3000.00"),
            "Expenses:Food": Decimal("450.00"),
        },
    )
    all_pass = all_pass and result
    
    # 4b: 5月，应包含5月1日，不包含4月30日
    begin = date(2024, 5, 1)
    end = date(2024, 6, 1)
    filtered = create_filtered_ledger(ledger, begin, end)
    
    result = assert_boundary_consistency(
        "2024年5月",
        filtered,
        begin,
        end,
        expected_include_begin=1,  # 5月1日有1条
        expected_include_end_minus_1=0,  # 5月31日没有条目
        expected_total_count=1,
        expected_totals={"Expenses:Travel": Decimal("2000.00")},
    )
    all_pass = all_pass and result
    
    # 4c: 验证4月30日不在5月中
    apr_30_in_may = count_entries_on_date(filtered.actual_transactions, date(2024, 4, 30))
    try:
        assert apr_30_in_may == 0, "4月30日不应该在5月中"
        print("  ✓ 4月30日 (4月末) 正确排除在5月外")
    except AssertionError as e:
        print(f"  ✗ 4月30日错误: {e}")
        all_pass = False
    
    # 4d: 验证5月1日在5月中
    may_1_in_may = count_entries_on_date(filtered.actual_transactions, date(2024, 5, 1))
    try:
        assert may_1_in_may == 1, "5月1日应该在5月中"
        print("  ✓ 5月1日 (5月初) 正确包含在5月中")
    except AssertionError as e:
        print(f"  ✗ 5月1日错误: {e}")
        all_pass = False
    
    test_file.unlink()
    return all_pass


def test_system_entry_filtering():
    """测试系统生成条目的过滤规则"""
    print("\n" + "=" * 60)
    print("测试 5: 系统生成条目过滤 (is_system_entry)")
    print("=" * 60)
    
    test_file = write_test_file()
    ledger = load_ledger(test_file)
    
    all_pass = True
    
    # 使用有时间过滤的账本，clamp_opt 会生成系统条目
    begin = date(2024, 2, 1)
    end = date(2024, 3, 1)
    filtered = create_filtered_ledger(ledger, begin, end)
    
    # 检查所有条目中的系统条目
    all_entries = filtered.entries
    system_entries = [e for e in all_entries if is_system_entry(e)]
    actual_trans = [e for e in all_entries if is_actual_transaction(e)]
    
    print(f"  总条目数: {len(all_entries)}")
    print(f"  系统生成条目: {len(system_entries)}")
    print(f"  实际用户交易: {len(actual_trans)}")
    
    # 验证系统条目识别一致
    try:
        assert len(filtered.actual_transactions) == len(actual_trans), "actual_transactions 数量不一致"
        print("  ✓ actual_transactions 与 is_actual_transaction 筛选结果一致")
    except AssertionError as e:
        print(f"  ✗ {e}")
        all_pass = False
    
    # 验证系统条目都有 < 开头的 filename
    for entry in system_entries:
        filename = entry.meta.get("filename", "")
        try:
            assert filename.startswith("<"), f"系统条目 filename 不以 '<' 开头: {filename}"
        except AssertionError as e:
            print(f"  ✗ {e}")
            all_pass = False
    
    if system_entries:
        print(f"  ✓ 系统条目识别规则正确 (meta.filename 以 '<' 开头)")
    
    # 验证三页面都正确排除系统条目
    journal_actual = [e for e in filtered.journal_entries if is_actual_transaction(e)]
    budget_actual = [e for e in filtered.entries_without_system_generated if is_actual_transaction(e)]
    
    try:
        assert len(journal_actual) == len(filtered.actual_transactions), "journal 与 actual 数量不一致"
        assert len(budget_actual) == len(filtered.actual_transactions), "budget 与 actual 数量不一致"
        print("  ✓ 三页面都正确排除系统生成条目")
    except AssertionError as e:
        print(f"  ✗ {e}")
        all_pass = False
    
    test_file.unlink()
    return all_pass


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("边界日回归测试 - 跨年 / 月末 / 季度 / 闰年")
    print("=" * 60)
    
    results = []
    results.append(("跨年边界", test_year_boundary()))
    results.append(("闰年边界", test_leap_year_boundary()))
    results.append(("季度交接", test_quarter_boundary()))
    results.append(("月末边界", test_month_end_boundary()))
    results.append(("系统条目过滤", test_system_entry_filtering()))
    
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
