import os
import redis
from typing import List, Optional, Any, Union

try:
    from redlock import Redlock
except Exception:
    Redlock = None

from .metrics import LOCK_ACQUIRE_TOTAL, LOCK_ACQUIRE_FAILED_TOTAL, LOCK_RELEASE_TOTAL, LOCK_RELEASE_FAILED_TOTAL


def _parse_redis_url(url: str) -> dict:
    # minimal parser for redis://host:port/db
    # supports redis://[:password@]host:port/db
    from urllib.parse import urlparse
    p = urlparse(url)
    host = p.hostname or 'localhost'
    port = p.port or 6379
    db = int(p.path.lstrip('/') or 0)
    password = p.password
    return {'host': host, 'port': port, 'db': db, 'password': password}


class RedLockManager:
    """Wrapper that uses redlock-py if available, else falls back to single-node redis lock.

    Usage:
        mgr = RedLockManager(["redis://host:6379/0", ...])
        lock = mgr.acquire("resource", ttl=10000, block=True, timeout=10)
        if lock:
            try:
                ...
            finally:
                mgr.release(lock)
    """

    def __init__(self, redis_urls: Optional[Union[List[str], str]] = None, require_quorum: bool = True):
        # redis_urls may be a list or a comma-separated string; normalize to list
        raw = redis_urls or os.getenv('REDLOCK_NODES') or os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        if isinstance(raw, str):
            urls = [u.strip() for u in raw.split(',') if u.strip()]
        else:
            urls = list(raw)

        self._clients = []
        for u in urls:
            cfg = _parse_redis_url(u)
            client = redis.Redis(host=cfg['host'], port=cfg['port'], db=cfg['db'], password=cfg['password'])
            self._clients.append(client)

        # Validate quorum if requested (RedLock requires multiple independent masters; recommend >=3)
        if require_quorum and Redlock and len(self._clients) < 3:
            raise ValueError('RedLock requires at least 3 independent Redis nodes for safe distributed locking')

        if Redlock and len(self._clients) > 0:
            try:
                self._dlm = Redlock(self._clients)
            except Exception:
                self._dlm = None
        else:
            self._dlm = None

    def acquire(self, resource: str, ttl: int = 10000, block: bool = False, timeout: int = 10) -> Any:
        """Acquire a distributed lock.

        Returns a lock object (opaque) when acquired, or None.
        If Redlock is not available or not initialized, falls back to single-node redis lock object.
        """
        # prefer Redlock if available
        LOCK_ACQUIRE_TOTAL.inc()
        if self._dlm:
            # redlock.lock returns lock dict or None; blocking behavior: implement retry loop
            if not block:
                lock = self._dlm.lock(resource, ttl)
                if not lock:
                    LOCK_ACQUIRE_FAILED_TOTAL.inc()
                return lock
            end = None
            import time
            if timeout:
                end = time.time() + timeout
            while True:
                lock = self._dlm.lock(resource, ttl)
                if lock:
                    return lock
                if end and time.time() > end:
                    LOCK_ACQUIRE_FAILED_TOTAL.inc()
                    return None
                time.sleep(0.1)

        # fallback: use first redis client with redis-py Lock
        if self._clients:
            client = self._clients[0]
            lock = client.lock(resource, timeout=ttl/1000 if ttl else None)
            have = lock.acquire(blocking=block, blocking_timeout=timeout if block else None)
            if not have:
                LOCK_ACQUIRE_FAILED_TOTAL.inc()
            return lock if have else None

        return None

    def release(self, lock: Any):
        if lock is None:
            return
        # redlock-py lock is a dict with 'resource' and 'value' keys; it supplies unlock(lock)
        if self._dlm and isinstance(lock, dict):
            try:
                self._dlm.unlock(lock)
                LOCK_RELEASE_TOTAL.inc()
            except Exception:
                LOCK_RELEASE_FAILED_TOTAL.inc()
            return

        # fallback: assume redis-py Lock
        try:
            lock.release()
            LOCK_RELEASE_TOTAL.inc()
        except Exception:
            LOCK_RELEASE_FAILED_TOTAL.inc()
