#!/usr/bin/env python3
"""
Startup preflight: wait for PostgreSQL and Redis, and explain failures in plain language.

start-vm.js runs this before migrations so a database that is restarting does not kill
the whole stack, and a misconfigured one fails with an actionable message instead of a
200-line traceback.

Run from backend/:
  .venv/bin/python scripts/check_services.py             # single attempt
  .venv/bin/python scripts/check_services.py --wait 180  # keep retrying transient failures
Exit code 0 when every service is reachable, 1 otherwise.
"""

from __future__ import annotations

import argparse
import re
import socket
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import Settings, get_settings  # noqa: E402
from app.core.database import postgres_connect_args  # noqa: E402

_TAG = "[preflight]"


@dataclass
class CheckResult:
    ok: bool
    summary: str
    retryable: bool = True
    hints: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _say(message: str) -> None:
    print(f"{_TAG} {message}", flush=True)


def _first_line(exc: BaseException) -> str:
    text = str(exc).strip()
    return text.splitlines()[0].strip() if text else exc.__class__.__name__


def _mask_url(url: str) -> str:
    return re.sub(r"://([^:/@]*):[^@]*@", r"://\1:***@", url)


def _tcp_probe(host: str, port: int, *, label: str, timeout: float = 5.0) -> CheckResult | None:
    """Return a failure result when nothing answers on host:port, else None."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return None
    except socket.gaierror as exc:
        return CheckResult(
            ok=False,
            retryable=False,
            summary=f"{label}: cannot resolve host '{host}' ({_first_line(exc)})",
            hints=[f"Check the {label} host name/IP in backend/.env."],
        )
    except ConnectionRefusedError:
        return CheckResult(
            ok=False,
            summary=f"{label}: connection refused on {host}:{port} (nothing is listening there)",
            hints=[
                f"Make sure the {label} service is running on {host} and listening on port {port}.",
                "If it only listens on localhost, bind it to the LAN interface so this VM can reach it.",
            ],
        )
    except (TimeoutError, socket.timeout):
        return CheckResult(
            ok=False,
            summary=f"{label}: no answer from {host}:{port} within {timeout:.0f}s (host down or port blocked)",
            hints=[
                f"Check that {host} is powered on and reachable from this VM (ping {host}).",
                f"Open the port on {host}'s firewall, e.g. sudo firewall-cmd --permanent --add-port={port}/tcp && sudo firewall-cmd --reload",
            ],
        )
    except OSError as exc:
        return CheckResult(
            ok=False,
            summary=f"{label}: cannot reach {host}:{port} ({_first_line(exc)})",
            hints=[f"Check network routing between this VM and {host}."],
        )


# --------------------------------------------------------------------------- PostgreSQL

_PG_FATAL = (
    ("password authentication failed", "Wrong DB_USER / DB_PASSWORD in backend/.env."),
    ("no pg_hba.conf entry", "Allow this VM in pg_hba.conf on the database host, then reload PostgreSQL."),
    ("does not exist", "Create the database/role named in backend/.env (see scripts/setup_local_database.sql)."),
    ("certificate", "TLS certificate problem; set DB_SSLMODE to match the server (e.g. disable on a trusted LAN)."),
)

_PG_TRANSIENT = (
    "the database system is starting up",
    "the database system is in recovery mode",
    "the database system is shutting down",
    "not yet accepting connections",
)


def _pg_conninfo(url_text: str) -> str:
    url = make_url(url_text).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


def _pg_connect(conninfo: str, settings: Settings, **overrides: object):  # type: ignore[no-untyped-def]
    import psycopg

    kwargs = {**postgres_connect_args(settings), "application_name": "biometrica-preflight", **overrides}
    return psycopg.connect(conninfo, autocommit=True, **kwargs)


def _closed_unexpectedly_hints(host: str, port: int) -> list[str]:
    return [
        f"The TCP port answers but the server hung up during the PostgreSQL handshake. On {host} check:",
        "  sudo systemctl status 'postgresql*'   and   sudo journalctl -u 'postgresql*' -n 100 --no-pager",
        f"  sudo ss -ltnp | grep :{port}          (is PostgreSQL itself on this port, or a proxy/tunnel/docker forward?)",
        "  docker ps -a                           (if PostgreSQL runs in a container: is it restarting/unhealthy?)",
        "Common causes: PostgreSQL crashed or is restarting (disk full, out of memory), a port-forward/pgbouncer "
        "whose backend is down, or max_connections exhausted at a pooler.",
    ]


def check_database(settings: Settings) -> CheckResult:
    url_text = str(settings.database_url)
    if url_text.startswith("sqlite"):
        return CheckResult(ok=True, summary="database: SQLite configured (skipped)")
    url = make_url(url_text)
    host = url.host or "localhost"
    port = int(url.port or 5432)
    target = f"{host}:{port}/{url.database}"

    if not host.startswith("/"):
        unreachable = _tcp_probe(host, port, label="PostgreSQL")
        if unreachable is not None:
            return unreachable

    conninfo = _pg_conninfo(url_text)
    try:
        conn = _pg_connect(conninfo, settings)
    except Exception as exc:  # noqa: BLE001
        reason = _first_line(exc)
        lowered = str(exc).lower()
        for needle, hint in _PG_FATAL:
            if needle in lowered:
                return CheckResult(ok=False, retryable=False, summary=f"PostgreSQL {target}: {reason}", hints=[hint])
        if "too many clients" in lowered or "remaining connection slots" in lowered:
            return CheckResult(
                ok=False,
                summary=f"PostgreSQL {target}: connection limit reached ({reason})",
                hints=[
                    "Another process is holding all connections. Look for an old start-vm / uvicorn / celery "
                    "still running on any machine using this database (ps aux | grep -E 'uvicorn|celery').",
                    "On the DB host: SELECT application_name, client_addr, count(*) FROM pg_stat_activity GROUP BY 1,2;",
                ],
            )
        if any(token in lowered for token in _PG_TRANSIENT):
            return CheckResult(ok=False, summary=f"PostgreSQL {target}: {reason} (waiting)")
        if "closed the connection unexpectedly" in lowered or "connection reset" in lowered:
            if "sslmode" not in conninfo:
                # Some proxies/forwarders drop the SSL negotiation packet psycopg sends by default.
                try:
                    _pg_connect(conninfo, settings, sslmode="disable").close()
                except Exception:  # noqa: BLE001
                    pass
                else:
                    return CheckResult(
                        ok=False,
                        retryable=False,
                        summary=f"PostgreSQL {target}: handshake only works without TLS",
                        hints=["Add DB_SSLMODE=disable to backend/.env (the server/proxy drops TLS negotiation)."],
                    )
            return CheckResult(
                ok=False,
                summary=f"PostgreSQL {target}: server closed the connection during the handshake",
                hints=_closed_unexpectedly_hints(host, port),
            )
        return CheckResult(ok=False, summary=f"PostgreSQL {target}: {reason}")

    notes: list[str] = []
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SHOW server_version")
            version = str(cur.fetchone()[0]).split()[0]
            cur.execute("SELECT current_setting('max_connections')::int, (SELECT count(*) FROM pg_stat_activity)")
            max_conn, used = cur.fetchone()
            if max_conn and used >= 0.8 * max_conn:
                cur.execute(
                    "SELECT coalesce(nullif(application_name, ''), '?'), coalesce(host(client_addr), 'local'), count(*) "
                    "FROM pg_stat_activity WHERE datname IS NOT NULL GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 6"
                )
                holders = ", ".join(f"{app}@{addr}={n}" for app, addr, n in cur.fetchall())
                notes.append(
                    f"warning: {used}/{max_conn} connections in use; top holders: {holders}. "
                    "Stop stale app processes or raise max_connections."
                )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(ok=False, summary=f"PostgreSQL {target}: connected but query failed ({_first_line(exc)})")
    return CheckResult(
        ok=True,
        summary=f"PostgreSQL {target} ok (server {version}, {used}/{max_conn} connections)",
        notes=notes,
    )


# --------------------------------------------------------------------------- Redis


def check_redis(settings: Settings) -> CheckResult:
    import redis
    from redis import exceptions as rex

    url_text = str(settings.redis_url)
    masked = _mask_url(url_text)
    parsed = redis.connection.parse_url(url_text)
    host = str(parsed.get("host") or "localhost")
    port = int(parsed.get("port") or 6379)
    if "path" not in parsed:
        unreachable = _tcp_probe(host, port, label="Redis")
        if unreachable is not None:
            return unreachable

    client = redis.Redis.from_url(url_text, socket_connect_timeout=5, socket_timeout=5)
    notes: list[str] = []
    try:
        client.ping()
        # A write proves Redis can accept Celery messages (catches MISCONF / read-only replicas).
        client.set(f"{settings.redis_namespace}:preflight", "1", ex=30)
        info = client.info()
        policy = str(info.get("maxmemory_policy", "noeviction"))
        if policy.startswith("allkeys"):
            notes.append(
                f"warning: maxmemory-policy is {policy}; Redis may evict queued Celery tasks. Use noeviction."
            )
        version = info.get("redis_version", "?")
    except rex.AuthenticationError as exc:
        return CheckResult(
            ok=False,
            retryable=False,
            summary=f"Redis {masked}: authentication failed ({_first_line(exc)})",
            hints=["Put the Redis password in REDIS_URL, e.g. redis://:PASSWORD@host:6379/0"],
        )
    except rex.BusyLoadingError:
        return CheckResult(ok=False, summary=f"Redis {masked}: still loading its dataset (waiting)")
    except rex.ReadOnlyError:
        return CheckResult(
            ok=False,
            retryable=False,
            summary=f"Redis {masked}: is a read-only replica",
            hints=["Point REDIS_URL at the primary Redis instance."],
        )
    except rex.ResponseError as exc:
        message = _first_line(exc)
        hints = []
        if message.startswith("MISCONF"):
            hints.append("Redis cannot save snapshots (usually disk full or bad dir permissions) on the Redis host.")
        elif message.startswith("DENIED"):
            hints.append("Redis protected mode is on: set a password (requirepass) or bind/allow the LAN interface.")
        return CheckResult(ok=False, retryable=False, summary=f"Redis {masked}: {message}", hints=hints)
    except (rex.ConnectionError, rex.TimeoutError, OSError) as exc:
        return CheckResult(ok=False, summary=f"Redis {masked}: {_first_line(exc)}")
    finally:
        client.close()
    return CheckResult(ok=True, summary=f"Redis {masked} ok (server {version})", notes=notes)


# --------------------------------------------------------------------------- main


def _report_failure(name: str, result: CheckResult) -> None:
    _say(f"FAIL {name}: {result.summary}")
    for hint in result.hints:
        _say(f"     {hint}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait for PostgreSQL and Redis before starting the app.")
    parser.add_argument("--wait", type=float, default=0, help="Keep retrying transient failures for this many seconds.")
    parser.add_argument("--skip-redis", action="store_true", help="Only check PostgreSQL.")
    args = parser.parse_args()

    settings = get_settings()
    checks: dict[str, Callable[[Settings], CheckResult]] = {"database": check_database}
    if not args.skip_redis:
        checks["redis"] = check_redis

    deadline = time.monotonic() + max(0.0, args.wait)
    reported: set[str] = set()
    last: dict[str, CheckResult] = {}
    attempt = 0
    while True:
        attempt += 1
        for name, check in list(checks.items()):
            result = check(settings)
            if result.ok:
                _say(f"ok   {result.summary}")
                for note in result.notes:
                    _say(f"     {note}")
                del checks[name]
                continue
            last[name] = result
            if name not in reported:
                _report_failure(name, result)
                reported.add(name)
        if not checks:
            return 0

        remaining = deadline - time.monotonic()
        fatal = [name for name in checks if not last[name].retryable]
        if fatal or remaining <= 0:
            if attempt > 1:
                for name in checks:
                    _report_failure(name, last[name])
            if not fatal and args.wait > 0:
                _say(f"gave up after {args.wait:.0f}s.")
            return 1

        delay = min(2.0**attempt, 10.0, remaining)
        waiting = ", ".join(f"{name} ({last[name].summary})" for name in checks)
        _say(f"waiting {delay:.0f}s for {waiting}; {remaining:.0f}s left")
        time.sleep(delay)


if __name__ == "__main__":
    sys.exit(main())
