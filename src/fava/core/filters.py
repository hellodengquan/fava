"""Entry filters."""

from __future__ import annotations

import re
import signal
from abc import ABC
from abc import abstractmethod
from decimal import Decimal
from typing import Any
from typing import TYPE_CHECKING

import ply.yacc  # type: ignore[import-untyped]
from beancount.core import account
from beancount.ops.summarize import clamp_opt

from fava.beans.account import get_entry_accounts
from fava.helpers import FavaAPIError
from fava.util.date import DateRange
from fava.util.date import parse_date

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable
    from collections.abc import Iterable
    from collections.abc import Sequence

    from fava.beans.abc import Directive
    from fava.beans.types import BeancountOptions
    from fava.core.fava_options import FavaOptions


MAX_REGEX_LENGTH = 512
MAX_REGEX_NEST_DEPTH = 10
REGEX_TIMEOUT_SECONDS = 2.0

_REDOS_DANGER_PATTERNS = [
    re.compile(r"\([^()]*[+*?][^()]*\)[+*?]"),
    re.compile(r"\.\*.*\.\*"),
]

DANGEROUS_REGEX_MSG = (
    "Regex pattern rejected due to potential ReDoS risk. "
    "Please simplify the pattern or use a more specific search string."
)


class FilterError(FavaAPIError):
    """Filter exception."""

    def __init__(self, filter_type: str, message: str) -> None:
        super().__init__(message)
        self.filter_type = filter_type

    def __str__(self) -> str:
        return self.message


class RegexDoSError(FilterError):
    """Regex denied due to catastrophic backtracking risk."""

    def __init__(self) -> None:
        super().__init__("regex", DANGEROUS_REGEX_MSG)


def _check_regex_safety(pattern: str) -> None:
    """Run static checks for common ReDoS / catastrophic-backtracking patterns.

    The checks are deliberately conservative: we'd rather reject a few
    harmless-but-convoluted patterns than let an exponential-time regex
    through to the Python engine.  Detected families include:

    * nested quantifiers ``(a+)+``, ``(a|b)+`` where branches overlap
    * two overlapping ``.*`` / ``.+`` groups in sequence
    * excessive bracket / parenthesis nesting depth
    * overlong patterns
    """
    if len(pattern) > MAX_REGEX_LENGTH:
        raise RegexDoSError

    depth = 0
    max_depth = 0
    for ch in pattern:
        if ch == "(":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch == ")":
            depth -= 1
        if max_depth > MAX_REGEX_NEST_DEPTH:
            raise RegexDoSError

    for danger_re in _REDOS_DANGER_PATTERNS:
        if danger_re.search(pattern):
            raise RegexDoSError

    _check_alternation_overlap(pattern)


def _check_alternation_overlap(pattern: str) -> None:
    """Reject alternation+quantifier where branches can match the same string.

    This catches patterns like ``(a|a)+``, ``(a|aa)+`` or ``(.|a)+``
    where the branches overlap on their prefix, leading to exponential
    backtracking when the outer group is quantified.
    """
    group_re = re.compile(r"\(([^()]+)\)([+*?]|{\d+,?\d*})")
    for match in group_re.finditer(pattern):
        inner = match.group(1)
        if "|" not in inner:
            continue
        branches = inner.split("|")
        if len(branches) < 2:
            continue
        stripped = [b.strip() for b in branches]
        if len(set(stripped)) < len(stripped):
            raise RegexDoSError
        for i, a in enumerate(stripped):
            for b in stripped[i + 1 :]:
                if not a or not b:
                    continue
                if a.startswith(b) or b.startswith(a):
                    if len(a) <= 3 or len(b) <= 3:
                        raise RegexDoSError
                if a[0] == b[0] and len(a) <= 2 and len(b) <= 2:
                    raise RegexDoSError


class _RegexTimeout:
    """Context manager that aborts a regex match after a timeout.

    Uses :py:data:`signal.SIGALRM` on Unix platforms where the main
    thread can be interrupted; on other platforms falls back to a no-op
    so that the static safety checks above are still effective.
    """

    def __init__(self, timeout: float = REGEX_TIMEOUT_SECONDS) -> None:
        self.timeout = timeout
        self._old_handler = None

    def __enter__(self) -> None:
        if not hasattr(signal, "SIGALRM"):
            return
        self._old_handler = signal.signal(signal.SIGALRM, self._handler)
        signal.setitimer(signal.ITIMER_REAL, self.timeout)

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        if not hasattr(signal, "SIGALRM"):
            return False
        signal.setitimer(signal.ITIMER_REAL, 0)
        if self._old_handler is not None:
            signal.signal(signal.SIGALRM, self._old_handler)
        if exc_type is RegexDoSError:
            return True
        return False

    @staticmethod
    def _handler(signum: int, frame: Any) -> None:  # noqa: ARG004
        raise RegexDoSError


