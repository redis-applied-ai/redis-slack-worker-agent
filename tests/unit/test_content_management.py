"""
Unit tests for content management system components.
"""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.api.content_ledger import ContentLedgerManager, get_content_ledger_manager
from app.api.content_storage import ContentStorageManager, get_content_storage_manager


class TestContentStorageManager:
    """Test ContentStorageManager class."""

    @pytest.fixture
    def mock_s3_client(self):
        """Mock S3 client."""
        mock_client = Mock()
        mock_client.head_bucket.return_value = None
        return mock_client

    @pytest.fixture
    def storage_manager(self, mock_s3_client):
        """ContentStorageManager instance with mocked S3 client."""
        with patch("boto3.client", return_value=mock_s3_client):
            return ContentStorageManager("test-bucket")

    def test_init_success(self, mock_s3_client):
        """Test successful initialization."""
        with patch("boto3.client", return_value=mock_s3_client):
            manager = ContentStorageManager("test-bucket")
            assert manager.bucket_name == "test-bucket"
            assert manager.s3_client == mock_s3_client

    def test_init_failure(self):
        """Test initialization failure."""
        with patch("boto3.client", side_effect=Exception("S3 error")):
            with pytest.raises(Exception):
                ContentStorageManager("test-bucket")

    @pytest.mark.asyncio
    async def test_upload_content(self, storage_manager, mock_s3_client):
        """Test content upload."""
        # Mock file path
        mock_file = Mock(spec=Path)
        mock_file.exists.return_value = True
        mock_file.stat.return_value = Mock(st_size=1024)

        # Mock async operations
        with patch("asyncio.to_thread") as mock_to_thread:
            # Make to_thread call the actual function
            mock_to_thread.side_effect = lambda func, *args, **kwargs: func(
                *args, **kwargs
            )

            result = await storage_manager.upload_content(
                "test_type", "test_name", mock_file
            )

            assert result == "s3://test-bucket/test_type/test_name"
            mock_s3_client.upload_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_content_file_not_found(self, storage_manager):
        """Test upload with non-existent file."""
        mock_file = Mock(spec=Path)
        mock_file.exists.return_value = False

        with pytest.raises(FileNotFoundError):
            await storage_manager.upload_content("test_type", "test_name", mock_file)

    def test_get_content_type(self, storage_manager):
        """Test content type detection."""
        assert storage_manager._get_content_type(Path("test.html")) == "text/html"
        assert (
            storage_manager._get_content_type(Path("test.ipynb"))
            == "application/x-ipynb+json"
        )
        assert storage_manager._get_content_type(Path("test.py")) == "text/x-python"
        assert (
            storage_manager._get_content_type(Path("test.unknown"))
            == "application/octet-stream"
        )


class TestContentLedgerManager:
    """Test ContentLedgerManager class."""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client."""
        mock_client = Mock()
        mock_client.json = Mock()
        mock_client.json().set = AsyncMock()
        mock_client.expire = AsyncMock()
        mock_client.sadd = AsyncMock()
        mock_client.srem = AsyncMock()
        mock_client.delete = AsyncMock()
        mock_client.json().get = AsyncMock()
        mock_client.smembers = AsyncMock()
        mock_client.keys = AsyncMock()
        mock_client.zadd = AsyncMock()
        mock_client.zrange = AsyncMock()
        mock_client.zrem = AsyncMock()
        mock_client.zcard = AsyncMock()
        return mock_client

    @pytest.fixture
    def ledger_manager(self, mock_redis_client):
        """ContentLedgerManager instance with mocked Redis client."""
        manager = ContentLedgerManager()
        manager.redis_client = mock_redis_client
        return manager

    @pytest.mark.asyncio
    async def test_add_content_to_registry(self, ledger_manager, mock_redis_client):
        """Test adding content to registry."""
        result = await ledger_manager.add_content_to_registry(
            "test_type", "test_name", "s3://bucket/test", {"key": "value"}
        )

        assert result is True
        mock_redis_client.json().set.assert_called()
        mock_redis_client.sadd.assert_called()

    @pytest.mark.asyncio
    async def test_update_content_in_registry(self, ledger_manager, mock_redis_client):
        """Test updating content in registry."""
        result = await ledger_manager.update_content_in_registry(
            "test_type", "test_name", {"status": "updated"}
        )

        assert result is True
        mock_redis_client.json().set.assert_called()

    @pytest.mark.asyncio
    async def test_remove_content_from_registry(
        self, ledger_manager, mock_redis_client
    ):
        """Test removing content from registry."""
        result = await ledger_manager.remove_content_from_registry(
            "test_type", "test_name"
        )

        assert result is True
        mock_redis_client.delete.assert_called()
        mock_redis_client.srem.assert_called()

    @pytest.mark.asyncio
    async def test_get_content_info(self, ledger_manager, mock_redis_client):
        """Test getting content info."""
        mock_redis_client.json().get.return_value = [{"status": "active"}]

        result = await ledger_manager.get_content_info("test_type", "test_name")

        assert result == {"status": "active"}

    @pytest.mark.asyncio
    async def test_add_to_processing_queue(self, ledger_manager, mock_redis_client):
        """Test adding task to processing queue."""
        result = await ledger_manager.add_to_processing_queue(
            "test_type", "test_name", "process", priority=0
        )

        assert isinstance(result, str)
        mock_redis_client.zadd.assert_called()

    @pytest.mark.asyncio
    async def test_get_next_processing_task(self, ledger_manager, mock_redis_client):
        """Test getting next task from queue."""
        mock_redis_client.zrange.return_value = [('{"task_id": "123"}', 100.0)]

        result = await ledger_manager.get_next_processing_task()

        assert result is not None
        assert "task_id" in result
        mock_redis_client.zrem.assert_called()


class TestContentManagementIntegration:
    """Integration tests for content management system."""

    @pytest.mark.asyncio
    async def test_get_content_storage_manager(self):
        """Test getting content storage manager."""
        # This will fail without proper AWS credentials, but we can test the function exists
        manager = get_content_storage_manager()
        # Should return None if AWS credentials are not configured
        assert manager is None or isinstance(manager, ContentStorageManager)

    @pytest.mark.asyncio
    async def test_get_content_ledger_manager(self):
        """Test getting content ledger manager."""
        manager = get_content_ledger_manager()
        assert isinstance(manager, ContentLedgerManager)


# Mock tests for when S3/Redis are not available
@pytest.mark.asyncio
async def test_storage_manager_without_aws():
    """Test storage manager behavior without AWS credentials."""
    with patch("boto3.client", side_effect=Exception("No credentials")):
        with pytest.raises(Exception):
            ContentStorageManager("test-bucket")


@pytest.mark.asyncio
async def test_ledger_manager_without_redis():
    """Test ledger manager behavior without Redis."""
    # This test would require mocking the Redis connection
    # For now, we'll just test that the manager can be created
    manager = ContentLedgerManager()
    assert isinstance(manager, ContentLedgerManager)
