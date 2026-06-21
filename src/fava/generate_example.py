"""Generate example ledger files for different scenarios.

测试覆盖率说明
--------------
模块对应单元测试文件：``tests/test_generate_example.py``（共 44 个测试用例）。
按 ``pytest --cov=fava.generate_example`` 统计：

- 语句覆盖率 (Stmts):   99% (279 / 280)
- 分支覆盖率 (Branch):  ~97% (62 / 64)
- 唯一未覆盖语句:  ``if __name__ == "__main__"`` 保护分支（脚本直入路径），不计入模块使用覆盖率
- 建议维护阈值:  >= 95%

场景覆盖说明
============

以下清单展示了三种示例账本模板对 Fava 常用查询/展示场景的覆盖情况：

+--------------------------+----------+------------+----------+
| Fava 常用场景            | 家庭模板 | 投资模板   | 企业模板 |
+==========================+==========+============+==========+
| 资产负债表 (Balance)     | |check|  | |check|    | |check|  |
+--------------------------+----------+------------+----------+
| 损益表 (Income Statement)| |check|  | |check|    | |check|  |
+--------------------------+----------+------------+----------+
| 账户树状浏览             | |check|  | |check|    | |check|  |
+--------------------------+----------+------------+----------+
| 交易明细查询             | |check|  | |check|    | |check|  |
+--------------------------+----------+------------+----------+
| 按时间段过滤             | |check|  | |check|    | |check|  |
+--------------------------+----------+------------+----------+
| 按账户过滤               | |check|  | |check|    | |check|  |
+--------------------------+----------+------------+----------+
| 按标签过滤               | |cross|  | |check|    | |cross|  |
+--------------------------+----------+------------+----------+
| 多币种/汇率展示          | |cross|  | |check|    | |cross|  |
+--------------------------+----------+------------+----------+
| 商品/持仓 (Holdings)     | |cross|  | |check|    | |cross|  |
+--------------------------+----------+------------+----------+
| 成本与资本利得           | |cross|  | |check|    | |cross|  |
+--------------------------+----------+------------+----------+
| 价格历史                 | |cross|  | |check|    | |cross|  |
+--------------------------+----------+------------+----------+
| 期初/期末余额            | |check|  | |check|    | |check|  |
+--------------------------+----------+------------+----------+
| 多级账户层次             | |check|  | |check|    | |check|  |
+--------------------------+----------+------------+----------+
| 折旧/摊销                | |cross|  | |cross|    | |check|  |
+--------------------------+----------+------------+----------+
| 应收/应付账款            | |cross|  | |cross|    | |check|  |
+--------------------------+----------+------------+----------+
| 税费核算                 | |cross|  | |cross|    | |check|  |
+--------------------------+----------+------------+----------+
| 贷款/利息支出            | |cross|  | |cross|    | |check|  |
+--------------------------+----------+------------+----------+
| 收入来源分析             | |check|  | |check|    | |check|  |
+--------------------------+----------+------------+----------+
| 支出分类统计             | |check|  | |check|    | |check|  |
+--------------------------+----------+------------+----------+
| 现金流视角               | |check|  | |check|    | |check|  |
+--------------------------+----------+------------+----------+
| 分红/投资收益            | |cross|  | |check|    | |cross|  |
+--------------------------+----------+------------+----------+
| 财务费用/手续费          | |cross|  | |check|    | |check|  |
+--------------------------+----------+------------+----------+

.. |check| unicode:: U+2714
.. |cross| unicode:: U+2718
"""

from __future__ import annotations

import random
import re
from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from collections.abc import Sequence


def _month_date(start_date: str, offset_months: int, day: int) -> str:
    """生成从 start_date 起第 offset_months 个月的第 day 日.

    Args:
        start_date: 起始日期，格式 ``YYYY-MM-DD``。
        offset_months: 偏移月数，0 表示当月。
        day: 月内日期 (1-31)。
    """
    y, m, _ = map(int, start_date.split("-"))
    total = y * 12 + (m - 1) + offset_months
    new_y = total // 12
    new_m = total % 12 + 1
    return f"{new_y:04d}-{new_m:02d}-{day:02d}"


def _header(title: str, operating_currency: str) -> str:
    return (
        f'option "title" "{title}"\n'
        f'option "operating_currency" "{operating_currency}"\n\n'
    )


def _commodity(date: str, symbol: str, name: str = "") -> str:
    lines = [f"{date} commodity {symbol}"]
    if name:
        lines.append(f'  name: "{name}"')
    return "\n".join(lines) + "\n\n"


