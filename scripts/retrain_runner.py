"""Simple retrain runner. Call this from scheduler, CI, or k8s CronJob to retrain model.

This script attempts to acquire a Redis-based lock before running a retrain to
prevent concurrent retrains across replicas or cron jobs.
"""
import os
import time
from dotenv import load_dotenv
from app.recommender import HybridRecommender
from app.cache import RedisCache
from app.lock import RedLockManager

load_dotenv()

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
MODEL_PATH = os.getenv('MODEL_PATH', './models/hybrid_model.joblib')
LOCK_TTL = int(os.getenv('REDIS_RETRAIN_LOCK_TTL', '1800'))
LOCK_KEY = os.getenv('REDIS_RETRAIN_LOCK_KEY', 'mr:retrain-lock')
REDLOCK_ENABLED = os.getenv('REDLOCK_ENABLED', 'false').lower() in ('1', 'true', 'yes')


def main(wait_for_lock: bool = False):
    cache = RedisCache(REDIS_URL)
    have_lock = False
    lock_handle = None
    redlock_mgr = None
    try:
            if REDLOCK_ENABLED:
                # try distributed RedLock across provided REDLOCK_NODES (or REDIS_URL if not set)
                # REDLOCK_NODES may be comma-separated
                nodes_raw = os.getenv('REDLOCK_NODES') or os.getenv('REDIS_URL')
                nodes = [u.strip() for u in nodes_raw.split(',') if u.strip()]
                redlock_mgr = RedLockManager(nodes)
                lock_handle = redlock_mgr.acquire(LOCK_KEY, ttl=LOCK_TTL * 1000, block=wait_for_lock, timeout=10)
            have_lock = lock_handle is not None
        else:
            # fallback to a single-node redis lock
            lock = cache.client.lock(LOCK_KEY, timeout=LOCK_TTL)
            have_lock = lock.acquire(blocking=wait_for_lock, blocking_timeout=10)
            lock_handle = lock if have_lock else None

        if not have_lock:
            print('Another retrain is running; exiting')
            return 1

        print('Acquired retrain lock; starting retrain')
        r = HybridRecommender(model_path=MODEL_PATH, cache=cache)
        r.retrain_and_reload()
        print('Retrain complete')
        return 0
    except Exception as e:
        print('Retrain failed:', e)
        return 2
    finally:
        try:
            if have_lock:
                if REDLOCK_ENABLED and redlock_mgr:
                    redlock_mgr.release(lock_handle)
                else:
                    try:
                        lock_handle.release()
                    except Exception:
                        pass
                # small sleep to allow release propagation
                time.sleep(0.1)
        except Exception:
            pass


if __name__ == '__main__':
    # when invoked from CronJob or scheduler we don't block waiting for lock
    raise SystemExit(main(wait_for_lock=False))
