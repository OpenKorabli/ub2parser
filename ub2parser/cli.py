#!/usr/bin/env python3
"""
Unbound 2 CLI — parse, validate, and convert .unbound files.

Usage:
    python -m unbound.cli parse <file.unbound>      Parse and print AST summary
    python -m unbound.cli validate <file.unbound>   Check if file parses correctly
    python -m unbound.cli validate --all <dir>       Validate all .unbound files in dir
    python -m unbound.cli roundtrip <file.unbound>   Test round-trip fidelity
    python -m unbound.cli tokens <file.unbound>      Show token stream
"""

import argparse
import os
import sys

from ub2parser import tokenize, parse, serialize


def cmd_parse(args):
    """Parse a file and print AST summary."""
    with open(args.file, 'r', encoding='utf-8') as f:
        source = f.read()

    tokens = tokenize(source)
    doc = parse(tokens)

    print(f"File: {args.file}")
    print(f"Size: {len(source)} bytes, {len(tokens)} tokens")
    print(f"Top-level definitions: {len(doc.definitions)}")
    print()

    # Count by kind
    kinds = {}
    for d in doc.definitions:
        kinds[d.def_kind] = kinds.get(d.def_kind, 0) + 1

    print("By kind:")
    for kind, count in sorted(kinds.items()):
        print(f"  {kind}: {count}")

    if args.verbose:
        print()
        for i, d in enumerate(doc.definitions):
            name = d.name.name if d.name else "?"
            params = ", ".join(
                f"{p.name.name if p.name else '?'}:{p.type_ident.name if p.type_ident else '?'}"
                for p in d.params
            )
            body_info = f", body={len(d.body)} items" if d.body else ""
            print(f"  [{i}] {d.def_kind} {name}({params}){body_info}")


def cmd_validate(args):
    """Validate .unbound file(s)."""
    if args.all:
        # Walk directory
        all_files = []
        for root, dirs, files in os.walk(args.path):
            for f in files:
                if f.endswith('.unbound'):
                    all_files.append(os.path.join(root, f))

        print(f"Validating {len(all_files)} files...")
        failed = []
        for fpath in all_files:
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    source = f.read()
                tokens = tokenize(source)
                doc = parse(tokens)
                result = serialize(doc, tokens)
                if source != result:
                    failed.append((fpath, "round-trip mismatch"))
            except Exception as e:
                failed.append((fpath, str(e)))

        if failed:
            print(f"FAILED: {len(failed)}/{len(all_files)}")
            for fpath, err in failed:
                print(f"  {fpath}: {err}")
            sys.exit(1)
        else:
            print(f"OK: {len(all_files)} files valid")
    else:
        with open(args.file, 'r', encoding='utf-8') as f:
            source = f.read()
        try:
            tokens = tokenize(source)
            doc = parse(tokens)
            result = serialize(doc, tokens)
            if source == result:
                print(f"OK: {args.file} — {len(doc.definitions)} definitions, round-trip clean")
            else:
                print(f"FAIL: {args.file} — round-trip mismatch")
                sys.exit(1)
        except Exception as e:
            print(f"FAIL: {args.file} — {e}")
            sys.exit(1)


def cmd_roundtrip(args):
    """Test round-trip: parse then serialize, compare to source."""
    with open(args.file, 'r', encoding='utf-8') as f:
        source = f.read()

    tokens = tokenize(source)
    doc = parse(tokens)
    result = serialize(doc, tokens)

    if source == result:
        print(f"OK: {args.file} — round-trip matches exactly")
    else:
        print(f"FAIL: {args.file} — round-trip differs")
        for i, (a, b) in enumerate(zip(source, result)):
            if a != b:
                ctx = 30
                print(f"  First difference at byte {i}:")
                print(f"    expected: {source[max(0,i-ctx):i+ctx]!r}")
                print(f"    got:      {result[max(0,i-ctx):i+ctx]!r}")
                break
        sys.exit(1)


def cmd_tokens(args):
    """Print the token stream for a file."""
    with open(args.file, 'r', encoding='utf-8') as f:
        source = f.read()

    tokens = tokenize(source)

    for t in tokens:
        if args.compact and t.type.name in ('WHITESPACE', 'NEWLINE'):
            continue
        print(f"L{t.line:4d}:{t.col:<4d} {t.type.name:<12s} {t.text!r}")


def main():
    parser = argparse.ArgumentParser(
        description="Unbound 2 parser CLI — parse, validate, and inspect .unbound files"
    )
    sub = parser.add_subparsers(dest='command', help='Commands')

    # parse
    p = sub.add_parser('parse', help='Parse and show AST summary')
    p.add_argument('file', help='.unbound file to parse')
    p.add_argument('-v', '--verbose', action='store_true', help='Show all definitions')
    p.set_defaults(func=cmd_parse)

    # validate
    v = sub.add_parser('validate', help='Validate .unbound file(s)')
    v.add_argument('file', nargs='?', help='.unbound file to validate')
    v.add_argument('--all', action='store_true', help='Validate all .unbound files under path')
    v.add_argument('--path', default='.', help='Root path for --all (default: .)')
    v.set_defaults(func=cmd_validate)

    # roundtrip
    r = sub.add_parser('roundtrip', help='Test round-trip fidelity')
    r.add_argument('file', help='.unbound file to test')
    r.set_defaults(func=cmd_roundtrip)

    # tokens
    t = sub.add_parser('tokens', help='Show token stream')
    t.add_argument('file', help='.unbound file to tokenize')
    t.add_argument('-c', '--compact', action='store_true', help='Omit whitespace/newline tokens')
    t.set_defaults(func=cmd_tokens)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == '__main__':
    main()
