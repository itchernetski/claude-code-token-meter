from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from . import __version__
from .server import create_app

DEFAULT_PORT = 3378
DEFAULT_HOST = "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="claude-code-token-meter",
        description="Local viewer for Claude Code token usage.",
    )
    parser.add_argument("--host", default=os.getenv("HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", DEFAULT_PORT)),
    )
    parser.add_argument(
        "--projects-dir",
        type=Path,
        default=None,
        help="Override path to ~/.claude/projects (for testing).",
    )
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args()

    app = create_app(projects_dir=args.projects_dir)
    print(
        f"claude-code-token-meter v{__version__} → http://{args.host}:{args.port}"
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
