"""The reminder scheduler as its own process: python -m app.scheduler_main

In the Docker stack the API copies run with SCHEDULER=off and this service sends the reminders. You can run two of
these for failover: they elect one leader through a Redis lease (see reminder_service), so a dose is still sent once.
"""
from __future__ import annotations

import os
import signal
import threading
import time
from pathlib import Path

os.environ["SCHEDULER"] = "on"

from sqlalchemy import text  # noqa: E402

from . import reminder_service  # noqa: E402
from .database import engine  # noqa: E402

ALIVE = Path("/tmp/scheduler-alive")
stop = threading.Event()


def _wait_for_db() -> None:
    for _ in range(60):
        try:
            with engine.connect() as c:
                c.execute(text("select 1"))
            return
        except Exception as e:
            print(f"[scheduler] waiting for the database ({type(e).__name__})")
            time.sleep(2)


def main() -> None:
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    _wait_for_db()
    reminder_service.start()
    while not stop.wait(10):
        ALIVE.write_text(str(time.time()))  # the container healthcheck reads this
    reminder_service.stop()
    print("[scheduler] stopped")


if __name__ == "__main__":
    main()
