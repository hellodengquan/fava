from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from beancount.core.account import has_component

from fava.beans import create
from fava.beans.account import get_entry_accounts
from fava.core.filters import AccountFilter
from fava.core.filters import AdvancedFilter
from fava.core.filters import FilterError
from fava.core.filters import FilterSyntaxLexer
from fava.core.filters import Match
from fava.core.filters import MatchAmount
from fava.core.filters import TimeFilter

if TYPE_CHECKING:  # pragma: no cover
    from fava.core import FavaLedger


def test_match() -> None:
    assert Match("asdf")("asdf")
    assert Match("asdf")("asdfasdf")
    assert Match("asdf")("aasdfasdf")
    assert Match("^asdf")("asdfasdf")
    assert not Match("asdf")("fdsadfs")
    assert not Match("^asdf")("aasdfasdf")
    assert Match("(((")("(((")


def test_match_amount() -> None:
    one = Decimal(1)
    two = Decimal(2)

    one_amt = create.amount("1 EUR")
    two_amt = create.amount("2 EUR")
    three_amt = create.amount("3 EUR")

    assert MatchAmount("=", one)(one_amt)
    assert MatchAmount("=", one)(one_amt)

    assert MatchAmount(">", two)(three_amt)
    assert not MatchAmount(">", two)(two_amt)
    assert not MatchAmount(">", two)(one_amt)

    assert MatchAmount(">=", two)(three_amt)
    assert MatchAmount(">=", two)(two_amt)
    assert not MatchAmount(">=", two)(one_amt)

    assert not MatchAmount("<", two)(three_amt)
    assert not MatchAmount("<", two)(two_amt)
    assert MatchAmount("<", two)(one_amt)

    assert not MatchAmount("<=", two)(three_amt)
    assert MatchAmount("<=", two)(two_amt)
    assert MatchAmount("<=", two)(one_amt)


def test_lexer_basic() -> None:
    lex = FilterSyntaxLexer().lex
    data = "#some_tag ^some_link -^some_link"
    assert [(tok.type, tok.value) for tok in lex(data)] == [
        ("TAG", "some_tag"),
        ("LINK", "some_link"),
        ("-", "-"),
        ("LINK", "some_link"),
    ]
    data = "'string' string \"string\""
    assert [(tok.type, tok.value) for tok in lex(data)] == [
        ("STRING", "string"),
        ("STRING", "string"),
        ("STRING", "string"),
    ]
    with pytest.raises(FilterError):
        list(lex("|"))


def test_lexer_literals_in_string() -> None:
    lex = FilterSyntaxLexer().lex
    data = "string-2-2 string"
    assert [(tok.type, tok.value) for tok in lex(data)] == [
        ("STRING", "string-2-2"),
        ("STRING", "string"),
    ]


def test_lexer_key() -> None:
    lex = FilterSyntaxLexer().lex
    data = 'payee:asdfasdf ^some_link somekey:"testtest" units>80.2 '
    assert [(tok.type, tok.value) for tok in lex(data)] == [
        ("KEY", "payee"),
        ("EQ_OP", ":"),
        ("STRING", "asdfasdf"),
        ("LINK", "some_link"),
        ("KEY", "somekey"),
        ("EQ_OP", ":"),
        ("STRING", "testtest"),
        ("KEY", "units"),
        ("CMP_OP", ">"),
        ("NUMBER", Decimal("80.2")),
    ]


def test_lexer_parentheses() -> None:
    lex = FilterSyntaxLexer().lex
    data = "(payee:asdfasdf ^some_link) (somekey:'testtest')"
    assert [(tok.type, tok.value) for tok in lex(data)] == [
        ("(", "("),
        ("KEY", "payee"),
        ("EQ_OP", ":"),
        ("STRING", "asdfasdf"),
        ("LINK", "some_link"),
        (")", ")"),
        ("(", "("),
        ("KEY", "somekey"),
        ("EQ_OP", ":"),
        ("STRING", "testtest"),
        (")", ")"),
    ]


def test_filterexception() -> None:
    with pytest.raises(FilterError, match='Illegal character """ in filter'):
        AdvancedFilter('who:"fff')

    with pytest.raises(FilterError, match="Failed to parse filter"):
        AdvancedFilter('any(who:"Martin"')


