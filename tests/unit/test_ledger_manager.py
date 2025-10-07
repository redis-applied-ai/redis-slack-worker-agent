"""
Tests for ETL ledger manager.

This module tests the ledger management functionality including:
- Getting and setting ledger data
- Adding/removing content items
- JSON storage in Redis
- CRUD operations for repos, blogs, and notebooks
"""

from unittest.mock import AsyncMock, Mock

import pytest

from app.etl.ledger_manager import ETLedgerManager, get_etl_ledger_manager


class TestETLedgerManager:
    """Test cases for ETL ledger manager."""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client."""
        client = AsyncMock()
        json_mock = Mock()
        json_mock.get = AsyncMock()
        json_mock.set = AsyncMock()
        client.json = Mock(return_value=json_mock)
        return client

    @pytest.fixture
    def ledger_manager(self, mock_redis_client):
        """ETL ledger manager with mocked Redis client."""
        manager = ETLedgerManager()
        manager.redis_client = mock_redis_client
        return manager

    @pytest.fixture
    def sample_ledger_data(self):
        """Sample ledger data for testing."""
        return {
            "repos": [
                {"name": "test-repo", "github_url": "https://github.com/user/test-repo"}
            ],
            "blogs": [
                {"name": "test-blog", "blog_url": "https://example.com/test-blog"}
            ],
            "notebooks": [
                {
                    "name": "test-notebook",
                    "github_url": "https://github.com/user/repo/blob/main/notebook.ipynb",
                }
            ],
        }

    @pytest.fixture
    def empty_ledger_data(self):
        """Empty ledger data for testing."""
        return {"repos": [], "blogs": [], "notebooks": []}

    def test_get_etl_ledger_manager(self):
        """Test getting ETL ledger manager instance."""
        manager = get_etl_ledger_manager()
        assert isinstance(manager, ETLedgerManager)

    @pytest.mark.asyncio
    async def test_get_ledger_success(
        self, ledger_manager, sample_ledger_data, mock_redis_client
    ):
        """Test successful ledger retrieval."""
        mock_redis_client.json.return_value.get.return_value = sample_ledger_data

        result = await ledger_manager.get_ledger()

        assert result == sample_ledger_data
        mock_redis_client.json.return_value.get.assert_called_once_with(
            "etl:content_ledger"
        )

    @pytest.mark.asyncio
    async def test_get_ledger_empty(
        self, ledger_manager, empty_ledger_data, mock_redis_client
    ):
        """Test getting empty ledger."""
        mock_redis_client.json.return_value.get.return_value = None

        result = await ledger_manager.get_ledger()

        assert result == empty_ledger_data

    @pytest.mark.asyncio
    async def test_get_ledger_error(self, ledger_manager, mock_redis_client):
        """Test ledger retrieval error."""
        mock_redis_client.json.return_value.get.side_effect = Exception("Redis error")

        with pytest.raises(Exception, match="Redis error"):
            await ledger_manager.get_ledger()

    @pytest.mark.asyncio
    async def test_update_ledger_success(
        self, ledger_manager, sample_ledger_data, mock_redis_client
    ):
        """Test successful ledger update."""
        result = await ledger_manager.update_ledger(sample_ledger_data)

        assert result is True
        mock_redis_client.json.return_value.set.assert_called_once_with(
            "etl:content_ledger", "$", sample_ledger_data
        )

    @pytest.mark.asyncio
    async def test_update_ledger_error(
        self, ledger_manager, sample_ledger_data, mock_redis_client
    ):
        """Test ledger update error."""
        mock_redis_client.json.return_value.set.side_effect = Exception("Redis error")

        with pytest.raises(Exception, match="Redis error"):
            await ledger_manager.update_ledger(sample_ledger_data)

    @pytest.mark.asyncio
    async def test_add_repo_to_ledger_success(self, ledger_manager, mock_redis_client):
        """Test successful repo addition."""
        mock_redis_client.json.return_value.get.return_value = {
            "repos": [],
            "blogs": [],
            "notebooks": [],
        }

        result = await ledger_manager.add_repo_to_ledger(
            "new-repo", "https://github.com/user/new-repo"
        )

        assert result is True
        mock_redis_client.json.return_value.set.assert_called_once()

        # Check the updated ledger data
        call_args = mock_redis_client.json.return_value.set.call_args
        ledger_data = call_args[0][2]
        assert len(ledger_data["repos"]) == 1
        assert ledger_data["repos"][0]["name"] == "new-repo"
        assert (
            ledger_data["repos"][0]["github_url"] == "https://github.com/user/new-repo"
        )

    @pytest.mark.asyncio
    async def test_add_repo_to_ledger_duplicate(
        self, ledger_manager, mock_redis_client
    ):
        """Test adding duplicate repo."""
        existing_ledger = {
            "repos": [
                {
                    "name": "existing-repo",
                    "github_url": "https://github.com/user/existing-repo",
                }
            ],
            "blogs": [],
            "notebooks": [],
        }
        mock_redis_client.json.return_value.get.return_value = existing_ledger

        result = await ledger_manager.add_repo_to_ledger(
            "existing-repo", "https://github.com/user/existing-repo"
        )

        assert result is True  # Current implementation returns True for duplicate

    @pytest.mark.asyncio
    async def test_add_blog_to_ledger_success(self, ledger_manager, mock_redis_client):
        """Test successful blog addition."""
        mock_redis_client.json.return_value.get.return_value = {
            "repos": [],
            "blogs": [],
            "notebooks": [],
        }

        result = await ledger_manager.add_blog_to_ledger(
            "new-blog", "https://example.com/new-blog"
        )

        assert result is True
        mock_redis_client.json.return_value.set.assert_called_once()

        # Check the updated ledger data
        call_args = mock_redis_client.json.return_value.set.call_args
        ledger_data = call_args[0][2]
        assert len(ledger_data["blogs"]) == 1
        assert ledger_data["blogs"][0]["name"] == "new-blog"
        assert ledger_data["blogs"][0]["blog_url"] == "https://example.com/new-blog"

    @pytest.mark.asyncio
    async def test_add_notebook_to_ledger_success(
        self, ledger_manager, mock_redis_client
    ):
        """Test successful notebook addition."""
        mock_redis_client.json.return_value.get.return_value = {
            "repos": [],
            "blogs": [],
            "notebooks": [],
        }

        result = await ledger_manager.add_notebook_to_ledger(
            "new-notebook", "https://github.com/user/repo/blob/main/new-notebook.ipynb"
        )

        assert result is True
        mock_redis_client.json.return_value.set.assert_called_once()

        # Check the updated ledger data
        call_args = mock_redis_client.json.return_value.set.call_args
        ledger_data = call_args[0][2]
        assert len(ledger_data["notebooks"]) == 1
        assert ledger_data["notebooks"][0]["name"] == "new-notebook"
        assert (
            ledger_data["notebooks"][0]["github_url"]
            == "https://github.com/user/repo/blob/main/new-notebook.ipynb"
        )

    @pytest.mark.asyncio
    async def test_remove_repo_from_ledger_success(
        self, ledger_manager, mock_redis_client
    ):
        """Test successful repo removal."""
        existing_ledger = {
            "repos": [
                {
                    "name": "repo-to-remove",
                    "github_url": "https://github.com/user/repo-to-remove",
                }
            ],
            "blogs": [],
            "notebooks": [],
        }
        mock_redis_client.json.return_value.get.return_value = existing_ledger

        result = await ledger_manager.remove_repo_from_ledger("repo-to-remove")

        assert result is True
        mock_redis_client.json.return_value.set.assert_called_once()

        # Check the updated ledger data
        call_args = mock_redis_client.json.return_value.set.call_args
        ledger_data = call_args[0][2]
        assert len(ledger_data["repos"]) == 0

    @pytest.mark.asyncio
    async def test_remove_repo_from_ledger_not_found(
        self, ledger_manager, mock_redis_client
    ):
        """Test removing non-existent repo."""
        existing_ledger = {
            "repos": [
                {
                    "name": "existing-repo",
                    "github_url": "https://github.com/user/existing-repo",
                }
            ],
            "blogs": [],
            "notebooks": [],
        }
        mock_redis_client.json.return_value.get.return_value = existing_ledger

        result = await ledger_manager.remove_repo_from_ledger("non-existent-repo")

        assert result is True  # Current implementation returns True regardless

    @pytest.mark.asyncio
    async def test_remove_blog_from_ledger_success(
        self, ledger_manager, mock_redis_client
    ):
        """Test successful blog removal."""
        existing_ledger = {
            "repos": [],
            "blogs": [
                {
                    "name": "blog-to-remove",
                    "blog_url": "https://example.com/blog-to-remove",
                }
            ],
            "notebooks": [],
        }
        mock_redis_client.json.return_value.get.return_value = existing_ledger

        result = await ledger_manager.remove_blog_from_ledger("blog-to-remove")

        assert result is True
        mock_redis_client.json.return_value.set.assert_called_once()

        # Check the updated ledger data
        call_args = mock_redis_client.json.return_value.set.call_args
        ledger_data = call_args[0][2]
        assert len(ledger_data["blogs"]) == 0

    @pytest.mark.asyncio
    async def test_remove_notebook_from_ledger_success(
        self, ledger_manager, mock_redis_client
    ):
        """Test successful notebook removal."""
        existing_ledger = {
            "repos": [],
            "blogs": [],
            "notebooks": [
                {
                    "name": "notebook-to-remove",
                    "github_url": "https://github.com/user/repo/blob/main/notebook-to-remove.ipynb",
                }
            ],
        }
        mock_redis_client.json.return_value.get.return_value = existing_ledger

        result = await ledger_manager.remove_notebook_from_ledger("notebook-to-remove")

        assert result is True
        mock_redis_client.json.return_value.set.assert_called_once()

        # Check the updated ledger data
        call_args = mock_redis_client.json.return_value.set.call_args
        ledger_data = call_args[0][2]
        assert len(ledger_data["notebooks"]) == 0

    @pytest.mark.asyncio
    async def test_seed_ledger_with_sample_content_success(
        self, ledger_manager, mock_redis_client
    ):
        """Test successful ledger seeding with sample content."""
        mock_redis_client.json.return_value.get.return_value = {
            "repos": [],
            "blogs": [],
            "notebooks": [],
        }

        result = await ledger_manager.seed_ledger_with_sample_content()

        assert result is True
        # Should be called multiple times: once for blog, once for notebook, and once for final update
        assert mock_redis_client.json.return_value.set.call_count >= 2

    @pytest.mark.asyncio
    async def test_seed_ledger_with_sample_content_error(
        self, ledger_manager, mock_redis_client
    ):
        """Test ledger seeding with error."""
        mock_redis_client.json.return_value.get.side_effect = Exception("Redis error")

        with pytest.raises(Exception, match="Redis error"):
            await ledger_manager.seed_ledger_with_sample_content()

    @pytest.mark.asyncio
    async def test_ledger_data_structure_consistency(
        self, ledger_manager, mock_redis_client
    ):
        """Test that ledger data structure is consistent across operations."""
        # Start with empty ledger
        mock_redis_client.json.return_value.get.return_value = {
            "repos": [],
            "blogs": [],
            "notebooks": [],
        }

        # Add one item of each type
        await ledger_manager.add_repo_to_ledger(
            "test-repo", "https://github.com/user/test-repo"
        )
        await ledger_manager.add_blog_to_ledger(
            "test-blog", "https://example.com/test-blog"
        )
        await ledger_manager.add_notebook_to_ledger(
            "test-notebook",
            "https://github.com/user/repo/blob/main/test-notebook.ipynb",
        )

        # Check that all operations maintained the correct structure
        assert mock_redis_client.json.return_value.set.call_count == 3

        # Verify the final ledger structure
        final_call = mock_redis_client.json.return_value.set.call_args_list[-1]
        final_ledger = final_call[0][2]

        assert "repos" in final_ledger
        assert "blogs" in final_ledger
        assert "notebooks" in final_ledger
        assert isinstance(final_ledger["repos"], list)
        assert isinstance(final_ledger["blogs"], list)
        assert isinstance(final_ledger["notebooks"], list)
        assert len(final_ledger["repos"]) == 1
        assert len(final_ledger["blogs"]) == 1
        assert len(final_ledger["notebooks"]) == 1
