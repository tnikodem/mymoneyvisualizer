# -*- coding: utf-8 -*-
"""
    mymoneyvisualizer.cli
    ~~~~~~~~~
    A simple tool to visualize your incomes and expenses.
"""

import sys
import logging

from PyQt6.QtWidgets import QApplication

from mymoneyvisualizer.configuration import Configuration

from mymoneyvisualizer.windows.window_main import WindowMain

logger = logging.getLogger(__name__)


def main():
    # configure logging
    logging_level = logging.ERROR
    if len(sys.argv) > 1 and sys.argv[1] == "--debug":  # TODO use click(?) if more convenient cli preferrable
            logging_level = logging.DEBUG
    logging.basicConfig(level=logging_level,
                        format="%(asctime)s %(levelname)-7s %(module)s: %(message)s",
                        datefmt="%y-%m-%d %H:%M:%S")

    logger.info("Starting MyMoneyVisualizer")
    config = Configuration(dir_path="./config")
    app = QApplication(sys.argv)
    ex = WindowMain(config=config)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