class FilterParseError(FilterError):
    """Filter parse error."""

    def __init__(self) -> None:
        super().__init__("filter", "Failed to parse filter: ")


class FilterIllegalCharError(FilterError):
    """Filter illegal char error."""

    def __init__(self, char: str) -> None:
        super().__init__(
            "filter",
            f'Illegal character "{char}" in filter.',
        )


class TimeFilterParseError(FilterError):
    """Time filter parse error."""

    def __init__(self, value: str) -> None:
        super().__init__("time", f"Failed to parse date: {value}")


class Token:
    """A token having a certain type and value.

    The lexer attribute only exists since PLY writes to it in case of a parser
    error.
    """

    __slots__ = ("lexer", "type", "value")

    def __init__(self, type_: str, value: str) -> None:
        self.type = type_
        self.value = value

    def __repr__(self) -> str:  # pragma: no cover
        return f"Token({self.type}, {self.value})"


class FilterSyntaxLexer:
    """Lexer for Fava's filter syntax."""

    tokens = (
        "ANY",
        "ALL",
        "CMP_OP",
        "EQ_OP",
        "KEY",
        "LINK",
        "NUMBER",
        "STRING",
        "TAG",
    )

    RULES = (
        ("LINK", r"\^[A-Za-z0-9\-_/.]+"),
        ("TAG", r"\#[A-Za-z0-9\-_/.]+"),
        ("ALL", r"all\("),
        ("ANY", r"any\("),
        ("KEY", r"[a-z][a-zA-Z0-9\-_]+(?=\s*(:|=|>=|<=|<|>))"),
        ("EQ_OP", r":"),
        ("CMP_OP", r"(=|>=|<=|<|>)"),
        ("NUMBER", r"\d*\.?\d+"),
        ("STRING", r"""\w[-\w]*|"[^"]*"|'[^']*'"""),
    )

    regex = re.compile(
        "|".join((f"(?P<{name}>{rule})" for name, rule in RULES)),
    )

    def LINK(self, token: str, value: str) -> tuple[str, str]:  # noqa: N802
        return token, value[1:]

    def TAG(self, token: str, value: str) -> tuple[str, str]:  # noqa: N802
        return token, value[1:]

    def KEY(self, token: str, value: str) -> tuple[str, str]:  # noqa: N802
        return token, value

    def ALL(self, token: str, _: str) -> tuple[str, str]:  # noqa: N802
        return token, token

    def ANY(self, token: str, _: str) -> tuple[str, str]:  # noqa: N802
        return token, token

    def EQ_OP(self, token: str, value: str) -> tuple[str, str]:  # noqa: N802
        return token, value

    def CMP_OP(self, token: str, value: str) -> tuple[str, str]:  # noqa: N802
        return token, value

    def NUMBER(self, token: str, value: str) -> tuple[str, Decimal]:  # noqa: N802
        return token, Decimal(value)

    def STRING(self, token: str, value: str) -> tuple[str, str]:  # noqa: N802
        if value[0] in {'"', "'"}:
            return token, value[1:-1]
        return token, value

    def lex(self, data: str) -> Iterable[Token]:
        """A generator yielding all tokens in a given line.

        Arguments:
            data: A string, the line to lex.

        Yields:
            All Tokens in the line.
        """
        ignore = " \t"
        literals = "-,()"
        regex = self.regex.match

        pos = 0
        length = len(data)
        while pos < length:
            char = data[pos]
            if char in ignore:
                pos += 1
                continue
            match = regex(data, pos)
            if match:
                value = match.group()
                pos += len(value)
                token = match.lastgroup
                if token is None:  # pragma: no cover
                    msg = "Internal Error"
                    raise ValueError(msg)
                func: Callable[[str, str], tuple[str, str]] = getattr(
                    self,
                    token,
                )
                ret = func(token, value)
                yield Token(*ret)
            elif char in literals:
                yield Token(char, char)
                pos += 1
            else:
                raise FilterIllegalCharError(char)


