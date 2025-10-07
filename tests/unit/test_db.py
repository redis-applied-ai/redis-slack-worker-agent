"""Test database functionality including schema validation and index creation."""

from unittest import mock
from unittest.mock import MagicMock, patch

from redisvl.schema import IndexSchema
from redisvl.schema.fields import (
    VectorDataType,
    VectorDistanceMetric,
    VectorIndexAlgorithm,
)

from app.utilities.database import (
    ANSWER_SCHEMA,
    DOCUMENT_SCHEMA,
    get_answer_index,
    get_document_index,
    get_redis_client,
    get_vectorizer,
)


class TestSchemaValidation:
    """Test that our schemas are valid and can be created."""

    def test_document_schema_validation(self):
        """Test that DOCUMENT_SCHEMA is valid RedisVL schema."""
        # This should not raise any validation errors
        schema = IndexSchema.from_dict(DOCUMENT_SCHEMA)
        assert schema.index.name == "rag_doc"
        assert schema.index.storage_type.value == "hash"

        # Verify all expected fields are present
        field_names = schema.field_names
        expected_fields = [
            "name",
            "description",
            "source_file",
            "type",
            "chunk_index",
            "start_index",
            "vector",
        ]
        for field in expected_fields:
            assert field in field_names

    def test_answer_schema_validation(self):
        """Test that ANSWER_SCHEMA is valid RedisVL schema."""
        # This should not raise any validation errors
        schema = IndexSchema.from_dict(ANSWER_SCHEMA)
        assert schema.index.name == "answer"
        assert schema.index.storage_type.value == "json"

        # Verify all expected fields are present
        field_names = schema.field_names
        expected_fields = [
            "user_id",
            "question",
            "answer",
            "accepted",
            "created_at",
            "updated_at",
            "thread_ts",
            "channel_id",
            "processed_at",
            "question_vector",
            "answer_vector",
        ]
        for field in expected_fields:
            assert field in field_names

    def test_accepted_field_is_tag_type(self):
        """Test that the 'accepted' field is properly configured as a tag type."""
        schema = IndexSchema.from_dict(ANSWER_SCHEMA)
        accepted_field = schema.fields["accepted"]
        # Check that it's a tag field (not boolean)
        assert accepted_field.type == "tag"

    def test_vector_fields_configuration(self):
        """Test that vector fields are properly configured."""
        schema = IndexSchema.from_dict(ANSWER_SCHEMA)

        for vector_field_name in ["question_vector", "answer_vector"]:
            vector_field = schema.fields[vector_field_name]
            assert vector_field.type == "vector"
            assert vector_field.attrs.dims == 1536  # type: ignore
            assert vector_field.attrs.distance_metric == VectorDistanceMetric.COSINE  # type: ignore
            assert vector_field.attrs.algorithm == VectorIndexAlgorithm.FLAT  # type: ignore
            assert vector_field.attrs.datatype == VectorDataType.FLOAT32  # type: ignore


