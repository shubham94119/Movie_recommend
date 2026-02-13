# Metrics

Prometheus metrics are exposed on `/metrics`. We add two metrics in the scaffold:

- `retrain_duration_seconds` (Summary)
- `recommend_requests_total` (Counter)

Wire Prometheus to scrape `http://<host>:8000/metrics`.
