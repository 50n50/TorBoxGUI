"""Main entry point for TorBox GUI & CLI."""

import argparse
import sys


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="TorBox GUI and fast CLI download generator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                      Launch GUI
  python main.py "magnet:?xt=urn:btih:..."            Quick CLI generation
  python main.py file.torrent -d                      CLI download to disk
  python main.py "https://example.com/file" --wait    Wait if uncached
  python main.py "magnet:?xt=..." --gui               Open in GUI prefilled
        """,
    )

    parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help="Magnet URI, .torrent file path, web debrid URL, or NZB file/link",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Force open graphical user interface (prefills source if provided)",
    )
    parser.add_argument(
        "--zip",
        action="store_true",
        default=True,
        help="Request multi-file torrent as a ZIP archive (default: True)",
    )
    parser.add_argument(
        "--no-zip",
        action="store_false",
        dest="zip",
        help="Do not request as ZIP archive",
    )
    parser.add_argument(
        "-d",
        "--download",
        action="store_true",
        help="Automatically download file to local disk",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Custom destination directory or filename for download",
    )
    parser.add_argument(
        "-c",
        "--copy",
        action="store_true",
        help="Copy direct CDN download link to clipboard",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open generated download link in default browser",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait and poll if item is not yet cached on TorBox",
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="Configure or update TorBox API token via command-line",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Display TorBox account plan and download statistics",
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    # If --gui is specified, or no arguments were provided at all, launch GUI
    if args.gui or (not args.source and not args.config and not args.info):
        from gui.app import TorBoxApp

        app = TorBoxApp(prefill_source=args.source)
        app.mainloop()
    else:
        from cli.runner import run_cli

        run_cli(args)


if __name__ == "__main__":
    main()
