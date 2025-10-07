import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

logger = logging.getLogger(__name__)

load_dotenv()


class TavilySearchService:
    """Web search service using Tavily API - optimized for AI applications."""

    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")
        self._client = None
        self._executor = ThreadPoolExecutor(max_workers=4)

        if not self.api_key:
            logger.warning("TAVILY_API_KEY not found in environment variables")

    @property
    def client(self):
        """Lazy-load the Tavily client."""
        if self._client is None:
            try:
                from tavily import TavilyClient

                self._client = TavilyClient(api_key=self.api_key)
            except ImportError:
                logger.error(
                    "tavily-python package not installed. Run: pip install tavily-python"
                )
                raise ImportError(
                    "tavily-python package required. Install with: pip install tavily-python"
                )
        return self._client

    async def search(
        self,
        query: str,
        search_depth: str = "basic",  # "basic" or "advanced"
        max_results: int = 5,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        include_answer: bool = True,
        include_raw_content: bool = False,
    ) -> Dict[str, Any]:
        """
        Perform web search using Tavily API.

        Args:
            query: Search query
            search_depth: "basic" (faster) or "advanced" (more thorough)
            max_results: Maximum number of results to return
            include_domains: List of domains to include in search
            exclude_domains: List of domains to exclude from search
            include_answer: Whether to include AI-generated answer
            include_raw_content: Whether to include raw content

        Returns:
            Dictionary containing search results
        """
        if not self.api_key:
            return {
                "error": "Tavily API key not configured",
                "results": [],
                "answer": "Web search is not available - missing API key",
            }

        try:
            # Prepare search parameters
            search_params = {
                "query": query,
                "search_depth": search_depth,
                "max_results": max_results,
                "include_answer": include_answer,
                "include_raw_content": include_raw_content,
            }

            # Add optional parameters
            if include_domains:
                search_params["include_domains"] = include_domains
            if exclude_domains:
                search_params["exclude_domains"] = exclude_domains

            # Run the synchronous Tavily client in a thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                self._executor, lambda: self.client.search(**search_params)
            )

            return self._format_results(response)

        except Exception as e:
            logger.error(f"Tavily API error: {e}")
            return {
                "error": str(e),
                "results": [],
                "answer": "Web search encountered an error",
            }

    def _format_results(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format Tavily API response for our RAG system."""
        formatted_results = []

        # Process search results
        for result in data.get("results", []):
            formatted_result = {
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "content": result.get("content", ""),
                "score": result.get("score", 0.0),
                "published_date": result.get("published_date", ""),
            }
            formatted_results.append(formatted_result)

        return {
            "query": data.get("query", ""),
            "answer": data.get("answer", ""),
            "results": formatted_results,
            "search_depth": data.get("search_depth", "basic"),
            "response_time": data.get("response_time", 0),
            "follow_up_questions": data.get("follow_up_questions", []),
        }

    def close(self):
        """Clean up resources."""
        if self._executor:
            self._executor.shutdown(wait=True)

    def __del__(self):
        """Cleanup on deletion."""
        self.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self.close()

    def format_for_llm(self, search_results: Dict[str, Any]) -> str:
        """Format search results for LLM consumption."""
        if search_results.get("error"):
            return f"Web search error: {search_results['error']}"

        formatted_content = []

        # Add AI-generated answer if available
        if search_results.get("answer"):
            formatted_content.append(f"**Summary**: {search_results['answer']}")
            formatted_content.append("")

        # Add individual search results
        formatted_content.append("**Search Results:**")
        for i, result in enumerate(search_results.get("results", []), 1):
            title = result.get("title", "No title")
            content = result.get("content", "No content")
            url = result.get("url", "")

            # Truncate content if too long
            if len(content) > 300:
                content = content[:297] + "..."

            formatted_content.append(f"{i}. **{title}**")
            formatted_content.append(f"   {content}")
            formatted_content.append(f"   Source: {url}")
            formatted_content.append("")

        # Add follow-up questions if available
        follow_ups = search_results.get("follow_up_questions", [])
        if follow_ups:
            formatted_content.append("**Related Questions:**")
            for question in follow_ups[:3]:  # Limit to 3 questions
                formatted_content.append(f"- {question}")

        return "\n".join(formatted_content)


# Global instance
_search_service = None


def get_search_service() -> TavilySearchService:
    """Get the global Tavily search service instance."""
    global _search_service
    if _search_service is None:
        _search_service = TavilySearchService()
    return _search_service


async def perform_web_search(
    query: str,
    search_depth: str = "basic",
    max_results: int = 5,
    redis_focused: bool = True,
) -> str:
    """
    Perform web search optimized for Redis AI questions.

    Args:
        query: Search query
        search_depth: "basic" or "advanced"
        max_results: Number of results to return
        redis_focused: Whether to focus on Redis/database-related domains

    Returns:
        Formatted search results as string
    """
    service = get_search_service()

    # Optimize search for Redis/database content if requested
    include_domains = None
    if redis_focused and any(
        term in query.lower() for term in ["redis", "database", "vector", "ai", "ml"]
    ):
        include_domains = [
            "redis.io",
            "docs.redis.com",
            "developer.redis.com",
            "redis.com",
            "github.com",
            "stackoverflow.com",
            "medium.com",
            "dev.to",
            "arxiv.org",
        ]

    # Perform the search
    results = await service.search(
        query=query,
        search_depth=search_depth,
        max_results=max_results,
        include_domains=include_domains,
        include_answer=True,
        include_raw_content=False,
    )

    # Format for LLM
    formatted_results = service.format_for_llm(results)

    # Log search metrics
    if not results.get("error"):
        logger.info(
            f"Web search completed: query='{query}', results={len(results.get('results', []))}, response_time={results.get('response_time', 0)}ms"
        )

    return formatted_results


# For backwards compatibility and easy import
async def search_web(query: str) -> str:
    """Simple web search function - backwards compatible."""
    return await perform_web_search(query)


def get_web_search_tool() -> ChatCompletionToolParam:
    """Get the web search tool configuration."""
    return ChatCompletionToolParam(
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for current information. Use this when you need real-time data, recent developments, or information not in the knowledge base.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to find current information",
                        }
                    },
                    "required": ["query"],
                },
            },
        }
    )
