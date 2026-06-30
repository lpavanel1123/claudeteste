from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import psycopg2.pool

import config

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.SimpleConnectionPool(1, 5, dsn=config.DATABASE_URL)
    return _pool


@contextmanager
def get_cursor(commit: bool = False):
    """Yields a RealDictCursor (rows behave like dicts; JSONB columns decode to list/dict)."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