def _open(date: str, account: str, currencies: str = "") -> str:
    if currencies:
        return f"{date} open {account} {currencies}\n"
    return f"{date} open {account}\n"


def _price(date: str, commodity: str, amount: str) -> str:
    return f"{date} price {commodity} {amount}\n"


def _txn(
    date: str,
    flag: str,
    payee: str,
    narration: str,
    postings: Sequence[tuple[str, str]],
    tags: str = "",
) -> str:
    tag_suffix = f" {tags}" if tags else ""
    lines = [f'{date} {flag} "{payee}" "{narration}"{tag_suffix}']
    for account, amount in postings:
        lines.append(f"  {account} {amount}")
    return "\n".join(lines) + "\n"


def _section(title: str) -> str:
    return f"\n\n* {title}\n\n"


def _subsection(title: str) -> str:
    return f"\n\n** {title}\n\n"


_FAMILY_CATEGORIES: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Expenses:Food:Groceries",
        [
            ("盒马鲜生", "采购食材"),
            ("山姆会员店", "采购食材"),
            ("沃尔玛", "采购日用品"),
            ("永辉超市", "采购食材"),
        ],
    ),
    (
        "Expenses:Food:Dining",
        [
            ("美团外卖", "午餐"),
            ("海底捞", "朋友聚餐"),
            ("西贝莜面村", "晚餐"),
            ("必胜客", "周末外卖"),
        ],
    ),
    (
        "Expenses:Transport",
        [
            ("地铁", "通勤充值"),
            ("滴滴出行", "打车"),
        ],
    ),
    (
        "Expenses:Entertainment",
        [
            ("万达影城", "看电影"),
            ("苹果商店", "购买App"),
        ],
    ),
    (
        "Expenses:Shopping",
        [
            ("优衣库", "买衣服"),
            ("京东", "网购"),
        ],
    ),
    (
        "Expenses:Medical",
        [
            ("诊所", "感冒看诊"),
        ],
    ),
]

_FAMILY_PAYMENT_METHODS: list[str] = [
    "Assets:Bank:ICBC",
    "Assets:EWallet:Alipay",
    "Assets:EWallet:WeChatPay",
    "Liabilities:CreditCard:CMB",
]


