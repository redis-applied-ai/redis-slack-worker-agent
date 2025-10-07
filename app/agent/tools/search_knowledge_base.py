"""
Knowledge base search tool for the applied-ai-agent.

This module provides the search_knowledge_base tool functionality for RAG operations.
"""

import logging
from typing import Optional

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from redisvl.index.index import AsyncSearchIndex
from redisvl.query import VectorQuery
from redisvl.utils.vectorize import OpenAITextVectorizer

logger = logging.getLogger(__name__)


async def search_knowledge_base(
    index: AsyncSearchIndex,
    vectorizer: OpenAITextVectorizer,
    query: str,
    num_results: int = 5,
) -> str:
    """
    Search the knowledge base using vector similarity.

    Args:
        index: Redis vector search index
        vectorizer: OpenAI text vectorizer
        query: Search query string
        num_results: Number of results to return (default: 5)

    Returns:
        Formatted search results as a string
    """
    try:
        logger.info(f"Searching knowledge base with query: {query}")

        # Generate vector embedding for the query
        query_vector = vectorizer.embed(query, as_buffer=True)

        # Perform vector search
        results = await index.query(
            VectorQuery(
                vector=query_vector,
                vector_field_name="vector",
                return_fields=["name", "description"],
                num_results=num_results,
            )
        )

        # Format results as readable context
        if not results:
            return f"No relevant information found for query: '{query}'"

        # Format results with query context
        context_lines = [f"Search results for '{query}':"]
        for i, result in enumerate(results, 1):
            name = result.get("name", "Unknown")
            description = result.get("description", "No description")
            context_lines.append(f"{i}. {name}: {description}")

        formatted_results = "\n".join(context_lines)
        logger.info(f"Found {len(results)} results for query: {query}")

        return formatted_results

    except Exception as e:
        logger.error(f"Error searching knowledge base: {e}")
        return f"Error searching knowledge base: {str(e)}"


async def search_knowledge_base_with_metadata(
    index: AsyncSearchIndex,
    vectorizer: OpenAITextVectorizer,
    query: str,
    num_results: int = 5,
    return_fields: Optional[list] = None,
) -> list[dict]:
    """
    Search the knowledge base and return raw results with metadata.

    Args:
        index: Redis vector search index
        vectorizer: OpenAI text vectorizer
        query: Search query string
        num_results: Number of results to return (default: 5)
        return_fields: Fields to return from the index (default: ["name", "description"])

    Returns:
        List of search results with metadata
    """
    try:
        logger.info(f"Searching knowledge base with metadata for query: {query}")

        # Default return fields
        if return_fields is None:
            return_fields = ["name", "description"]

        # Generate vector embedding for the query
        query_vector = vectorizer.embed(query, as_buffer=True)

        # Perform vector search
        results = await index.query(
            VectorQuery(
                vector=query_vector,
                vector_field_name="vector",
                return_fields=return_fields,
                num_results=num_results,
            )
        )

        logger.info(f"Found {len(results)} results with metadata for query: {query}")
        return results

    except Exception as e:
        logger.error(f"Error searching knowledge base with metadata: {e}")
        return []


def get_search_tool_config() -> dict:
    """
    Get the tool configuration for the search_knowledge_base tool.

    Returns:
        Dictionary containing the tool configuration
    """
    return {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search the Redis AI knowledge base for specific information. Use this when you need details about Redis AI features, implementations, or specific use cases.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to find relevant information. Be specific about what you're looking for (e.g., 'vector database performance', 'semantic caching implementation', 'agent memory patterns').",
                    }
                },
                "required": ["query"],
            },
        },
    }


def get_search_knowledge_base_tool() -> ChatCompletionToolParam:
    """Get the knowledge base search tool configuration."""
    return ChatCompletionToolParam(get_search_tool_config())
