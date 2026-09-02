from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from quinovo.api.app import create_app
from quinovo.initpack import init_pack
from quinovo.kernel import open_kernel
from quinovo.mcp.server import run_stdio
from quinovo.paths import DEFAULT_DB, EXAMPLE_PACK


def main() -> None:
    parser = argparse.ArgumentParser(prog="quinovo")
    sub = parser.add_subparsers(dest="cmd", required=True)

    mcp = sub.add_parser("mcp", help="run Quinovo as an MCP server (stdio)")
    mcp.add_argument("--pack", type=Path, default=EXAMPLE_PACK)
    mcp.add_argument("--db", type=Path, default=DEFAULT_DB)

    serve = sub.add_parser("serve", help="debug HTTP API (not the product surface)")
    serve.add_argument("--pack", type=Path, default=EXAMPLE_PACK)
    serve.add_argument("--db", type=Path, default=DEFAULT_DB)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8791)

    init = sub.add_parser("init", help="copy a starter pack (example or clinic)")
    init.add_argument("dest", type=Path)
    init.add_argument("--from", dest="starter", default="example")

    propose = sub.add_parser("propose", help="propose object types from files (HITL below 80%)")
    propose.add_argument("root", type=Path)
    propose.add_argument("--pack", type=Path, default=EXAMPLE_PACK)
    propose.add_argument("--db", type=Path, default=DEFAULT_DB)
    propose.add_argument("--confidence", type=float, default=0.5)

    args = parser.parse_args()
    match args.cmd:
        case "mcp":
            run_stdio(open_kernel(args.pack, args.db))
        case "serve":
            uvicorn.run(
                create_app(pack_dir=args.pack, db_path=args.db),
                host=args.host,
                port=args.port,
            )
        case "init":
            path = init_pack(args.dest, args.starter)
            print(path)
        case "propose":
            kernel = open_kernel(args.pack, args.db)
            proposals = kernel.propose_types(args.root, args.confidence)
            print(f"{len(proposals)} proposals")
        case _ as unreachable:
            raise AssertionError(f"unhandled command {unreachable}")