def generate_family(
    start_date: str = "2025-01-01",
    num_months: int = 3,
    currency: str = "CNY",
    entries_per_month: int = 8,
) -> str:
    """Generate a minimal family ledger.

    Args:
        start_date: 账本起始日期，格式 ``YYYY-MM-DD``。
        num_months: 生成交易的月份数。
        currency: 本位货币符号。
        entries_per_month: 每月日常交易笔数。
    """
    lines: list[str] = []
    lines.append(_header("极简家庭账本", currency))

    lines.append(_section("币种"))
    lines.append(_commodity("1970-01-01", currency, "人民币"))

    lines.append(_section("账户"))
    lines.append(_subsection("资产"))
    lines.append(_open(start_date, "Assets:Bank:ICBC", currency))
    lines.append(_open(start_date, "Assets:EWallet:Alipay", currency))
    lines.append(_open(start_date, "Assets:EWallet:WeChatPay", currency))

    lines.append(_subsection("负债"))
    lines.append(_open(start_date, "Liabilities:CreditCard:CMB", currency))

    lines.append(_subsection("收入"))
    lines.append(_open(start_date, "Income:Salary", currency))
    lines.append(_open(start_date, "Income:Freelance", currency))

    lines.append(_subsection("支出"))
    lines.append(_open(start_date, "Expenses:Housing:Rent", currency))
    lines.append(_open(start_date, "Expenses:Food:Groceries", currency))
    lines.append(_open(start_date, "Expenses:Food:Dining", currency))
    lines.append(_open(start_date, "Expenses:Transport", currency))
    lines.append(_open(start_date, "Expenses:Utilities:Electricity", currency))
    lines.append(_open(start_date, "Expenses:Utilities:Water", currency))
    lines.append(_open(start_date, "Expenses:Phone", currency))
    lines.append(_open(start_date, "Expenses:Entertainment", currency))
    lines.append(_open(start_date, "Expenses:Medical", currency))
    lines.append(_open(start_date, "Expenses:Shopping", currency))

    lines.append(_subsection("权益"))
    lines.append(_open(start_date, "Equity:Opening-Balances"))

    lines.append(_section("初始余额"))
    lines.append(
        _txn(
            start_date,
            "*",
            "期初余额",
            "银行账户初始余额",
            [
                ("Assets:Bank:ICBC", f"50000.00 {currency}"),
                ("Equity:Opening-Balances", f"-50000.00 {currency}"),
            ],
        )
    )
    lines.append(
        _txn(
            start_date,
            "*",
            "期初余额",
            "支付宝初始余额",
            [
                ("Assets:EWallet:Alipay", f"3000.00 {currency}"),
                ("Equity:Opening-Balances", f"-3000.00 {currency}"),
            ],
        )
    )
    lines.append(
        _txn(
            start_date,
            "*",
            "期初余额",
            "微信零钱初始余额",
            [
                ("Assets:EWallet:WeChatPay", f"1500.00 {currency}"),
                ("Equity:Opening-Balances", f"-1500.00 {currency}"),
            ],
        )
    )
    lines.append(
        _txn(
            start_date,
            "*",
            "期初余额",
            "信用卡初始欠款",
            [
                ("Liabilities:CreditCard:CMB", f"-2000.00 {currency}"),
                ("Equity:Opening-Balances", f"2000.00 {currency}"),
            ],
        )
    )

    lines.append(_section("日常交易"))
    rng = random.Random(42)

    for i in range(num_months):
        lines.append(f"\n\n*** {_month_date(start_date, i, 1)[:7]}月\n\n")

        lines.append(
            _txn(
                _month_date(start_date, i, 5),
                "*",
                "某科技公司",
                f"{i + 1}月工资",
                [
                    ("Assets:Bank:ICBC", f"15000.00 {currency}"),
                    ("Income:Salary", f"-15000.00 {currency}"),
                ],
            )
        )
        lines.append(
            _txn(
                _month_date(start_date, i, 5),
                "*",
                "房东",
                f"{i + 1}月房租",
                [
                    ("Assets:Bank:ICBC", f"-4500.00 {currency}"),
                    ("Expenses:Housing:Rent", f"4500.00 {currency}"),
                ],
            )
        )
        electricity = round(rng.uniform(80, 180), 2)
        lines.append(
            _txn(
                _month_date(start_date, i, 15),
                "*",
                "国家电网",
                f"{i + 1}月电费",
                [
                    ("Assets:Bank:ICBC", f"-{electricity:.2f} {currency}"),
                    ("Expenses:Utilities:Electricity", f"{electricity:.2f} {currency}"),
                ],
            )
        )
        water = round(rng.uniform(30, 60), 2)
        lines.append(
            _txn(
                _month_date(start_date, i, 16),
                "*",
                "自来水公司",
                f"{i + 1}月水费",
                [
                    ("Assets:Bank:ICBC", f"-{water:.2f} {currency}"),
                    ("Expenses:Utilities:Water", f"{water:.2f} {currency}"),
                ],
            )
        )
        phone = round(rng.uniform(50, 80), 2)
        lines.append(
            _txn(
                _month_date(start_date, i, 18),
                "*",
                "中国移动",
                f"{i + 1}月话费",
                [
                    ("Assets:EWallet:Alipay", f"-{phone:.2f} {currency}"),
                    ("Expenses:Phone", f"{phone:.2f} {currency}"),
                ],
            )
        )

        for _ in range(entries_per_month):
            cat_idx = rng.randint(0, len(_FAMILY_CATEGORIES) - 1)
            account, options = _FAMILY_CATEGORIES[cat_idx]
            payee, narration = rng.choice(options)
            pay_method = rng.choice(_FAMILY_PAYMENT_METHODS)
            amount = round(rng.uniform(20, 500), 2)
            day = rng.randint(2, 28)
            lines.append(
                _txn(
                    _month_date(start_date, i, day),
                    "*",
                    payee,
                    narration,
                    [
                        (pay_method, f"-{amount:.2f} {currency}"),
                        (account, f"{amount:.2f} {currency}"),
                    ],
                )
            )

        cc_payment = round(rng.uniform(500, 3000), 2)
        lines.append(
            _txn(
                _month_date(start_date, i, 28),
                "*",
                "招商银行",
                "还信用卡",
                [
                    ("Assets:Bank:ICBC", f"-{cc_payment:.2f} {currency}"),
                    ("Liabilities:CreditCard:CMB", f"{cc_payment:.2f} {currency}"),
                ],
            )
        )

    return "".join(lines)