class Match:
    """Match a string with regex safety guards.

    User-supplied regex patterns are first passed through
    :func:`_check_regex_safety` to reject catastrophic-backtracking
    patterns before compilation.  The first match against a real
    payload is additionally wrapped in a signal-based timeout
    (:class:`_RegexTimeout`) as a second line of defence.
    """

    __slots__ = ("_compiled", "_match", "_safe", "_search")

    def __init__(self, search: str) -> None:
        self._search = search
        _check_regex_safety(search)
        try:
            self._compiled = re.compile(search, re.IGNORECASE)
            self._safe = True
        except re.error:
            self._compiled = None
            self._safe = False

        self._match = self._match_first

    def _match_first(self, s: str) -> bool:
        """First-call wrapper that runs the timeout probe."""
        if self._compiled is None:
            self._match = self._literal_match
            return self._literal_match(s)

        probe_text = s[:1024] if len(s) > 1024 else s
        try:
            with _RegexTimeout():
                result = bool(self._compiled.search(probe_text))
        except RegexDoSError:
            self._safe = False
            self._match = self._literal_match
            return self._literal_match(s)

        self._match = self._fast_match
        if result and len(s) == len(probe_text):
            return True
        return bool(self._compiled.search(s))

    def _fast_match(self, s: str) -> bool:
        """Subsequent calls use plain search (no timeout overhead)."""
        return bool(self._compiled.search(s))

    def _literal_match(self, s: str) -> bool:
        """Fallback literal equality comparison."""
        return s == self._search

    def __call__(self, obj: Any) -> bool:
        return self._match(str(obj))


class MatchAmount:
    """Matches an amount."""

    __slots__ = ("match",)

    match: Callable[[Decimal], bool]

    def __init__(self, op: str, value: Decimal) -> None:
        if op == "=":
            self.match = lambda x: x == value
        elif op == ">=":
            self.match = lambda x: x >= value
        elif op == "<=":
            self.match = lambda x: x <= value
        elif op == ">":
            self.match = lambda x: x > value
        else:  # op == "<":
            self.match = lambda x: x < value

    def __call__(self, obj: Any) -> bool:
        # Compare to the absolute value to simplify this filter.
        number = getattr(obj, "number", None)
        return self.match(abs(number)) if number is not None else False