@pytest.mark.parametrize(
    ("string", "number"),
    [
        ('any(account:"Assets:US:ETrade")', 48),
        ('all(-account:"Assets:US:ETrade")', 1826 - 48),
        ("#test", 2),
        ("#test,#nomatch", 2),
        ("-#nomatch", 1826),
        ("-#nomatch -#nomatch", 1826),
        ("-#nomatch -#test", 1824),
        ("-#test", 1824),
        ("^test-link", 3),
        ("^test-link,#test", 4),
        ("^test-link -#test", 2),
        ("payee:BayBook", 62),
        ("BayBook", 62),
        ("(payee:BayBook, #test,#nomatch) -#nomatch", 64),
        ('payee:"BayBo.*"', 62),
        ('payee:"baybo.*"', 62),
        (r'number:"\d*"', 3),
        ('not_a_meta_key:".*"', 0),
        ('name:".*ETF"', 4),
        ('name:".*ETF$"', 3),
        ('name:".*etf"', 4),
        ('name:".*etf$"', 3),
        ('any(overage:"GB$")', 1),
        ("=26.87", 1),
        (">=17500", 3),
        (">=17500 <18000", 1),
        ("any(units >= 17500)", 3),
    ],
)
def test_advanced_filter(
    example_ledger: FavaLedger,
    string: str,
    number: int,
) -> None:
    filter_ = AdvancedFilter(string)
    filtered_entries = filter_.apply(example_ledger.all_entries)
    assert len(filtered_entries) == number


def test_null_meta_posting() -> None:
    filter_ = AdvancedFilter('any(some_meta:"1")')

    txn = create.transaction(
        {},
        datetime.date(2017, 12, 12),
        "*",
        "",
        "",
        frozenset(),
        frozenset(),
        [create.posting("Assets:ETrade:Cash", "100 USD")],
    )
    assert txn.postings[0].meta is None
    assert len(filter_.apply([txn])) == 0


def test_account_filter(example_ledger: FavaLedger) -> None:
    account_filter = AccountFilter("")
    filtered_entries = account_filter.apply(example_ledger.all_entries)
    assert filtered_entries is example_ledger.all_entries

    account_filter = AccountFilter("Assets")
    filtered_entries = account_filter.apply(example_ledger.all_entries)
    assert len(filtered_entries) == 541
    for entry in filtered_entries:
        assert any(
            has_component(a, "Assets") for a in get_entry_accounts(entry)
        )

    account_filter = AccountFilter(".*US:State")
    filtered_entries = account_filter.apply(example_ledger.all_entries)
    assert len(filtered_entries) == 67


def test_time_filter(example_ledger: FavaLedger) -> None:
    time_filter = TimeFilter(
        example_ledger.options,
        example_ledger.fava_options,
        "2017",
    )

    date_range = time_filter.date_range
    assert date_range
    assert date_range.begin == datetime.date(2017, 1, 1)
    assert date_range.end == datetime.date(2018, 1, 1)
    filtered_entries = time_filter.apply(example_ledger.all_entries)
    assert len(filtered_entries) == 83

    time_filter = TimeFilter(
        example_ledger.options,
        example_ledger.fava_options,
        "1000",
    )
    filtered_entries = time_filter.apply(example_ledger.all_entries)
    assert not filtered_entries

    with pytest.raises(FilterError):
        TimeFilter(
            example_ledger.options,
            example_ledger.fava_options,
            "no_date",
        )