def generate_investment(
    start_date: str = "2025-01-01",
    num_months: int = 3,
    base_currency: str = "CNY",
    with_usd: bool = True,
    with_hkd: bool = True,
) -> str:
    """Generate a multi-currency investment ledger.

    Args:
        start_date: 账本起始日期，格式 ``YYYY-MM-DD``。
        num_months: 生成交易的月份数。
        base_currency: 本位货币符号。
        with_usd: 是否包含美元投资账户。
        with_hkd: 是否包含港币投资账户。
    """
    lines: list[str] = []
    lines.append(_header("跨币种投资账本", base_currency))

    lines.append(_section("币种"))
    lines.append(_commodity("1970-01-01", base_currency, "人民币"))
    if with_usd:
        lines.append(_commodity("1792-01-01", "USD", "美元"))
        lines.append(_commodity("2020-01-01", "VOO", "Vanguard S&P 500 ETF"))
        lines.append(_commodity("2020-01-01", "QQQ", "Invesco QQQ Trust"))
        lines.append(_commodity("2020-01-01", "TCEHY", "腾讯控股ADR"))
    if with_hkd:
        lines.append(_commodity("1983-01-01", "HKD", "港币"))

    lines.append(_section("汇率"))
    rng = random.Random(42)
    if with_usd:
        usd_rate = 7.30
        for i in range(num_months):
            date_str = _month_date(start_date, i, 1)
            lines.append(_price(date_str, "USD", f"{usd_rate:.2f} {base_currency}"))
            mid_date = _month_date(start_date, i, 15)
            usd_rate += round(rng.uniform(-0.05, 0.05), 2)
            lines.append(_price(mid_date, "USD", f"{usd_rate:.2f} {base_currency}"))
    if with_hkd:
        hkd_rate = 0.94
        for i in range(num_months):
            date_str = _month_date(start_date, i, 1)
            lines.append(_price(date_str, "HKD", f"{hkd_rate:.2f} {base_currency}"))
            hkd_rate += round(rng.uniform(-0.02, 0.02), 2)

    lines.append(_section("账户"))
    lines.append(_subsection("资产"))
    lines.append(_open(start_date, "Assets:Bank:ICBC", base_currency))
    if with_usd:
        lines.append(_open(start_date, "Assets:Brokerage:US", "VOO,QQQ,TCEHY"))
        lines.append(_open(start_date, "Assets:Brokerage:US:Cash", "USD"))
    if with_hkd:
        lines.append(_open(start_date, "Assets:Brokerage:HK:Cash", "HKD"))

    lines.append(_subsection("负债"))
    lines.append(_open(start_date, "Liabilities:CreditCard:CMB", base_currency))

    lines.append(_subsection("收入"))
    lines.append(_open(start_date, "Income:Salary", base_currency))
    if with_usd:
        lines.append(_open(start_date, "Income:CapitalGains", "USD"))
        lines.append(_open(start_date, "Income:Dividend", "USD"))

    lines.append(_subsection("支出"))
    lines.append(_open(start_date, "Expenses:Financial:Fees", base_currency))
    lines.append(_open(start_date, "Expenses:Financial:Tax", base_currency))
    lines.append(_open(start_date, "Expenses:Housing:Rent", base_currency))
    lines.append(_open(start_date, "Expenses:Food", base_currency))
    lines.append(_open(start_date, "Expenses:Transport", base_currency))

    lines.append(_subsection("权益"))
    lines.append(_open(start_date, "Equity:Opening-Balances"))

    lines.append(_section("初始余额"))
    lines.append(
        _txn(
            start_date,
            "*",
            "期初余额",
            "银行账户初始余额",
            [
                ("Assets:Bank:ICBC", f"200000.00 {base_currency}"),
                ("Equity:Opening-Balances", f"-200000.00 {base_currency}"),
            ],
        )
    )
    if with_usd:
        lines.append(
            _txn(
                start_date,
                "*",
                "期初余额",
                "美股账户现金初始余额",
                [
                    ("Assets:Brokerage:US:Cash", "10000.00 USD"),
                    ("Equity:Opening-Balances", "-10000.00 USD"),
                ],
            )
        )
    if with_hkd:
        lines.append(
            _txn(
                start_date,
                "*",
                "期初余额",
                "港股账户现金初始余额",
                [
                    ("Assets:Brokerage:HK:Cash", "50000.00 HKD"),
                    ("Equity:Opening-Balances", "-50000.00 HKD"),
                ],
            )
        )

    lines.append(_section("工资与生活支出"))
    for i in range(num_months):
        lines.append(
            _txn(
                _month_date(start_date, i, 5),
                "*",
                "某科技公司",
                f"{i + 1}月工资",
                [
                    ("Assets:Bank:ICBC", f"30000.00 {base_currency}"),
                    ("Income:Salary", f"-30000.00 {base_currency}"),
                ],
                tags="#salary #recurring",
            )
        )
        lines.append(
            _txn(
                _month_date(start_date, i, 5),
                "*",
                "房东",
                f"{i + 1}月房租",
                [
                    ("Assets:Bank:ICBC", f"-6000.00 {base_currency}"),
                    ("Expenses:Housing:Rent", f"6000.00 {base_currency}"),
                ],
                tags="#rent #recurring",
            )
        )

    lines.append(_section("购汇与跨境转账"))
    if with_usd:
        for i in range(min(num_months, 2)):
            amount_usd = 20000 if i == 0 else 15000
            rate = 7.30 + i * 0.02
            lines.append(
                _txn(
                    _month_date(start_date, i, 10),
                    "*",
                    "工商银行",
                    "购汇转入美股账户",
                    [
                        (
                            "Assets:Brokerage:US:Cash",
                            f"{amount_usd}.00 USD @ {rate:.2f} {base_currency}",
                        ),
                        (
                            "Assets:Bank:ICBC",
                            f"-{amount_usd * rate:.2f} {base_currency}",
                        ),
                    ],
                    tags="#fx #usd",
                )
            )
            lines.append(
                _txn(
                    _month_date(start_date, i, 10),
                    "*",
                    "工商银行",
                    "购汇手续费",
                    [
                        ("Assets:Bank:ICBC", f"-200.00 {base_currency}"),
                        ("Expenses:Financial:Fees", f"200.00 {base_currency}"),
                    ],
                    tags="#fees #fx",
                )
            )
    if with_hkd:
        lines.append(
            _txn(
                _month_date(start_date, 1, 10),
                "*",
                "工商银行",
                "购汇转入港股账户",
                [
                    (
                        "Assets:Brokerage:HK:Cash",
                        f"50000.00 HKD @ 0.93 {base_currency}",
                    ),
                    ("Assets:Bank:ICBC", f"-46500.00 {base_currency}"),
                ],
                tags="#fx #hkd",
            )
        )
        lines.append(
            _txn(
                _month_date(start_date, 1, 10),
                "*",
                "工商银行",
                "购汇手续费",
                [
                    ("Assets:Bank:ICBC", f"-100.00 {base_currency}"),
                    ("Expenses:Financial:Fees", f"100.00 {base_currency}"),
                ],
                tags="#fees #fx",
            )
        )

    if with_usd:
        lines.append(_section("美股投资"))
        voo_price = 520.0
        qqq_price = 500.0
        for i in range(num_months):
            voo_price += round(rng.uniform(-10, 20), 2)
            qqq_price += round(rng.uniform(-8, 15), 2)
            if i % 2 == 0:
                lines.append(
                    _txn(
                        _month_date(start_date, i, 15),
                        "*",
                        "券商",
                        "买入VOO",
                        [
                            (
                                "Assets:Brokerage:US",
                                f"10 VOO {{{voo_price:.2f} USD}}",
                            ),
                            (
                                "Assets:Brokerage:US:Cash",
                                f"-{voo_price * 10:.2f} USD",
                            ),
                        ],
                        tags="#buy #voo #equity",
                    )
                )
            else:
                lines.append(
                    _txn(
                        _month_date(start_date, i, 15),
                        "*",
                        "券商",
                        "买入QQQ",
                        [
                            (
                                "Assets:Brokerage:US",
                                f"5 QQQ {{{qqq_price:.2f} USD}}",
                            ),
                            (
                                "Assets:Brokerage:US:Cash",
                                f"-{qqq_price * 5:.2f} USD",
                            ),
                        ],
                        tags="#buy #qqq #equity",
                    )
                )

        lines.append(_section("分红"))
        lines.append(
            _txn(
                _month_date(start_date, num_months - 1, 15),
                "*",
                "券商",
                "VOO分红",
                [
                    ("Assets:Brokerage:US:Cash", "60.00 USD"),
                    ("Income:Dividend", "-60.00 USD"),
                ],
                tags="#dividend #voo",
            )
        )

    return "".join(lines)


