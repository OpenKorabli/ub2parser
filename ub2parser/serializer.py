"""
Unbound 2 serializer — reproduces source text from CST nodes.

Strategy: Each node stores a [token_start, token_end) span into the
original flat token list.  The serializer walks the AST in document
order and uses emit_spans to output the raw token text for each
contiguous region.  This guarantees serialize(parse(tokens)) == original.
"""

from __future__ import annotations
from typing import List

from ub2parser.tokenizer import Token
from ub2parser.ast import (
    Document, DefNode, DefParam,
    SExpr, Property, ScopeNode, VarDecl, EventDecl,
    BindNode, BindCallNode, SyncNode, DispatchNode,
    ControllerNode, MacroCallNode, MacroArg, DOMethod,
    StyleNode, FiltersNode,
    ListNode, MapNode, MapEntry,
    Node,
)


def serialize(doc: Document, tokens: List[Token]) -> str:
    """Serialize a Document back to source text using the original tokens.

    Because every CST node stores token indices and the token list preserves
    every byte of the original source, the output is byte-identical to the
    input.
    """
    # Build a sorted list of token regions to emit.
    # We walk the AST and collect all (start, end) spans, then merge contiguous ones.
    spans: List[tuple[int, int]] = []
    _collect_spans(doc, spans)

    if not spans:
        return ""

    # Sort by start
    spans.sort(key=lambda s: s[0])

    # Merge overlapping/adjacent spans
    merged: List[tuple[int, int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    # Convert to text
    result_parts: List[str] = []
    last_end = 0
    for s, e in merged:
        # Fill gaps with original tokens (e.g. whitespace between top-level defs)
        if s > last_end:
            for ti in range(last_end, min(s, len(tokens))):
                result_parts.append(tokens[ti].text)
        # Emit tokens for the span
        for ti in range(s, min(e, len(tokens))):
            result_parts.append(tokens[ti].text)
        last_end = e

    # Emit trailing tokens
    for ti in range(last_end, len(tokens)):
        result_parts.append(tokens[ti].text)

    return ''.join(result_parts)


def _collect_spans(node: Node, spans: List[tuple[int, int]]) -> None:
    """Recursively collect token spans from the AST."""
    if node.token_start >= 0 and node.token_end > node.token_start:
        spans.append((node.token_start, node.token_end))

    if isinstance(node, Document):
        for d in node.definitions:
            _collect_spans(d, spans)

    elif isinstance(node, DefNode):
        if node.name:
            _collect_spans(node.name, spans)
        for p in node.params:
            _collect_spans(p, spans)
        for child in node.body:
            _collect_spans(child, spans)

    elif isinstance(node, DefParam):
        if node.name:
            _collect_spans(node.name, spans)
        if node.type_ident:
            _collect_spans(node.type_ident, spans)
        if node.default_value:
            _collect_spans(node.default_value, spans)

    elif isinstance(node, SExpr):
        if node.command:
            _collect_spans(node.command, spans)
        for a in node.args:
            _collect_spans(a, spans)

    elif isinstance(node, Property):
        if node.name:
            _collect_spans(node.name, spans)
        if node.value:
            _collect_spans(node.value, spans)
        for m in node.modifiers:
            _collect_spans(m, spans)

    elif isinstance(node, ScopeNode):
        for d in node.declarations:
            _collect_spans(d, spans)

    elif isinstance(node, VarDecl):
        if node.name:
            _collect_spans(node.name, spans)
        if node.type_ident:
            _collect_spans(node.type_ident, spans)
        if node.value:
            _collect_spans(node.value, spans)
        for m in node.modifiers:
            _collect_spans(m, spans)

    elif isinstance(node, EventDecl):
        if node.name:
            _collect_spans(node.name, spans)

    elif isinstance(node, BindNode):
        if node.target:
            _collect_spans(node.target, spans)
        if node.source:
            _collect_spans(node.source, spans)
        for o in node.options:
            _collect_spans(o, spans)

    elif isinstance(node, BindCallNode):
        if node.method:
            _collect_spans(node.method, spans)
        for a in node.args:
            _collect_spans(a, spans)

    elif isinstance(node, SyncNode):
        if node.target:
            _collect_spans(node.target, spans)
        if node.source:
            _collect_spans(node.source, spans)
        for o in node.options:
            _collect_spans(o, spans)

    elif isinstance(node, DispatchNode):
        if node.event_name:
            _collect_spans(node.event_name, spans)
        for o in node.options:
            _collect_spans(o, spans)

    elif isinstance(node, ControllerNode):
        if node.name:
            _collect_spans(node.name, spans)
        for child in node.body:
            _collect_spans(child, spans)

    elif isinstance(node, MacroCallNode):
        if node.name:
            _collect_spans(node.name, spans)
        for a in node.args:
            _collect_spans(a, spans)

    elif isinstance(node, MacroArg):
        if node.name:
            _collect_spans(node.name, spans)
        if node.value:
            _collect_spans(node.value, spans)

    elif isinstance(node, DOMethod):
        if node.method_name:
            _collect_spans(node.method_name, spans)
        for child in node.body:
            _collect_spans(child, spans)

    elif isinstance(node, StyleNode):
        for p in node.properties:
            _collect_spans(p, spans)

    elif isinstance(node, FiltersNode):
        for f in node.filters:
            _collect_spans(f, spans)

    elif isinstance(node, ListNode):
        for item in node.items:
            _collect_spans(item, spans)

    elif isinstance(node, MapNode):
        for entry in node.entries:
            _collect_spans(entry, spans)

    elif isinstance(node, MapEntry):
        if node.key:
            _collect_spans(node.key, spans)
        if node.value:
            _collect_spans(node.value, spans)

    # Leaf nodes (Identifier, NumberLiteral, StringLiteral, BooleanLiteral)
    # are handled by their own token_start/token_end.
