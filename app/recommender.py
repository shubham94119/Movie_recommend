import os
import joblib
import logging
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
from prometheus_client import Summary, Counter

log = logging.getLogger(__name__)

# Metrics
MODEL_SAVE_METRIC = Summary('retrain_duration_seconds', 'Time spent retraining model')
RECOMMEND_COUNTER = Counter('recommend_requests_total', 'Number of recommend calls')
RECOMMEND_LATENCY = Summary('recommend_latency_seconds', 'Latency for recommend endpoint')
RETRAIN_SUCCESS = Counter('retrain_success_total', 'Number of successful retrains')
RETRAIN_FAILURE = Counter('retrain_failure_total', 'Number of failed retrains')


class HybridRecommender:
    def __init__(self, model_path: str = './models/hybrid_model.joblib', cache=None):
        self.model_path = model_path
        self.cache = cache
        self.user_item = None
        self.item_profiles = None
        self.user_index = None
        self.item_index = None
        self.model_version = None
        self.movies_df = None
        log.info('HybridRecommender initialized; model_path=%s', self.model_path)

    def load_or_train(self):
        if os.path.exists(self.model_path):
            self._load()
        else:
            self.train_and_save()

        # ensure model_version is set after load/train
        self.model_version = self._compute_model_version()
        log.info('Model loaded/trained; version=%s', self.model_version)

    def _load(self):
        data = joblib.load(self.model_path)
        self.user_item = data['user_item']
        self.item_profiles = data['item_profiles']
        self.user_index = data['user_index']
        self.item_index = data['item_index']
        # movies metadata optional
        self.movies_df = data.get('movies') if isinstance(data.get('movies'), pd.DataFrame) else None
        if self.movies_df is None and os.path.exists(os.path.join('data', 'movies.csv')):
            try:
                self.movies_df = pd.read_csv(os.path.join('data', 'movies.csv')).set_index('movieId')
            except Exception:
                self.movies_df = None

        self.model_version = self._compute_model_version()
        log.info('Loaded model from %s (version=%s)', self.model_path, self.model_version)

    @MODEL_SAVE_METRIC.time()
    def train_and_save(self):
        # Sample data loader: expects `data/movies.csv` and `data/ratings.csv` in workspace
        movies_path = os.path.join('data', 'movies.csv')
        ratings_path = os.path.join('data', 'ratings.csv')
        if not os.path.exists(movies_path) or not os.path.exists(ratings_path):
            # create tiny sample dataset
            os.makedirs('data', exist_ok=True)
            movies = pd.DataFrame([
                {'movieId': 1, 'title': 'The Matrix', 'genres': 'Action|Sci-Fi'},
                {'movieId': 2, 'title': 'Toy Story', 'genres': 'Animation|Children|Comedy'},
                {'movieId': 3, 'title': 'The Godfather', 'genres': 'Crime|Drama'},
            ])
            ratings = pd.DataFrame([
                {'userId': 1, 'movieId': 1, 'rating': 5.0},
                {'userId': 1, 'movieId': 2, 'rating': 4.0},
                {'userId': 2, 'movieId': 3, 'rating': 5.0},
            ])
            movies.to_csv(movies_path, index=False)
            ratings.to_csv(ratings_path, index=False)
        movies = pd.read_csv(movies_path)
        ratings = pd.read_csv(ratings_path)

        # Build user-item matrix
        pivot = ratings.pivot_table(index='userId', columns='movieId', values='rating', fill_value=0)
        self.user_index = list(pivot.index)
        self.item_index = list(pivot.columns)
        self.user_item = pivot.values

        # Item profiles via TF-IDF on genres + title
        features = (movies.set_index('movieId').reindex(self.item_index).fillna('')
                    .assign(text=lambda df: df['title'].fillna('') + ' ' + df['genres'].fillna(''))['text'])
        tf = TfidfVectorizer(max_features=5000)
        self.item_profiles = tf.fit_transform(features.values).toarray()

        # Save (include movies metadata to allow API to return titles/genres)
        os.makedirs(os.path.dirname(self.model_path) or '.', exist_ok=True)
        payload = {
            'user_item': self.user_item,
            'item_profiles': self.item_profiles,
            'user_index': self.user_index,
            'item_index': self.item_index,
            'movies': movies.set_index('movieId')
        }
        try:
            joblib.dump(payload, self.model_path)
            # set in-memory metadata too
            self.movies_df = movies.set_index('movieId')
            # update model version after saving
            self.model_version = self._compute_model_version()
            log.info('Trained and saved model to %s (version=%s)', self.model_path, self.model_version)
            return True
        except Exception as e:
            log.exception('Failed to save model: %s', e)
            return False

    def _compute_model_version(self) -> str:
        try:
            if os.path.exists(self.model_path):
                st = os.stat(self.model_path)
                return f"{int(st.st_mtime)}-{st.st_size}"
        except Exception:
            pass
        return "none"

    def retrain_and_reload(self):
        old_version = self.model_version
        try:
            ok = self.train_and_save()
            if not ok:
                RETRAIN_FAILURE.inc()
                return False
            # reload structures from disk
            self._load()
            # delete old recommendation keys matching the old model version to free space
            if self.cache and old_version:
                try:
                    self.cache.delete_pattern(f"rec:v{old_version}:*")
                except Exception:
                    log.warning('Failed to delete old cache keys for version %s', old_version)
            RETRAIN_SUCCESS.inc()
            return True
        except Exception as e:
            log.exception('Retrain failed: %s', e)
            RETRAIN_FAILURE.inc()
            return False

    def recommend(self, user_id: int, n: int = 10):
        RECOMMEND_COUNTER.inc()
        # include model version in cache key so keys automatically invalidate when model changes
        mv = self.model_version or self._compute_model_version()
        key = f"rec:v{mv}:u{user_id}:n{n}"
        if self.cache:
            cached = self.cache.get(key)
            if cached is not None:
                log.debug('Cache hit for %s', key)
                return cached

        with RECOMMEND_LATENCY.time():
            if user_id not in self.user_index:
                log.debug('Unknown user_id %s; returning empty', user_id)
                return []
            uidx = self.user_index.index(user_id)
            user_vec = self.user_item[uidx:uidx+1]

            # Collaborative scores: item similarity via users
            item_sim = cosine_similarity(self.user_item.T, user_vec.T).ravel()

            # Content scores: similarity between user profile (weighted items) and item_profiles
            try:
                user_profile = (user_vec.ravel() @ self.item_profiles)  # weighted sum
                content_sim = cosine_similarity(self.item_profiles, user_profile.reshape(1, -1)).ravel()
            except Exception:
                content_sim = np.zeros(len(self.item_index))

            scores = normalize((item_sim.reshape(1, -1) + content_sim.reshape(1, -1))).ravel()
            top_idx = np.argsort(-scores)[:n]
            rec_ids = [int(self.item_index[i]) for i in top_idx]

            # attach metadata for each recommended movie
            recs = []
            for mid in rec_ids:
                try:
                    if self.movies_df is not None and int(mid) in self.movies_df.index:
                        row = self.movies_df.loc[int(mid)]
                        title = str(row.get('title', ''))
                        genres = str(row.get('genres', ''))
                    else:
                        title = ''
                        genres = ''
                except Exception:
                    title = ''
                    genres = ''
                poster = f"https://via.placeholder.com/160x240?text={mid}"
                recs.append({'movieId': mid, 'title': title, 'genres': genres, 'poster_url': poster})

            if self.cache:
                try:
                    self.cache.set(key, recs, ex=3600)
                except Exception:
                    log.warning('Failed to set cache for %s', key)
            return recs

