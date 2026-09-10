"""Background operational loop. Ticks on an interval and when the index changes."""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class Autonomy:
    def __init__(self, kernel: Any, interval: float = 2.0) -> None:
        self.kernel = kernel
        self.interval = interval
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._thread = threading.Thread(
            target=self._run,
            name="quinovo-autonomy",
            daemon=True,
        )

    def start(self) -> None:
        if self._thread.is_alive():
            return
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=5.0)

    def nudge(self) -> None:
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self.interval)
            if self._stop.is_set():
                break
            self._wake.clear()
            self._tick()

    def _tick(self) -> None:
        with self._lock:
            try:
                result = self.kernel.tick("autonomous", wait_for_quiet=True)
            except Exception as exc:  # noqa: BLE001 — loop must not die
                logger.warning("autonomy tick failed: %s", exc)
                self.kernel._last_tick = {"errors": [{"error": str(exc)}]}
                return
            self.kernel._last_tick = result


def start_autonomy(kernel: Any, interval: float = 2.0) -> Autonomy:
    existing = getattr(kernel, "_autonomy", None)
    if existing is not None and existing._thread.is_alive():
        return existing
    loop = Autonomy(kernel, interval)
    kernel._autonomy = loop
    loop.start()
    return loop


def nudge(kernel: Any) -> None:
    loop = getattr(kernel, "_autonomy", None)
    if loop is not None:
        loop.nudge()
