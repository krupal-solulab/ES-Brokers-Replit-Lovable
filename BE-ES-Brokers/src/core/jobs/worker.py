"""Arq worker settings for production.

Run with:  arq core.jobs.worker.WorkerSettings   (requires a running Redis at REDIS_URL)

Redis unavailable at startup: arq retries the connection with exponential back-off
automatically; the FastAPI process is unaffected (monitors degrade to on-demand /run).
"""

from __future__ import annotations

import logging

from arq.connections import RedisSettings

from core.config import get_settings
from core.jobs.monitor import _cron_to_arq_kwargs, run_scheduled_monitors
from core.jobs.service import ingest_and_extract
import verticals.es.monitors  # noqa: F401 — side-effect: registers E&S ScheduledMonitors

_log = logging.getLogger(__name__)


def _build_cron_jobs() -> list:
    """Build the arq cron list from MONITOR_CRON_DEFAULT (or the config default).

    Returns an empty list on parse failure so the worker still starts without
    crashing — monitors fall back to on-demand /run only.
    """
    try:
        from arq import cron as arq_cron  # local import — arq optional at API runtime

        settings = get_settings()
        kwargs = _cron_to_arq_kwargs(settings.monitor_cron_default)
        _log.debug("monitor cron kwargs from %r: %s", settings.monitor_cron_default, kwargs)
        return [arq_cron(run_scheduled_monitors, **kwargs)]
    except Exception as exc:
        _log.warning("could not build cron_jobs list: %s — monitors run on-demand only", exc)
        return []


class WorkerSettings:
    """Arq entrypoint. ``functions`` are the tasks the worker can run on demand;
    ``cron_jobs`` drive the scheduled-monitor loop."""

    functions = [ingest_and_extract, run_scheduled_monitors]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    cron_jobs = _build_cron_jobs()
