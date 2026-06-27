"""
Unbound 2 AST — node types for the Concrete Syntax Tree.

Every node stores its token range [token_start, token_end) into the
original token list, enabling perfect source reproduction.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Union


# ---------------------------------------------------------------------------
# Base node
# ---------------------------------------------------------------------------

@dataclass
class Node:
    """Base class for all CST nodes."""
    token_start: int = -1   # inclusive index into token list
    token_end: int = -1     # exclusive index into token list

    def span(self, start: int, end: int) -> 'Node':
        """Set token span and return self (builder pattern)."""
        self.token_start = start
        self.token_end = end
        return self


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

@dataclass
class Identifier(Node):
    """A dotted identifier like `width`, `$ClassName`, `SC.path.Value`."""
    name: str = ""

    @staticmethod
    def from_token(token_idx: int, text: str) -> 'Identifier':
        return Identifier(token_idx, token_idx + 1, text)


@dataclass
class NumberLiteral(Node):
    """A numeric literal: `42`, `3.14`, `0xFF0000`, `100px`, `50%`, `-3`."""
    value: str = ""


@dataclass
class StringLiteral(Node):
    """A string literal: `'hello'` or `"hello"` (includes quotes)."""
    value: str = ""

    @property
    def unquoted(self) -> str:
        """Return the string content without quotes."""
        if len(self.value) >= 2:
            return self.value[1:-1]
        return self.value


@dataclass
class BooleanLiteral(Node):
    """A boolean literal: `true` or `false`."""
    value: str = ""


@dataclass
class ListNode(Node):
    """A list literal: `[a, b, c]` or `[a b c]`."""
    items: List[Value] = field(default_factory=list)


@dataclass
class MapNode(Node):
    """A map/dict literal: `{key: val, key2: val2}`."""
    entries: List[MapEntry] = field(default_factory=list)


@dataclass
class MapEntry(Node):
    """A key-value pair inside a map."""
    key: Optional[Identifier] = None
    value: Optional['Value'] = None
    colon_token: int = -1   # token index of the ':'


# Union of all possible value types
Value = Union[Identifier, NumberLiteral, StringLiteral, BooleanLiteral,
              ListNode, MapNode]


# ---------------------------------------------------------------------------
# Expressions (computed expressions in quotes)
# ---------------------------------------------------------------------------

@dataclass
class Expression(Node):
    """A computed expression inside double quotes: `"a + b"`."""
    source: str = ""  # the raw string including quotes


# ---------------------------------------------------------------------------
# S-Expression
# ---------------------------------------------------------------------------

@dataclass
class SExpr(Node):
    """An S-expression: `(command arg1 arg2 ...)`."""
    command: Optional[Identifier] = None
    args: List[Node] = field(default_factory=list)
    lparen_token: int = -1
    rparen_token: int = -1


# ---------------------------------------------------------------------------
# Property assignment
# ---------------------------------------------------------------------------

@dataclass
class Property(Node):
    """A property assignment within an S-expression: `(width = 100px)`."""
    name: Optional[Identifier] = None
    value: Optional[Value] = None
    equals_token: int = -1

    # Optional post-property modifiers like bindcall's extra args
    # or (event "...") / (bind ...) attached after the value
    modifiers: List[Node] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Definition forms
# ---------------------------------------------------------------------------

@dataclass
class DefParam(Node):
    """A parameter in a def form: `name:type` or `name:type = default`."""
    name: Optional[Identifier] = None
    type_ident: Optional[Identifier] = None   # the type annotation
    default_value: Optional[Value] = None
    colon_token: int = -1
    equals_token: int = -1


@dataclass
class DefNode(Node):
    """A top-level definition: `(def kind Name(params...) body...)`."""
    def_kind: str = ""          # "constant", "element", "css", "macro", "struct"
    name: Optional[Identifier] = None
    params: List[DefParam] = field(default_factory=list)
    body: List[Node] = field(default_factory=list)
    lparen_token: int = -1
    rparen_token: int = -1
    def_token: int = -1         # token index of the 'def' keyword


# ---------------------------------------------------------------------------
# Special scope constructs
# ---------------------------------------------------------------------------

@dataclass
class ScopeNode(Node):
    """A (scope ...) block containing var/event declarations and bindings."""
    declarations: List[Node] = field(default_factory=list)
    lparen_token: int = -1
    rparen_token: int = -1


@dataclass
class VarDecl(Node):
    """A variable declaration: `(var name:type = expr)`."""
    name: Optional[Identifier] = None
    type_ident: Optional[Identifier] = None
    value: Optional[Value] = None  # usually an Expression string
    colon_token: int = -1
    equals_token: int = -1

    # Extra modifiers like (event "...") attached after the value
    modifiers: List[Node] = field(default_factory=list)


@dataclass
class EventDecl(Node):
    """An event declaration: `(event name)`."""
    name: Optional[Identifier] = None


# ---------------------------------------------------------------------------
# Binding forms
# ---------------------------------------------------------------------------

@dataclass
class BindNode(Node):
    """A binding: `(bind target "source" ...options...)`."""
    target: Optional[Identifier] = None
    source: Optional[Value] = None
    options: List[Node] = field(default_factory=list)  # init=true, watch=false, on='...', (event "..."), etc.


@dataclass
class BindCallNode(Node):
    """A bindcall: `(bindcall method ...args...)`."""
    method: Optional[Identifier] = None
    args: List[Node] = field(default_factory=list)


@dataclass
class SyncNode(Node):
    """A sync: `(sync target source ...options...)`."""
    target: Optional[Identifier] = None
    source: Optional[Value] = None
    options: List[Node] = field(default_factory=list)


@dataclass
class DispatchNode(Node):
    """A dispatch: `(dispatch event ...options...)`."""
    event_name: Optional[Value] = None
    options: List[Node] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

@dataclass
class ControllerNode(Node):
    """A controller: `(controller $Name ...body...)`."""
    name: Optional[Identifier] = None
    body: List[Node] = field(default_factory=list)
    lparen_token: int = -1
    rparen_token: int = -1


# ---------------------------------------------------------------------------
# Macro invocation
# ---------------------------------------------------------------------------

@dataclass
class MacroCallNode(Node):
    """A macro invocation: `(macro Name param=value ...)`."""
    name: Optional[Identifier] = None
    args: List[MacroArg] = field(default_factory=list)
    lparen_token: int = -1
    rparen_token: int = -1


@dataclass
class MacroArg(Node):
    """A macro argument: `name=value`."""
    name: Optional[Identifier] = None
    value: Optional[Value] = None
    equals_token: int = -1


# ---------------------------------------------------------------------------
# Display object methods (sprite, tf, block, element, etc.)
# ---------------------------------------------------------------------------

@dataclass
class DOMethod(Node):
    """A display-object creation/invocation: `(sprite ...)`, `(tf ...)`, `(block ...)`, etc."""
    method_name: Optional[Identifier] = None
    body: List[Node] = field(default_factory=list)
    lparen_token: int = -1
    rparen_token: int = -1


# ---------------------------------------------------------------------------
# Style block
# ---------------------------------------------------------------------------

@dataclass
class StyleNode(Node):
    """A (style ...) block."""
    properties: List[Property] = field(default_factory=list)
    lparen_token: int = -1
    rparen_token: int = -1


# ---------------------------------------------------------------------------
# Filters block
# ---------------------------------------------------------------------------

@dataclass
class FiltersNode(Node):
    """A (filters ...) block."""
    filters: List[Node] = field(default_factory=list)
    lparen_token: int = -1
    rparen_token: int = -1


# ---------------------------------------------------------------------------
# Document root
# ---------------------------------------------------------------------------

@dataclass
class Document(Node):
    """Root of the parsed .unbound file — a list of top-level definitions."""
    definitions: List[DefNode] = field(default_factory=list)
