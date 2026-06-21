"""Tests for generate_example module."""

from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from fava.generate_example import _month_date
from fava.generate_example import generate_enterprise
from fava.generate_example import generate_family
from fava.generate_example import generate_investment
from fava.generate_example import main

if TYPE_CHECKING:
    from collections.abc import Callable


def _count_txns(content: str) -> int:
    return len(re.findall(r"^\d{4}-\d{2}-\d{2} [*?] ", content, re.MULTILINE))


def _count_accounts(content: str) -> int:
    return len(re.findall(r"\n\d{4}-\d{2}-\d{2} open ", content))


def _has_section(content: str, title: str) -> bool:
    return f"* {title}" in content


class TestMonthDate:
    def test_same_month(self) -> None:
        assert _month_date("2025-01-01", 0, 15) == "2025-01-15"

    def test_next_month(self) -> None:
        assert _month_date("2025-01-01", 1, 5) == "2025-02-05"

    def test_year_boundary(self) -> None:
        assert _month_date("2024-12-01", 2, 10) == "2025-02-10"

    def test_multiple_months(self) -> None:
        assert _month_date("2025-03-15", 5, 20) == "2025-08-20"


class TestGenerateFamily:
    def test_basic_structure(self) -> None:
        content = generate_family()
        assert 'option "title" "极简家庭账本"' in content
        assert 'option "operating_currency" "CNY"' in content
        assert _has_section(content, "币种")
        assert _has_section(content, "账户")
        assert _has_section(content, "初始余额")
        assert _has_section(content, "日常交易")

    def test_default_month_count(self) -> None:
        content = generate_family()
        assert content.count("*** 2025-01月") == 1
        assert content.count("*** 2025-02月") == 1
        assert content.count("*** 2025-03月") == 1

    def test_custom_months(self) -> None:
        content = generate_family(num_months=6)
        assert content.count("*** 2025-01月") == 1
        assert content.count("*** 2025-06月") == 1

    def test_custom_currency(self) -> None:
        content = generate_family(currency="USD")
        assert 'option "operating_currency" "USD"' in content
        assert "50000.00 USD" in content

    def test_custom_start_date(self) -> None:
        content = generate_family(start_date="2024-06-01", num_months=2)
        assert content.count("*** 2024-06月") == 1
        assert content.count("*** 2024-07月") == 1

    def test_entries_per_month(self) -> None:
        content_min = generate_family(entries_per_month=2, num_months=1)
        content_max = generate_family(entries_per_month=20, num_months=1)
        assert _count_txns(content_max) > _count_txns(content_min)

    def test_deterministic_output(self) -> None:
        a = generate_family()
        b = generate_family()
        assert a == b

    def test_core_accounts_exist(self) -> None:
        content = generate_family()
        assert "Assets:Bank:ICBC" in content
        assert "Income:Salary" in content
        assert "Expenses:Housing:Rent" in content
        assert "Liabilities:CreditCard:CMB" in content
        assert "Equity:Opening-Balances" in content


class TestGenerateInvestment:
    def test_basic_structure(self) -> None:
        content = generate_investment()
        assert 'option "title" "跨币种投资账本"' in content
        assert _has_section(content, "汇率")
        assert _has_section(content, "购汇与跨境转账")
        assert _has_section(content, "美股投资")
        assert _has_section(content, "分红")

    def test_default_multi_currency(self) -> None:
        content = generate_investment()
        assert "commodity USD" in content
        assert "commodity HKD" in content
        assert "commodity VOO" in content
        assert "Assets:Brokerage:US:Cash" in content

    def test_without_usd(self) -> None:
        content = generate_investment(with_usd=False)
        assert "commodity USD" not in content
        assert "VOO" not in content
        assert "Assets:Brokerage:US" not in content

    def test_without_hkd(self) -> None:
        content = generate_investment(with_hkd=False)
        assert "commodity HKD" not in content
        assert "Assets:Brokerage:HK" not in content

    def test_custom_base_currency(self) -> None:
        content = generate_investment(base_currency="EUR")
        assert 'option "operating_currency" "EUR"' in content

    def test_custom_months(self) -> None:
        content = generate_investment(num_months=6)
        assert content.count("price USD") >= 12

    def test_deterministic_output(self) -> None:
        a = generate_investment()
        b = generate_investment()
        assert a == b

    def test_stock_lots(self) -> None:
        content = generate_investment()
        assert "VOO {" in content