class TestAccountFilterExclude:
    """Test account filter with reverse/exclude semantics via AdvancedFilter."""

    def test_all_exclude_account(
        self, example_ledger: FavaLedger
    ) -> None:
        """all(-account:...) keeps entries where ALL postings are NOT the account."""
        total = len(example_ledger.all_entries)
        f = AdvancedFilter('all(-account:"Assets:US:ETrade")')
        filtered = f.apply(example_ledger.all_entries)
        assert len(filtered) == total - 48
        for entry in filtered:
            for posting in getattr(entry, "postings", []):
                assert "Assets:US:ETrade" not in posting.account

    def test_any_exclude_account(
        self, example_ledger: FavaLedger
    ) -> None:
        """any(-account:...) keeps entries where any posting is NOT ETrade."""
        f = AdvancedFilter('any(-account:"Assets:US:ETrade")')
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            postings = getattr(entry, "postings", [])
            if postings:
                assert any(
                    "Assets:US:ETrade" not in p.account for p in postings
                )

    def test_exclude_multiple_accounts_all(
        self, example_ledger: FavaLedger
    ) -> None:
        """Exclude two accounts using all() with OR-negated pattern."""
        total = len(example_ledger.all_entries)
        f1 = AdvancedFilter('all(-account:"Assets:US:ETrade")')
        f2 = AdvancedFilter('all(-account:"Assets:US:BofA")')
        filtered1 = f1.apply(example_ledger.all_entries)
        filtered_both = f2.apply(filtered1)
        assert len(filtered_both) < total
        for entry in filtered_both:
            for posting in getattr(entry, "postings", []):
                assert "Assets:US:ETrade" not in posting.account
                assert "Assets:US:BofA" not in posting.account

    def test_exclude_vs_include_complement(
        self, example_ledger: FavaLedger
    ) -> None:
        """Exclude is the complement of include for posting-level filters."""
        total = len(example_ledger.all_entries)
        include_etrade = AdvancedFilter('any(account:"Assets:US:ETrade")')
        exclude_etrade = AdvancedFilter('all(-account:"Assets:US:ETrade")')
        included = len(include_etrade.apply(example_ledger.all_entries))
        excluded = len(exclude_etrade.apply(example_ledger.all_entries))
        assert included + excluded == total

    def test_exclude_tag(self, example_ledger: FavaLedger) -> None:
        """Exclude entries with a specific tag."""
        total = len(example_ledger.all_entries)
        exclude_test = AdvancedFilter("-#test")
        filtered = exclude_test.apply(example_ledger.all_entries)
        assert len(filtered) == total - 2
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            assert "test" not in tags

    def test_exclude_link(self, example_ledger: FavaLedger) -> None:
        """Exclude entries with a specific link."""
        exclude_link = AdvancedFilter("-^test-link")
        filtered = exclude_link.apply(example_ledger.all_entries)
        for entry in filtered:
            links = getattr(entry, "links", frozenset())
            assert "test-link" not in links

    def test_exclude_payee(self, example_ledger: FavaLedger) -> None:
        """Exclude entries from a specific payee."""
        exclude_baybook = AdvancedFilter('-payee:BayBook')
        filtered = exclude_baybook.apply(example_ledger.all_entries)
        for entry in filtered:
            payee = getattr(entry, "payee", "") or ""
            assert "BayBook" not in payee

    def test_double_negation(self, example_ledger: FavaLedger) -> None:
        """Double negation should include entries with the tag."""
        include_test = AdvancedFilter("-#nomatch -#nomatch")
        total = len(example_ledger.all_entries)
        filtered = include_test.apply(example_ledger.all_entries)
        assert len(filtered) == total

    def test_exclude_and_include_tag(
        self, example_ledger: FavaLedger
    ) -> None:
        """Include one tag while excluding another."""
        f = AdvancedFilter("#test -#nomatch")
        filtered = f.apply(example_ledger.all_entries)
        assert len(filtered) == 2
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            assert "test" in tags

    def test_exclude_string_match(
        self, example_ledger: FavaLedger
    ) -> None:
        """Exclude entries matching a string pattern in narration/payee."""
        total = len(example_ledger.all_entries)
        f = AdvancedFilter("-BayBook")
        filtered = f.apply(example_ledger.all_entries)
        assert len(filtered) == total - 62
        for entry in filtered:
            for attr in ("narration", "payee", "comment"):
                val = getattr(entry, attr, "") or ""
                assert "BayBook" not in val


