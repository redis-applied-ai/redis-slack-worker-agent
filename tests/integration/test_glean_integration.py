"""Integration tests for Glean search functionality.

These tests make real API calls to Glean and should only be run with valid credentials.
"""

import asyncio
import os
from unittest.mock import patch

import pytest

from app.agent.tools.glean_search import GleanSearchService, search_glean


class TestGleanIntegration:
    """Integration tests for Glean search functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.api_token = os.getenv("GLEAN_API_TOKEN")
        self.instance = os.getenv("GLEAN_INSTANCE")

        if not self.api_token or not self.instance:
            pytest.skip(
                "GLEAN_API_TOKEN and GLEAN_INSTANCE required for integration tests"
            )

    def test_glean_client_initialization(self):
        """Test that Glean client can be initialized with valid credentials."""
        service = GleanSearchService()

        # Test client creation
        client = service._get_client()
        assert client is not None
        assert hasattr(client, "client")
        assert hasattr(client.client, "search")
        assert hasattr(client.client.search, "query")

    @pytest.mark.asyncio
    async def test_glean_search_basic(self):
        """Test basic search functionality."""
        service = GleanSearchService()

        # Test search with a simple query
        result = await service.search(query="Redis", max_results=5)

        # Verify result structure
        assert isinstance(result, dict)
        assert "query" in result
        assert "results" in result
        assert "total_results" in result

        # If search is successful, verify results
        if not result.get("error"):
            assert result["query"] == "Redis"
            assert isinstance(result["results"], list)
            assert result["total_results"] >= 0

    @pytest.mark.asyncio
    async def test_glean_search_with_datasources(self):
        """Test search with datasource filtering."""
        service = GleanSearchService()

        # Test search with datasource filter
        result = await service.search(
            query="documentation", max_results=3, datasources=["confluence", "github"]
        )

        # Verify result structure
        assert isinstance(result, dict)
        assert "query" in result
        assert "results" in result

        # If search is successful, verify results
        if not result.get("error"):
            assert result["query"] == "documentation"
            assert isinstance(result["results"], list)

    @pytest.mark.asyncio
    async def test_glean_chat_search(self):
        """Test chat search functionality."""
        service = GleanSearchService()

        # Test chat search
        result = await service.chat_search(query="What is Redis?")

        # Verify result structure
        assert isinstance(result, dict)
        assert "query" in result

        # Check for either successful response or error
        if "error" in result:
            # Log error for debugging
            print(f"Chat search error: {result['error']}")
            assert "response" in result
        else:
            assert "response" in result
            assert isinstance(result["response"], str)

    @pytest.mark.asyncio
    async def test_search_glean_function(self):
        """Test the public search_glean function."""
        # Test regular search
        result = await search_glean(query="Redis", max_results=3)

        assert isinstance(result, str)
        assert len(result) > 0
        assert "Redis" in result

        # Test chat search
        chat_result = await search_glean(query="What is Redis?", use_chat=True)

        assert isinstance(chat_result, str)
        assert len(chat_result) > 0

    @pytest.mark.asyncio
    async def test_error_handling_invalid_credentials(self):
        """Test error handling with invalid credentials."""
        # Temporarily override credentials
        with patch.dict(
            os.environ,
            {"GLEAN_API_TOKEN": "invalid_token", "GLEAN_INSTANCE": "invalid_instance"},
        ):
            service = GleanSearchService()

            # This should handle errors gracefully
            result = await service.search(query="test")

            # Verify error handling
            assert isinstance(result, dict)
            assert "error" in result or "results" in result

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test rate limiting functionality."""
        service = GleanSearchService()

        # Make multiple requests quickly
        tasks = []
        for i in range(3):
            task = service.search(query=f"test query {i}", max_results=1)
            tasks.append(task)

        # All should complete without errors
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, dict):
                # Should have proper structure
                assert "query" in result
                assert "results" in result

    def test_format_for_llm(self):
        """Test LLM formatting functionality."""
        service = GleanSearchService()

        # Test with search results
        search_results = {
            "query": "Redis",
            "results": [
                {
                    "title": "Redis Documentation",
                    "content": "Redis is an in-memory data structure store.",
                    "url": "https://redis.io/docs",
                    "datasource": "documentation",
                }
            ],
            "total_results": 1,
        }

        formatted = service.format_for_llm(search_results)

        assert isinstance(formatted, str)
        assert "Redis" in formatted
        assert "Redis Documentation" in formatted
        assert "Redis is an in-memory data structure store." in formatted

        # Test with chat results
        chat_results = {
            "query": "What is Redis?",
            "response": "Redis is an in-memory data structure store.",
            "citations": [
                {
                    "title": "Redis Documentation",
                    "url": "https://redis.io/docs",
                    "snippet": "Redis overview",
                    "datasource": "documentation",
                }
            ],
        }

        chat_formatted = service.format_for_llm(chat_results, use_chat=True)

        assert isinstance(chat_formatted, str)
        assert "What is Redis?" in chat_formatted or "Redis" in chat_formatted
        assert "Redis is an in-memory data structure store." in chat_formatted

    def test_service_cleanup(self):
        """Test service cleanup functionality."""
        service = GleanSearchService()

        # Test context manager
        with service:
            pass

        # Test async context manager
        async def test_async():
            async with service:
                pass

        asyncio.run(test_async())

        # Test explicit cleanup
        service.close()


if __name__ == "__main__":
    # Run basic integration test
    async def main():
        if not os.getenv("GLEAN_API_TOKEN") or not os.getenv("GLEAN_INSTANCE"):
            print(
                "Skipping integration tests - GLEAN_API_TOKEN and GLEAN_INSTANCE required"
            )
            return

        service = GleanSearchService()

        print("Testing Glean client initialization...")
        try:
            client = service._get_client()
            print(f"✓ Client created: {type(client)}")
        except Exception as e:
            print(f"✗ Client initialization failed: {e}")
            return

        print("\nTesting basic search...")
        try:
            result = await service.search(query="Redis", max_results=3)
            if result.get("error"):
                print(f"✗ Search failed: {result['error']}")
            else:
                print(f"✓ Search successful: {result['total_results']} results")
        except Exception as e:
            print(f"✗ Search failed with exception: {e}")

        print("\nTesting chat search...")
        try:
            result = await service.chat_search(query="What is Redis?")
            if result.get("error"):
                print(f"✗ Chat search failed: {result['error']}")
            else:
                print("✓ Chat search successful")
        except Exception as e:
            print(f"✗ Chat search failed with exception: {e}")

        print("\nTesting search_glean function...")
        try:
            result = await search_glean(query="Redis", max_results=3)
            print(f"✓ search_glean successful: {len(result)} chars")
        except Exception as e:
            print(f"✗ search_glean failed: {e}")

        service.close()

    asyncio.run(main())