class FilterSyntaxParser:
    precedence = (("left", "AND"), ("right", "UMINUS"))
    tokens = FilterSyntaxLexer.tokens

    def p_error(self, _: Any) -> None:
        raise FilterParseError

    def p_filter(self, p: list[Any]) -> None:
        """
        filter : expr
        """
        p[0] = p[1]

    def p_expr(self, p: list[Any]) -> None:
        """
        expr : simple_expr
        """
        p[0] = p[1]

    def p_expr_all(self, p: list[Any]) -> None:
        """
        expr : ALL expr ')'
        """
        expr = p[2]

        def _match_postings(entry: Directive) -> bool:
            return all(
                expr(posting) for posting in getattr(entry, "postings", [])
            )

        p[0] = _match_postings

    def p_expr_any(self, p: list[Any]) -> None:
        """
        expr : ANY expr ')'
        """
        expr = p[2]

        def _match_postings(entry: Directive) -> bool:
            return any(
                expr(posting) for posting in getattr(entry, "postings", [])
            )

        p[0] = _match_postings

    def p_expr_parentheses(self, p: list[Any]) -> None:
        """
        expr : '(' expr ')'
        """
        p[0] = p[2]

    def p_expr_and(self, p: list[Any]) -> None:
        """
        expr : expr expr %prec AND
        """
        left, right = p[1], p[2]

        def _and(entry: Directive) -> bool:
            return left(entry) and right(entry)  # type: ignore[no-any-return]

        p[0] = _and

    def p_expr_or(self, p: list[Any]) -> None:
        """
        expr : expr ',' expr
        """
        left, right = p[1], p[3]

        def _or(entry: Directive) -> bool:
            return left(entry) or right(entry)  # type: ignore[no-any-return]

        p[0] = _or

    def p_expr_negated(self, p: list[Any]) -> None:
        """
        expr : '-' expr %prec UMINUS
        """
        func = p[2]

        def _neg(entry: Directive) -> bool:
            return not func(entry)

        p[0] = _neg

    def p_simple_expr_TAG(self, p: list[Any]) -> None:  # noqa: N802
        """
        simple_expr : TAG
        """
        tag = p[1]

        def _tag(entry: Directive) -> bool:
            tags = getattr(entry, "tags", None)
            return (tag in tags) if tags is not None else False

        p[0] = _tag

    def p_simple_expr_LINK(self, p: list[Any]) -> None:  # noqa: N802
        """
        simple_expr : LINK
        """
        link = p[1]

        def _link(entry: Directive) -> bool:
            links = getattr(entry, "links", None)
            return (link in links) if links is not None else False

        p[0] = _link

    def p_simple_expr_STRING(self, p: list[Any]) -> None:  # noqa: N802
        """
        simple_expr : STRING
        """
        string = p[1]
        match = Match(string)

        def _string(entry: Directive) -> bool:
            for name in ("narration", "payee", "comment"):
                value = getattr(entry, name, "")
                if value and match(value):
                    return True
            return False

        p[0] = _string

    def p_simple_expr_key(self, p: list[Any]) -> None:
        """
        simple_expr : KEY EQ_OP STRING
                    | KEY CMP_OP NUMBER
        """
        key, op, value = p[1], p[2], p[3]
        match: Match | MatchAmount = (
            Match(value) if op == ":" else MatchAmount(op, value)
        )

        def _key(entry: Directive) -> bool:
            if hasattr(entry, key):
                return match(getattr(entry, key) or "")
            if entry.meta is not None and key in entry.meta:
                return match(entry.meta.get(key))
            return False

        p[0] = _key

    def p_simple_expr_units(self, p: list[Any]) -> None:
        """
        simple_expr : CMP_OP NUMBER
        """
        op, value = p[1], p[2]
        match = MatchAmount(op, value)

        def _range(entry: Directive) -> bool:
            return any(
                match(posting.units)
                for posting in getattr(entry, "postings", [])
            )

        p[0] = _range


class EntryFilter(ABC):
    """Filters a list of entries."""

    @abstractmethod
    def apply(self, entries: Sequence[Directive]) -> Sequence[Directive]:
        """Filter a list of directives."""


class TimeFilter(EntryFilter):
    """Filter by dates."""

    __slots__ = ("_options", "date_range")

    def __init__(
        self,
        options: BeancountOptions,
        fava_options: FavaOptions,
        value: str,
    ) -> None:
        self._options = options
        begin, end = parse_date(value, fava_options.fiscal_year_end)
        if not begin or not end:
            raise TimeFilterParseError(value)
        self.date_range = DateRange(begin, end)

    def apply(self, entries: Sequence[Directive]) -> Sequence[Directive]:
        clamped_entries, _ = clamp_opt(
            entries,  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]
            self.date_range.begin,
            self.date_range.end,
            self._options,
        )
        return clamped_entries  # type: ignore[return-value]  # ty:ignore[invalid-return-type]


LEXER = FilterSyntaxLexer()
PARSE = ply.yacc.yacc(
    errorlog=ply.yacc.NullLogger(),
    write_tables=False,
    debug=False,
    module=FilterSyntaxParser(),
).parse


class AdvancedFilter(EntryFilter):
    """Filter by tags and links and keys."""

    __slots__ = ("_include",)

    def __init__(self, value: str) -> None:
        try:
            tokens = LEXER.lex(value)
            self._include = PARSE(
                lexer="NONE",
                tokenfunc=lambda toks=tokens: next(toks, None),  # ty:ignore[invalid-argument-type]
            )
        except FilterError as exception:
            exception.message += value
            raise

    def apply(self, entries: Sequence[Directive]) -> Sequence[Directive]:
        include = self._include
        return [entry for entry in entries if include(entry)]


class AccountFilter(EntryFilter):
    """Filter by account.

    The filter string can either be a regular expression or a parent account.
    """

    __slots__ = ("_match", "_value")

    def __init__(self, value: str) -> None:
        self._value = value
        self._match = Match(value)

    def apply(self, entries: Sequence[Directive]) -> Sequence[Directive]:
        value = self._value
        if not value:
            return entries
        match = self._match
        return [
            entry
            for entry in entries
            if any(
                account.has_component(name, value) or match(name)
                for name in get_entry_accounts(entry)
            )
        ]