class TestGenerateEnterprise:
    def test_basic_structure(self) -> None:
        content = generate_enterprise()
        assert 'option "title" "企业核算账本"' in content
        assert _has_section(content, "初始余额")
        assert _has_section(content, "月度业务")

    def test_account_hierarchy(self) -> None:
        content = generate_enterprise()
        assert "Assets:Current:Bank:ICBC" in content
        assert "Liabilities:NonCurrent:BankLoan" in content
        assert "Income:Operating:Sales" in content
        assert "Expenses:Operating:COGS" in content
        assert "Expenses:Selling:Advertising" in content
        assert "Expenses:Admin:Travel" in content
        assert "Expenses:Tax:VAT" in content
        assert "Equity:RetainedEarnings" in content

    def test_custom_months(self) -> None:
        content = generate_enterprise(num_months=6)
        assert _count_txns(content) > _count_txns(generate_enterprise(num_months=2))

    def test_custom_currency(self) -> None:
        content = generate_enterprise(currency="EUR")
        assert "500000.00 EUR" in content

    def test_custom_start_date(self) -> None:
        content = generate_enterprise(start_date="2023-01-01", num_months=2)
        assert "2023-01月" in content
        assert "2023-02月" in content

    def test_deterministic_output(self) -> None:
        a = generate_enterprise()
        b = generate_enterprise()
        assert a == b

    def test_monthly_depreciation(self) -> None:
        content = generate_enterprise(num_months=3)
        assert content.count("固定资产折旧") == 3


class TestCli:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "--template" in result.output
        assert "--output" in result.output
        assert "--start-date" in result.output
        assert "--months" in result.output
        assert "--currency" in result.output

    def test_generate_family_via_cli(self) -> None:
        runner = CliRunner()
        with TemporaryDirectory() as tmpdir:
            result = runner.invoke(
                main,
                ["--template", "family", "--output", tmpdir],
            )
            assert result.exit_code == 0
            assert "极简家庭账本" in result.output
            path = Path(tmpdir) / "example-family.beancount"
            assert path.exists()
            assert path.stat().st_size > 0

    def test_generate_investment_via_cli(self) -> None:
        runner = CliRunner()
        with TemporaryDirectory() as tmpdir:
            result = runner.invoke(
                main,
                ["--template", "investment", "--output", tmpdir],
            )
            assert result.exit_code == 0
            assert "跨币种投资账本" in result.output
            assert (Path(tmpdir) / "example-investment.beancount").exists()

    def test_generate_enterprise_via_cli(self) -> None:
        runner = CliRunner()
        with TemporaryDirectory() as tmpdir:
            result = runner.invoke(
                main,
                ["--template", "enterprise", "--output", tmpdir],
            )
            assert result.exit_code == 0
            assert "企业核算账本" in result.output
            assert (Path(tmpdir) / "example-enterprise.beancount").exists()

    def test_custom_months_via_cli(self) -> None:
        runner = CliRunner()
        with TemporaryDirectory() as tmpdir:
            result = runner.invoke(
                main,
                ["-t", "family", "-o", tmpdir, "-m", "1"],
            )
            assert result.exit_code == 0
            path = Path(tmpdir) / "example-family.beancount"
            content = path.read_text()
            assert content.count("*** 2025-01月") == 1
            assert "*** 2025-02月" not in content

    def test_invalid_template(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["-t", "invalid"])
        assert result.exit_code != 0

    def test_with_usd_flag(self) -> None:
        runner = CliRunner()
        with TemporaryDirectory() as tmpdir:
            result = runner.invoke(
                main,
                ["-t", "investment", "-o", tmpdir, "--no-with-usd"],
            )
            assert result.exit_code == 0
            content = (Path(tmpdir) / "example-investment.beancount").read_text()
            assert "VOO" not in content

    def test_entries_per_month_flag(self) -> None:
        runner = CliRunner()
        with TemporaryDirectory() as tmpdir_small:
            runner.invoke(
                main,
                ["-t", "family", "-o", tmpdir_small, "--entries-per-month", "2"],
            )
            small_content = (
                Path(tmpdir_small) / "example-family.beancount"
            ).read_text()

        with TemporaryDirectory() as tmpdir_large:
            runner.invoke(
                main,
                ["-t", "family", "-o", tmpdir_large, "--entries-per-month", "20"],
            )
            large_content = (
                Path(tmpdir_large) / "example-family.beancount"
            ).read_text()

        assert _count_txns(large_content) > _count_txns(small_content)
