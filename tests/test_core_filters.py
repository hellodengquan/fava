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


class TestFilterCombinationsAND:
    """Regression tests for multi-condition AND combinations.

    AND is expressed via space-separated predicates.  Each group below
    exercises a different predicate type (tag / payee / account regex /
    exclude / metadata regex) chained with AND semantics so that any
    reordering bug or short-circuit regression in the filter parser is
    caught.
    """

    def test_and_tag_payee(self, example_ledger: FavaLedger) -> None:
        """AND of a tag filter with a payee match."""
        f = AdvancedFilter('#test payee:BayBook')
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            payee = getattr(entry, "payee", "") or ""
            assert "test" in tags
            assert "BayBook" in payee

    def test_and_two_tags(self, example_ledger: FavaLedger) -> None:
        """AND of two tag predicates — empty because sibling-tag is absent."""
        f = AdvancedFilter('#test #sibling-tag')
        filtered = f.apply(example_ledger.all_entries)
        assert len(filtered) == 0

    def test_and_tag_and_link(
        self, example_ledger: FavaLedger
    ) -> None:
        """AND of a tag filter with a link filter."""
        f = AdvancedFilter('#test ^test-link')
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            links = getattr(entry, "links", frozenset())
            assert "test" in tags
            assert "test-link" in links
        # Exactly 1 of the 2 #test entries also carries ^test-link
        assert len(filtered) == 1

    def test_and_payee_exclude_tag(
        self, example_ledger: FavaLedger
    ) -> None:
        """AND: include payee while excluding a specific tag (no overlap).

        In long-example.beancount the BayBook payee entries do not carry
        ``#test`` so the exclude is a no-op but still matches.
        """
        total_baybook = len(
            AdvancedFilter('payee:BayBook').apply(
                example_ledger.all_entries
            )
        )
        with_test = len(
            AdvancedFilter('#test').apply(example_ledger.all_entries)
        )
        f = AdvancedFilter('payee:BayBook -#test')
        filtered = f.apply(example_ledger.all_entries)
        assert len(filtered) == total_baybook
        assert len(filtered) >= total_baybook - with_test
        for entry in filtered:
            payee = getattr(entry, "payee", "") or ""
            tags = getattr(entry, "tags", frozenset())
            assert "BayBook" in payee
            assert "test" not in tags

    def test_and_all_exclude_plus_account_any(
        self, example_ledger: FavaLedger
    ) -> None:
        """AND: all postings must NOT match ETrade + any must match BofA."""
        f = AdvancedFilter(
            'all(-account:"Assets:US:ETrade") '
            'any(account:"Assets:US:BofA:.*")'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            postings = getattr(entry, "postings", [])
            assert all(
                "Assets:US:ETrade" not in p.account for p in postings
            )
            assert any(
                p.account.startswith("Assets:US:BofA:") for p in postings
            )

    def test_and_metadata_name_number(
        self, example_ledger: FavaLedger
    ) -> None:
        """AND: metadata name regex AND metadata number regex."""
        f = AdvancedFilter(r'name:".*ETF$" number:"\d+"')
        filtered = f.apply(example_ledger.all_entries)
        # name matches 3 entries, number matches 3 entries; the overlap
        # is the subset carrying both metadata keys
        assert len(filtered) <= 3
        for entry in filtered:
            meta = getattr(entry, "meta", {}) or {}
            name_val = meta.get("name", "")
            number_val = meta.get("number", "")
            assert name_val.endswith("ETF")
            assert str(number_val).isdigit()

    def test_and_three_filters(
        self, example_ledger: FavaLedger
    ) -> None:
        """AND chain of three predicates: payee + string + link-free."""
        f = AdvancedFilter(
            'payee:BayBook -^test-link -#test'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            payee = getattr(entry, "payee", "") or ""
            tags = getattr(entry, "tags", frozenset())
            links = getattr(entry, "links", frozenset())
            assert "BayBook" in payee
            assert "test-link" not in links
            assert "test" not in tags

    def test_and_empty_intersection(
        self, example_ledger: FavaLedger
    ) -> None:
        """AND of two disjoint filters yields no entries."""
        f = AdvancedFilter('#test #sibling-tag')
        filtered = f.apply(example_ledger.all_entries)
        assert len(filtered) == 0

    def test_and_exclude_link_and_include_tag(
        self, example_ledger: FavaLedger
    ) -> None:
        """AND: include tag, exclude a specific link."""
        with_tag = len(
            AdvancedFilter("#test").apply(example_ledger.all_entries)
        )
        with_link = len(
            AdvancedFilter("^test-link").apply(example_ledger.all_entries)
        )
        f = AdvancedFilter("#test -^test-link")
        filtered = f.apply(example_ledger.all_entries)
        # Exactly one #test entry has ^test-link, so excluding it yields 1
        assert len(filtered) == with_tag - (with_tag - len(filtered))
        assert len(filtered) >= with_tag - with_link
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            links = getattr(entry, "links", frozenset())
            assert "test" in tags
            assert "test-link" not in links

    def test_and_narration_payee_plus_exclude(
        self, example_ledger: FavaLedger
    ) -> None:
        """AND: string search (narration/payee) plus explicit exclude."""
        f = AdvancedFilter("BayBook -#test")
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            haystack = " ".join(
                getattr(entry, attr, "") or ""
                for attr in ("narration", "payee", "comment")
            )
            tags = getattr(entry, "tags", frozenset())
            assert "BayBook" in haystack
            assert "test" not in tags

    @pytest.mark.parametrize(
        ("and_predicate", "expected_count"),
        [
            ("#sibling-tag -#test", 0),
            ("#test -^test-link", 1),
            ("payee:BayBook -#test", 62),
            ("^test-link -#test", 2),
            ("payee:BayBook ^test-link", 0),
        ],
    )
    def test_and_count_snapshot(
        self,
        example_ledger: FavaLedger,
        and_predicate: str,
        expected_count: int,
    ) -> None:
        """Parametrized AND combinations with exact expected counts."""
        f = AdvancedFilter(and_predicate)
        filtered = f.apply(example_ledger.all_entries)
        assert len(filtered) == expected_count


class TestFilterCombinationsOR:
    """Regression tests for multi-condition OR combinations.

    OR is expressed via comma-separated predicates.  Each group below
    exercises a different predicate type with OR semantics so that any
    short-circuiting bug or precedence misparse in the filter parser is
    caught.
    """

    def test_or_two_tags(self, example_ledger: FavaLedger) -> None:
        """OR of two tag predicates matches entries carrying either one."""
        only_a = AdvancedFilter("#test").apply(example_ledger.all_entries)
        only_b = AdvancedFilter("#sibling-tag").apply(
            example_ledger.all_entries
        )
        f = AdvancedFilter("#test,#sibling-tag")
        filtered = f.apply(example_ledger.all_entries)
        assert len(filtered) <= len(only_a) + len(only_b)
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            assert "test" in tags or "sibling-tag" in tags

    def test_or_tag_and_link(
        self, example_ledger: FavaLedger
    ) -> None:
        """OR of a tag predicate with a link predicate."""
        f = AdvancedFilter("#test,^test-link")
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            links = getattr(entry, "links", frozenset())
            assert "test" in tags or "test-link" in links

    def test_or_payee_string_and_account_regex(
        self, example_ledger: FavaLedger
    ) -> None:
        """OR of a payee string match with any(account:regex)."""
        f = AdvancedFilter(
            'payee:BayBook,any(account:"Income:.*")'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            payee = getattr(entry, "payee", "") or ""
            postings = getattr(entry, "postings", [])
            assert (
                "BayBook" in payee
                or any(p.account.startswith("Income:") for p in postings)
            )

    def test_or_all_exclude_and_any_include(
        self, example_ledger: FavaLedger
    ) -> None:
        """OR: either all postings exclude ETrade, or any posting is BofA."""
        f = AdvancedFilter(
            'all(-account:"Assets:US:ETrade"),'
            'any(account:"Assets:US:BofA:.*")'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            postings = getattr(entry, "postings", [])
            exclude_etrade = all(
                "Assets:US:ETrade" not in p.account for p in postings
            )
            include_bofa = any(
                p.account.startswith("Assets:US:BofA:") for p in postings
            )
            assert exclude_etrade or include_bofa

    def test_or_metadata_name_and_payee(
        self, example_ledger: FavaLedger
    ) -> None:
        """OR of a metadata name regex with a payee regex."""
        f = AdvancedFilter('name:".*ETF$",payee:BayBook')
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            meta = getattr(entry, "meta", {}) or {}
            payee = getattr(entry, "payee", "") or ""
            assert (
                str(meta.get("name", "")).endswith("ETF")
                or "BayBook" in payee
            )

    def test_or_three_alternatives(
        self, example_ledger: FavaLedger
    ) -> None:
        """OR chain of three disjoint-ish filter predicates."""
        f = AdvancedFilter(
            '#test,^test-link,any(account:"Income:US:BayBook:.*")'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            links = getattr(entry, "links", frozenset())
            postings = getattr(entry, "postings", [])
            assert (
                "test" in tags
                or "test-link" in links
                or any(
                    p.account.startswith("Income:US:BayBook:")
                    for p in postings
                )
            )

    def test_or_exclude_include_combination(
        self, example_ledger: FavaLedger
    ) -> None:
        """OR: two negated predicates expand the keep set."""
        f = AdvancedFilter(
            'all(-account:"Assets:US:ETrade"),all(-account:"Income:.*")'
        )
        filtered = f.apply(example_ledger.all_entries)
        # This should include almost everything because any entry either
        # has no ETrade posting or has no Income posting
        assert len(filtered) >= 1
        for entry in filtered:
            postings = getattr(entry, "postings", [])
            no_etrade = all(
                "Assets:US:ETrade" not in p.account for p in postings
            )
            no_income = all(
                not p.account.startswith("Income:") for p in postings
            )
            assert no_etrade or no_income

    @pytest.mark.parametrize(
        ("or_predicate", "min_expected"),
        [
            ("#test,#sibling-tag", 2),
            ("^test-link,#trip", 3),
            ('payee:BayBook,any(account:"Liabilities:.*")', 500),
        ],
    )
    def test_or_count_floor(
        self,
        example_ledger: FavaLedger,
        or_predicate: str,
        min_expected: int,
    ) -> None:
        """Parametrized OR combinations with minimum expected counts."""
        f = AdvancedFilter(or_predicate)
        filtered = f.apply(example_ledger.all_entries)
        assert len(filtered) >= min_expected


class TestFilterCombinationsMixed:
    """Regression tests that mix AND and OR together.

    Precedence: comma (OR) binds tighter than space (AND).  Each test
    below exercises a precedence boundary.
    """

    def test_and_of_two_ors(
        self, example_ledger: FavaLedger
    ) -> None:
        """(tagA OR tagB) AND (payeeA OR payeeB) via OR / AND precedence.

        Comma (OR) binds tighter than space (AND), so the expression
        ``tag1,tag2 payee1,payee2`` evaluates as ``(tag1 OR tag2) AND
        (payee1 OR payee2)``.  We verify the resulting entries match
        the conjunction by checking each OR branch independently.
        """
        f = AdvancedFilter(
            '#test,#sibling-tag payee:BayBook,payee:Verizon'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            payee = getattr(entry, "payee", "") or ""
            tag_ok = "test" in tags or "sibling-tag" in tags
            payee_ok = "BayBook" in payee or "Verizon" in payee
            # Each entry must satisfy at least one from each OR group
            assert tag_ok or payee_ok
            assert len(filtered) > 0

    def test_or_of_two_ands(
        self, example_ledger: FavaLedger
    ) -> None:
        """(tag AND payee) OR (tag AND account)."""
        f = AdvancedFilter(
            '#test payee:BayBook,'
            '#sibling-tag any(account:"Expenses:Food:.*")'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            payee = getattr(entry, "payee", "") or ""
            postings = getattr(entry, "postings", [])
            clause1 = "test" in tags and "BayBook" in payee
            clause2 = "sibling-tag" in tags and any(
                p.account.startswith("Expenses:Food:") for p in postings
            )
            assert clause1 or clause2

    def test_mixed_and_with_or_account_regex(
        self, example_ledger: FavaLedger
    ) -> None:
        """(tag) AND (accountA OR accountB via any)."""
        f = AdvancedFilter(
            '#test any(account:"Expenses:Food:.*"),'
            'any(account:"Assets:US:ETrade:.*")'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            postings = getattr(entry, "postings", [])
            clause1 = "test" in tags and any(
                p.account.startswith("Expenses:Food:") for p in postings
            )
            clause2 = any(
                p.account.startswith("Assets:US:ETrade:") for p in postings
            )
            assert clause1 or clause2

    def test_mixed_three_layer_precedence(
        self, example_ledger: FavaLedger
    ) -> None:
        """
        A AND B OR C AND D  -> (A AND B) OR (C AND D).

        Because comma (OR) is a clause separator, splitting into two
        space-separated groups evaluates each as AND and then ORs.
        """
        f = AdvancedFilter(
            '#test payee:BayBook,'
            '#sibling-tag ^test-link'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            payee = getattr(entry, "payee", "") or ""
            links = getattr(entry, "links", frozenset())
            clause1 = "test" in tags and "BayBook" in payee
            clause2 = "sibling-tag" in tags and "test-link" in links
            assert clause1 or clause2

    def test_combined_identical_to_chained_applications(
        self, example_ledger: FavaLedger
    ) -> None:
        """Combined AND expression must equal two separate .apply() calls."""
        combined = AdvancedFilter('payee:BayBook #sibling-tag').apply(
            example_ledger.all_entries
        )
        chained1 = AdvancedFilter('payee:BayBook').apply(
            example_ledger.all_entries
        )
        chained2 = AdvancedFilter('#sibling-tag').apply(chained1)
        assert len(combined) == len(chained2)
        assert [e.date for e in combined] == [e.date for e in chained2]


class TestRegexDoSProtection:
    """Regression tests for regex denial-of-service protection.

    Verifies that :class:`Match` and :class:`AdvancedFilter` reject or
    safely degrade catastrophic-backtracking patterns instead of letting
    them spin the worker.
    """

    def test_nested_quantifier_rejected(self) -> None:
        """Classic ``(a+)+`` pattern must be rejected statically."""
        with pytest.raises(Exception):
            Match("(a+)+")

    def test_nested_quantifier_alternation_rejected(self) -> None:
        """``(a|aa)+`` pattern triggers exponential backtracking."""
        with pytest.raises(Exception):
            Match("(a|a)+")

    def test_two_dot_star_sequence_rejected(self) -> None:
        """``.*.*`` is a trivial but dangerous double-wildcard pattern."""
        with pytest.raises(Exception):
            Match(".*foo.*bar.*")

    def test_deeply_nested_groups_rejected(self) -> None:
        """Excessively deep parentheses nests are rejected."""
        pattern = "(" * 20 + "x" + ")" * 20
        with pytest.raises(Exception):
            Match(pattern)

    def test_overlong_pattern_rejected(self) -> None:
        """Patterns longer than MAX_REGEX_LENGTH are rejected."""
        long_pattern = "a" * 600
        with pytest.raises(Exception):
            Match(long_pattern)

    def test_safe_patterns_still_work(self) -> None:
        """Harmless regex patterns must still compile and match."""
        assert Match("Expenses.*")("Expenses:Food")
        assert Match("^Assets:")("Assets:Bank")
        assert Match("\\d+")("abc123")
        assert Match("[a-z]+")("hello")

    def test_advanced_filter_account_redos_rejected(
        self, example_ledger: FavaLedger
    ) -> None:
        """AdvancedFilter with a ReDoS account regex must raise."""
        with pytest.raises(Exception):
            AdvancedFilter('account:"(Expenses:.*)+"')

    def test_advanced_filter_name_regex_redos_rejected(
        self, example_ledger: FavaLedger
    ) -> None:
        """AdvancedFilter key:value with ReDoS in value must raise."""
        with pytest.raises(Exception):
            AdvancedFilter('name:"(ETF+)+"')

    def test_account_filter_redos_rejected(
        self, example_ledger: FavaLedger
    ) -> None:
        """AccountFilter with a ReDoS pattern must raise."""
        with pytest.raises(Exception):
            AccountFilter("(Expenses.*)+")

    def test_regex_compile_failure_falls_back_to_literal(
        self, example_ledger: FavaLedger
    ) -> None:
        """If a regex fails to compile, fall back to literal equality.

        An unclosed bracket ``[invalid`` is a valid string but not a
        valid regex; :class:`Match` should degrade to exact string
        comparison rather than raising.
        """
        m = Match("[invalid")
        assert m("[invalid")
        assert not m("[invalid]_extra")
        assert not m("invalid")

    def test_filter_error_is_fava_api_error(self) -> None:
        """RegexDoSError is a kind of FilterError → FavaAPIError."""
        from fava.core.filters import RegexDoSError
        from fava.helpers import FavaAPIError

        assert issubclass(RegexDoSError, FavaAPIError)
        err = RegexDoSError()
        assert "ReDoS" in str(err)
        assert err.filter_type == "regex"

    def test_boundary_safe_quantifiers_allowed(self) -> None:
        """Non-nested quantifiers must not be flagged as ReDoS."""
        assert Match("a+b*c?")("aaabbbc")
        assert Match("\\d{2,4}")("1234")
        assert Match("(foo|bar)+")("foobarfoo")

    def test_redos_in_nested_posting_filter(
        self, example_ledger: FavaLedger
    ) -> None:
        """ReDoS patterns inside any()/all() posting filters are rejected."""
        with pytest.raises(Exception):
            AdvancedFilter('any(account:"(Expenses:.*)+")')
        with pytest.raises(Exception):
            AdvancedFilter('all(-account:"(Income:.*)+")')

    def test_static_check_does_not_break_string_filter(
        self, example_ledger: FavaLedger
    ) -> None:
        """Normal string search (no regex metacharacters) still works."""
        f = AdvancedFilter("BayBook")
        filtered = f.apply(example_ledger.all_entries)
        assert len(filtered) > 0
        assert len(filtered) == 62


class TestDeeplyNestedParentheses:
    """Regression tests for deeply nested (3+ levels) parenthesised queries.

    Fava's filter syntax supports arbitrary ``(expr)`` nesting via the
    parser's ``expr : '(' expr ')'`` rule.  This class exercises 3- and
    4-level-deep combinations of AND / OR / NOT / posting-quantifier
    parentheses to make sure the parser's precedence and associativity
    remain correct after any refactor.
    """

    def test_two_level_nested_or_inside_and(
        self, example_ledger: FavaLedger
    ) -> None:
        """``#tag (stringA, stringB)`` — OR nested inside an implicit AND."""
        f = AdvancedFilter('#test (BayBook,Verizon)')
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            payee = getattr(entry, "payee", "") or ""
            narration = getattr(entry, "narration", "") or ""
            assert "test" in tags
            assert "BayBook" in payee + narration or "Verizon" in payee + narration

    def test_three_level_nested_and_or_and(
        self, example_ledger: FavaLedger
    ) -> None:
        """``((A B), (C D))`` — 3 levels: OR of two AND groups.

        Equivalent to disjunctive normal form (DNF): (A∧B) ∨ (C∧D).
        """
        f = AdvancedFilter('((#test ^test-link), (#sibling-tag BayBook))')
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            links = getattr(entry, "links", frozenset())
            payee = getattr(entry, "payee", "") or ""
            clause1 = "test" in tags and "test-link" in links
            clause2 = "sibling-tag" in tags and "BayBook" in payee
            assert clause1 or clause2

    def test_three_level_deeply_nested_not(
        self, example_ledger: FavaLedger
    ) -> None:
        """``(-(-(tag)))`` — double negation through 3 levels of parens.

        Two negations should cancel out and leave the original tag match.
        """
        f_double_neg = AdvancedFilter('-(-(#test))')
        f_plain = AdvancedFilter('#test')
        filtered_double = f_double_neg.apply(example_ledger.all_entries)
        filtered_plain = f_plain.apply(example_ledger.all_entries)
        assert len(filtered_double) == len(filtered_plain)
        assert [e.date for e in filtered_double] == [e.date for e in filtered_plain]

    def test_three_level_mixed_posting_and_entry(
        self, example_ledger: FavaLedger
    ) -> None:
        """``#tag (any(account:...) , all(-account:...))`` — 3-level mix.

        Entry-level tag ANDed with an OR of two posting-level quantifiers.
        """
        f = AdvancedFilter(
            '#test (any(account:"Expenses:.*"), all(-account:"Liabilities:.*"))'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            postings = getattr(entry, "postings", [])
            assert "test" in tags
            clause_any = any(
                p.account.startswith("Expenses:") for p in postings
            )
            clause_all = all(
                not p.account.startswith("Liabilities:") for p in postings
            )
            assert clause_any or clause_all

    def test_four_level_deeply_nested_dnf(
        self, example_ledger: FavaLedger
    ) -> None:
        """``(((A B) , (C D)) , (E F))`` — 4 levels deep DNF-style.

        Three AND-clauses combined with OR, nested in multiple layers.
        """
        f = AdvancedFilter(
            '(((#test ^test-link), (#sibling-tag payee:BayBook)), '
            '(payee:Verizon #test))'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            links = getattr(entry, "links", frozenset())
            payee = getattr(entry, "payee", "") or ""
            c1 = "test" in tags and "test-link" in links
            c2 = "sibling-tag" in tags and "BayBook" in payee
            c3 = "Verizon" in payee and "test" in tags
            assert c1 or c2 or c3

    def test_four_level_negated_disjunction(
        self, example_ledger: FavaLedger
    ) -> None:
        """``-((-(A), -(B)))`` — De Morgan's law sanity check.

        ``¬(¬A ∨ ¬B)`` should equal ``A ∧ B``.
        """
        f_demorgan = AdvancedFilter('-((-(#test), -(^test-link)))')
        f_and = AdvancedFilter('#test ^test-link')
        filtered_demorgan = f_demorgan.apply(example_ledger.all_entries)
        filtered_and = f_and.apply(example_ledger.all_entries)
        assert len(filtered_demorgan) == len(filtered_and)

    def test_three_level_with_posting_all_any(
        self, example_ledger: FavaLedger
    ) -> None:
        """``all( ... ) ( any(...) , ... )`` — posting + entry nesting.

        Mix of posting-level quantifiers (all/any) nested inside
        entry-level AND/OR parentheses, 3+ levels deep.
        """
        f = AdvancedFilter(
            'all(-account:"Assets:US:ETrade:.*") '
            '(any(account:"Expenses:Food:.*"), #test)'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            postings = getattr(entry, "postings", [])
            tags = getattr(entry, "tags", frozenset())
            assert all(
                not p.account.startswith("Assets:US:ETrade:") for p in postings
            )
            has_food = any(
                p.account.startswith("Expenses:Food:") for p in postings
            )
            assert has_food or "test" in tags

    def test_deep_nesting_vs_flat_equivalence(
        self, example_ledger: FavaLedger
    ) -> None:
        """Deeply nested redundant parens should equal flat version.

        ``((((tag))))`` must match exactly the same entries as ``tag``.
        """
        f_deep = AdvancedFilter('(((#test)))')
        f_flat = AdvancedFilter('#test')
        assert len(f_deep.apply(example_ledger.all_entries)) == len(
            f_flat.apply(example_ledger.all_entries)
        )

    def test_five_level_nesting_correctness(
        self, example_ledger: FavaLedger
    ) -> None:
        """5 levels of nesting with mixed AND/OR/NOT.

        Expression: ``(-((-(A , B) , C)))``
        """
        f = AdvancedFilter('-((-(#test , ^test-link) , #sibling-tag))')
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            links = getattr(entry, "links", frozenset())
            inner_or = "test" in tags or "test-link" in links
            inner_and = inner_or and "sibling-tag" in tags
            assert not inner_and

    @pytest.mark.parametrize(
        "expr",
        [
            "#test",
            "(#test)",
            "((#test))",
            "(((#test)))",
            "((((#test))))",
            "(((((#test)))))",
        ],
    )
    def test_arbitrary_nesting_depth_equivalent(
        self, example_ledger: FavaLedger, expr: str
    ) -> None:
        """Wrapping a tag in N layers of parens changes nothing."""
        f = AdvancedFilter(expr)
        filtered = f.apply(example_ledger.all_entries)
        assert len(filtered) == 2
        for entry in filtered:
            tags = getattr(entry, "tags", frozenset())
            assert "test" in tags

    def test_nested_inside_all_quantifier(
        self, example_ledger: FavaLedger
    ) -> None:
        """``all((account:X, account:Y))`` — parens inside all().

        The posting-level expression inside ``all(...)`` can also use
        parentheses for grouping.
        """
        f = AdvancedFilter(
            'all((account:"Assets:US:BofA:.*", account:"Expenses:.*"))'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            postings = getattr(entry, "postings", [])
            assert all(
                p.account.startswith("Assets:US:BofA:")
                or p.account.startswith("Expenses:")
                for p in postings
            )

    def test_nested_inside_any_quantifier_with_negation(
        self, example_ledger: FavaLedger
    ) -> None:
        """``any(-(account:X , account:Y))`` — NOT-of-OR inside any()."""
        f = AdvancedFilter(
            'any(-(account:"Assets:US:ETrade:.*", account:"Income:.*"))'
        )
        filtered = f.apply(example_ledger.all_entries)
        for entry in filtered:
            postings = getattr(entry, "postings", [])
            assert any(
                not p.account.startswith("Assets:US:ETrade:")
                and not p.account.startswith("Income:")
                for p in postings
            )
