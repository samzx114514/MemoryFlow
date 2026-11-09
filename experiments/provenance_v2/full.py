"""Build and query MemoryFlow's reusable per-call matrices."""

from __future__ import annotations

import argparse
from pathlib import Path

from .full_batch import replay_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    replay = commands.add_parser("replay", help="materialize every call matrix in one episode")
    replay.add_argument("--run", type=Path, required=True)
    replay.add_argument("--out", type=Path, required=True)
    replay.add_argument("--model-dir", type=Path, required=True)
    replay.add_argument("--user-id")
    replay.add_argument("--gpu", type=int, required=True)
    replay.add_argument("--memory-cap-gib", type=float, default=24.0)
    replay.add_argument("--layer", type=int, default=19)
    replay.add_argument("--head", type=int, default=15)
    replay.set_defaults(func=replay_run)
    from .full_batch import write_json
    from .full_forest import build_run
    from .full_query import FullQuery, target_span

    build = commands.add_parser("build", help="build the context forest and exact content links")
    build.add_argument("--run", type=Path, required=True)
    build.add_argument("--matrix-dir", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)

    query = commands.add_parser("query", help="query a recorded output using saved matrices")
    query.add_argument("--forest", type=Path, required=True)
    query.add_argument("--matrix-dir", type=Path, required=True)
    query.add_argument("--call", required=True)
    target = query.add_mutually_exclusive_group(required=True)
    target.add_argument("--text")
    target.add_argument("--span", nargs=2, type=int, metavar=("START", "END"))
    query.add_argument("--occurrence", type=int)
    query.add_argument("--top-k", type=int, default=5)
    query.add_argument("--depth", type=int, default=4)
    query.add_argument("--out", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "build":
        build_run(args.run, args.matrix_dir, args.out)
        return
    if args.command == "query":
        engine = FullQuery(args.forest, args.matrix_dir, args.top_k, args.depth)
        span = tuple(args.span) if args.span else target_span(engine.load(args.call)[0]["output"], args.text, args.occurrence)
        write_json(args.out, engine.walk(args.call, span))
        return
    args.func(args)


if __name__ == "__main__":
    main()
