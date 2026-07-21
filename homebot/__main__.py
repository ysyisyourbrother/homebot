"""
Entry point for homebot: python -m homebot
"""

import argparse

from homebot import __logo__, __version__


def main():
    parser = argparse.ArgumentParser(
        prog="homebot",
        description=f"{__logo__} homebot - Personal AI Assistant (v{__version__})",
    )
    sub = parser.add_subparsers(dest="command", help="Commands")

    sub.add_parser("init", help="Initialize homebot for first use")
    sub.add_parser("config", help="Configure homebot settings")
    gateway_parser = sub.add_parser("gateway", help="Start homebot gateway")
    gateway_parser.add_argument("--port", "-p", type=int, help="Gateway port for this run")
    gateway_parser.add_argument("--config", "-c", help="Path to config file")
    gateway_parser.add_argument("--workspace", "-w", help="Workspace directory")
    gateway_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.set_defaults(port=None, config=None, workspace=None, verbose=False)

    args = parser.parse_args()

    if args.command == "init":
        from homebot.cli.init import run_init

        run_init()

    elif args.command == "config":
        from homebot.cli.config import run_config

        run_config()

    else:
        # Default: start gateway
        from homebot.cli.gateway import _load_runtime_config, run

        if args.verbose:
            import logging
            logging.basicConfig(level=logging.DEBUG)

        cfg = _load_runtime_config(args.config, args.workspace)
        run(cfg, port=args.port)


if __name__ == "__main__":
    main()