class TestAccountFilterRegex:
    """Test AccountFilter and AdvancedFilter with regex patterns."""

    def test_regex_prefix_match(
        self, example_ledger: FavaLedger
    ) -> None:
        """^ prefix anchors to start of account name."""
        af = AccountFilter("^Expenses")
        filtered = af.apply(example_ledger.all_entries)
        for entry in filtered:
            accounts = get_entry_accounts(entry)
            assert any(a.startswith("Expenses") for a in accounts)

    def test_regex_suffix_match(
        self, example_ledger: FavaLedger
    ) -> None:
        """$ suffix anchors to end of account name."""
        af = AccountFilter("Cash$")
        filtered = af.apply(example_ledger.all_entries)
        assert len(filtered) > 0
        for entry in filtered:
            accounts = get_entry_accounts(entry)
            assert any(a.endswith("Cash") for a in accounts)

    def test_regex_wildcard_middle(
        self, example_ledger: FavaLedger
    ) -> None:
        """.* wildcard matching in the middle of account name."""
        af = AccountFilter(".*US:.*:Cash")
        filtered = af.apply(example_ledger.all_entries)
        assert len(filtered) > 0
        for entry in filtered:
            accounts = get_entry_accounts(entry)
            assert any(
                "US:" in a and a.endswith("Cash") for a in accounts
            )

    def test_regex_character_class(
        self, example_ledger: FavaLedger
    ) -> None:
        """Character class [0-9] in regex."""
        af = AccountFilter(".*[0-9].*")
        filtered = af.apply(example_ledger.all_entries)
        import re

        pattern = re.compile("[0-9]")
        for entry in filtered:
            accounts = get_entry_accounts(entry)
            assert any(pattern.search(a) for a in accounts)

    def test_regex_case_insensitive(
        self, example_ledger: FavaLedger
    ) -> None:
        """Account filter is case-insensitive for regex."""
        af_lower = AccountFilter("assets")
        af_upper = AccountFilter("ASSETS")
        filtered_lower = af_lower.apply(example_ledger.all_entries)
        filtered_upper = af_upper.apply(example_ledger.all_entries)
        assert len(filtered_lower) == len(filtered_upper)

    def test_regex_exact_account(
        self, example_ledger: FavaLedger
    ) -> None:
        """^...$ matches exactly one account name."""
        af = AccountFilter("^Assets:US:BofA:Checking$")
        filtered = af.apply(example_ledger.all_entries)
        assert len(filtered) > 0
        for entry in filtered:
            accounts = get_entry_accounts(entry)
            assert "Assets:US:BofA:Checking" in accounts

    def test_regex_invalid_pattern_crashes(
        self, example_ledger: FavaLedger
    ) -> None:
        """Invalid regex in AccountFilter raises re.error from has_component."""
        af = AccountFilter("[invalid")
        with pytest.raises(Exception):
            af.apply(example_ledger.all_entries)

    def test_advanced_filter_account_regex_any(
        self, example_ledger: FavaLedger
    ) -> None:
        """any(account:regex) filters transactions by posting account."""
        f = AdvancedFilter('any(account:"Assets:US:.*")')
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            accounts = [p.account for p in getattr(entry, "postings", [])]
            assert any(a.startswith("Assets:US:") for a in accounts)

    def test_advanced_filter_account_regex_exclude(
        self, example_ledger: FavaLedger
    ) -> None:
        """all(-account:regex) excludes transactions by posting account."""
        total = len(example_ledger.all_entries)
        f = AdvancedFilter('all(-account:"Assets:US:.*")')
        filtered = f.apply(example_ledger.all_entries)
        assert len(filtered) < total
        for entry in filtered:
            for posting in getattr(entry, "postings", []):
                assert not posting.account.startswith("Assets:US:")

    def test_advanced_filter_name_regex(
        self, example_ledger: FavaLedger
    ) -> None:
        """Name metadata with regex patterns."""
        f = AdvancedFilter('name:".*ETF$"')
        filtered = f.apply(example_ledger.all_entries)
        assert len(filtered) == 3

    def test_advanced_filter_name_regex_case_insensitive(
        self, example_ledger: FavaLedger
    ) -> None:
        """Name metadata regex is case-insensitive."""
        f_upper = AdvancedFilter('name:".*ETF$"')
        f_lower = AdvancedFilter('name:".*etf$"')
        filtered_upper = f_upper.apply(example_ledger.all_entries)
        filtered_lower = f_lower.apply(example_ledger.all_entries)
        assert len(filtered_upper) == len(filtered_lower)

    def test_advanced_filter_number_regex(
        self, example_ledger: FavaLedger
    ) -> None:
        """Number metadata with regex."""
        f = AdvancedFilter(r'number:"\d*"')
        filtered = f.apply(example_ledger.all_entries)
        assert len(filtered) == 3

    def test_account_filter_vs_component_match(
        self, example_ledger: FavaLedger
    ) -> None:
        """AccountFilter matches both has_component and regex."""
        af_component = AccountFilter("BofA")
        af_regex = AccountFilter(".*BofA.*")
        filtered_component = af_component.apply(example_ledger.all_entries)
        filtered_regex = af_regex.apply(example_ledger.all_entries)
        assert len(filtered_component) == len(filtered_regex)

    def test_account_filter_empty_returns_all(
        self, example_ledger: FavaLedger
    ) -> None:
        """Empty AccountFilter returns all entries unchanged."""
        af = AccountFilter("")
        filtered = af.apply(example_ledger.all_entries)
        assert filtered is example_ledger.all_entries

    def test_advanced_filter_negated_account_regex(
        self, example_ledger: FavaLedger
    ) -> None:
        """Negated account regex with all() quantifier."""
        f = AdvancedFilter('all(-account:"Liabilities:.*")')
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            for posting in getattr(entry, "postings", []):
                assert not posting.account.startswith("Liabilities:")

    def test_advanced_filter_or_with_regex(
        self, example_ledger: FavaLedger
    ) -> None:
        """OR (comma) with account regex patterns."""
        f = AdvancedFilter(
            'any(account:"Assets:US:ETrade"),any(account:"Liabilities:.*")'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            accounts = [p.account for p in getattr(entry, "postings", [])]
            assert any(
                "Assets:US:ETrade" in a or a.startswith("Liabilities:")
                for a in accounts
            )

    def test_advanced_filter_and_with_exclude_regex(
        self, example_ledger: FavaLedger
    ) -> None:
        """AND (space) with include + exclude regex at posting level."""
        f = AdvancedFilter(
            'any(account:"Assets:US:.*") all(-account:"Assets:US:ETrade")'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            postings = getattr(entry, "postings", [])
            assert any(p.account.startswith("Assets:US:") for p in postings)
            assert all(
                "Assets:US:ETrade" not in p.account for p in postings
            )

    def test_match_fallback_on_invalid_regex(self) -> None:
        """Match class falls back to literal string on invalid regex."""
        m = Match("[invalid")
        assert not m("anything")
        assert m("[invalid")
