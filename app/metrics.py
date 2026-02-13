from prometheus_client import Counter

# Lock metrics
LOCK_ACQUIRE_TOTAL = Counter('lock_acquire_total', 'Total lock acquire attempts')
LOCK_ACQUIRE_FAILED_TOTAL = Counter('lock_acquire_failed_total', 'Failed lock acquire attempts')
LOCK_RELEASE_TOTAL = Counter('lock_release_total', 'Total lock releases')
LOCK_RELEASE_FAILED_TOTAL = Counter('lock_release_failed_total', 'Failed lock releases')
