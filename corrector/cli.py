from __future__ import annotations

import argparse
import logging
import sys

from .pipeline import Corrector


def main() -> int:
    ap = argparse.ArgumentParser(description="Correct text from stdin via the PII gateway")
    ap.add_argument("--backend", choices=["local", "external"])
    ap.add_argument("--show-tokenized", action="store_true", help="print what would leave the device")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)

    from .config import Settings
    import dataclasses
    s = Settings.load()
    if args.backend:
        s = dataclasses.replace(s, backend=args.backend)

    text = sys.stdin.read()
    if args.show_tokenized:
        from .factory import build_gate
        with build_gate(s).session() as sess:
            print(sess.protect(text))
        return 0
    res = Corrector(s).correct(text)
    if not res.ok:
        print("Correction aborted:", "; ".join(res.problems), file=sys.stderr)
        return 2
    sys.stdout.write(res.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
