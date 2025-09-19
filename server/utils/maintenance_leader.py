"""
Cooperative single-runner guard for background maintenance tasks using
PostgreSQL advisory locks.

Usage:
    if acquire_maintenance_leadership('maintenance_v1'):
        # start background tasks
    else:
        # skip; another process is leader
"""

import logging

from server.database.engine import engine

logger = logging.getLogger(__name__)

# Module-level handle to keep the DB session open while holding the lock.
_leader_connection = None  # type: Optional[object]


def wait_for_maintenance_leadership(lock_key: str) -> None:
    """
    Block until this process holds the advisory lock keyed by ``lock_key``.

    Uses ``pg_advisory_lock`` so we only return once the lock is available and
    bound to a dedicated connection that lives for the lifetime of the leader.
    """
    global _leader_connection

    if _leader_connection is not None:
        # Already leader in this process; nothing else to do.
        return

    conn = engine.raw_connection()
    try:
        # Keep the session alive without holding an open transaction.
        conn.autocommit = True  # type: ignore[attr-defined]
        cur = conn.cursor()
        try:
            cur.execute(
                'SELECT pg_advisory_lock(hashtextextended(%s, 77))',
                [lock_key],
            )
            # ``pg_advisory_lock`` blocks until it acquires the lock; fetching the
            # single row ensures the command is complete before we proceed.
            cur.fetchone()
        finally:
            cur.close()
        _leader_connection = conn
        logger.info(f"Acquired maintenance leadership with key '{lock_key}'")
    except Exception as e:
        logger.error(f'Failed to wait for maintenance leadership: {e}')
        try:
            conn.close()
        except Exception:
            pass
        raise


def acquire_maintenance_leadership(lock_key: str) -> bool:
    """
    Try to acquire a session-level advisory lock keyed by the provided string.

    Returns True if this process became the maintenance leader. The connection
    is kept open until release_maintenance_leadership() is called (or process exit).
    """
    global _leader_connection

    if _leader_connection is not None:
        # Already leader in this process
        return True

    # Create a dedicated DBAPI connection outside of SQLAlchemy sessions
    # so we can keep it open and hold the advisory lock for the process lifetime.
    conn = engine.raw_connection()
    try:
        # Use a stable hash for the key and a seed to avoid collisions with other app locks
        conn.autocommit = True  # type: ignore[attr-defined]
        cur = conn.cursor()
        try:
            cur.execute(
                'SELECT pg_try_advisory_lock(hashtextextended(%s, 77))',
                [lock_key],
            )
            row = cur.fetchone()
            locked = bool(row and row[0])
        finally:
            cur.close()
        if not locked:
            # Not leader; close the connection immediately
            conn.close()
            return False

        # Keep the connection open to hold the session-level advisory lock
        _leader_connection = conn
        logger.info(f"Acquired maintenance leadership with key '{lock_key}'")
        return True
    except Exception as e:
        logger.error(f'Failed to acquire maintenance leadership: {e}')
        try:
            conn.close()
        except Exception:
            pass
        return False


def release_maintenance_leadership(lock_key: str) -> None:
    """
    Release the advisory lock if held by this process and close the connection.
    Safe to call multiple times.
    """
    global _leader_connection

    if _leader_connection is None:
        return

    try:
        cur = _leader_connection.cursor()
        cur.execute(
            'SELECT pg_advisory_unlock(hashtextextended(%s, 77))',
            [lock_key],
        )
        # Close cursor and connection regardless of unlock result
        cur.close()
    except Exception as e:
        logger.warning(f'Error while releasing maintenance leadership: {e}')
    finally:
        try:
            _leader_connection.close()
        except Exception:
            pass
        _leader_connection = None
