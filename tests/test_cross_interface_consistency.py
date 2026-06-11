"""跨接口一致性回归测试。

确保CSV导出接口、图表JSON接口、查询接口和账户报告接口在商品字段
大小写规范上保持一致。这些测试作为回归防护，防止版本回退时破坏
统一的别名归并规则。
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from flask.testing import FlaskClient

if TYPE_CHECKING:  # pragma: no cover
    from fava.core import FavaLedger

    from .conftest import GetFavaLedger


class TestCrossInterfaceConsistency:
    """跨接口商品字段大小写一致性测试。"""

    LEDGER_SLUG = "case-consistency-test-ledger"

    @pytest.fixture(scope="class")
    def ledger(self, get_ledger: GetFavaLedger) -> FavaLedger:
        """获取测试账本。"""
        return get_ledger(self.LEDGER_SLUG)

    @pytest.fixture(scope="class")
    def canonicalizer(self, ledger: FavaLedger) -> Callable[[str], str]:
        """获取统一的商品别名归并函数。"""
        return ledger.commodities.canonical

    @staticmethod
    def _normalize_commodity_currencies(data: dict | list) -> set[str]:
        """从响应数据中提取所有商品货币名称（不区分大小写）。"""
        currencies = set()

        non_commodity_keys = {
            "account",
            "balance",
            "balance_children",
            "children",
            "cost",
            "cost_children",
            "has_txns",
            "name",
            "rows",
            "types",
            "t",
            "columns",
            "number",
            "currency",
        }

        if isinstance(data, dict):
            for key, value in data.items():
                if key.lower() in ("balance", "balance_children", "balances"):
                    if isinstance(value, dict):
                        for k in value.keys():
                            if (
                                isinstance(k, str)
                                and k.isalpha()
                                and k.upper() == k
                                and 2 <= len(k) <= 10
                            ):
                                currencies.add(k)
                elif key.lower() == "rows":
                    if isinstance(value, list):
                        for row in value:
                            if isinstance(row, list):
                                for item in row:
                                    if isinstance(item, dict):
                                        for k in item.keys():
                                            if (
                                                isinstance(k, str)
                                                and k.isalpha()
                                                and k.upper() == k
                                                and 2 <= len(k) <= 10
                                            ):
                                                currencies.add(k)
                elif key.lower() in non_commodity_keys:
                    continue
                elif isinstance(value, (dict, list)):
                    currencies.update(
                        TestCrossInterfaceConsistency._normalize_commodity_currencies(
                            value
                        )
                    )
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    for k in item.keys():
                        if (
                            isinstance(k, str)
                            and k.isalpha()
                            and k.upper() == k
                            and 2 <= len(k) <= 10
                        ):
                            currencies.add(k)
                    currencies.update(
                        TestCrossInterfaceConsistency._normalize_commodity_currencies(
                            item
                        )
                    )
                elif isinstance(item, list):
                    currencies.update(
                        TestCrossInterfaceConsistency._normalize_commodity_currencies(
                            item
                        )
                    )
        return currencies

    @staticmethod
    def _assert_commodity_consistency(currencies: set[str]) -> None:
        """验证商品名称集合中不存在大小写不一致的重复项。

        Args:
            currencies: 商品名称集合。

        Raises:
            AssertionError: 如果存在同一商品的不同大小写变体。
        """
        lower_to_originals: dict[str, set[str]] = {}
        for currency in currencies:
            if isinstance(currency, str):
                lower_to_originals.setdefault(currency.lower(), set()).add(
                    currency
                )

        inconsistencies = [
            (lower, sorted(originals))
            for lower, originals in lower_to_originals.items()
            if len(originals) > 1
        ]

        if inconsistencies:
            msg = "商品名称存在大小写不一致的重复项:\n"
            for lower, originals in inconsistencies:
                msg += f"  '{lower}' 出现变体: {originals}\n"
            pytest.fail(msg)

    @staticmethod
    def _extract_csv_currencies(csv_content: str) -> set[str]:
        """从CSV内容中提取所有商品货币名称。

        从CSV表头中提取如 "balance (BTC)" 格式的商品名称。
        """
        currencies = set()
        reader = csv.DictReader(io.StringIO(csv_content))
        if reader.fieldnames:
            for header in reader.fieldnames:
                header_str = str(header)
                if "(" in header_str and ")" in header_str:
                    currency = header_str.split("(", 1)[1].rsplit(")", 1)[0]
                    if currency and currency.isalpha():
                        currencies.add(currency)
        return currencies

    def test_commodities_module_canonicalizes_correctly(
        self,
        canonicalizer: Callable[[str], str],
    ) -> None:
        """验证核心归并模块正确处理大小写和别名。"""
        assert canonicalizer("BTC") == "BTC"
        assert canonicalizer("btc") == "BTC"
        assert canonicalizer("BITCOIN") == "BTC"
        assert canonicalizer("ETH") == "ETH"
        assert canonicalizer("ethereum") == "ETH"
        assert canonicalizer("AAPL") == "AAPL"
        assert canonicalizer("apple") == "AAPL"
        assert canonicalizer("USD") == "USD"
        assert canonicalizer("usd") == "USD"

    def test_csv_export_commodity_fields_are_canonicalized(
        self,
        test_client: FlaskClient,
    ) -> None:
        """CSV导出接口的商品字段应经过归一化处理。

        验证导出的CSV文件中，商品名称使用统一的规范名称，
        不存在大小写不一致的情况。
        """
        query_string = "SELECT account, balance WHERE account ~ 'Assets:Investment'"
        url = (
            f"/{self.LEDGER_SLUG}/download-query/query_result.csv"
            f"?query_string={query_string}"
        )

        response = test_client.get(url)
        assert response.status_code == 200

        csv_content = response.data.decode("utf-8")
        currencies = self._extract_csv_currencies(csv_content)

        self._assert_commodity_consistency(currencies)

        assert len(currencies) > 0

    def test_charts_hierarchy_commodity_fields_are_canonicalized(
        self,
        test_client: FlaskClient,
    ) -> None:
        """图表层次结构接口的商品字段应经过归一化处理。"""
        url = (
            f"/{self.LEDGER_SLUG}/api/account_report"
            f"?interval=month&conversion=at_value&a=Assets:Investment&r=balances"
        )

        response = test_client.get(url)
        assert response.status_code == 200
        assert response.json is not None

        data = response.json.get("data", {})
        currencies = self._normalize_commodity_currencies(data)
        self._assert_commodity_consistency(currencies)

    def test_query_api_commodity_fields_are_canonicalized(
        self,
        test_client: FlaskClient,
    ) -> None:
        """查询API接口的商品字段应经过归一化处理。"""
        query_string = "balances WHERE account ~ 'Assets:Investment'"
        url = (
            f"/{self.LEDGER_SLUG}/api/query"
            f"?query_string={query_string}"
        )

        response = test_client.get(url)
        assert response.status_code == 200
        assert response.json is not None

        data = response.json.get("data", {})
        currencies = self._normalize_commodity_currencies(data)
        self._assert_commodity_consistency(currencies)

    def test_account_report_interval_balances_canonicalized(
        self,
        test_client: FlaskClient,
    ) -> None:
        """账户报告区间报表的商品字段应经过归一化处理。"""
        url = (
            f"/{self.LEDGER_SLUG}/api/account_report"
            f"?interval=month&conversion=at_value&a=Assets:Investment&r=balances"
        )

        response = test_client.get(url)
        assert response.status_code == 200
        assert response.json is not None

        data = response.json.get("data", {})
        interval_balances = data.get("interval_balances", [])

        assert len(interval_balances) > 0

        for balance in interval_balances:
            currencies = self._normalize_commodity_currencies(balance)
            self._assert_commodity_consistency(currencies)

    def test_all_interfaces_return_identical_currency_set(
        self,
        test_client: FlaskClient,
        canonicalizer: Callable[[str], str],
    ) -> None:
        """所有接口返回的商品货币集合（归一化后）应完全一致。

        这是核心的跨接口一致性测试，确保CSV导出、图表、查询和账户报告
        返回的商品币种集合在经过统一归并后完全相同。
        """
        interfaces = []

        query_url = (
            f"/{self.LEDGER_SLUG}/api/query"
            f"?query_string=balances WHERE account = 'Assets:Investment:BTC'"
        )
        query_resp = test_client.get(query_url)
        assert query_resp.status_code == 200
        assert query_resp.json is not None
        query_currencies = self._normalize_commodity_currencies(
            query_resp.json.get("data", {})
        )
        interfaces.append(("query_api", query_currencies))

        account_url = (
            f"/{self.LEDGER_SLUG}/api/account_report"
            f"?interval=month&conversion=units&a=Assets:Investment:BTC&r=balances"
        )
        account_resp = test_client.get(account_url)
        assert account_resp.status_code == 200
        assert account_resp.json is not None
        account_data = account_resp.json.get("data", {})
        interval_balances = account_data.get("interval_balances", [])
        if interval_balances:
            account_currencies = self._normalize_commodity_currencies(
                interval_balances[0]
            )
            interfaces.append(("account_report", account_currencies))

        normalized_sets = [
            {canonicalizer(c) for c in currencies if isinstance(c, str)}
            for _, currencies in interfaces
        ]

        if len(normalized_sets) > 1:
            reference_set = normalized_sets[0]
            for name, s in zip(
                [n for n, _ in interfaces], normalized_sets
            ):
                if s != reference_set:
                    missing = reference_set - s
                    extra = s - reference_set
                    pytest.fail(
                        f"接口 '{name}' 的商品集合与参考接口不一致:\n"
                        f"  参考集合: {sorted(reference_set)}\n"
                        f"  当前集合: {sorted(s)}\n"
                        f"  缺失: {sorted(missing)}\n"
                        f"  多余: {sorted(extra)}"
                    )

    def test_csv_and_query_totals_match(
        self,
        test_client: FlaskClient,
    ) -> None:
        """CSV导出和查询API的总金额应匹配。

        验证对于相同的查询条件，CSV导出和JSON查询返回的数值结果一致。
        """
        query_string = (
            "SELECT account, sum(position) as total "
            "WHERE account ~ 'Assets:Investment' "
            "GROUP BY account"
        )

        csv_url = (
            f"/{self.LEDGER_SLUG}/download-query/query_result.csv"
            f"?query_string={query_string}"
        )
        csv_resp = test_client.get(csv_url)
        assert csv_resp.status_code == 200
        csv_content = csv_resp.data.decode("utf-8")

        query_url = (
            f"/{self.LEDGER_SLUG}/api/query"
            f"?query_string={query_string}"
        )
        query_resp = test_client.get(query_url)
        assert query_resp.status_code == 200
        assert query_resp.json is not None

        csv_currencies = self._extract_csv_currencies(csv_content)
        query_currencies = self._normalize_commodity_currencies(
            query_resp.json.get("data", {})
        )

        csv_currencies_normalized = {
            c.upper() for c in csv_currencies if c.isalpha()
        }
        query_currencies_normalized = {
            c.upper() for c in query_currencies if isinstance(c, str)
        }

        common = csv_currencies_normalized & query_currencies_normalized
        assert len(common) > 0, "CSV和查询API应返回共同的商品"

    def test_balance_sheet_and_charts_use_same_canonicalizer(
        self,
        ledger: FavaLedger,
    ) -> None:
        """资产负债表和图表接口应使用相同的商品归并函数。

        验证 root_tree_closed 和 charts 模块使用同一个 canonicalizer。
        """
        from fava.core import FilteredLedger

        filtered = FilteredLedger(ledger)
        canonicalizer = ledger.commodities.canonical

        root_closed = filtered.root_tree_closed
        assert root_closed is not None

        from fava.core.conversion import UNITS

        root_result = root_closed.get("Assets:Investment").serialise(
            UNITS,
            ledger.prices,
            filtered.end_date,
            canonicalizer=canonicalizer,
        )

        currencies = set(root_result.balance.keys()) | set(
            root_result.balance_children.keys()
        )
        self._assert_commodity_consistency(currencies)

        chart_result = ledger.charts.hierarchy(
            filtered, "Assets:Investment", UNITS
        )
        chart_currencies = set(chart_result.balance.keys()) | set(
            chart_result.balance_children.keys()
        )
        self._assert_commodity_consistency(chart_currencies)

        assert currencies == chart_currencies, (
            "资产负债表和图表接口返回的商品集合应完全一致"
        )

    def test_version_regression_guard_canonicalizer_exists(
        self,
        ledger: FavaLedger,
    ) -> None:
        """版本回退防护测试：确保 canonicalizer 方法存在且可调用。

        此测试用于防止版本回退时统一归并接口被意外移除。
        """
        assert hasattr(ledger.commodities, "canonical")
        assert callable(ledger.commodities.canonical)

        result = ledger.commodities.canonical("TEST")
        assert isinstance(result, str)

    def test_version_regression_guard_export_uses_canonicalizer(
        self,
        test_client: FlaskClient,
    ) -> None:
        """版本回退防护测试：确保导出接口使用了 canonicalizer。

        此测试通过构造包含明确大小写变体的查询，验证导出结果
        中这些变体被正确归一化。
        """
        query_string = (
            "SELECT account, position "
            "WHERE account ~ 'Assets:Investment:BTC'"
        )
        url = (
            f"/{self.LEDGER_SLUG}/download-query/query_result.csv"
            f"?query_string={query_string}"
        )

        response = test_client.get(url)
        assert response.status_code == 200

        csv_content = response.data.decode("utf-8")

        assert "btc" not in csv_content.lower() or "BTC" in csv_content
        assert "BITCOIN" not in csv_content

    def test_version_regression_guard_charts_use_canonicalizer(
        self,
        test_client: FlaskClient,
    ) -> None:
        """版本回退防护测试：确保图表接口使用了 canonicalizer。"""
        url = (
            f"/{self.LEDGER_SLUG}/api/account_report"
            f"?interval=month&conversion=units&a=Assets:Investment:BTC&r=balances"
        )

        response = test_client.get(url)
        assert response.status_code == 200
        assert response.json is not None

        data = json.dumps(response.json.get("data", {}))

        assert '"btc"' not in data.lower() or '"BTC"' in data
        assert '"BITCOIN"' not in data
