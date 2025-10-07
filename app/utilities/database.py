import logging

from redis.asyncio import Redis
from redisvl.extensions.cache.embeddings.embeddings import EmbeddingsCache
from redisvl.index.index import AsyncSearchIndex
from redisvl.utils.vectorize import OpenAITextVectorizer

from app.utilities.environment import get_env_var

INDEX_NAME = "rag_doc"
ANSWER_INDEX_NAME = "answer"
TRACKING_INDEX_NAME = "knowledge_tracking"

_document_index: AsyncSearchIndex | None = None
_vectorizer: OpenAITextVectorizer | None = None
_answer_index: AsyncSearchIndex | None = None
_tracking_index: AsyncSearchIndex | None = None
logger = logging.getLogger(__name__)


DOCUMENT_SCHEMA = {
    "index": {"name": INDEX_NAME, "prefix": f"{INDEX_NAME}:", "storage_type": "hash"},
    "fields": [
        {
            "name": "name",
            "type": "tag",
        },
        {
            "name": "description",
            "type": "text",
        },
        {
            "name": "source_file",
            "type": "tag",
        },
        {
            "name": "type",
            "type": "tag",
        },
        {
            "name": "chunk_index",
            "type": "numeric",
        },
        {
            "name": "start_index",
            "type": "numeric",
        },
        {"name": "source_date", "type": "tag"},
        {"name": "update_date", "type": "tag"},
        {"name": "updated_at", "type": "numeric"},
        {
            "name": "vector",
            "type": "vector",
            "attrs": {
                "dims": 1536,
                "distance_metric": "cosine",
                "algorithm": "flat",
                "datatype": "float32",
            },
        },
    ],
}

ANSWER_SCHEMA = {
    "index": {
        "name": ANSWER_INDEX_NAME,
        "prefix": ANSWER_INDEX_NAME,
        "storage_type": "json",
    },
    "fields": [
        {"name": "user_id", "type": "tag"},
        {"name": "question", "type": "text"},
        {"name": "answer", "type": "text"},
        {"name": "accepted", "type": "tag"},
        {"name": "created_at", "type": "numeric"},
        {"name": "updated_at", "type": "numeric"},
        {"name": "thread_ts", "type": "tag"},
        {"name": "channel_id", "type": "tag"},
        {"name": "processed_at", "type": "numeric"},
        {
            "name": "question_vector",
            "type": "vector",
            "attrs": {
                "dims": 1536,
                "distance_metric": "cosine",
                "algorithm": "flat",
                "datatype": "float32",
            },
        },
        {
            "name": "answer_vector",
            "type": "vector",
            "attrs": {
                "dims": 1536,
                "distance_metric": "cosine",
                "algorithm": "flat",
                "datatype": "float32",
            },
        },
    ],
}

TRACKING_SCHEMA = {
    "index": {
        "name": TRACKING_INDEX_NAME,
        "prefix": TRACKING_INDEX_NAME,
        "storage_type": "json",
    },
    "fields": [
        {"name": "name", "type": "tag"},
        {"name": "content_type", "type": "text"},
        {"name": "content_url", "type": "text"},
        {"name": "source_date", "type": "tag"},
        {"name": "update_date", "type": "tag"},
        {"name": "updated_at", "type": "numeric"},
        {"name": "bucket_url", "type": "text"},
        {"name": "processing_status", "type": "tag"},
        {"name": "last_processing_attempt", "type": "numeric"},
        {"name": "failure_reason", "type": "text"},
        {"name": "retry_count", "type": "numeric"},
        {"name": "archive", "type": "tag"},
    ],
}


def get_vectorizer() -> OpenAITextVectorizer:
    global _vectorizer
    if _vectorizer is None:
        cache = EmbeddingsCache(
            redis_url=get_env_var("REDIS_URL", "redis://localhost:6379/0")
        )
        _vectorizer = OpenAITextVectorizer(model="text-embedding-3-small", cache=cache)
    return _vectorizer


def get_document_index() -> AsyncSearchIndex:
    global _document_index
    if _document_index is None:
        _document_index = AsyncSearchIndex.from_dict(
            DOCUMENT_SCHEMA,
            redis_url=get_env_var("REDIS_URL", "redis://localhost:6379/0"),
        )
    return _document_index


def get_answer_index() -> AsyncSearchIndex:
    global _answer_index
    if _answer_index is None:
        _answer_index = AsyncSearchIndex.from_dict(
            ANSWER_SCHEMA,
            redis_url=get_env_var("REDIS_URL", "redis://localhost:6379/0"),
        )
    return _answer_index


def get_tracking_index() -> AsyncSearchIndex:
    """Get the tracking index for knowledge base content tracking"""
    global _tracking_index
    if _tracking_index is None:
        _tracking_index = AsyncSearchIndex.from_dict(
            TRACKING_SCHEMA,
            redis_url=get_env_var("REDIS_URL", "redis://localhost:6379/0"),
        )
    return _tracking_index


def get_redis_client() -> Redis:
    return Redis.from_url(url=get_env_var("REDIS_URL", "redis://localhost:6379/0"))
