"""Entry point: python -m jumpscare [--config path]"""

import argparse
import logging
import signal
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from jumpscare.app import OverlayApp
from jumpscare.config import DEFAULT_CONFIG_PATH, PROJECT_ROOT, ConfigError, load_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Random jumpscare overlay for Valorant")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()

    handlers: list[logging.Handler] = [logging.FileHandler(PROJECT_ROOT / "overlay.log", encoding="utf-8")]
    if sys.stderr is not None:  # pythonw has no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        logging.error("Config error: %s", exc)
        return 1

    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)  # the overlay hides itself; that must not exit the app

    overlay_app = OverlayApp(qt_app, cfg)
    signal.signal(signal.SIGINT, lambda *_: overlay_app.quit())
    # Qt's event loop blocks Python signal handling; waking it periodically lets Ctrl+C work.
    wakeup = QTimer()
    wakeup.timeout.connect(lambda: None)
    wakeup.start(250)
    overlay_app.start()
    return qt_app.exec()


if __name__ == "__main__":
    sys.exit(main())
