from __future__ import annotations

import argparse
import asyncio
import sys

from tg_spam.config import load_config
from tg_spam.sender import configure_logging, run_broadcast


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send a Telegram message to chats from YAML using a userbot."
    )
    parser.add_argument(
        "-c",
        "--config",
        default="broadcast.yml",
        help="Path to YAML config. Default: broadcast.yml",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        configure_logging(config.logging.level, config.logging.file)
        results = asyncio.run(run_broadcast(config))
    except Exception as exc:  # noqa: BLE001
        print(f"fatal: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    for result in results:
        print(f"[{result.status}] {result.target} -> {result.details}")


if __name__ == "__main__":
    main()