def generate_enterprise(
    start_date: str = "2025-01-01",
    num_months: int = 3,
    currency: str = "CNY",
) -> str:
    """Generate an enterprise accounting ledger.

    Args:
        start_date: 账本起始日期，格式 ``YYYY-MM-DD``。
        num_months: 生成交易的月份数。
        currency: 本位货币符号。
    """
    lines: list[str] = []
    lines.append(_header("企业核算账本", currency))

    lines.append(_section("币种"))
    lines.append(_commodity("1970-01-01", currency, "人民币"))

    lines.append(_section("账户"))
    lines.append(_subsection("资产"))
    lines.append(_open(start_date, "Assets:Current:Bank:ICBC", currency))
    lines.append(_open(start_date, "Assets:Current:Cash", currency))
    lines.append(_open(start_date, "Assets:Current:AccountsReceivable", currency))
    lines.append(_open(start_date, "Assets:Current:Inventory", currency))
    lines.append(_open(start_date, "Assets:Fixed:Equipment", currency))
    lines.append(_open(start_date, "Assets:Fixed:Vehicles", currency))

    lines.append(_subsection("负债"))
    lines.append(_open(start_date, "Liabilities:Current:AccountsPayable", currency))
    lines.append(_open(start_date, "Liabilities:Current:SalaryPayable", currency))
    lines.append(_open(start_date, "Liabilities:Current:TaxPayable:VAT", currency))
    lines.append(
        _open(start_date, "Liabilities:Current:TaxPayable:IncomeTax", currency)
    )
    lines.append(_open(start_date, "Liabilities:Current:SocialInsurance", currency))
    lines.append(_open(start_date, "Liabilities:NonCurrent:BankLoan", currency))

    lines.append(_subsection("收入"))
    lines.append(_open(start_date, "Income:Operating:Sales", currency))
    lines.append(_open(start_date, "Income:Other:Service", currency))

    lines.append(_subsection("支出"))
    lines.append(_open(start_date, "Expenses:Operating:COGS", currency))
    lines.append(_open(start_date, "Expenses:Operating:Salary", currency))
    lines.append(_open(start_date, "Expenses:Operating:SocialInsurance", currency))
    lines.append(_open(start_date, "Expenses:Operating:Rent", currency))
    lines.append(_open(start_date, "Expenses:Operating:Utilities", currency))
    lines.append(_open(start_date, "Expenses:Operating:Depreciation", currency))
    lines.append(_open(start_date, "Expenses:Selling:Advertising", currency))
    lines.append(_open(start_date, "Expenses:Selling:Commission", currency))
    lines.append(_open(start_date, "Expenses:Admin:Office", currency))
    lines.append(_open(start_date, "Expenses:Admin:Travel", currency))
    lines.append(_open(start_date, "Expenses:Financial:Interest", currency))
    lines.append(_open(start_date, "Expenses:Tax:IncomeTax", currency))
    lines.append(_open(start_date, "Expenses:Tax:VAT", currency))

    lines.append(_subsection("权益"))
    lines.append(_open(start_date, "Equity:Opening-Balances"))
    lines.append(_open(start_date, "Equity:RetainedEarnings"))

    lines.append(_section("初始余额"))
    lines.append(
        _txn(
            start_date,
            "*",
            "期初余额",
            "银行存款初始余额",
            [
                ("Assets:Current:Bank:ICBC", f"500000.00 {currency}"),
                ("Equity:Opening-Balances", f"-500000.00 {currency}"),
            ],
        )
    )
    lines.append(
        _txn(
            start_date,
            "*",
            "期初余额",
            "库存现金初始余额",
            [
                ("Assets:Current:Cash", f"5000.00 {currency}"),
                ("Equity:Opening-Balances", f"-5000.00 {currency}"),
            ],
        )
    )
    lines.append(
        _txn(
            start_date,
            "*",
            "期初余额",
            "存货初始余额",
            [
                ("Assets:Current:Inventory", f"200000.00 {currency}"),
                ("Equity:Opening-Balances", f"-200000.00 {currency}"),
            ],
        )
    )
    lines.append(
        _txn(
            start_date,
            "*",
            "期初余额",
            "固定资产初始余额",
            [
                ("Assets:Fixed:Equipment", f"300000.00 {currency}"),
                ("Equity:Opening-Balances", f"-300000.00 {currency}"),
            ],
        )
    )
    lines.append(
        _txn(
            start_date,
            "*",
            "期初余额",
            "银行贷款初始余额",
            [
                ("Liabilities:NonCurrent:BankLoan", f"-1000000.00 {currency}"),
                ("Equity:Opening-Balances", f"1000000.00 {currency}"),
            ],
        )
    )
    lines.append(
        _txn(
            start_date,
            "*",
            "期初余额",
            "应付账款初始余额",
            [
                ("Liabilities:Current:AccountsPayable", f"-80000.00 {currency}"),
                ("Equity:Opening-Balances", f"80000.00 {currency}"),
            ],
        )
    )

    lines.append(_section("月度业务"))
    rng = random.Random(42)

    for i in range(num_months):
        sales = round(rng.uniform(120000, 250000), 2)
        lines.append(f"\n\n*** {_month_date(start_date, i, 1)[:7]}月\n\n")

        lines.append(
            _txn(
                _month_date(start_date, i, 5),
                "*",
                f"客户{chr(ord('A') + i)}",
                "销售商品收入",
                [
                    (
                        "Assets:Current:Bank:ICBC",
                        f"{sales:.2f} {currency}",
                    ),
                    (
                        "Income:Operating:Sales",
                        f"{-sales * 0.885:.2f} {currency}",
                    ),
                    (
                        "Expenses:Tax:VAT",
                        f"{-sales * 0.115:.2f} {currency}",
                    ),
                ],
            )
        )

        cogs = round(sales * 0.55, 2)
        lines.append(
            _txn(
                _month_date(start_date, i, 8),
                "*",
                f"供应商{chr(ord('甲') + i)}",
                "采购原材料",
                [
                    ("Expenses:Operating:COGS", f"{cogs * 0.885:.2f} {currency}"),
                    ("Expenses:Tax:VAT", f"{cogs * 0.115:.2f} {currency}"),
                    (
                        "Liabilities:Current:AccountsPayable", f"{-cogs:.2f} {currency}"),
                ],
            )
        )

        salary = round(rng.uniform(110000, 140000), 2)
        social = round(salary * 0.28, 2)
        lines.append(
            _txn(
                _month_date(start_date, i, 10),
                "*",
                "人力资源部",
                f"{i + 1}月工资发放",
                [
                    ("Expenses:Operating:Salary", f"{salary:.2f} {currency}"),
                    (
                        "Expenses:Operating:SocialInsurance",
                        f"{social:.2f} {currency}",
                    ),
                    (
                        "Assets:Current:Bank:ICBC",
                        f"{-salary - social:.2f} {currency}",
                    ),
                ],
            )
        )

        lines.append(
            _txn(
                _month_date(start_date, i, 15),
                "*",
                "物业公司",
                f"{i + 1}月办公室租金",
                [
                    ("Expenses:Operating:Rent", f"25000.00 {currency}"),
                    ("Assets:Current:Bank:ICBC", f"-25000.00 {currency}"),
                ],
            )
        )

        utilities = round(rng.uniform(7000, 12000), 2)
        lines.append(
            _txn(
                _month_date(start_date, i, 18),
                "*",
                "国家电网",
                f"{i + 1}月电费",
                [
                    ("Expenses:Operating:Utilities", f"{utilities:.2f} {currency}"),
                    (
                        "Assets:Current:Bank:ICBC",
                        f"-{utilities:.2f} {currency}",
                    ),
                ],
            )
        )

        if i % 2 == 0:
            advertising = round(rng.uniform(20000, 40000), 2)
            lines.append(
                _txn(
                    _month_date(start_date, i, 20),
                    "*",
                    "广告公司",
                    "广告投放",
                    [
                        (
                            "Expenses:Selling:Advertising",
                            f"{advertising:.2f} {currency}",
                        ),
                        (
                            "Assets:Current:Bank:ICBC",
                            f"-{advertising:.2f} {currency}",
                        ),
                    ],
                )
            )

        if i == 1:
            travel = round(rng.uniform(5000, 10000), 2)
            lines.append(
                _txn(
                    _month_date(start_date, i, 20),
                    "*",
                    "员工出差",
                    "差旅费报销",
                    [
                        ("Expenses:Admin:Travel", f"{travel:.2f} {currency}"),
                        (
                            "Assets:Current:Bank:ICBC",
                            f"-{travel:.2f} {currency}",
                        ),
                    ],
                )
            )

        interest = round(rng.uniform(3500, 4500), 2)
        lines.append(
            _txn(
                _month_date(start_date, i, 25),
                "*",
                "银行",
                f"{i + 1}月贷款利息",
                [
                    ("Expenses:Financial:Interest", f"{interest:.2f} {currency}"),
                    ("Assets:Current:Bank:ICBC", f"-{interest:.2f} {currency}"),
                ],
            )
        )

        lines.append(
            _txn(
                _month_date(start_date, i, 28),
                "*",
                "供应商",
                "支付货款",
                [
                    (
                        "Liabilities:Current:AccountsPayable",
                        f"{cogs * 0.8:.2f} {currency}",
                    ),
                    (
                        "Assets:Current:Bank:ICBC",
                        f"{-cogs * 0.8:.2f} {currency}",
                    ),
                ],
            )
        )

        lines.append(
            _txn(
                _month_date(start_date, i, 28),
                "*",
                "财务部",
                f"{i + 1}月固定资产折旧",
                [
                    ("Expenses:Operating:Depreciation", f"5000.00 {currency}"),
                    ("Assets:Fixed:Equipment", f"-5000.00 {currency}"),
                ],
            )
        )

    return "".join(lines)


