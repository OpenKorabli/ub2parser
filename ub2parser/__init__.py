"""
Unbound 2 (.unbound) parser — serialization and deserialization
for Mir Korabley's Unbound 2 UI framework definition files.

Provides:
    tokenize(text) -> list[Token]      — lex source into tokens
    parse(tokens)  -> Document         — build CST from tokens
    serialize(doc) -> str              — reproduce source from CST

Round-trip guarantee: serialize(parse(tokenize(text))) == text

Package name on PyPI: ub2parser
Module name for import: ub2parser
"""

__version__ = "0.1.2"

from ub2parser.tokenizer import tokenize, Token, TokenType
from ub2parser.parser import parse
from ub2parser.ast import (Document, Node, SExpr, Property, DefNode,
                          ScopeNode, VarDecl, EventDecl)
from ub2parser.serializer import serialize

__all__ = [
    'tokenize', 'Token', 'TokenType',
    'parse',
    'Document', 'Node', 'SExpr', 'Property', 'DefNode', 'ScopeNode', 'VarDecl', 'EventDecl',
    'serialize',
]
