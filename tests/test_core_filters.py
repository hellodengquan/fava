from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from beancount.core.account import has_component

from fava.beans import create
from fava.beans.account import get_entry_accounts
from fava.core import FilteredLedger
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


def test_filtered_ledger_no_filters(example_ledger: FavaLedger) -> None:
    filtered = FilteredLedger(example_ledger)
    assert len(filtered.entries) == len(example_ledger.all_entries)


def test_filtered_ledger_empty_string_filters(example_ledger: FavaLedger) -> None:
    filtered = FilteredLedger(
        example_ledger, account="", filter="", time=""
    )
    assert len(filtered.entries) == len(example_ledger.all_entries)


@pytest.mark.parametrize(
    ("account", "expected_count"),
    [
        ("Assets", 541),
        ("Assets:US:BofA", 280),
        (".*US:State", 67),
        ("Expenses", 723),
        ("Income", 125),
        ("NonExistentAccount", 0),
    ],
)
def test_filtered_ledger_account(
    example_ledger: FavaLedger,
    account: str,
    expected_count: int,
) -> None:
    filtered = FilteredLedger(example_ledger, account=account)
    assert len(filtered.entries) == expected_count


@pytest.mark.parametrize(
    ("filter_str", "expected_count"),
    [
        ("#test", 2),
        ("^test-link", 3),
        ("BayBook", 62),
        ("payee:BayBook", 62),
        ("#test,#nomatch", 2),
        ("^test-link,#test", 4),
        ("-#test", 1824),
    ],
)
def test_filtered_ledger_advanced(
    example_ledger: FavaLedger,
    filter_str: str,
    expected_count: int,
) -> None:
    filtered = FilteredLedger(example_ledger, filter=filter_str)
    assert len(filtered.entries) == expected_count


@pytest.mark.parametrize(
    ("time", "expected_count"),
    [
        ("2017", 83),
        ("2014", 752),
    ],
)
def test_filtered_ledger_time(
    example_ledger: FavaLedger,
    time: str,
    expected_count: int,
) -> None:
    filtered = FilteredLedger(example_ledger, time=time)
    assert len(filtered.entries) == expected_count


@pytest.mark.parametrize(
    ("account", "filter_str", "expected_count"),
    [
        ("Assets", "#test", 2),
        ("Assets", "^test-link", 3),
        ("Assets:US:BofA", "BayBook", 62),
        ("Expenses", "BayBook", 62),
        ("Assets", "#nomatch", 0),
        ("NonExistentAccount", "#test", 0),
    ],
)
def test_filtered_ledger_account_and_tag(
    example_ledger: FavaLedger,
    account: str,
    filter_str: str,
    expected_count: int,
) -> None:
    filtered = FilteredLedger(
        example_ledger, account=account, filter=filter_str
    )
    assert len(filtered.entries) == expected_count


@pytest.mark.parametrize(
    ("account", "time", "expected_count"),
    [
        ("Assets", "2017", 30),
        ("Assets", "2014", 223),
        ("Assets:US:BofA", "2014", 119),
        ("NonExistentAccount", "2014", 0),
    ],
)
def test_filtered_ledger_account_and_time(
    example_ledger: FavaLedger,
    account: str,
    time: str,
    expected_count: int,
) -> None:
    filtered = FilteredLedger(example_ledger, account=account, time=time)
    assert len(filtered.entries) == expected_count


@pytest.mark.parametrize(
    ("account", "filter_str", "time", "expected_count"),
    [
        ("Assets", "#test", "2014", 2),
        ("Assets", "^test-link", "2014", 3),
        ("Assets", "^test-link", "2017", 4),
        ("Assets:US:BofA", "BayBook", "2014", 26),
        ("Expenses", "BayBook", "2014", 26),
        ("Assets", "#test BayBook", "2014", 0),
        ("Assets", "#nomatch", "2014", 0),
        ("NonExistentAccount", "#test", "2014", 0),
    ],
)
def test_filtered_ledger_account_tag_and_time(
    example_ledger: FavaLedger,
    account: str,
    filter_str: str,
    time: str,
    expected_count: int,
) -> None:
    filtered = FilteredLedger(
        example_ledger, account=account, filter=filter_str, time=time
    )
    assert len(filtered.entries) == expected_count


@pytest.mark.parametrize(
    ("filter_str", "time", "expected_count"),
    [
        ("#test", "2014", 2),
        ("^test-link", "2014", 3),
        ("BayBook", "2014", 26),
        ("payee:BayBook", "2014", 26),
        ("#test,payee:BayBook", "2014", 28),
        ("#test payee:BayBook", "2014", 0),
        ("-#test", "2014", 750),
    ],
)
def test_filtered_ledger_tag_text_and_time(
    example_ledger: FavaLedger,
    filter_str: str,
    time: str,
    expected_count: int,
) -> None:
    filtered = FilteredLedger(
        example_ledger, filter=filter_str, time=time
    )
    assert len(filtered.entries) == expected_count


def test_filtered_ledger_date_range(example_ledger: FavaLedger) -> None:
    filtered = FilteredLedger(example_ledger, time="2017")
    assert filtered.date_range is not None
    assert filtered.date_range.begin == datetime.date(2017, 1, 1)
    assert filtered.date_range.end == datetime.date(2018, 1, 1)

    filtered_no_time = FilteredLedger(example_ledger)
    assert filtered_no_time.date_range is None


def test_filtered_ledger_filter_order(example_ledger: FavaLedger) -> None:
    filtered_account_first = FilteredLedger(
        example_ledger, account="Assets", time="2014"
    )
    all_after_account = AccountFilter("Assets").apply(
        example_ledger.all_entries
    )
    all_after_both = TimeFilter(
        example_ledger.options, example_ledger.fava_options, "2014"
    ).apply(all_after_account)
    assert len(filtered_account_first.entries) == len(all_after_both)