class TestIndexCreation:
    """Test index creation functions."""

    @patch("app.utilities.database.get_env_var", return_value="redis://test:6379/0")
    def test_get_answer_index_creation(self, mock_get_env_var):
        """Test that get_answer_index() successfully creates an AsyncSearchIndex."""
        with patch(
            "app.utilities.database.AsyncSearchIndex.from_dict"
        ) as mock_from_dict:
            mock_index = MagicMock()
            mock_from_dict.return_value = mock_index

            import app.utilities.database

            app.utilities.database._answer_index = None

            result = get_answer_index()

            mock_from_dict.assert_called_once_with(
                ANSWER_SCHEMA, redis_url="redis://test:6379/0"
            )
            assert result == mock_index

    @patch("app.utilities.database.get_env_var", return_value="redis://test:6379/0")
    def test_get_document_index_creation(self, mock_get_env_var):
        """Test that get_document_index() successfully creates an AsyncSearchIndex."""
        with patch(
            "app.utilities.database.AsyncSearchIndex.from_dict"
        ) as mock_from_dict:
            mock_index = MagicMock()
            mock_from_dict.return_value = mock_index

            # Clear global cache first
            import app.utilities.database

            app.utilities.database._document_index = None

            result = get_document_index()

            mock_from_dict.assert_called_once_with(
                DOCUMENT_SCHEMA, redis_url="redis://test:6379/0"
            )
            assert result == mock_index

    def test_index_caching(self):
        """Test that indexes are cached globally."""
        import app.utilities.database

        # Clear cache
        app.utilities.database._answer_index = None
        app.utilities.database._document_index = None

        with patch(
            "app.utilities.database.AsyncSearchIndex.from_dict"
        ) as mock_from_dict:
            mock_index = MagicMock()
            mock_from_dict.return_value = mock_index

            # First call should create the index
            result1 = get_answer_index()
            assert mock_from_dict.call_count == 1

            # Second call should return cached version
            result2 = get_answer_index()
            assert mock_from_dict.call_count == 1  # Still only called once

            assert result1 == result2 == mock_index

    @patch("app.utilities.database.OpenAITextVectorizer")
    def test_get_vectorizer_creation(self, mock_vectorizer_class):
        """Test that get_vectorizer() creates and caches a vectorizer."""
        mock_vectorizer = MagicMock()
        mock_vectorizer_class.return_value = mock_vectorizer

        # Clear global cache first
        import app.utilities.database

        app.utilities.database._vectorizer = None

        result = get_vectorizer()

        # Verify vectorizer was created with correct model
        mock_vectorizer_class.assert_called_once_with(
            model="text-embedding-3-small", cache=mock.ANY
        )
        assert result == mock_vectorizer

    @patch("app.utilities.database.get_env_var", return_value="redis://test:6379/0")
    @patch("app.utilities.database.Redis.from_url")
    def test_get_redis_client_creation(self, mock_redis_from_url, mock_get_env_var):
        """Test that get_redis_client() creates a Redis client."""
        mock_client = MagicMock()
        mock_redis_from_url.return_value = mock_client

        result = get_redis_client()

        # Verify Redis client was created with correct URL
        mock_redis_from_url.assert_called_once_with(url="redis://test:6379/0")
        assert result == mock_client

    @patch(
        "app.utilities.database.get_env_var", return_value="redis://localhost:6379/0"
    )
    def test_answer_data_storage_compatibility(self, mock_get_env_var):
        """Test that answer data with boolean values can be stored properly."""
        from datetime import datetime, timezone

        from ulid import ULID

        # This is the type of data that gets stored in the answer index
        answer_data = {
            "id": str(ULID()),
            "user_id": "test_user",
            "question": "Test question",
            "answer": "Test answer",
            "accepted": "false",  # Should be string, not boolean
            "created_at": datetime.now(timezone.utc).timestamp(),
            "updated_at": datetime.now(timezone.utc).timestamp(),
            "thread_ts": "",  # Should be string, not None
            "channel_id": "test_channel",
        }

        # Verify all values are Redis-compatible
        for key, value in answer_data.items():
            assert isinstance(
                value, (str, int, float)
            ), f"Field {key} should be string/int/float, got {type(value)}"

        # Specifically verify the problematic fields
        assert answer_data["accepted"] == "false"
        assert isinstance(answer_data["thread_ts"], str)


class TestFieldTypes:
    """Test that our schema only uses supported field types."""

    def test_no_boolean_field_types(self):
        """Test that we don't use boolean field types which aren't supported by RedisVL."""
        # Check both schemas for boolean fields
        for schema_name, schema in [
            ("DOCUMENT_SCHEMA", DOCUMENT_SCHEMA),
            ("ANSWER_SCHEMA", ANSWER_SCHEMA),
        ]:
            for field in schema["fields"]:
                field_type = field["type"]
                assert (
                    field_type != "boolean"
                ), f"Field {field.get('name', 'unknown')} in {schema_name} uses unsupported boolean type"

    def test_supported_field_types_only(self):
        """Test that we only use supported RedisVL field types."""
        supported_types = {"text", "tag", "numeric", "vector"}

        for schema_name, schema in [
            ("DOCUMENT_SCHEMA", DOCUMENT_SCHEMA),
            ("ANSWER_SCHEMA", ANSWER_SCHEMA),
        ]:
            for field in schema["fields"]:
                field_type = field["type"]
                assert (
                    field_type in supported_types
                ), f"Field {field.get('name', 'unknown')} in {schema_name} uses unsupported type: {field_type}"
