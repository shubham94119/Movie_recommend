import pickle
import redis
from typing import Any


class RedisCache:
    def __init__(self, url: str = "redis://localhost:6379/0", namespace: str = "mr"):
        self.client = redis.Redis.from_url(url, decode_responses=False)
        self.namespace = namespace

    def _pref(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def get(self, key: str) -> Any:
        v = self.client.get(self._pref(key))
        if v is None:
            return None
        return pickle.loads(v)

    def set(self, key: str, value: Any, ex: int = 3600):
        self.client.set(self._pref(key), pickle.dumps(value), ex=ex)

    def delete(self, key: str):
        self.client.delete(self._pref(key))

    def delete_pattern(self, pattern: str):
        # pattern is without namespace, we prefix it
        full_pattern = self._pref(pattern)
        # Use scan_iter to avoid blocking Redis
        for k in self.client.scan_iter(match=full_pattern):
            try:
                self.client.delete(k)
            except Exception:
                pass
