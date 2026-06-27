"""
Unbound 2 tokenizer — converts .unbound source text into a flat token stream.

Every character of input is represented in the output token stream:
  - Structural tokens: LPAREN, RPAREN, EQUALS, COLON, COMMA,
    LBRACKET, RBRACKET, LBRACE, RBRACE
  - Value tokens: IDENTIFIER, NUMBER, STRING, BOOLEAN
  - Whitespace tokens: WHITESPACE (spaces/tabs), NEWLINE, COMMENT

This allows perfect round-tripping: serialize(parse(tokenize(text))) == text.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import List


class TokenType(Enum):
    # Structural
    LPAREN = auto()      # (
    RPAREN = auto()      # )
    EQUALS = auto()      # =
    COLON = auto()       # :
    COMMA = auto()       # ,
    LBRACKET = auto()    # [
    RBRACKET = auto()    # ]
    LBRACE = auto()      # {
    RBRACE = auto()      # }

    # Values
    IDENTIFIER = auto()  # name, $Name, SC.path.Value, px, %
    NUMBER = auto()      # 42, 3.14, 0xFF0000
    STRING = auto()      # 'text' or "text"
    BOOLEAN = auto()     # true, false

    # Spacing / comments
    WHITESPACE = auto()  # spaces and tabs (runs)
    NEWLINE = auto()     # \n or \r\n
    COMMENT = auto()     # # comment text (including the #)


@dataclass
class Token:
    type: TokenType
    text: str
    pos: int          # byte offset in source
    line: int         # 1-based line number
    col: int          # 1-based column number

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.text!r}, L{self.line}:{self.col})"


# ---------------------------------------------------------------------------
# Single-char structural tokens
# ---------------------------------------------------------------------------
_SINGLE_CHAR = {
    '(': TokenType.LPAREN,
    ')': TokenType.RPAREN,
    '=': TokenType.EQUALS,
    ':': TokenType.COLON,
    ',': TokenType.COMMA,
    '[': TokenType.LBRACKET,
    ']': TokenType.RBRACKET,
    '{': TokenType.LBRACE,
    '}': TokenType.RBRACE,
}


def tokenize(source: str) -> List[Token]:
    """Convert source text into a flat list of tokens."""
    tokens: List[Token] = []
    i = 0
    n = len(source)
    line = 1
    col = 1

    def add(ttype: TokenType, text: str, start_i: int, start_line: int, start_col: int) -> None:
        tokens.append(Token(ttype, text, start_i, start_line, start_col))

    while i < n:
        ch = source[i]

        # --- Newline ---
        if ch == '\n':
            add(TokenType.NEWLINE, '\n', i, line, col)
            i += 1
            line += 1
            col = 1
            continue

        if ch == '\r':
            if i + 1 < n and source[i + 1] == '\n':
                add(TokenType.NEWLINE, '\r\n', i, line, col)
                i += 2
            else:
                add(TokenType.NEWLINE, '\r', i, line, col)
                i += 1
            line += 1
            col = 1
            continue

        # --- Whitespace (spaces / tabs) ---
        if ch in (' ', '\t'):
            start_i = i
            start_line = line
            start_col = col
            while i < n and source[i] in (' ', '\t'):
                i += 1
                col += 1
            add(TokenType.WHITESPACE, source[start_i:i], start_i, start_line, start_col)
            continue

        # --- Comment: # to end of line ---
        if ch == '#':
            start_i = i
            start_line = line
            start_col = col
            while i < n and source[i] not in ('\n', '\r'):
                i += 1
                col += 1
            add(TokenType.COMMENT, source[start_i:i], start_i, start_line, start_col)
            continue

        # --- Structural single-char ---
        if ch in _SINGLE_CHAR:
            add(_SINGLE_CHAR[ch], ch, i, line, col)
            i += 1
            col += 1
            continue

        # --- Unary minus/plus before a number ---
        if ch in ('-', '+') and i + 1 < n and (source[i + 1].isdigit() or source[i + 1] == '.'):
            start_i = i
            start_line = line
            start_col = col
            i += 1
            col += 1
            # Read the rest of the number
            while i < n and source[i] not in (' ', '\t', '\n', '\r',
                                                '(', ')', '=', ':', ',',
                                                '[', ']', '{', '}',
                                                "'", '"', '#'):
                i += 1
                col += 1
            text = source[start_i:i]
            add(TokenType.NUMBER, text, start_i, start_line, start_col)
            continue

        # --- String literals: '...' or "..." ---
        # Strings CAN span multiple lines in Unbound.
        if ch in ("'", '"'):
            quote = ch
            start_i = i
            start_line = line
            start_col = col
            i += 1
            col += 1
            while i < n:
                if source[i] == '\\':
                    i += 2
                    col += 2
                    continue
                if source[i] == quote:
                    i += 1
                    col += 1
                    break
                if source[i] == '\n':
                    line += 1
                    col = 1
                    i += 1
                    continue
                if source[i] == '\r':
                    if i + 1 < n and source[i + 1] == '\n':
                        i += 2
                    else:
                        i += 1
                    line += 1
                    col = 1
                    continue
                i += 1
                col += 1
            add(TokenType.STRING, source[start_i:i], start_i, start_line, start_col)
            continue

        # --- Identifier, number, boolean, or keyword ---
        # Identifiers can start with letter, $, _, and contain letters, digits, $, _, .
        # Numbers start with digit or 0x
        if ch.isalpha() or ch == '$' or ch == '_' or ch.isdigit():
            start_i = i
            start_line = line
            start_col = col

            # Collect the whole token
            while i < n and source[i] not in (' ', '\t', '\n', '\r',
                                                '(', ')', '=', ':', ',',
                                                '[', ']', '{', '}',
                                                "'", '"', '#'):
                i += 1
                col += 1

            text = source[start_i:i]

            # Classify
            if text == 'true' or text == 'false':
                add(TokenType.BOOLEAN, text, start_i, start_line, start_col)
            elif _looks_like_number(text):
                add(TokenType.NUMBER, text, start_i, start_line, start_col)
            else:
                add(TokenType.IDENTIFIER, text, start_i, start_line, start_col)
            continue

        # --- Unknown character — treat as single-char identifier ---
        add(TokenType.IDENTIFIER, ch, i, line, col)
        i += 1
        col += 1

    return tokens


def _looks_like_number(text: str) -> bool:
    """Return True if *text* is a number-like token.

    Matches:
        42, -42, +42, 3.14, .5, 0xFF, 100px, 50%, -3px, 1.5e10
    """
    if not text:
        return False
    t = text
    # Optional sign
    if t[0] in ('+', '-'):
        t = t[1:]
    if not t:
        return False
    # Hex: 0x...
    if t.startswith('0x') or t.startswith('0X'):
        hex_part = t[2:]
        return all(c.isdigit() or c.lower() in 'abcdef' for c in hex_part) if hex_part else False
    # Float with optional exponent
    # Strip trailing unit (px, %, pt, etc.)
    unit_stripped = t
    has_unit = False
    # Check for % suffix (very common)
    if unit_stripped.endswith('%'):
        unit_stripped = unit_stripped[:-1]
        has_unit = True
    # Check for px, pt, em, etc. suffix
    for suffix in ('px', 'pt', 'em', 'ms', 's', 'deg'):
        if unit_stripped.endswith(suffix) and len(unit_stripped) > len(suffix):
            after = unit_stripped[:-len(suffix)]
            if after[-1].isdigit() or after[-1] == '.':
                unit_stripped = after
                has_unit = True
                break

    # Now check the numeric part
    return _is_numeric(unit_stripped)


def _is_numeric(s: str) -> bool:
    """Check if s is a valid number: integer, float, or scientific notation."""
    if not s:
        return False
    # Scientific: 1.5e10, 2E-3
    if 'e' in s.lower():
        parts = s.lower().split('e')
        if len(parts) != 2:
            return False
        return _is_plain_number(parts[0]) and _is_plain_number(parts[1])
    return _is_plain_number(s)


def _is_plain_number(s: str) -> bool:
    """Check if s is a plain integer or float (no exponent, no unit)."""
    if not s:
        return False
    if s[0] in ('+', '-'):
        s = s[1:]
    if not s:
        return False
    if '.' in s:
        parts = s.split('.')
        if len(parts) != 2:
            return False
        left, right = parts
        return (left.isdigit() or left == '') and (right.isdigit() or right == '') and (left or right)
    return s.isdigit()
