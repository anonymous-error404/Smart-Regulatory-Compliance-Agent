"""
snowflake_connector.py
======================
Singleton wrappers for Snowpark Session and snowflake-connector-python
connections.  Both objects are lazily created on first call and cached
for the lifetime of the process.

Usage
-----
    from src.snowflake_connector import get_session, get_connection, close_all

    session = get_session()          # → snowpark Session
    conn    = get_connection()       # → snowflake.connector connection
    close_all()                      # graceful shutdown
"""

from __future__ import annotations

import sys
import os
import time
import logging
import functools
from typing import Callable, TypeVar, Any

# ---------------------------------------------------------------------------
# Ensure the project root (containing config.py) is importable
# ---------------------------------------------------------------------------
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config  # noqa: E402  (imported after sys.path fix)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class SnowflakeConnectionError(RuntimeError):
    """Raised when a Snowflake connection cannot be established."""


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

F = TypeVar("F", bound=Callable[..., Any])


def _retry(max_attempts: int = 3, delay_seconds: float = 2.0) -> Callable[[F], F]:
    """Decorator that retries *func* up to *max_attempts* times.

    Parameters
    ----------
    max_attempts:
        Maximum number of total invocation attempts (including the first).
    delay_seconds:
        Seconds to sleep between successive attempts.

    Returns
    -------
    Callable
        The decorated function with automatic retry behaviour.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except SnowflakeConnectionError:
                    # Configuration-level error — no point retrying
                    raise
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    logger.warning(
                        "[snowflake_connector] Attempt %d/%d failed for %s: %s",
                        attempt,
                        max_attempts,
                        func.__name__,
                        exc,
                    )
                    if attempt < max_attempts:
                        time.sleep(delay_seconds)
            raise RuntimeError(
                f"All {max_attempts} attempts failed for {func.__name__}"
            ) from last_exc

        return wrapper  # type: ignore[return-value]

    return decorator


# ---------------------------------------------------------------------------
# Module-level singletons (None until first call)
# ---------------------------------------------------------------------------

_session: Any = None   # snowflake.snowpark.Session
_connection: Any = None  # snowflake.connector.SnowflakeConnection


def _build_connection_params() -> dict:
    """Assemble Snowflake connection parameters from ``config``."""
    account = config.SNOWFLAKE_ACCOUNT
    if "://" in account:
        account = account.split("://")[-1]
    if account.endswith(".snowflakecomputing.com"):
        account = account.replace(".snowflakecomputing.com", "")

    return {
        "account":   account,
        "user":      config.SNOWFLAKE_USER,
        "password":  config.SNOWFLAKE_PASSWORD,
        "database":  config.SNOWFLAKE_DATABASE,
        "schema":    config.SNOWFLAKE_SCHEMA,
        "warehouse": config.SNOWFLAKE_WAREHOUSE,
        "role":      config.SNOWFLAKE_ROLE,
    }


def _guard_env() -> None:
    """Raise :class:`SnowflakeConnectionError` when running in local ENV.

    Raises
    ------
    SnowflakeConnectionError
        If ``config.ENV`` is ``'local'``.
    """
    if getattr(config, "ENV", "local") == "local":
        raise SnowflakeConnectionError(
            "Cannot connect to Snowflake in local ENV. "
            "Set AURIS_ENV=snowflake"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@_retry(max_attempts=3, delay_seconds=2.0)
def get_session():
    """Return a cached Snowpark :class:`~snowflake.snowpark.Session`.

    Creates a new session on the first call; subsequent calls return the
    cached instance.

    Returns
    -------
    snowflake.snowpark.Session
        An active Snowpark session connected to the configured Snowflake
        account.

    Raises
    ------
    SnowflakeConnectionError
        If ``config.ENV`` is ``'local'``.
    RuntimeError
        If all retry attempts fail.
    """
    global _session  # noqa: PLW0603

    _guard_env()

    if _session is not None:
        logger.debug("[snowflake_connector] Returning cached Snowpark session.")
        return _session

    try:
        from snowflake.snowpark import Session  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "snowflake-snowpark-python is not installed. "
            "Run: pip install snowflake-snowpark-python"
        ) from exc

    params = _build_connection_params()
    logger.info("[snowflake_connector] Creating Snowpark session for account=%s …", params["account"])
    _session = Session.builder.configs(params).create()
    logger.info("[snowflake_connector] Snowpark session established.")
    return _session


@_retry(max_attempts=3, delay_seconds=2.0)
def get_connection():
    """Return a cached ``snowflake.connector`` connection.

    Creates a new connection on the first call; subsequent calls return the
    cached instance.

    Returns
    -------
    snowflake.connector.SnowflakeConnection
        An active connector connection to the configured Snowflake account.

    Raises
    ------
    SnowflakeConnectionError
        If ``config.ENV`` is ``'local'``.
    RuntimeError
        If all retry attempts fail.
    """
    global _connection  # noqa: PLW0603

    _guard_env()

    if _connection is not None:
        logger.debug("[snowflake_connector] Returning cached connector connection.")
        return _connection

    try:
        import snowflake.connector  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "snowflake-connector-python is not installed. "
            "Run: pip install snowflake-connector-python"
        ) from exc

    params = _build_connection_params()
    logger.info(
        "[snowflake_connector] Creating connector connection for account=%s …",
        params["account"],
    )
    _connection = snowflake.connector.connect(**params)
    logger.info("[snowflake_connector] Connector connection established.")
    return _connection


def close_all() -> None:
    """Close both the Snowpark session and the connector connection.

    Resets the module-level singletons to ``None`` so that subsequent calls
    to :func:`get_session` or :func:`get_connection` will create fresh
    connections.

    Safe to call even if neither connection has been opened yet.
    """
    global _session, _connection  # noqa: PLW0603

    if _session is not None:
        try:
            _session.close()
            logger.info("[snowflake_connector] Snowpark session closed.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[snowflake_connector] Error closing Snowpark session: %s", exc)
        finally:
            _session = None

    if _connection is not None:
        try:
            _connection.close()
            logger.info("[snowflake_connector] Connector connection closed.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[snowflake_connector] Error closing connector connection: %s", exc)
        finally:
            _connection = None