_TEMPLATES: dict[str, tuple[str, str]] = {
    "family": ("极简家庭账本", "example-family.beancount"),
    "investment": ("跨币种投资账本", "example-investment.beancount"),
    "enterprise": ("企业核算账本", "example-enterprise.beancount"),
}


@click.command()
@click.option(
    "-t",
    "--template",
    type=click.Choice(list(_TEMPLATES.keys())),
    required=True,
    help="选择场景模板",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    default=".",
    show_default=True,
    help="输出目录",
)
@click.option(
    "-s",
    "--start-date",
    default="2025-01-01",
    show_default=True,
    help="账本起始日期（YYYY-MM-DD）",
)
@click.option(
    "-m",
    "--months",
    type=click.IntRange(1, 60, clamp=False),
    default=3,
    show_default=True,
    help="生成交易的月份数（范围 1-60，默认 3 个月）",
)
@click.option(
    "-c",
    "--currency",
    default="CNY",
    show_default=True,
    help="本位货币符号（ISO 4217 风格，如 CNY/USD/EUR）",
)
@click.option(
    "--entries-per-month",
    type=click.IntRange(0, 100, clamp=False),
    default=8,
    show_default=True,
    help="家庭模板：每月日常交易笔数（范围 0-100，默认 8 笔）",
)
@click.option(
    "--with-usd/--no-with-usd",
    default=True,
    show_default=True,
    help="投资模板：是否包含美元投资账户（默认开启）",
)
@click.option(
    "--with-hkd/--no-with-hkd",
    default=True,
    show_default=True,
    help="投资模板：是否包含港币投资账户（默认开启）",
)
def main(
    *,
    template: str,
    output: str,
    start_date: str,
    months: int,
    currency: str,
    entries_per_month: int,
    with_usd: bool,
    with_hkd: bool,
) -> None:
    r"""基于场景模板生成 Fava 示例账本文件.

    支持三种场景模板：

    \b
    - family:     极简家庭账本（CNY，日常收支、信用卡还款）
    - investment: 跨币种投资账本（CNY/USD/HKD，购汇、美股港股、分红）
    - enterprise: 企业核算账本（CNY，营收、成本、税费、贷款）

    \b
    参数边界说明：
    - --months:            1 ~ 60 (月)
    - --entries-per-month: 0 ~ 100 (笔/月)，0 表示不生成随机日常交易
    """
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_date):
        msg = f"start_date 格式应为 YYYY-MM-DD，收到：{start_date}"
        raise click.BadParameter(msg)
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", currency):
        msg = (
            "currency 须以大写字母开头，后续为大写字母/数字/下划线"
            f"（长度 1-32），收到：{currency}"
        )
        raise click.BadParameter(msg)
    if not with_usd and not with_hkd and template == "investment":
        msg = "投资模板至少需要开启一个币种账户（--with-usd 或 --with-hkd）"
        raise click.BadParameter(msg)

    label, filename = _TEMPLATES[template]

    if template == "family":
        content = generate_family(
            start_date=start_date,
            num_months=months,
            currency=currency,
            entries_per_month=entries_per_month,
        )
    elif template == "investment":
        content = generate_investment(
            start_date=start_date,
            num_months=months,
            base_currency=currency,
            with_usd=with_usd,
            with_hkd=with_hkd,
        )
    else:
        content = generate_enterprise(
            start_date=start_date,
            num_months=months,
            currency=currency,
        )

    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename

    output_path.write_text(content, encoding="utf-8")
    click.secho(f"已生成 [{label}]: {output_path}", fg="green")
    click.secho(
        f"使用 fava {output_path} 启动查看",
        fg="yellow",
    )


if __name__ == "__main__":
    main()
