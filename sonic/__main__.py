from __future__ import annotations

import sys

from sonic.cli import eval_main, route_main


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in {"route", "eval"}:
        cmd = sys.argv[1]
        rest = sys.argv[2:]
        raise SystemExit(route_main(rest) if cmd == "route" else eval_main(rest))
    raise SystemExit(route_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
