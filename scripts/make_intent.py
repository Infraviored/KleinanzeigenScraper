#!/usr/bin/env python3
"""Generates a starter intent profile from a category playbook.

A playbook says what is extractable; an intent says what a buyer wants. This
prints an editable skeleton of the second from the first, so nobody has to write
field ids by hand or guess which types accept which `buyer_wants` keys.

    python scripts/make_intent.py --list
    python scripts/make_intent.py electronics/laptops
    python scripts/make_intent.py electronics/laptops --write-knowledge-set 1

Nothing is written to the database unless --write-knowledge-set is given, and the
generated weights are deliberately neutral: they are a starting point to edit,
not a recommendation.
"""

import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scraper"
    ),
)

import playbooks  # noqa: E402

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "scraper.db"
)


def starter_wants(field):
    """A neutral `buyer_wants` stub appropriate to the field's type."""
    ftype = field.get("type", "boolean")
    if ftype == "boolean":
        return {"match": True}
    if ftype == "number":
        return {"min": None, "max": None}
    if ftype == "tier":
        return {"min": 3}
    if ftype == "enum":
        options = list(field.get("options") or [])
        return {"preferred": options[:1], "excluded": options[-1:] if options else []}
    return {"present": True}


def build_intent(playbook, include_all=False):
    fields = []
    for field in playbooks.extraction_fields(playbook):
        # Free-text fields rarely make good scoring criteria; they are extracted
        # for display rather than for judgement.
        if not include_all and field.get("type") == "text":
            continue
        fields.append(
            {
                "id": field["id"],
                "_label": field.get("label", field["id"]),
                "_type": field.get("type"),
                "importance": "medium",
                "buyer_wants": starter_wants(field),
            }
        )
    return {
        "fields": fields,
        "dimensions_enabled": True,
        "dimensions_weight": 0.3,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "playbook", nargs="?", help="playbook key, e.g. electronics/laptops"
    )
    parser.add_argument("--list", action="store_true", help="list available playbooks")
    parser.add_argument("--all-fields", action="store_true", help="include text fields")
    parser.add_argument(
        "--write-knowledge-set",
        type=int,
        metavar="ID",
        help="write the profile into this knowledge set's item_json",
    )
    args = parser.parse_args()

    if args.list or not args.playbook:
        print("Verfuegbare Playbooks:\n")
        for key, playbook in sorted(playbooks.all_playbooks().items()):
            scoreable = len([f for f in playbook["fields"] if f.get("type") != "text"])
            print(
                f"  {key:28s} v{playbook['version']}  "
                f"{len(playbook['fields']):2d} Felder ({scoreable} bewertbar)  "
                f"{playbook['label']}"
            )
        return 0

    playbook = playbooks.get_playbook(args.playbook)
    if playbook is None:
        print(f"Unbekanntes Playbook: {args.playbook}", file=sys.stderr)
        print("Mit --list die verfuegbaren anzeigen.", file=sys.stderr)
        return 1

    intent = build_intent(playbook, include_all=args.all_fields)
    rendered = json.dumps(intent, indent=2, ensure_ascii=False)

    if args.write_knowledge_set is None:
        print(rendered)
        print(
            f"\n// {len(intent['fields'])} bewertbare Felder aus {playbook['key']} "
            f"v{playbook['version']}.\n"
            "// importance und buyer_wants anpassen, dann mit "
            "--write-knowledge-set <ID> speichern.\n"
            "// Die _label/_type-Felder sind nur Lesehilfe und werden ignoriert.",
            file=sys.stderr,
        )
        return 0

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT name FROM knowledge_sets WHERE id = ?", (args.write_knowledge_set,)
    ).fetchone()
    if row is None:
        print(
            f"Knowledge-Set {args.write_knowledge_set} existiert nicht.",
            file=sys.stderr,
        )
        return 1

    conn.execute(
        "UPDATE knowledge_sets SET item_json = ? WHERE id = ?",
        (json.dumps(intent, ensure_ascii=False), args.write_knowledge_set),
    )
    conn.commit()
    print(
        f"Knowledge-Set {args.write_knowledge_set} ({row[0]}) auf "
        f"{len(intent['fields'])} Felder aus {playbook['key']} gesetzt."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
