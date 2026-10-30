"""Command line entry point ``mmv``."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from mymoneyvisualizer import __version__
from mymoneyvisualizer.storage.paths import ENV_VAR, resolve_data_dir

logger = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mmv", description="Where did all my money go? Visualize your finances.")
    parser.add_argument("--data-dir", help=f"directory with your data (default: ${ENV_VAR} or the user data dir)")
    parser.add_argument("--debug", action="store_true", help="print debug logs")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%y-%m-%d %H:%M:%S",
    )
    # Qt is imported here so that ``mmv --help`` works without a display
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from mymoneyvisualizer.app import AppModel
    from mymoneyvisualizer.storage.files import StorageError
    from mymoneyvisualizer.ui.main_window import MainWindow
    from mymoneyvisualizer.ui.style import apply_style, use_german

    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_style(app)
    use_german(app)
    data_dir = resolve_data_dir(args.data_dir)
    logger.info("using data directory %s", data_dir)
    try:
        model = AppModel.open(data_dir)
    except StorageError as e:
        QMessageBox.critical(None, "MyMoneyVisualizer", f"Deine Daten lassen sich nicht laden:\n{e}")
        return 1
    window = MainWindow(model)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
