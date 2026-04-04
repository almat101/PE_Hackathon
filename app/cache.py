"""Redis cache helper — fallback to no-op if Redis unavailable."""

import os

try:
    import redis
except ImportError:
    redis = None

_redis_client = None


def get_redis():
    """Get or create Redis client."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    if redis is None:
        return None

    try:
        _redis_client = redis.Redis(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", 6379)),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_keepalive=True,
        )
        _redis_client.ping()
        return _redis_client
    except (redis.ConnectionError, Exception):
        return None


def cache_get(key: str):
    """Get value from Redis cache. Returns None on miss or error."""
    try:
        client = get_redis()
        if client is None:
            return None
        return client.get(key)
    except Exception:
        return None


def cache_set(key: str, value: str, ttl: int = 300):
    """Set value in Redis cache with optional TTL. Fails gracefully."""
    try:
        client = get_redis()
        if client is None:
            return False
        client.setex(key, ttl, value)
        return True
    except Exception:
        return False


def cache_delete(key: str):
    """Delete key from Redis cache."""
    try:
        client = get_redis()
        if client is None:
            return False
        client.delete(key)
        return True
    except Exception:
        return False


def cache_clear_pattern(pattern: str):
    """Delete all keys matching pattern (e.g., 'url:*')."""
    try:
        client = get_redis()
        if client is None:
            return 0
        keys = client.keys(pattern)
        if keys:
            return client.delete(*keys)
        return 0
    except Exception:
        return 0
