# ub2parser — Unbound 2 Parser

A Python library for parsing and serializing Mir Korabley's **Unbound 2** UI framework definition files (`.unbound`). It converts source files into a concrete syntax tree that can be inspected or transformed, then writes them back with byte-level fidelity — comments, whitespace, and formatting are preserved unchanged.

## Supported constructs

Validated against 579 `.unbound` files from the game's UI codebase:

- **Definitions**: `constant`, `element`, `css`, `macro`, `struct`
- **Scope & bindings**: `scope`, `var`, `event`, `bind`, `bindcall`, `sync`, `dispatch`
- **Display objects**: `sprite`, `tf`, `block`, `element`, `htile`, `vtile`
- **Controllers & styles**: `controller`, `style`, `filters`, `args`, `extends`
- **Value types**: numbers with units (`100px`, `50%`), hex literals (`0xFF0000`), multi-line strings, maps `{}`, lists `[]`, dot-path identifiers (`SC.path.Value`), function-call syntax

## Installation

```bash
pip install ub2parser
```

For local development:

```bash
pip install -e .
```

## Usage

```python
from ub2parser import tokenize, parse, serialize

with open('my_ui.unbound', 'r', encoding='utf-8') as f:
    source = f.read()

tokens = tokenize(source)        # lexical analysis
doc = parse(tokens)              # build CST

# traverse the tree
for d in doc.definitions:
    print(f"{d.def_kind} {d.name.name}")
    for child in d.body:
        print(f"  {type(child).__name__}")

# serialize — always byte-identical to the original
result = serialize(doc, tokens)
assert source == result
```

## CLI

```bash
# AST summary
python -m ub2parser parse file.unbound
python -m ub2parser parse file.unbound -v

# Validate one file or a directory tree
python -m ub2parser validate file.unbound
python -m ub2parser validate --all examples/

# Verify round-trip fidelity
python -m ub2parser roundtrip file.unbound

# Inspect token stream
python -m ub2parser tokens file.unbound
```

## Architecture

The processing pipeline has three stages:

1. **Tokenizer** — converts source text into a flat token stream. Every byte is accounted for: structural tokens, value literals, whitespace, newlines, and comments are all retained.
2. **Parser** — a recursive-descent parser that builds a concrete syntax tree (CST). Each node records its start and end positions within the token stream.
3. **Serializer** — walks the CST and replays the original tokens in document order, producing output that is byte-for-byte identical to the input.

## AST node reference

Every top-level definition becomes a `DefNode` with a `def_kind` field (`"constant"`, `"element"`, `"css"`, `"macro"`, or `"struct"`), a `name`, and a `body` list.

Specialized node types produced by the parser:

| Node | Syntax |
|------|--------|
| `Property` | `(width = 100px)` |
| `ScopeNode` | `(scope ...)` |
| `VarDecl` | `(var name:type = expr)` |
| `EventDecl` | `(event name)` |
| `BindNode` | `(bind target "source")` |
| `BindCallNode` | `(bindcall method ...)` |
| `DispatchNode` | `(dispatch event ...)` |
| `MacroCallNode` | `(macro Name ...)` |
| `DOMethod` | `(block ...)`, `(tf ...)`, `(sprite ...)` |
| `StyleNode` | `(style ...)` |
| `ControllerNode` | `(controller $Name ...)` |

All nodes carry `token_start` and `token_end` indices into the token list, which enables the serializer to reproduce the exact source text.

## License

LGPL-3.0-only — see [LICENSE](LICENSE).

## References

- [Unbound 2 documentation](https://forum.korabli.su/topic/127231-ub2-%D0%B4%D0%BE%D0%BA%D1%83%D0%BC%D0%B5%D0%BD%D1%82%D0%B0%D1%86%D0%B8%D1%8F-%D0%BF%D0%BE-unbound-20/) (Korabley Forum, Russian)
- [Unbound 2 macros](https://forum.korabli.su/topic/170024-ub2-%D0%BC%D0%B0%D0%BA%D1%80%D0%BE%D1%81%D1%8B/)
