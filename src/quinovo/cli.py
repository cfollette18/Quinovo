from __future__ import annotations

import argparse
import logging
import logging.config
import os
from pathlib import Path

import uvicorn

from quinovo.api.app import create_app
from quinovo.kernel import TrainError, open_kernel
from quinovo.llm.tracing import load_langfuse_env
from quinovo.mcp.server import run_stdio
from quinovo.pack.create import PackCreateError, create_pack_from_yaml
from quinovo.pack.init import init_pack
from quinovo.workspace import DEFAULT_DB, DEFAULT_PACK, resolve_serve_paths


def configure_logging() -> None:
    """Stdlib logging for all quinovo commands. QUINOVO_LOG_LEVEL overrides."""
    level = os.environ.get("QUINOVO_LOG_LEVEL", "INFO").upper()
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                },
            },
            "root": {"level": level, "handlers": ["console"]},
        }
    )


def main() -> None:
    load_langfuse_env()
    configure_logging()
    parser = argparse.ArgumentParser(prog="quinovo")
    sub = parser.add_subparsers(dest="cmd", required=True)

    mcp = sub.add_parser("mcp", help="run Quinovo as an MCP server (stdio)")
    mcp.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    mcp.add_argument("--db", type=Path, default=DEFAULT_DB)

    serve = sub.add_parser("serve", help="workspace: graph, catalog, inference, audit, train")
    serve.add_argument("--pack", type=Path, default=None)
    serve.add_argument("--db", type=Path, default=None)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8791)

    init = sub.add_parser("init", help="copy a starter pack (world)")
    init.add_argument("dest", type=Path)
    init.add_argument("--from", dest="starter", default="world")

    propose = sub.add_parser("propose", help="propose object types from files (HITL below 80%%)")
    propose.add_argument("root", type=Path)
    propose.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    propose.add_argument("--db", type=Path, default=DEFAULT_DB)
    propose.add_argument("--confidence", type=float, default=0.5)

    create = sub.add_parser("create", help="scaffold a new pack from a YAML spec")
    create.add_argument("dest", type=Path)
    create.add_argument("--from-spec", dest="spec", type=Path, required=True)

    tick = sub.add_parser("tick", help="one autonomous pass; print pending HITL")
    tick.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    tick.add_argument("--db", type=Path, default=DEFAULT_DB)
    tick.add_argument("--actor", default="autonomous")

    train = sub.add_parser("train", help="save a filtered set and prepare a small specialist job")
    train.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    train.add_argument("--db", type=Path, default=DEFAULT_DB)
    train.add_argument("--name", default="Specialist set")
    train.add_argument("--job-name", dest="job_name", default="")
    train.add_argument("--kinds", default="things,connections,noticed,changed")
    train.add_argument("--types", default="")
    train.add_argument("--status", default="all")
    train.add_argument("--q", default="")
    train.add_argument("--since", default="")
    train.add_argument("--until", default="")
    train.add_argument("--include-fields", dest="include_fields", default="")
    train.add_argument("--exclude-fields", dest="exclude_fields", default="")
    train.add_argument("--only-approved", dest="only_approved", action="store_true")
    train.add_argument("--size", default="small", choices=("tiny", "small", "medium"))

    args = parser.parse_args()
    match args.cmd:
        case "mcp":
            run_stdio(open_kernel(args.pack, args.db))
        case "serve":
            pack, db = resolve_serve_paths(args.pack, args.db)
            uvicorn.run(
                create_app(pack_dir=pack, db_path=db),
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
        case "create":
            try:
                path = create_pack_from_yaml(args.dest, args.spec)
            except PackCreateError as exc:
                raise SystemExit(f"create: {exc}")
            print(path)
        case "tick":
            kernel = open_kernel(args.pack, args.db)
            result = kernel.tick(args.actor)
            pending = result.get("pending_proposals") or []
            print(
                f"proposed={len(result.get('proposed') or [])} "
                f"pending_proposals={len(pending)} "
                f"pending_facts={len(result.get('pending_facts') or [])} "
                f"applied={len(result.get('applied') or [])}"
            )
            for item in pending:
                payload = item.get("payload") or {}
                print(
                    f"  proposal {item['id']}  {item['kind']}  "
                    f"{payload.get('api_name', '')}  conf={item['confidence']}"
                )
        case "train":
            kernel = open_kernel(args.pack, args.db)
            try:
                filters = kernel.train_filters(
                    kinds=args.kinds,
                    types=args.types,
                    status=args.status,
                    q=args.q,
                    since=args.since,
                    until=args.until,
                    include_fields=args.include_fields,
                    exclude_fields=args.exclude_fields,
                    only_approved=args.only_approved,
                )
                dataset = kernel.save_train_dataset(args.name, filters)
                job = kernel.create_train_job(
                    args.job_name or f"{args.name} specialist",
                    dataset["id"],
                    args.size,
                )
            except TrainError as exc:
                raise SystemExit(f"train: {exc}") from exc
            root = kernel.train_root()
            print(
                f"dataset={dataset['id']} items={dataset['record_count']} "
                f"job={job['id']} status={job['status']} "
                f"jsonl={root / job['jsonl_path']}"
            )
        case _ as unreachable:
            raise AssertionError(f"unhandled command {unreachable}")


if __name__ == "__main__":
    main()
