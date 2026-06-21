"""Generate example ledger files for different scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from collections.abc import Sequence


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


def _balance(date: str, account: str, amount: str) -> str:
    return f"{date} balance {account} {amount}\n"


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


def _generate_family() -> str:
    lines: list[str] = []
    lines.append(_header("极简家庭账本", "CNY"))

    lines.append(_section("币种"))
    lines.append(_commodity("1970-01-01", "CNY", "人民币"))

    lines.append(_section("账户"))
    lines.append(_subsection("资产"))
    lines.append(_open("2025-01-01", "Assets:Bank:ICBC", "CNY"))
    lines.append(_open("2025-01-01", "Assets:EWallet:Alipay", "CNY"))
    lines.append(_open("2025-01-01", "Assets:EWallet:WeChatPay", "CNY"))

    lines.append(_subsection("负债"))
    lines.append(_open("2025-01-01", "Liabilities:CreditCard:CMB", "CNY"))

    lines.append(_subsection("收入"))
    lines.append(_open("2025-01-01", "Income:Salary", "CNY"))
    lines.append(_open("2025-01-01", "Income:Freelance", "CNY"))

    lines.append(_subsection("支出"))
    lines.append(_open("2025-01-01", "Expenses:Housing:Rent", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Food:Groceries", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Food:Dining", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Transport", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Utilities:Electricity", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Utilities:Water", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Phone", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Entertainment", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Medical", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Shopping", "CNY"))

    lines.append(_subsection("权益"))
    lines.append(_open("2025-01-01", "Equity:Opening-Balances"))

    lines.append(_section("初始余额"))
    lines.append(
        _txn(
            "2025-01-01",
            "*",
            "期初余额",
            "银行账户初始余额",
            [
                ("Assets:Bank:ICBC", "50000.00 CNY"),
                ("Equity:Opening-Balances", "-50000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-01",
            "*",
            "期初余额",
            "支付宝初始余额",
            [
                ("Assets:EWallet:Alipay", "3000.00 CNY"),
                ("Equity:Opening-Balances", "-3000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-01",
            "*",
            "期初余额",
            "微信零钱初始余额",
            [
                ("Assets:EWallet:WeChatPay", "1500.00 CNY"),
                ("Equity:Opening-Balances", "-1500.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-01",
            "*",
            "期初余额",
            "信用卡初始欠款",
            [
                ("Liabilities:CreditCard:CMB", "-2000.00 CNY"),
                ("Equity:Opening-Balances", "2000.00 CNY"),
            ],
        )
    )

    monthly_data: list[tuple[str, list[tuple[str, str, str, str, list[tuple[str, str]]]]]] = [
        (
            "01",
            [
                ("2025-01-05", "*", "某科技公司", "1月工资",
                 [("Assets:Bank:ICBC", "15000.00 CNY"), ("Income:Salary", "-15000.00 CNY")]),
                ("2025-01-05", "*", "房东", "1月房租",
                 [("Assets:Bank:ICBC", "-4500.00 CNY"), ("Expenses:Housing:Rent", "4500.00 CNY")]),
                ("2025-01-08", "*", "盒马鲜生", "采购食材",
                 [("Assets:EWallet:Alipay", "-680.00 CNY"), ("Expenses:Food:Groceries", "680.00 CNY")]),
                ("2025-01-12", "*", "美团外卖", "午餐",
                 [("Assets:EWallet:WeChatPay", "-35.50 CNY"), ("Expenses:Food:Dining", "35.50 CNY")]),
                ("2025-01-14", "*", "地铁", "通勤充值",
                 [("Assets:EWallet:Alipay", "-200.00 CNY"), ("Expenses:Transport", "200.00 CNY")]),
                ("2025-01-15", "*", "国家电网", "1月电费",
                 [("Assets:Bank:ICBC", "-156.30 CNY"), ("Expenses:Utilities:Electricity", "156.30 CNY")]),
                ("2025-01-16", "*", "自来水公司", "1月水费",
                 [("Assets:Bank:ICBC", "-45.80 CNY"), ("Expenses:Utilities:Water", "45.80 CNY")]),
                ("2025-01-18", "*", "中国移动", "1月话费",
                 [("Assets:EWallet:Alipay", "-58.00 CNY"), ("Expenses:Phone", "58.00 CNY")]),
                ("2025-01-20", "*", "海底捞", "朋友聚餐",
                 [("Liabilities:CreditCard:CMB", "-268.00 CNY"), ("Expenses:Food:Dining", "268.00 CNY")]),
                ("2025-01-22", "*", "优衣库", "买冬装",
                 [("Liabilities:CreditCard:CMB", "-399.00 CNY"), ("Expenses:Shopping", "399.00 CNY")]),
                ("2025-01-25", "*", "万达影城", "看电影",
                 [("Assets:EWallet:WeChatPay", "-80.00 CNY"), ("Expenses:Entertainment", "80.00 CNY")]),
                ("2025-01-28", "*", "招商银行", "还信用卡",
                 [("Assets:Bank:ICBC", "-2667.00 CNY"), ("Liabilities:CreditCard:CMB", "2667.00 CNY")]),
            ],
        ),
        (
            "02",
            [
                ("2025-02-05", "*", "某科技公司", "2月工资",
                 [("Assets:Bank:ICBC", "15000.00 CNY"), ("Income:Salary", "-15000.00 CNY")]),
                ("2025-02-05", "*", "房东", "2月房租",
                 [("Assets:Bank:ICBC", "-4500.00 CNY"), ("Expenses:Housing:Rent", "4500.00 CNY")]),
                ("2025-02-10", "*", "自由职业平台", "设计项目收入",
                 [("Assets:EWallet:Alipay", "3500.00 CNY"), ("Income:Freelance", "-3500.00 CNY")]),
                ("2025-02-12", "*", "沃尔玛", "采购日用品",
                 [("Assets:EWallet:WeChatPay", "-320.00 CNY"), ("Expenses:Food:Groceries", "320.00 CNY")]),
                ("2025-02-14", "*", "西贝莜面村", "情人节晚餐",
                 [("Liabilities:CreditCard:CMB", "-386.00 CNY"), ("Expenses:Food:Dining", "386.00 CNY")]),
                ("2025-02-16", "*", "滴滴出行", "打车",
                 [("Assets:EWallet:WeChatPay", "-42.50 CNY"), ("Expenses:Transport", "42.50 CNY")]),
                ("2025-02-18", "*", "国家电网", "2月电费",
                 [("Assets:Bank:ICBC", "-132.60 CNY"), ("Expenses:Utilities:Electricity", "132.60 CNY")]),
                ("2025-02-20", "*", "京东", "买书",
                 [("Assets:EWallet:Alipay", "-156.00 CNY"), ("Expenses:Shopping", "156.00 CNY")]),
                ("2025-02-22", "*", "诊所", "感冒看诊",
                 [("Assets:EWallet:WeChatPay", "-180.00 CNY"), ("Expenses:Medical", "180.00 CNY")]),
                ("2025-02-25", "*", "招商银行", "还信用卡",
                 [("Assets:Bank:ICBC", "-785.00 CNY"), ("Liabilities:CreditCard:CMB", "785.00 CNY")]),
            ],
        ),
        (
            "03",
            [
                ("2025-03-05", "*", "某科技公司", "3月工资",
                 [("Assets:Bank:ICBC", "15000.00 CNY"), ("Income:Salary", "-15000.00 CNY")]),
                ("2025-03-05", "*", "房东", "3月房租",
                 [("Assets:Bank:ICBC", "-4500.00 CNY"), ("Expenses:Housing:Rent", "4500.00 CNY")]),
                ("2025-03-08", "*", "山姆会员店", "采购食材",
                 [("Assets:EWallet:Alipay", "-520.00 CNY"), ("Expenses:Food:Groceries", "520.00 CNY")]),
                ("2025-03-10", "*", "中国移动", "3月话费",
                 [("Assets:EWallet:Alipay", "-58.00 CNY"), ("Expenses:Phone", "58.00 CNY")]),
                ("2025-03-12", "*", "国家电网", "3月电费",
                 [("Assets:Bank:ICBC", "-98.40 CNY"), ("Expenses:Utilities:Electricity", "98.40 CNY")]),
                ("2025-03-15", "*", "必胜客", "周末外卖",
                 [("Assets:EWallet:WeChatPay", "-89.00 CNY"), ("Expenses:Food:Dining", "89.00 CNY")]),
                ("2025-03-18", "*", "地铁", "通勤充值",
                 [("Assets:EWallet:Alipay", "-200.00 CNY"), ("Expenses:Transport", "200.00 CNY")]),
                ("2025-03-20", "*", "苹果商店", "购买App",
                 [("Liabilities:CreditCard:CMB", "-68.00 CNY"), ("Expenses:Entertainment", "68.00 CNY")]),
                ("2025-03-25", "*", "招商银行", "还信用卡",
                 [("Assets:Bank:ICBC", "-454.00 CNY"), ("Liabilities:CreditCard:CMB", "454.00 CNY")]),
            ],
        ),
    ]

    lines.append(_section("日常交易"))
    for _month_label, transactions in monthly_data:
        lines.extend(_txn(*txn_data) for txn_data in transactions)
        lines.append("\n")

    return "".join(lines)


def _generate_investment() -> str:
    lines: list[str] = []
    lines.append(_header("跨币种投资账本", "CNY"))

    lines.append(_section("币种"))
    lines.append(_commodity("1970-01-01", "CNY", "人民币"))
    lines.append(_commodity("1792-01-01", "USD", "美元"))
    lines.append(_commodity("1999-01-01", "EUR", "欧元"))
    lines.append(_commodity("1983-01-01", "HKD", "港币"))
    lines.append(_commodity("2020-01-01", "VOO", "Vanguard S&P 500 ETF"))
    lines.append(_commodity("2020-01-01", "QQQ", "Invesco QQQ Trust"))
    lines.append(_commodity("2020-01-01", "TCEHY", "腾讯控股ADR"))

    lines.append(_section("汇率"))
    prices = [
        ("2025-01-01", "USD", "7.30 CNY"),
        ("2025-01-15", "USD", "7.28 CNY"),
        ("2025-02-01", "USD", "7.25 CNY"),
        ("2025-02-15", "USD", "7.27 CNY"),
        ("2025-03-01", "USD", "7.24 CNY"),
        ("2025-03-15", "USD", "7.22 CNY"),
        ("2025-01-01", "EUR", "7.85 CNY"),
        ("2025-02-01", "EUR", "7.78 CNY"),
        ("2025-03-01", "EUR", "7.80 CNY"),
        ("2025-01-01", "HKD", "0.94 CNY"),
        ("2025-02-01", "HKD", "0.93 CNY"),
        ("2025-03-01", "HKD", "0.93 CNY"),
        ("2025-01-01", "VOO", "520.00 USD"),
        ("2025-01-15", "VOO", "535.00 USD"),
        ("2025-02-01", "VOO", "540.00 USD"),
        ("2025-02-15", "VOO", "555.00 USD"),
        ("2025-03-01", "VOO", "548.00 USD"),
        ("2025-03-15", "VOO", "560.00 USD"),
        ("2025-01-01", "QQQ", "500.00 USD"),
        ("2025-01-15", "QQQ", "515.00 USD"),
        ("2025-02-01", "QQQ", "525.00 USD"),
        ("2025-02-15", "QQQ", "530.00 USD"),
        ("2025-03-01", "QQQ", "518.00 USD"),
        ("2025-03-15", "QQQ", "535.00 USD"),
        ("2025-01-01", "TCEHY", "48.00 USD"),
        ("2025-01-15", "TCEHY", "50.00 USD"),
        ("2025-02-01", "TCEHY", "52.00 USD"),
        ("2025-02-15", "TCEHY", "51.00 USD"),
        ("2025-03-01", "TCEHY", "53.00 USD"),
        ("2025-03-15", "TCEHY", "55.00 USD"),
    ]
    for date, commodity, price in prices:
        lines.append(_price(date, commodity, price))

    lines.append(_section("账户"))
    lines.append(_subsection("资产"))
    lines.append(_open("2025-01-01", "Assets:Bank:ICBC", "CNY"))
    lines.append(_open("2025-01-01", "Assets:Brokerage:US", "VOO,QQQ,TCEHY"))
    lines.append(_open("2025-01-01", "Assets:Brokerage:US:Cash", "USD"))
    lines.append(_open("2025-01-01", "Assets:Brokerage:HK", "TCEHY"))
    lines.append(_open("2025-01-01", "Assets:Brokerage:HK:Cash", "HKD"))

    lines.append(_subsection("负债"))
    lines.append(_open("2025-01-01", "Liabilities:CreditCard:CMB", "CNY"))

    lines.append(_subsection("收入"))
    lines.append(_open("2025-01-01", "Income:Salary", "CNY"))
    lines.append(_open("2025-01-01", "Income:CapitalGains", "USD"))
    lines.append(_open("2025-01-01", "Income:Dividend", "USD"))

    lines.append(_subsection("支出"))
    lines.append(_open("2025-01-01", "Expenses:Financial:Fees", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Financial:Tax", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Housing:Rent", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Food", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Transport", "CNY"))

    lines.append(_subsection("权益"))
    lines.append(_open("2025-01-01", "Equity:Opening-Balances"))

    lines.append(_section("初始余额"))
    lines.append(
        _txn(
            "2025-01-01",
            "*",
            "期初余额",
            "银行账户初始余额",
            [
                ("Assets:Bank:ICBC", "200000.00 CNY"),
                ("Equity:Opening-Balances", "-200000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-01",
            "*",
            "期初余额",
            "美股账户现金初始余额",
            [
                ("Assets:Brokerage:US:Cash", "10000.00 USD"),
                ("Equity:Opening-Balances", "-10000.00 USD"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-01",
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
    lines.append(
        _txn(
            "2025-01-05",
            "*",
            "某科技公司",
            "1月工资",
            [
                ("Assets:Bank:ICBC", "30000.00 CNY"),
                ("Income:Salary", "-30000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-05",
            "*",
            "房东",
            "1月房租",
            [
                ("Assets:Bank:ICBC", "-6000.00 CNY"),
                ("Expenses:Housing:Rent", "6000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-02-05",
            "*",
            "某科技公司",
            "2月工资",
            [
                ("Assets:Bank:ICBC", "30000.00 CNY"),
                ("Income:Salary", "-30000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-02-05",
            "*",
            "房东",
            "2月房租",
            [
                ("Assets:Bank:ICBC", "-6000.00 CNY"),
                ("Expenses:Housing:Rent", "6000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-03-05",
            "*",
            "某科技公司",
            "3月工资",
            [
                ("Assets:Bank:ICBC", "30000.00 CNY"),
                ("Income:Salary", "-30000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-03-05",
            "*",
            "房东",
            "3月房租",
            [
                ("Assets:Bank:ICBC", "-6000.00 CNY"),
                ("Expenses:Housing:Rent", "6000.00 CNY"),
            ],
        )
    )

    lines.append(_section("购汇与跨境转账"))
    lines.append(
        _txn(
            "2025-01-10",
            "*",
            "工商银行",
            "购汇20000美元转入美股账户",
            [
                ("Assets:Brokerage:US:Cash", "20000.00 USD @ 7.30 CNY"),
                ("Assets:Bank:ICBC", "-146000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-02-10",
            "*",
            "工商银行",
            "购汇50000港币转入港股账户",
            [
                ("Assets:Brokerage:HK:Cash", "50000.00 HKD @ 0.93 CNY"),
                ("Assets:Bank:ICBC", "-46500.00 CNY"),
            ],
        )
    )

    lines.append(_section("美股投资"))
    lines.append(
        _txn(
            "2025-01-15",
            "*",
            "券商",
            "买入VOO",
            [
                ("Assets:Brokerage:US", "20 VOO {535.00 USD}"),
                ("Assets:Brokerage:US:Cash", "-10700.00 USD"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-20",
            "*",
            "券商",
            "买入QQQ",
            [
                ("Assets:Brokerage:US", "15 QQQ {515.00 USD}"),
                ("Assets:Brokerage:US:Cash", "-7725.00 USD"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-02-20",
            "*",
            "券商",
            "加仓VOO",
            [
                ("Assets:Brokerage:US", "10 VOO {555.00 USD}"),
                ("Assets:Brokerage:US:Cash", "-5550.00 USD"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-03-10",
            "*",
            "券商",
            "卖出QQQ",
            [
                ("Assets:Brokerage:US:Cash", "7770.00 USD"),
                ("Assets:Brokerage:US", "-15 QQQ {515.00 USD}"),
                ("Income:CapitalGains", "-45.00 USD"),
            ],
        )
    )

    lines.append(_section("中概股投资"))
    lines.append(
        _txn(
            "2025-01-20",
            "*",
            "券商",
            "买入腾讯ADR",
            [
                ("Assets:Brokerage:US", "200 TCEHY {48.00 USD}"),
                ("Assets:Brokerage:US:Cash", "-9600.00 USD"),
            ],
        )
    )

    lines.append(_section("分红"))
    lines.append(
        _txn(
            "2025-03-15",
            "*",
            "券商",
            "VOO分红",
            [
                ("Assets:Brokerage:US:Cash", "60.00 USD"),
                ("Income:Dividend", "-60.00 USD"),
            ],
        )
    )

    lines.append(_section("手续费"))
    lines.append(
        _txn(
            "2025-01-10",
            "*",
            "工商银行",
            "购汇手续费",
            [
                ("Assets:Bank:ICBC", "-200.00 CNY"),
                ("Expenses:Financial:Fees", "200.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-02-10",
            "*",
            "工商银行",
            "购汇手续费",
            [
                ("Assets:Bank:ICBC", "-100.00 CNY"),
                ("Expenses:Financial:Fees", "100.00 CNY"),
            ],
        )
    )

    return "".join(lines)


def _generate_enterprise() -> str:
    lines: list[str] = []
    lines.append(_header("企业核算账本", "CNY"))

    lines.append(_section("币种"))
    lines.append(_commodity("1970-01-01", "CNY", "人民币"))

    lines.append(_section("账户"))
    lines.append(_subsection("资产"))
    lines.append(_open("2025-01-01", "Assets:Current:Bank:ICBC", "CNY"))
    lines.append(_open("2025-01-01", "Assets:Current:Cash", "CNY"))
    lines.append(_open("2025-01-01", "Assets:Current:AccountsReceivable", "CNY"))
    lines.append(_open("2025-01-01", "Assets:Current:Inventory", "CNY"))
    lines.append(_open("2025-01-01", "Assets:Fixed:Equipment", "CNY"))
    lines.append(_open("2025-01-01", "Assets:Fixed:Vehicles", "CNY"))

    lines.append(_subsection("负债"))
    lines.append(_open("2025-01-01", "Liabilities:Current:AccountsPayable", "CNY"))
    lines.append(_open("2025-01-01", "Liabilities:Current:SalaryPayable", "CNY"))
    lines.append(_open("2025-01-01", "Liabilities:Current:TaxPayable:VAT", "CNY"))
    lines.append(_open("2025-01-01", "Liabilities:Current:TaxPayable:IncomeTax", "CNY"))
    lines.append(_open("2025-01-01", "Liabilities:Current:SocialInsurance", "CNY"))
    lines.append(_open("2025-01-01", "Liabilities:NonCurrent:BankLoan", "CNY"))

    lines.append(_subsection("收入"))
    lines.append(_open("2025-01-01", "Income:Operating:Sales", "CNY"))
    lines.append(_open("2025-01-01", "Income:Other:Service", "CNY"))

    lines.append(_subsection("支出"))
    lines.append(_open("2025-01-01", "Expenses:Operating:COGS", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Operating:Salary", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Operating:SocialInsurance", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Operating:Rent", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Operating:Utilities", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Operating:Depreciation", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Selling:Advertising", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Selling:Commission", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Admin:Office", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Admin:Travel", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Financial:Interest", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Tax:IncomeTax", "CNY"))
    lines.append(_open("2025-01-01", "Expenses:Tax:VAT", "CNY"))

    lines.append(_subsection("权益"))
    lines.append(_open("2025-01-01", "Equity:Opening-Balances"))
    lines.append(_open("2025-01-01", "Equity:RetainedEarnings"))

    lines.append(_section("初始余额"))
    lines.append(
        _txn(
            "2025-01-01",
            "*",
            "期初余额",
            "银行存款初始余额",
            [
                ("Assets:Current:Bank:ICBC", "500000.00 CNY"),
                ("Equity:Opening-Balances", "-500000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-01",
            "*",
            "期初余额",
            "库存现金初始余额",
            [
                ("Assets:Current:Cash", "5000.00 CNY"),
                ("Equity:Opening-Balances", "-5000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-01",
            "*",
            "期初余额",
            "存货初始余额",
            [
                ("Assets:Current:Inventory", "200000.00 CNY"),
                ("Equity:Opening-Balances", "-200000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-01",
            "*",
            "期初余额",
            "固定资产初始余额",
            [
                ("Assets:Fixed:Equipment", "300000.00 CNY"),
                ("Equity:Opening-Balances", "-300000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-01",
            "*",
            "期初余额",
            "银行贷款初始余额",
            [
                ("Liabilities:NonCurrent:BankLoan", "-1000000.00 CNY"),
                ("Equity:Opening-Balances", "1000000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-01",
            "*",
            "期初余额",
            "应付账款初始余额",
            [
                ("Liabilities:Current:AccountsPayable", "-80000.00 CNY"),
                ("Equity:Opening-Balances", "80000.00 CNY"),
            ],
        )
    )

    lines.append(_section("1月业务"))
    lines.append(
        _txn(
            "2025-01-05",
            "*",
            "客户A",
            "销售商品收入",
            [
                ("Assets:Current:AccountsReceivable", "150000.00 CNY"),
                ("Income:Operating:Sales", "-132743.36 CNY"),
                ("Expenses:Tax:VAT", "-17256.64 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-08",
            "*",
            "供应商甲",
            "采购原材料",
            [
                ("Expenses:Operating:COGS", "85000.00 CNY"),
                ("Expenses:Tax:VAT", "11050.00 CNY"),
                ("Liabilities:Current:AccountsPayable", "-96050.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-10",
            "*",
            "人力资源部",
            "1月工资发放",
            [
                ("Expenses:Operating:Salary", "120000.00 CNY"),
                ("Expenses:Operating:SocialInsurance", "35000.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-155000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-12",
            "*",
            "客户A",
            "收到货款",
            [
                ("Assets:Current:Bank:ICBC", "150000.00 CNY"),
                ("Assets:Current:AccountsReceivable", "-150000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-15",
            "*",
            "供应商甲",
            "支付货款",
            [
                ("Liabilities:Current:AccountsPayable", "80000.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-80000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-15",
            "*",
            "物业公司",
            "1月办公室租金",
            [
                ("Expenses:Operating:Rent", "25000.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-25000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-18",
            "*",
            "国家电网",
            "1月电费",
            [
                ("Expenses:Operating:Utilities", "8500.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-8500.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-20",
            "*",
            "广告公司",
            "1月广告投放",
            [
                ("Expenses:Selling:Advertising", "30000.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-30000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-25",
            "*",
            "银行",
            "1月贷款利息",
            [
                ("Expenses:Financial:Interest", "4500.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-4500.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-31",
            "*",
            "财务部",
            "1月固定资产折旧",
            [
                ("Expenses:Operating:Depreciation", "5000.00 CNY"),
                ("Assets:Fixed:Equipment", "-5000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-01-31",
            "*",
            "行政部",
            "1月办公用品",
            [
                ("Expenses:Admin:Office", "3200.00 CNY"),
                ("Assets:Current:Cash", "-3200.00 CNY"),
            ],
        )
    )

    lines.append(_section("2月业务"))
    lines.append(
        _txn(
            "2025-02-05",
            "*",
            "客户B",
            "销售商品收入",
            [
                ("Assets:Current:Bank:ICBC", "180000.00 CNY"),
                ("Income:Operating:Sales", "-159292.04 CNY"),
                ("Expenses:Tax:VAT", "-20707.96 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-02-08",
            "*",
            "供应商乙",
            "采购原材料",
            [
                ("Expenses:Operating:COGS", "95000.00 CNY"),
                ("Expenses:Tax:VAT", "12350.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-107350.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-02-10",
            "*",
            "人力资源部",
            "2月工资发放",
            [
                ("Expenses:Operating:Salary", "125000.00 CNY"),
                ("Expenses:Operating:SocialInsurance", "36000.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-161000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-02-12",
            "*",
            "客户C",
            "技术服务收入",
            [
                ("Assets:Current:Bank:ICBC", "50000.00 CNY"),
                ("Income:Other:Service", "-47169.81 CNY"),
                ("Expenses:Tax:VAT", "-2830.19 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-02-15",
            "*",
            "物业公司",
            "2月办公室租金",
            [
                ("Expenses:Operating:Rent", "25000.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-25000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-02-18",
            "*",
            "销售人员",
            "2月销售提成",
            [
                ("Expenses:Selling:Commission", "15000.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-15000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-02-20",
            "*",
            "员工出差",
            "差旅费报销",
            [
                ("Expenses:Admin:Travel", "8500.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-8500.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-02-25",
            "*",
            "银行",
            "2月贷款利息",
            [
                ("Expenses:Financial:Interest", "4500.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-4500.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-02-28",
            "*",
            "财务部",
            "2月固定资产折旧",
            [
                ("Expenses:Operating:Depreciation", "5000.00 CNY"),
                ("Assets:Fixed:Equipment", "-5000.00 CNY"),
            ],
        )
    )

    lines.append(_section("3月业务"))
    lines.append(
        _txn(
            "2025-03-05",
            "*",
            "客户D",
            "销售商品收入",
            [
                ("Assets:Current:Bank:ICBC", "220000.00 CNY"),
                ("Income:Operating:Sales", "-194690.27 CNY"),
                ("Expenses:Tax:VAT", "-25309.73 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-03-08",
            "*",
            "供应商甲",
            "采购原材料",
            [
                ("Expenses:Operating:COGS", "110000.00 CNY"),
                ("Expenses:Tax:VAT", "14300.00 CNY"),
                ("Liabilities:Current:AccountsPayable", "-124300.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-03-10",
            "*",
            "人力资源部",
            "3月工资发放",
            [
                ("Expenses:Operating:Salary", "130000.00 CNY"),
                ("Expenses:Operating:SocialInsurance", "37000.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-167000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-03-15",
            "*",
            "供应商甲",
            "支付货款",
            [
                ("Liabilities:Current:AccountsPayable", "124300.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-124300.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-03-20",
            "*",
            "银行",
            "偿还部分贷款",
            [
                ("Liabilities:NonCurrent:BankLoan", "200000.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-200000.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-03-25",
            "*",
            "银行",
            "3月贷款利息",
            [
                ("Expenses:Financial:Interest", "3600.00 CNY"),
                ("Assets:Current:Bank:ICBC", "-3600.00 CNY"),
            ],
        )
    )
    lines.append(
        _txn(
            "2025-03-31",
            "*",
            "财务部",
            "3月固定资产折旧",
            [
                ("Expenses:Operating:Depreciation", "5000.00 CNY"),
                ("Assets:Fixed:Equipment", "-5000.00 CNY"),
            ],
        )
    )

    return "".join(lines)


_TEMPLATES: dict[str, tuple[str, str]] = {
    "family": ("极简家庭账本", "example-family.beancount"),
    "investment": ("跨币种投资账本", "example-investment.beancount"),
    "enterprise": ("企业核算账本", "example-enterprise.beancount"),
}

_GENERATORS: dict[str, object] = {
    "family": _generate_family,
    "investment": _generate_investment,
    "enterprise": _generate_enterprise,
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
def main(*, template: str, output: str) -> None:
    r"""基于场景模板生成 Fava 示例账本文件.

    支持三种场景模板：

    \b
    - family:     极简家庭账本（CNY，日常收支、信用卡还款）
    - investment: 跨币种投资账本（CNY/USD/HKD，购汇、美股港股、分红）
    - enterprise: 企业核算账本（CNY，营收、成本、税费、贷款）
    """
    label, filename = _TEMPLATES[template]
    generator = _GENERATORS[template]
    content = generator()

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
