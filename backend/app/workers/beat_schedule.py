"""Celery beat helpers: interval schedules with a one-time startup offset."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from celery.schedules import schedule, schedstate


class OffsetInterval(schedule):
    """Interval schedule that waits `initial_delay` after beat process start.

    Prevents probe + sync + reconcile from all opening the ZK terminal in the same
    second when PersistentScheduler reloads overdue entries after a restart.
    """

    def __init__(
        self,
        run_every: float | timedelta,
        *,
        initial_delay: float = 0.0,
        relative: bool = False,
        nowfun=None,
    ) -> None:
        super().__init__(run_every=run_every, relative=relative, nowfun=nowfun)
        self.initial_delay = float(initial_delay)
        self._boot = time.monotonic()

    def is_due(self, last_run_at: datetime | None = None):  # type: ignore[override]
        if self.initial_delay > 0:
            remaining = self.initial_delay - (time.monotonic() - self._boot)
            if remaining > 0:
                return schedstate(False, remaining)
        if last_run_at is None:
            last_run_at = self.now()
        return super().is_due(last_run_at)

    def __reduce__(self):  # type: ignore[no-untyped-def]
        return (
            self.__class__,
            (self.run_every,),
            {
                "initial_delay": self.initial_delay,
                "relative": self.relative,
                "nowfun": self.nowfun,
            },
        )

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        # Fresh beat process: re-apply startup stagger from this boot.
        self._boot = time.monotonic()
