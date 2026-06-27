"""
Unbound 2 recursive-descent parser — converts tokens into CST nodes.

The parser produces a Document root.  Every significant node carries
token-span information so the serializer can reproduce the original source.
"""

from __future__ import annotations
from typing import List, Optional

from ub2parser.tokenizer import Token, TokenType
from ub2parser.ast import (
    Node, Document, DefNode, DefParam,
    SExpr, Property, ScopeNode, VarDecl, EventDecl,
    Identifier, NumberLiteral, StringLiteral, BooleanLiteral,
    ListNode, MapNode, MapEntry,
    BindNode, BindCallNode, SyncNode, DispatchNode,
    ControllerNode, MacroCallNode, MacroArg, DOMethod,
    StyleNode, FiltersNode, Expression,
    Value,
)


class ParseError(Exception):
    def __init__(self, msg: str, token: Optional[Token] = None):
        if token:
            super().__init__(f"{msg} at line {token.line}, col {token.col}")
        else:
            super().__init__(msg)


class Parser:
    """Recursive-descent parser over a token list."""

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0  # current token index

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def current(self) -> Optional[Token]:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def peek(self) -> Optional[TokenType]:
        t = self.current
        return t.type if t else None

    def advance(self) -> Optional[Token]:
        t = self.current
        if t:
            self.pos += 1
        return t

    def expect(self, ttype: TokenType) -> Token:
        t = self.current
        if t is None:
            raise ParseError(f"Expected {ttype.name}, got end of file")
        if t.type != ttype:
            raise ParseError(f"Expected {ttype.name}, got {t.type.name} ({t.text!r})", t)
        self.pos += 1
        return t

    def match(self, ttype: TokenType) -> bool:
        if self.peek() == ttype:
            self.pos += 1
            return True
        return False

    def skip_whitespace_and_comments(self) -> None:
        """Skip whitespace, newlines, and comments (structural skip)."""
        while self.peek() in (TokenType.WHITESPACE, TokenType.NEWLINE, TokenType.COMMENT):
            self.pos += 1

    # ------------------------------------------------------------------
    # Top level
    # ------------------------------------------------------------------

    def parse(self) -> Document:
        """Parse the entire token stream into a Document."""
        doc = Document(token_start=0, token_end=len(self.tokens))

        while self.pos < len(self.tokens):
            self.skip_whitespace_and_comments()
            if self.pos >= len(self.tokens):
                break
            defn = self.parse_def()
            if defn:
                doc.definitions.append(defn)
            else:
                # Skip unexpected token
                self.pos += 1

        return doc

    # ------------------------------------------------------------------
    # Definitions
    # ------------------------------------------------------------------

    def parse_def(self) -> Optional[DefNode]:
        """Parse (def kind Name(params...) body...).

        For 'constant': (def constant Name value)
            — single value body, stored as body[0] if present.

        For 'element', 'css', 'macro', 'struct':
            (def kind Name (params...) body...)
            — body is a list of S-expressions.
        """
        if self.peek() != TokenType.LPAREN:
            return None

        lparen_idx = self.pos
        self.pos += 1

        self.skip_whitespace_and_comments()

        # Expect 'def'
        if self.peek() != TokenType.IDENTIFIER or self.current.text != 'def':
            # Not a def — rewind so the caller can try something else
            self.pos = lparen_idx
            return None

        def_token = self.pos
        self.pos += 1  # consume 'def'

        self.skip_whitespace_and_comments()

        # Kind: constant, element, css, macro, struct
        kind_tok = self.current
        if kind_tok is None or kind_tok.type != TokenType.IDENTIFIER:
            raise ParseError("Expected def kind (constant/element/css/macro/struct)", kind_tok)
        def_kind = kind_tok.text
        self.pos += 1

        self.skip_whitespace_and_comments()

        # Name
        name = self.parse_value()
        if not isinstance(name, Identifier):
            raise ParseError(f"Expected identifier as def name, got {type(name).__name__}", self.current)

        self.skip_whitespace_and_comments()

        # Parameters: (paramName:type = default) or ()
        params: List[DefParam] = []
        if self.peek() == TokenType.LPAREN:
            self.pos += 1  # consume '('
            self.skip_whitespace_and_comments()

            while self.peek() != TokenType.RPAREN and self.pos < len(self.tokens):
                param = self.parse_def_param()
                if param:
                    params.append(param)
                self.skip_whitespace_and_comments()
                if self.peek() == TokenType.COMMA:
                    self.pos += 1
                    self.skip_whitespace_and_comments()

            self.expect(TokenType.RPAREN)
            self.skip_whitespace_and_comments()

        # ---- Body handling ----
        body: List[Node] = []

        if def_kind == 'constant':
            # (def constant Name value) — single value then ')'
            self.skip_whitespace_and_comments()
            if self.peek() != TokenType.RPAREN:
                val = self.parse_value()
                if val is not None:
                    body.append(val)
            self.skip_whitespace_and_comments()
        else:
            # element, css, macro, struct — S-expression body
            while self.peek() != TokenType.RPAREN and self.pos < len(self.tokens):
                self.skip_whitespace_and_comments()
                if self.peek() == TokenType.RPAREN:
                    break

                if self.peek() == TokenType.LPAREN:
                    child = self.parse_any()
                    if child:
                        body.append(child)
                    continue

                # Try to parse key=value or positional value
                saved = self.pos
                val = self.parse_value()
                if val is None:
                    if self.peek() != TokenType.RPAREN:
                        self.pos += 1
                    continue

                if isinstance(val, Identifier):
                    self.skip_whitespace_and_comments()
                    if self.peek() == TokenType.EQUALS:
                        eq_idx = self.pos
                        self.pos += 1
                        self.skip_whitespace_and_comments()
                        rhs = self.parse_value()
                        body.append(Property(
                            token_start=saved,
                            token_end=self.pos,
                            name=val,
                            value=rhs,
                            equals_token=eq_idx,
                        ))
                        continue

                body.append(val)

        rparen_idx = self.pos
        if self.peek() == TokenType.RPAREN:
            self.pos += 1
        else:
            raise ParseError("Expected RPAREN to close def", self.current)

        return DefNode(
            token_start=lparen_idx,
            token_end=self.pos,
            def_kind=def_kind,
            name=name,
            params=params,
            body=body,
            lparen_token=lparen_idx,
            rparen_token=rparen_idx,
            def_token=def_token,
        )

    def parse_def_param(self) -> Optional[DefParam]:
        """Parse a single def parameter: `name:type` or `name:type = default`."""
        self.skip_whitespace_and_comments()

        name_tok = self.current
        if name_tok is None:
            return None
        if name_tok.type != TokenType.IDENTIFIER:
            return None

        # Check if this looks like a parameter (has : or we're in a param list)
        # We use a simple heuristic: if the identifier is followed by ':', it's a param
        name_text = name_tok.text
        param_start = self.pos

        # Save position and try to parse as param
        saved = self.pos
        self.pos += 1  # consume name

        self.skip_whitespace_and_comments()

        colon_token = -1
        type_ident: Optional[Identifier] = None
        if self.peek() == TokenType.COLON:
            colon_token = self.pos
            self.pos += 1
            self.skip_whitespace_and_comments()
            type_val = self.parse_value()
            if isinstance(type_val, Identifier):
                type_ident = type_val

        self.skip_whitespace_and_comments()

        equals_token = -1
        default_value: Optional[Value] = None
        if self.peek() == TokenType.EQUALS:
            equals_token = self.pos
            self.pos += 1
            self.skip_whitespace_and_comments()
            default_value = self.parse_value()

        return DefParam(
            token_start=param_start,
            token_end=self.pos,
            name=Identifier.from_token(saved - 1, name_text),
            type_ident=type_ident,
            default_value=default_value,
            colon_token=colon_token,
            equals_token=equals_token,
        )

    # ------------------------------------------------------------------
    # Any node — dispatcher
    # ------------------------------------------------------------------

    def parse_any(self) -> Optional[Node]:
        """Parse any construct at the current position."""
        self.skip_whitespace_and_comments()

        if self.peek() is None:
            return None

        if self.peek() == TokenType.LPAREN:
            return self.parse_sexpr_or_special()

        # Bare value at top level (shouldn't normally happen)
        return None

    # ------------------------------------------------------------------
    # S-Expression dispatcher
    # ------------------------------------------------------------------

    def parse_sexpr_or_special(self) -> Optional[Node]:
        """Parse an S-expression and dispatch to the right handler."""
        if self.peek() != TokenType.LPAREN:
            return None

        lparen_idx = self.pos
        self.pos += 1

        self.skip_whitespace_and_comments()

        command_tok = self.current
        if command_tok is None:
            # Empty parens? Unusual but handle
            self.skip_whitespace_and_comments()
            rparen_idx = self.pos
            self.expect(TokenType.RPAREN)
            return SExpr(token_start=lparen_idx, token_end=self.pos,
                         lparen_token=lparen_idx, rparen_token=rparen_idx)

        if command_tok.type != TokenType.IDENTIFIER:
            # Value S-expression? Just parse as generic
            self.pos = lparen_idx
            return self.parse_generic_sexpr()

        cmd = command_tok.text
        self.pos += 1

        # Dispatch based on command
        if cmd == 'def':
            # Should have been handled at top level, but handle here too
            self.pos = lparen_idx
            return self.parse_def()

        if cmd == 'scope':
            return self._finish_scope(lparen_idx)

        if cmd == 'style':
            return self._finish_style(lparen_idx)

        if cmd == 'filters':
            return self._finish_filters(lparen_idx)

        if cmd in ('var',):
            return self._finish_var_decl(lparen_idx)

        if cmd in ('struct',):
            # Struct instantiation: (struct name = Type(args)) or (struct name:type = value)
            return self._finish_var_decl(lparen_idx)

        if cmd in ('event',):
            return self._finish_event_decl(lparen_idx)

        if cmd in ('bind',):
            return self._finish_bind(lparen_idx)

        if cmd in ('bindcall',):
            return self._finish_bindcall(lparen_idx)

        if cmd in ('sync',):
            return self._finish_sync(lparen_idx)

        if cmd in ('dispatch',):
            return self._finish_dispatch(lparen_idx)

        if cmd in ('controller',):
            return self._finish_controller(lparen_idx)

        if cmd in ('macro',):
            return self._finish_macro_call(lparen_idx)

        if cmd in ('args',):
            return self._finish_args_block(lparen_idx)

        # Property check: (name = value ...)
        # Look ahead past whitespace to see if '=' follows.
        # If so, this is a property assignment — rewind and let _finish_property handle it.
        saved_pos = self.pos
        self.skip_whitespace_and_comments()
        if self.peek() == TokenType.EQUALS:
            # Rewind to just after the LPAREN so _finish_property can parse the name
            self.pos = lparen_idx
            return self._finish_property(lparen_idx)
        self.pos = saved_pos

        # Display object methods: sprite, tf, block, element, symbol, htile, vtile, etc.
        if cmd in ('sprite', 'symbol', 'tf', 'element', 'block', 'htile', 'vtile',
                    'dropShadow', 'glow', 'bevel', 'extends'):
            return self._finish_do_method(lparen_idx, cmd)

        # Generic S-expression
        return self._finish_generic_sexpr(lparen_idx, cmd)

    # ------------------------------------------------------------------
    # Property: (name = value ...modifiers...)
    # ------------------------------------------------------------------

    def _finish_property(self, lparen_idx: int) -> Property:
        """Parse a property assignment like (width = 100px).
        
        Expects self.pos to be at the LPAREN (just before it).
        """
        # Consume LPAREN
        self.pos += 1  # skip '('
        self.skip_whitespace_and_comments()

        # Parse the property name
        name_tok = self.current
        if name_tok is None or name_tok.type != TokenType.IDENTIFIER:
            raise ParseError("Expected property name", name_tok)
        name_node = Identifier.from_token(self.pos, name_tok.text)
        self.pos += 1

        self.skip_whitespace_and_comments()
        eq_idx = self.pos
        self.expect(TokenType.EQUALS)

        self.skip_whitespace_and_comments()
        value = self.parse_complex_value()

        # Optional modifiers: (event "..."), (bind ...), init=true, watch=false, on='...'
        modifiers: List[Node] = []
        while True:
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RPAREN:
                break
            if self.peek() == TokenType.LPAREN:
                # Only accept (event ...) and (bind ...) as modifiers
                ahead = self.pos + 1
                while ahead < len(self.tokens) and self.tokens[ahead].type in (TokenType.WHITESPACE, TokenType.NEWLINE, TokenType.COMMENT):
                    ahead += 1
                if ahead < len(self.tokens) and self.tokens[ahead].type == TokenType.IDENTIFIER and self.tokens[ahead].text in ('event', 'bind'):
                    mod = self.parse_any()
                    if mod:
                        modifiers.append(mod)
                    continue
                # Not a recognized modifier — stop
                break
            # Key=value option
            if self.peek() == TokenType.IDENTIFIER:
                opt = self._parse_option()
                if opt:
                    modifiers.append(opt)
                    continue
            break

        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return Property(
            token_start=lparen_idx,
            token_end=self.pos,
            name=name_node,
            value=value,
            equals_token=eq_idx,
            modifiers=modifiers,
        )

    def _parse_option(self) -> Optional[Property]:
        """Parse a key=value option like `init=true` or `on='evName'`."""
        saved = self.pos
        name_val = self.parse_value()
        if not isinstance(name_val, Identifier):
            self.pos = saved
            return None

        self.skip_whitespace_and_comments()
        if self.peek() != TokenType.EQUALS:
            self.pos = saved
            return None

        eq_idx = self.pos
        self.pos += 1

        self.skip_whitespace_and_comments()
        value = self.parse_value()

        return Property(
            token_start=saved,
            token_end=self.pos,
            name=name_val,
            value=value,
            equals_token=eq_idx,
        )

    # ------------------------------------------------------------------
    # Scope: (scope ...)
    # ------------------------------------------------------------------

    def _finish_scope(self, lparen_idx: int) -> ScopeNode:
        """Parse (scope ...) block."""
        declarations: List[Node] = []
        while self.peek() != TokenType.RPAREN and self.pos < len(self.tokens):
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RPAREN:
                break
            node = self.parse_any()
            if node:
                declarations.append(node)
            else:
                # Skip unexpected
                self.skip_whitespace_and_comments()
                if self.peek() != TokenType.RPAREN:
                    self.pos += 1

        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return ScopeNode(
            token_start=lparen_idx,
            token_end=self.pos,
            declarations=declarations,
            lparen_token=lparen_idx,
            rparen_token=rparen_idx,
        )

    # ------------------------------------------------------------------
    # Style: (style ...)
    # ------------------------------------------------------------------

    def _finish_style(self, lparen_idx: int) -> StyleNode:
        """Parse (style ...) block."""
        properties: List[Property] = []
        while self.peek() != TokenType.RPAREN and self.pos < len(self.tokens):
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RPAREN:
                break
            if self.peek() == TokenType.LPAREN:
                node = self.parse_any()
                if isinstance(node, Property):
                    properties.append(node)
                elif node:
                    # Non-property inside style — still collect
                    pass
                continue
            # Unexpected, skip
            break

        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return StyleNode(
            token_start=lparen_idx,
            token_end=self.pos,
            properties=properties,
            lparen_token=lparen_idx,
            rparen_token=rparen_idx,
        )

    # ------------------------------------------------------------------
    # Filters: (filters ...)
    # ------------------------------------------------------------------

    def _finish_filters(self, lparen_idx: int) -> FiltersNode:
        """Parse (filters ...) block."""
        filter_list: List[Node] = []
        while self.peek() != TokenType.RPAREN and self.pos < len(self.tokens):
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RPAREN:
                break
            if self.peek() == TokenType.LPAREN:
                node = self.parse_any()
                if node:
                    filter_list.append(node)
                continue
            break

        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return FiltersNode(
            token_start=lparen_idx,
            token_end=self.pos,
            filters=filter_list,
            lparen_token=lparen_idx,
            rparen_token=rparen_idx,
        )

    # ------------------------------------------------------------------
    # Var: (var name:type = value ...modifiers...)
    # ------------------------------------------------------------------

    def _finish_var_decl(self, lparen_idx: int) -> VarDecl:
        """Parse (var name:type = value ...) declaration."""
        self.skip_whitespace_and_comments()

        # Name
        name_tok = self.current
        if name_tok is None or name_tok.type != TokenType.IDENTIFIER:
            raise ParseError("Expected variable name", name_tok)
        name = Identifier.from_token(self.pos, name_tok.text)
        self.pos += 1

        self.skip_whitespace_and_comments()

        # Optional :type
        colon_token = -1
        type_ident: Optional[Identifier] = None
        if self.peek() == TokenType.COLON:
            colon_token = self.pos
            self.pos += 1
            self.skip_whitespace_and_comments()
            type_val = self.parse_value()
            if isinstance(type_val, Identifier):
                type_ident = type_val

        self.skip_whitespace_and_comments()

        # Optional = value
        equals_token = -1
        value: Optional[Value] = None
        if self.peek() == TokenType.EQUALS:
            equals_token = self.pos
            self.pos += 1
            self.skip_whitespace_and_comments()
            value = self.parse_complex_value()

        # Optional modifiers: (event "...") only — other S-expressions
        # are siblings, not modifiers.
        modifiers: List[Node] = []
        while True:
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RPAREN:
                break
            # Only accept (event ...) as LPAREN modifier
            if self.peek() == TokenType.LPAREN:
                # Look ahead to see if this is an (event ...) form
                ahead = self.pos + 1
                while ahead < len(self.tokens) and self.tokens[ahead].type in (TokenType.WHITESPACE, TokenType.NEWLINE, TokenType.COMMENT):
                    ahead += 1
                if ahead < len(self.tokens) and self.tokens[ahead].type == TokenType.IDENTIFIER and self.tokens[ahead].text == 'event':
                    mod = self.parse_any()
                    if mod:
                        modifiers.append(mod)
                    continue
                # Not an event — this is a sibling, stop
                break
            # Try key=value option (watch=false, etc.)
            saved = self.pos
            opt_val = self.parse_value()
            if isinstance(opt_val, Identifier):
                self.skip_whitespace_and_comments()
                if self.peek() == TokenType.EQUALS:
                    eq_idx = self.pos
                    self.pos += 1
                    self.skip_whitespace_and_comments()
                    opt_rhs = self.parse_value()
                    modifiers.append(Property(
                        token_start=saved,
                        token_end=self.pos,
                        name=opt_val,
                        value=opt_rhs,
                        equals_token=eq_idx,
                    ))
                    continue
            # Not a recognized modifier, rewind and stop
            self.pos = saved
            break

        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return VarDecl(
            token_start=lparen_idx,
            token_end=self.pos,
            name=name,
            type_ident=type_ident,
            value=value,
            colon_token=colon_token,
            equals_token=equals_token,
            modifiers=modifiers,
        )

    # ------------------------------------------------------------------
    # Event: (event name)
    # ------------------------------------------------------------------

    def _finish_event_decl(self, lparen_idx: int) -> EventDecl:
        """Parse (event name) declaration or (event name="expr") reference."""
        self.skip_whitespace_and_comments()

        name_tok = self.current
        if name_tok is None:
            raise ParseError("Expected event name", name_tok)
        
        # Handle (event name="expression") form
        if name_tok.type == TokenType.IDENTIFIER and name_tok.text == 'name':
            self.pos += 1
            self.skip_whitespace_and_comments()
            self.expect(TokenType.EQUALS)
            self.skip_whitespace_and_comments()
            val = self.parse_value()
            if val is None:
                raise ParseError("Expected event name value", self.current)
            name_node: Identifier
            if isinstance(val, Identifier):
                name_node = val
            elif isinstance(val, StringLiteral):
                name_node = Identifier.from_token(val.token_start, val.value)
            else:
                name_node = Identifier.from_token(val.token_start, str(val))
        elif name_tok.type == TokenType.IDENTIFIER:
            name = Identifier.from_token(self.pos, name_tok.text)
            self.pos += 1
            name_node = name
        elif name_tok.type == TokenType.STRING:
            name = Identifier.from_token(self.pos, name_tok.text)
            self.pos += 1
            name_node = name
        else:
            raise ParseError(f"Expected event name, got {name_tok.type.name} ({name_tok.text!r})", name_tok)

        self.skip_whitespace_and_comments()
        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return EventDecl(
            token_start=lparen_idx,
            token_end=self.pos,
            name=name_node,
        )

    # ------------------------------------------------------------------
    # Bind: (bind target source ...options...)
    # ------------------------------------------------------------------

    def _finish_bind(self, lparen_idx: int) -> BindNode:
        """Parse (bind target "source" ...) statement."""
        self.skip_whitespace_and_comments()

        target = self.parse_value()
        if not isinstance(target, Identifier):
            raise ParseError("Expected bind target identifier", self.current)

        self.skip_whitespace_and_comments()

        # Source value (required)
        source = self.parse_value()

        # Options: init=true/false, watch=true/false, on='...', (event "..."), etc.
        options: List[Node] = []
        while True:
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RPAREN:
                break
            if self.peek() == TokenType.LPAREN:
                opt_node = self.parse_any()
                if opt_node:
                    options.append(opt_node)
                continue
            if self.peek() == TokenType.IDENTIFIER:
                opt = self._parse_option()
                if opt:
                    options.append(opt)
                    continue
            break

        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return BindNode(
            token_start=lparen_idx,
            token_end=self.pos,
            target=target,
            source=source,
            options=options,
        )

    # ------------------------------------------------------------------
    # Bindcall: (bindcall method ...args...)
    # ------------------------------------------------------------------

    def _finish_bindcall(self, lparen_idx: int) -> BindCallNode:
        """Parse (bindcall method ...args...) statement."""
        self.skip_whitespace_and_comments()

        method = self.parse_value()
        if not isinstance(method, Identifier):
            raise ParseError("Expected bindcall method name", self.current)

        # Parse remaining args: positional values, key=value pairs, (event "..."), etc.
        args: List[Node] = []
        while True:
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RPAREN:
                break
            if self.peek() == TokenType.LPAREN:
                node = self.parse_any()
                if node:
                    args.append(node)
                continue

            # Try to parse a value
            saved = self.pos
            val = self.parse_value()
            if val is None:
                break

            # If it's an identifier, check for key=value
            if isinstance(val, Identifier):
                self.skip_whitespace_and_comments()
                if self.peek() == TokenType.EQUALS:
                    eq_idx = self.pos
                    self.pos += 1
                    self.skip_whitespace_and_comments()
                    rhs = self.parse_value()
                    args.append(Property(
                        token_start=saved,
                        token_end=self.pos,
                        name=val,
                        value=rhs,
                        equals_token=eq_idx,
                    ))
                    continue

            # Positional argument (any value type)
            args.append(val)

        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return BindCallNode(
            token_start=lparen_idx,
            token_end=self.pos,
            method=method,
            args=args,
        )

    # ------------------------------------------------------------------
    # Sync: (sync target source ...options...)
    # ------------------------------------------------------------------

    def _finish_sync(self, lparen_idx: int) -> SyncNode:
        """Parse (sync target source ...) or (sync target from='...' ...) statement."""
        self.skip_whitespace_and_comments()
        target = self.parse_value()
        if not isinstance(target, Identifier):
            raise ParseError("Expected sync target", self.current)

        self.skip_whitespace_and_comments()
        
        # Try to parse source — it can be a value or omitted in favor of from= option
        source: Optional[Value] = None
        saved = self.pos
        maybe_source = self.parse_value()
        if isinstance(maybe_source, Identifier):
            # Check if it's actually a key=value option (like from='text')
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.EQUALS:
                # It's a key=value option, not a source. Backtrack and add to options.
                self.pos = saved
            else:
                source = maybe_source
        elif maybe_source is not None:
            source = maybe_source

        options: List[Node] = []
        while True:
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RPAREN:
                break
            if self.peek() == TokenType.LPAREN:
                node = self.parse_any()
                if node:
                    options.append(node)
                continue
            # Try key=value option or positional value
            saved_opt = self.pos
            val = self.parse_value()
            if isinstance(val, Identifier):
                self.skip_whitespace_and_comments()
                if self.peek() == TokenType.EQUALS:
                    eq_idx = self.pos
                    self.pos += 1
                    self.skip_whitespace_and_comments()
                    rhs = self.parse_value()
                    options.append(Property(
                        token_start=saved_opt,
                        token_end=self.pos,
                        name=val,
                        value=rhs,
                        equals_token=eq_idx,
                    ))
                    continue
            # Positional value
            if val is not None:
                options.append(val)
                continue
            break

        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return SyncNode(
            token_start=lparen_idx,
            token_end=self.pos,
            target=target,
            source=source,
            options=options,
        )

    # ------------------------------------------------------------------
    # Dispatch: (dispatch event ...options...)
    # ------------------------------------------------------------------

    def _finish_dispatch(self, lparen_idx: int) -> DispatchNode:
        """Parse (dispatch event ...) statement."""
        self.skip_whitespace_and_comments()
        event_name = self.parse_value()
        if event_name is None:
            raise ParseError("Expected dispatch event name", self.current)
        # Accept identifiers and strings as event names

        options: List[Node] = []
        while True:
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RPAREN:
                break
            if self.peek() == TokenType.LPAREN:
                node = self.parse_any()
                if node:
                    options.append(node)
                continue
            if self.peek() == TokenType.IDENTIFIER:
                opt = self._parse_option()
                if opt:
                    options.append(opt)
                    continue
            break

        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return DispatchNode(
            token_start=lparen_idx,
            token_end=self.pos,
            event_name=event_name,
            options=options,
        )

    # ------------------------------------------------------------------
    # Controller: (controller $Name ...body...)
    # ------------------------------------------------------------------

    def _finish_controller(self, lparen_idx: int) -> ControllerNode:
        """Parse (controller $Name ...) block."""
        self.skip_whitespace_and_comments()
        name = self.parse_value()
        if not isinstance(name, Identifier):
            raise ParseError("Expected controller name (e.g. $Animation)", self.current)

        body: List[Node] = []
        while self.peek() != TokenType.RPAREN and self.pos < len(self.tokens):
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RPAREN:
                break

            if self.peek() == TokenType.LPAREN:
                node = self.parse_any()
                if node:
                    body.append(node)
                continue

            # Try to parse key=value or positional value
            saved = self.pos
            val = self.parse_value()
            if val is None:
                if self.peek() != TokenType.RPAREN:
                    self.pos += 1
                continue

            if isinstance(val, Identifier):
                self.skip_whitespace_and_comments()
                if self.peek() == TokenType.EQUALS:
                    eq_idx = self.pos
                    self.pos += 1
                    self.skip_whitespace_and_comments()
                    rhs = self.parse_complex_value()
                    body.append(Property(
                        token_start=saved,
                        token_end=self.pos,
                        name=val,
                        value=rhs,
                        equals_token=eq_idx,
                    ))
                    continue

            body.append(val)

        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return ControllerNode(
            token_start=lparen_idx,
            token_end=self.pos,
            name=name,
            body=body,
            lparen_token=lparen_idx,
            rparen_token=rparen_idx,
        )

    # ------------------------------------------------------------------
    # Macro call: (macro Name param=value ...)
    # ------------------------------------------------------------------

    def _finish_macro_call(self, lparen_idx: int) -> MacroCallNode:
        """Parse (macro Name key=value ...) invocation."""
        self.skip_whitespace_and_comments()
        name = self.parse_value()
        if not isinstance(name, Identifier):
            raise ParseError("Expected macro name", self.current)

        args: List[MacroArg] = []
        while True:
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RPAREN:
                break

            saved = self.pos

            # Try to parse a value (could be identifier, string, number, etc.)
            val = self.parse_value()
            if val is None:
                break

            # Check if it's a key=value pair (only possible for identifiers)
            if isinstance(val, Identifier):
                self.skip_whitespace_and_comments()
                if self.peek() == TokenType.EQUALS:
                    eq_idx = self.pos
                    self.pos += 1
                    self.skip_whitespace_and_comments()
                    arg_value = self.parse_value()
                    args.append(MacroArg(
                        token_start=saved,
                        token_end=self.pos,
                        name=val,
                        value=arg_value,
                        equals_token=eq_idx,
                    ))
                    continue

            # Positional argument (any value type)
            args.append(MacroArg(
                token_start=saved,
                token_end=self.pos,
                value=val,
            ))

        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return MacroCallNode(
            token_start=lparen_idx,
            token_end=self.pos,
            name=name,
            args=args,
            lparen_token=lparen_idx,
            rparen_token=rparen_idx,
        )

    def _finish_args_block(self, lparen_idx: int) -> SExpr:
        """Parse (args ...) block — key=value pairs and positional values."""
        cmd_node = Identifier.from_token(self.pos - 1, 'args')

        args: List[Node] = []
        while True:
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RPAREN:
                break

            saved = self.pos
            val = self.parse_value()
            if val is None:
                break

            # If identifier, check for key=value
            if isinstance(val, Identifier):
                self.skip_whitespace_and_comments()
                if self.peek() == TokenType.EQUALS:
                    eq_idx = self.pos
                    self.pos += 1
                    self.skip_whitespace_and_comments()
                    rhs = self.parse_complex_value()
                    args.append(Property(
                        token_start=saved,
                        token_end=self.pos,
                        name=val,
                        value=rhs,
                        equals_token=eq_idx,
                    ))
                    continue

            # Positional value (any type)
            args.append(val)

        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return SExpr(
            token_start=lparen_idx,
            token_end=self.pos,
            command=cmd_node,
            args=args,
            lparen_token=lparen_idx,
            rparen_token=rparen_idx,
        )

    # ------------------------------------------------------------------
    # DO method: (sprite ...), (tf ...), (block ...), etc.
    # ------------------------------------------------------------------

    def _finish_do_method(self, lparen_idx: int, cmd: str) -> DOMethod:
        """Parse a display-object method call like (element Name key=val ...)
        or (sprite ...) with property children."""
        name_node = Identifier.from_token(lparen_idx + 1, cmd)

        body: List[Node] = []
        while self.peek() != TokenType.RPAREN and self.pos < len(self.tokens):
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RPAREN:
                break

            if self.peek() == TokenType.LPAREN:
                node = self.parse_any()
                if node:
                    body.append(node)
                continue

            # Try to parse a value
            saved = self.pos
            val = self.parse_value()
            if val is None:
                # Can't parse, skip token to avoid infinite loop
                if self.peek() != TokenType.RPAREN:
                    self.pos += 1
                continue

            # If it's an identifier, check for key=value
            if isinstance(val, Identifier):
                self.skip_whitespace_and_comments()
                if self.peek() == TokenType.EQUALS:
                    eq_idx = self.pos
                    self.pos += 1
                    self.skip_whitespace_and_comments()
                    rhs = self.parse_value()
                    body.append(Property(
                        token_start=saved,
                        token_end=self.pos,
                        name=val,
                        value=rhs,
                        equals_token=eq_idx,
                    ))
                    continue

            # Positional value
            body.append(val)

        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return DOMethod(
            token_start=lparen_idx,
            token_end=self.pos,
            method_name=name_node,
            body=body,
            lparen_token=lparen_idx,
            rparen_token=rparen_idx,
        )

    # ------------------------------------------------------------------
    # Generic S-expression
    # ------------------------------------------------------------------

    def _finish_generic_sexpr(self, lparen_idx: int, cmd: str) -> SExpr:
        """Parse a generic S-expression with mixed positional and key=value args."""
        cmd_node = Identifier.from_token(self.pos - 1, cmd)

        args: List[Node] = []
        while self.peek() != TokenType.RPAREN and self.pos < len(self.tokens):
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RPAREN:
                break
            if self.peek() == TokenType.LPAREN:
                node = self.parse_any()
                if node:
                    args.append(node)
                continue

            # Try to parse a value
            saved = self.pos
            val = self.parse_value()
            if val is None:
                break

            # If identifier, check for key=value
            if isinstance(val, Identifier):
                self.skip_whitespace_and_comments()
                if self.peek() == TokenType.EQUALS:
                    eq_idx = self.pos
                    self.pos += 1
                    self.skip_whitespace_and_comments()
                    rhs = self.parse_complex_value()
                    args.append(Property(
                        token_start=saved,
                        token_end=self.pos,
                        name=val,
                        value=rhs,
                        equals_token=eq_idx,
                    ))
                    continue

            # Positional value
            args.append(val)

        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return SExpr(
            token_start=lparen_idx,
            token_end=self.pos,
            command=cmd_node,
            args=args,
            lparen_token=lparen_idx,
            rparen_token=rparen_idx,
        )

    # ------------------------------------------------------------------
    # Value parsing
    # ------------------------------------------------------------------

    def parse_complex_value(self) -> Optional[Value]:
        """Parse a value that may be followed by function-call parentheses.

        E.g., `GET_PREF_BOOL(_option = "...")` is parsed as a single SExpr
        with GET_PREF_BOOL as the command.
        """
        val = self.parse_value()
        if val is None:
            return None

        # If the value is an identifier, check for trailing function call
        if isinstance(val, Identifier):
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.LPAREN:
                lparen_pos = self.pos
                self.pos += 1
                return self._finish_generic_sexpr(lparen_pos, val.name)

        return val

    # ------------------------------------------------------------------
    # Value parsing
    # ------------------------------------------------------------------

    def parse_value(self) -> Optional[Value]:
        """Parse a single value: identifier, number, string, boolean, list, map."""
        self.skip_whitespace_and_comments()

        tok = self.current
        if tok is None:
            return None

        if tok.type == TokenType.IDENTIFIER:
            self.pos += 1
            return Identifier.from_token(self.pos - 1, tok.text)

        if tok.type == TokenType.NUMBER:
            self.pos += 1
            return NumberLiteral(token_start=self.pos - 1, token_end=self.pos, value=tok.text)

        if tok.type == TokenType.STRING:
            self.pos += 1
            return StringLiteral(token_start=self.pos - 1, token_end=self.pos, value=tok.text)

        if tok.type == TokenType.BOOLEAN:
            self.pos += 1
            return BooleanLiteral(token_start=self.pos - 1, token_end=self.pos, value=tok.text)

        if tok.type == TokenType.LBRACKET:
            return self.parse_list()

        if tok.type == TokenType.LBRACE:
            return self.parse_map()

        # Handle lone '-' or '+' as sign prefix for numbers
        # (tokenizer normally merges them, but this handles edge cases)
        if tok.type == TokenType.IDENTIFIER and tok.text in ('-', '+'):
            sign = tok.text
            sign_start = self.pos
            self.pos += 1
            self.skip_whitespace_and_comments()
            next_tok = self.current
            if next_tok and next_tok.type == TokenType.NUMBER:
                self.pos += 1
                combined = sign + next_tok.text
                return NumberLiteral(
                    token_start=sign_start,
                    token_end=self.pos,
                    value=combined,
                )
            # Not followed by a number, return the sign as identifier
            return Identifier.from_token(sign_start, sign)

        return None

    def parse_list(self) -> ListNode:
        """Parse a list literal: [item1, item2, ...]."""
        start = self.pos
        self.pos += 1  # consume '['

        items: List[Value] = []
        while self.peek() != TokenType.RBRACKET and self.pos < len(self.tokens):
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RBRACKET:
                break
            if self.peek() == TokenType.COMMA:
                self.pos += 1
                continue
            val = self.parse_value()
            if val:
                items.append(val)
            else:
                break

        self.skip_whitespace_and_comments()
        self.expect(TokenType.RBRACKET)

        return ListNode(
            token_start=start,
            token_end=self.pos,
            items=items,
        )

    def parse_map(self) -> MapNode:
        """Parse a map literal: {key: val, key2: val2}.

        Keys can be identifiers, strings, or numbers.
        The colon between key and value is required.
        """
        start = self.pos
        self.pos += 1  # consume '{'

        entries: List[MapEntry] = []
        while self.peek() != TokenType.RBRACE and self.pos < len(self.tokens):
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RBRACE:
                break
            if self.peek() == TokenType.COMMA:
                self.pos += 1
                continue

            # Parse the key (any value type)
            key_start = self.pos
            key = self.parse_value()
            if key is None:
                # Can't parse anything useful, skip a token to avoid infinite loop
                if self.pos < len(self.tokens) and self.peek() != TokenType.RBRACE:
                    self.pos += 1
                continue

            self.skip_whitespace_and_comments()

            # Check for colon
            colon_token = -1
            value: Optional[Value] = None
            if self.peek() == TokenType.COLON:
                colon_token = self.pos
                self.pos += 1  # consume ':'
                self.skip_whitespace_and_comments()
                value = self.parse_value()

            entry_end = self.pos

            entries.append(MapEntry(
                token_start=key_start,
                token_end=entry_end,
                key=key if isinstance(key, Identifier) else None,
                value=value if value is not None else key,
                colon_token=colon_token,
            ))

        self.skip_whitespace_and_comments()
        if self.peek() == TokenType.RBRACE:
            self.pos += 1
        # else: let caller handle error

        return MapNode(
            token_start=start,
            token_end=self.pos,
            entries=entries,
        )

    # ------------------------------------------------------------------
    # Generic S-expression (used as fallback)
    # ------------------------------------------------------------------

    def parse_generic_sexpr(self) -> Optional[SExpr]:
        """Parse any S-expression generically."""
        if self.peek() != TokenType.LPAREN:
            return None

        lparen_idx = self.pos
        self.pos += 1

        self.skip_whitespace_and_comments()

        command_tok = self.current
        cmd_node: Optional[Identifier] = None
        if command_tok and command_tok.type == TokenType.IDENTIFIER:
            cmd_node = Identifier.from_token(self.pos, command_tok.text)
            self.pos += 1
        elif command_tok:
            cmd_node = Identifier.from_token(self.pos, command_tok.text)
            self.pos += 1

        args: List[Node] = []
        while self.peek() != TokenType.RPAREN and self.pos < len(self.tokens):
            self.skip_whitespace_and_comments()
            if self.peek() == TokenType.RPAREN:
                break
            if self.peek() == TokenType.LPAREN:
                node = self.parse_any()
                if node:
                    args.append(node)
                continue
            val = self.parse_value()
            if val:
                args.append(val)
            else:
                break

        rparen_idx = self.pos
        self.expect(TokenType.RPAREN)

        return SExpr(
            token_start=lparen_idx,
            token_end=self.pos,
            command=cmd_node,
            args=args,
            lparen_token=lparen_idx,
            rparen_token=rparen_idx,
        )


def parse(tokens: List[Token]) -> Document:
    """Parse a list of tokens into a Document AST."""
    parser = Parser(tokens)
    return parser.parse()
