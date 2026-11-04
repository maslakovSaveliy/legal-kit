#!/usr/bin/env python3
"""Read the requirement cards of the pack from cards.tar.gz. Python 3.9+, standard library only.

  kb.py card <ru:slug>... [--section <title>]  print cards (or one "## " section of each) as Markdown;
                                               with several ids each one follows a line "==> ru:<slug> <=="
  kb.py search <text> [--max N]              JSON list of {id, line, text}: case-insensitive substring
  kb.py list                                 JSON list of {id, card}
  kb.py extract --to <dir>                   write <dir>/cards/<slug>.md for every card

A link `<slug>.md` inside a card names the card ru:<slug>. Without python3 the same card is printed by
`tar -xzOf cards.tar.gz cards/<slug>.md` run in the pack folder. Exit codes: 0 ok, 2 bad input.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _kb  # noqa: E402  (must come first: it protects the stdlib `select` module)

import argparse  # noqa: E402


def build_parser():
    parser = argparse.ArgumentParser(prog="kb.py", description="Read requirement cards from the pack's cards.tar.gz.")
    sub = parser.add_subparsers(dest="command", required=True)
    card = sub.add_parser("card", help="print cards as Markdown")
    card.add_argument("ref", nargs="+", help="ru:<slug>, <slug> or cards/<slug>.md; several ids print in turn")
    card.add_argument("--section", help='print only the "## <title>" section')
    search = sub.add_parser("search", help="find a text in all cards (JSON)")
    search.add_argument("text")
    search.add_argument("--max", type=int, default=50, help="most hits to print (default 50)")
    sub.add_parser("list", help="list the cards (JSON)")
    extract = sub.add_parser("extract", help="write every card into <dir>/cards/")
    extract.add_argument("--to", required=True, help="target directory")
    for command in sub.choices.values():
        command.add_argument("--kb", default=_kb.DEFAULT_KB, help="jurisdiction pack directory (default: bundled ru)")
    return parser


def card_text(cards, ref):
    key = _kb.card_ref(ref)
    if key not in cards:
        raise _kb.KbError("no card %s; try: kb.py search <words>" % key)
    return cards[key]


def section(text, title):
    lines, found, out = text.split("\n"), [], None
    for line in lines:
        if line.startswith("## "):
            found.append(line[3:].strip())
            if out is not None:
                break
            if line[3:].strip() == title:
                out = [line]
                continue
        if out is not None:
            out.append(line)
    if out is None:
        raise _kb.KbError("no section %r; sections: %s" % (title, ", ".join(found)))
    return "\n".join(out).rstrip("\n") + "\n\n"


def search(cards, text, limit):
    needle, hits = text.casefold(), []
    for key, body in cards.items():
        for number, line in enumerate(body.split("\n"), 1):
            if needle in line.casefold():
                hits.append({"id": key, "line": number, "text": line.strip()})
                if len(hits) >= limit:
                    return hits
    return hits


def extract(cards, target):
    folder = os.path.join(target, "cards")
    os.makedirs(folder, exist_ok=True)
    for key, body in cards.items():
        with open(os.path.join(folder, key[3:] + ".md"), "w", encoding="utf-8", newline="") as handle:
            handle.write(body)
    return {"extracted": len(cards), "dir": target}


def main(argv=None):
    args, code = _kb.parse_args(build_parser(), sys.argv[1:] if argv is None else argv)
    if args is None:
        return code
    try:
        cards = _kb.load_cards(args.kb)
        if args.command == "card":
            parts = []
            for ref in args.ref:
                text = card_text(cards, ref)
                parts.append((_kb.card_ref(ref), section(text, args.section) if args.section else text))
            if len(parts) == 1:
                sys.stdout.write(parts[0][1])
            else:
                sys.stdout.write("\n".join("==> %s <==\n%s" % part for part in parts))
            return 0
        if args.command == "search":
            if args.max < 1:
                raise _kb.KbError("--max must be at least 1")
            result = search(cards, args.text, args.max)
        elif args.command == "list":
            result = [{"id": key, "card": "cards/%s.md" % key[3:]} for key in cards]
        else:
            result = extract(cards, args.to)
    except _kb.KbError as exc:
        return _kb.fail(str(exc))
    _kb.emit(result)
    return 0


if __name__ == "__main__":
    _kb.setup_stdio()
    sys.exit(main())
