"""
Core agent functionality for the applied-ai-agent.

This module contains the main agent functions for processing questions and managing conversations.
"""

import json
import logging
import os

import openai
from agent_memory_client import MemoryAPIClient
from agent_memory_client.client import create_memory_client
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_tool_message_param import (
    ChatCompletionToolMessageParam,
)
from redisvl.index.index import AsyncSearchIndex
from redisvl.utils.vectorize import OpenAITextVectorizer

from app.agent.tools import get_search_knowledge_base_tool, get_web_search_tool
from app.utilities.bedrock_client import (
    bedrock_text_blocks_to_text,
    get_bedrock_runtime_client,
    map_openai_tools_to_bedrock_tool_config,
)
from app.utilities.openai_client import get_instrumented_client

logger = logging.getLogger(__name__)

# Model configuration
CHAT_MODEL = "gpt-4.1"

# System prompt for the agent
SYSTEM_PROMPT = """
You are the applied AI agent, a polite and knowledgeable member of the Applied AI team at Redis, Inc. You're here to help colleagues with AI/ML questions in a natural, conversational way.

## Read Social Cues & Question Intent

For brief satisfied responses like "sure", "thanks", "yep", "got it":
- These indicate the user is satisfied and done with the conversation
- Respond with ONLY a brief acknowledgment: "Happy to help!" or "You're welcome!"
- DO NOT mention Redis capabilities, features, or ask follow-up questions
- DO NOT offer additional information unless specifically requested

### Examples:
- User: "sure" → You: "Happy to help!"
- User: "thanks, that answers it" → You: "You're welcome!"
- User: "yep, got it" → You: "Great! Let me know if you need anything else."

## When asked about YOUR capabilities as an AI agent:
- Questions like "What can you do?", "What are your capabilities?", "What tools
  do you have?" are about YOU, not Redis - do not answer about Redis's AI capabilities
- Answer ONLY about the tools you can use as an LLM: search_knowledge_base, web_search,
  and tools for using memory (search_memory, get_working_memory,
  add_memory_to_working_memory, update_working_memory_data)
- Keep it simple: "I'm an agentic assistant that can help you understand Redis
  AI capabilities and answer questions about where Redis fits in the AI
  landscape."

## Your Personality
- Ask clarifying questions
- Be conversational and friendly, not robotic or overly formal
- Read social cues - if someone seems overwhelmed, dial it back
- Match the user's tone and energy level
- Don't always push the Redis angle- sometimes people just want general AI information

## Available Tools
You have access to the following tools:
- search_knowledge_base: Search the Redis AI knowledge base for specific information
- web_search: Search the web for current information and recent developments
- search_memory: Find information about users from previous conversations
- get_working_memory: Retrieve current working memory for a thread
- add_memory_to_working_memory: Store long-term memories about users
- update_working_memory_data: Update existing working memory data

## Tool Call Constraints
You can make up to 25 tool calls. This means you are free to call tools as many
times as you need to answer the user's question. You can also call the same tool
multiple times in the same iteration. For example, making subsequent calls to
web_search to find more information.

## When to Use Tools

*Use search_knowledge_base for:*
- Redis features, implementations, best practices
- RedisVL, Agent Memory Server, or other Redis AI tools questions
- Technical details about Redis vector database capabilities

*Use web_search for (often in combination with search_knowledge_base):*
- Questions with recency indicators ("latest", "recent", "current", "new")
- ANY time users provide URLs, links, or reference external websites/documentation
- Unfamiliar tools, products, technologies, or terminology that may not be in our knowledge base
- Technical terms, acronyms, or product names you're unsure about
- Competitor comparisons or market analysis
- Breaking news or recent developments
- Questions about specific external content, GitHub repos, or documentation sites
- When you want to supplement internal knowledge with current web information
- General AI/ML trends and emerging technologies
- Version-specific questions about software releases or updates

*Pro-tip: When in doubt about terminology or external resources, USE BOTH search_knowledge_base AND web_search to provide comprehensive answers.*

*Use memory tools for:*
- Finding information about a user from previous conversations with long-term
  memory (search_memory)
- Storing information about a user in working memory (add_memory_to_working_memory)

## How to Use Memory Tools

- If you include entities with the search_memory tool, use multiple variations:
  e.g. "Andrew Brookins", "Brookins,Andrew", etc.
- IMPORTANT: If you get 0 search results for `search_memory`, try again without
  just the query -- no topics, entities, etc.

## When to use the ReACT response style

**Important**: Only use the formal "Thought/Action/Observation" structure for
genuinely complex questions that require multi-step research. For simple
questions or casual conversation, just respond naturally.

## Response Format

Respond in JSON format with the following keys:

- `response` (string): The response to the user's question
- `use_org_search` (boolean): Whether to search the organization's internal
  knowledge base for additional context to enhance your response. Set this to true
  if you think the response would benefit from additional internal documentation,
  implementation details, best practices, or specific use cases from our organization.

### Examples:

Question: "Does Redis support vector search?"
Response:
```json
{
  "response": "Yes, Redis supports both full-text and vector search, making hybrid search possible. The RedisVL library makes this even easier by providing components you can drop into your Python applications.",
  "use_org_search": false
}
```

Question: "Do we have any public case studies of companies like MicroCorp using Redis?"
Response:
```json
{
  "response": "I couldn't find any public case studies of companies like MicroCorp using web search or by searching my AI-specific knowledge base. I'll do a deeper search to see if I can find more information.",
  "use_org_search": true
}
```

Question: "What are the most common AI use cases for Redis?"
Response:
```json
{
  "response": "The most common AI use cases for Redis are:
  • Vector search
  • Semantic caching
  • Feature stores
  • Agent memory
  • Asynchronous AI tasks
  • Open-source tools: RedisVL, Agent Memory Server, LangChain/LangGraph integrations",
  "use_org_search": true
}
```

## Response Text Guidelines
Within the "response" field, you should follow these guidelines:

### BULLET POINT FORMATTING RULE
ALWAYS use Unicode bullet (•) for bullet points in Slack apps. Markdown bullets
(* or -) don't work in app-generated Slack messages.

#### Organizing Information with Headers
Never use nested bullet points. Instead, use headers to group related information:

#### Redis Performance Features:
• Sub-millisecond response times
• Horizontal scaling capabilities

#### Redis Vector Search Features:
• Native vector indexing
• FLAT and HNSW algorithms available
• Hybrid search capabilities

#### Incorrect Format:
Do not use "* Redis is fast and scalable" or "- Redis is fast and scalable"

### CRITICAL: Always format responses using Slack markdown (mrkdwn) format:

#### Text Formatting:
• Use `*bold*` for bold text (NOT **bold**)
• Use `_italic_` for italic text (not *italic*)
• Use `~strikethrough~` for strikethrough
• Use `code` for inline code
• Use ```code blocks``` for multiline code
• Use `>` for block quotes

#### Bullet Points:
• ALWAYS use Unicode bullet `•` for bullet points, NEVER use `*` or `-`
• Never use nested bullets - use headers to group information instead

#### Links and Structure:
• Format links as `<url|text>` for custom link text
• Use line breaks `\\n` to separate paragraphs

#### Tables:
Use code blocks with preformatted text since Block Kit doesn't support native tables:
```
Feature              | Redis            | Pinecone
--------------------|------------------|------------------
In-memory speed     | Yes (sub-ms)     | No (cloud storage)
Vector search       | Yes (native)     | Yes (purpose-built)
```

### Character Limit:
- Keep all responses under 12,000 characters including Markdown formatting
- Slack markdown blocks have a 12,000 character limit - exceeding this will cause API errors
- Be concise while maintaining helpfulness and accuracy

### For broad questions like "What's new in AI?"
- Ask what specific area they're interested in
- Offer a few options: "Are you thinking about LLMs, vector databases, AI tooling, or something else?"
- Don't immediately dump a Redis-focused response

### When asked about YOUR AI agent capabilities/tools/what you can do:
- If the question is about YOU ("What can you do?", "What are your
  capabilities?", "What tools do you have?"), this is NOT about Redis products
- Answer with ONLY: search_knowledge_base, web_search, research assistance, conversation
- Do NOT search for or mention: vector databases, caching, Redis features, RedisVL, LangCache, feature stores
- Keep responses short and focused on being an AI research assistant
- Wrong: "I can help with Redis vector databases..." Right: "I can search for information and help you research topics"

### For Redis-relevant questions:
- Lead with the direct answer to their question
- Mention relevant Redis capabilities naturally, not as a sales pitch
- Provide practical next steps or resources

### For general AI questions:
- Answer the question directly first
- Only mention Redis if it's genuinely relevant to their specific need
- Focus on being helpful, not promotional

## Example Interactions

*Bad*: "Here's everything about Redis AI capabilities..." (when they asked a broad question)
*Good*: "What area of AI are you most curious about? LLMs, vector search, ML ops, or something else?"

*Bad*: "Redis is the fastest vector database..." (immediately promotional)
*Good*: "For vector search, there are several good options. Redis is
particularly strong for [specific use case]. What's your specific need?"

*For agent capability questions ("What can you do?", "What are your capabilities?", "What tools do you have?"):*
*Bad*: "I can help with Redis vector databases, semantic caching, feature stores..." (describing Redis products)
*Good*: "I'm an AI research assistant. I can search our knowledge base, find current web information, and help you explore topics through conversation. What would you like to know about?"

*Bad*: "I have search tools and can guide you on Redis AI features..." (mixing AI tools with Redis products)
*Good*: "I have two main tools: search_knowledge_base and web_search. I help by finding information and answering questions."

## Redis Context (mention naturally when relevant)
- Vector database with strong performance
- Semantic caching (including upcoming LangCache)
- Feature store capabilities
- Agent memory solutions
- Orchestrate asynchronous AI tasks with streams
- Open-source tools: RedisVL, Agent Memory Server, LangChain/LangGraph integrations

Be helpful first, Redis-focused second. Build relationships through genuine assistance, not constant promotion.
"""

# Global variables for client management
_client: openai.OpenAI | None = None
_memory_client: MemoryAPIClient | None = None


def get_client() -> openai.OpenAI:
    """Get or create OpenAI client with instrumentation."""
    return get_instrumented_client()._client


async def get_memory_client() -> MemoryAPIClient:
    """Get or create memory client."""
    global _memory_client
    if _memory_client is None:
        _memory_client = await create_memory_client(
            base_url=os.environ.get("AGENT_MEMORY_SERVER_URL", "http://localhost:8000"),
        )
        if os.environ.get("AGENT_MEMORY_SERVER_API_KEY", None) is not None:
            _memory_client._client.headers["Authorization"] = (
                f"Bearer {os.environ.get('AGENT_MEMORY_SERVER_API_KEY')}"
            )
    return _memory_client


async def answer_question(
    index: AsyncSearchIndex,
    vectorizer: OpenAITextVectorizer,
    query: str,
    session_id: str,
    user_id: str,
    thread_context: list[dict] | None = None,
    progress_callback=None,
) -> str:
    """Answer the user's question using agentic RAG with iterative search and thread context

    Args:
        index: Redis vector search index
        vectorizer: OpenAI text vectorizer
        query: User's question
        session_id: Required session identifier for the conversation
        user_id: Required Slack user ID - ensures proper data isolation
        thread_context: Optional conversation context
        progress_callback: Optional callback function to send progress updates
    """
    # Provider toggle: route to Bedrock implementation when requested
    provider = os.getenv("LLM_PROVIDER", "bedrock").lower()
    if provider == "bedrock":
        return await answer_question_bedrock(
            index=index,
            vectorizer=vectorizer,
            query=query,
            session_id=session_id,
            user_id=user_id,
            thread_context=thread_context,
            progress_callback=progress_callback,
        )

    # Get the underlying OpenAI client for direct access
    client = get_instrumented_client()._client

    # Create initial message with just the query and thread history - let the
    # model decide if it needs retrieval
    initial_message = create_initial_message_without_search(query, thread_context)

    # Convert None to empty list for internal processing after creating the message
    if thread_context is None:
        thread_context = []

    # Start conversation with tool calling enabled
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": initial_message},
    ]

    max_iterations = 25  # Limit iterations to prevent infinite loops
    iteration = 0
    tools = [
        get_search_knowledge_base_tool(),
        get_web_search_tool(),
        *MemoryAPIClient.get_all_memory_tool_schemas(),
    ]

    logger.info(f"Using LLM provider=openai model={CHAT_MODEL}")

    logger.info(f"Available tools: {[tool['function']['name'] for tool in tools]}")

    # Track total tokens and tool calls across all iterations
    total_tokens = 0
    total_tool_calls = 0

    while iteration < max_iterations:
        iteration += 1
        logger.info(
            f"Iteration {iteration}: Calling OpenAI with {len(messages)} messages"
        )

        # Use the standard OpenAI client structure
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.1,
            seed=42,
        )

        # Track token usage from this response
        if response.usage:
            total_tokens += response.usage.total_tokens or 0

        message: ChatCompletionMessage = response.choices[0].message
        messages.append(message.model_dump())  # type: ignore

        # Check if the model wants to use tools
        if message.tool_calls:
            total_tool_calls += len(message.tool_calls)
            logger.info(f"Model wants to make {len(message.tool_calls)} tool calls")

            for tool_call in message.tool_calls:
                if tool_call.function.name == "search_knowledge_base":
                    # Notify user we're searching internal knowledge
                    if progress_callback:
                        await progress_callback("Searching knowledge base...")

                    # Parse the search query
                    try:
                        args = json.loads(tool_call.function.arguments)
                        search_query = args.get("query", "")
                        logger.info(f"Performing knowledge base search: {search_query}")

                        # Perform the search using the dedicated tool
                        from app.agent.tools.search_knowledge_base import (
                            search_knowledge_base,
                        )

                        search_results = await search_knowledge_base(
                            index, vectorizer, search_query
                        )

                        # Add tool result to conversation
                        tool_message: ChatCompletionToolMessageParam = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": search_results,
                        }
                        messages.append(tool_message)

                    except json.JSONDecodeError:
                        # Handle malformed tool arguments
                        tool_message: ChatCompletionToolMessageParam = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": "Error: Could not parse search query",
                        }
                        messages.append(tool_message)

                elif tool_call.function.name == "web_search":
                    # Notify user we're searching the web
                    if progress_callback:
                        await progress_callback("Searching the web...")

                    try:
                        from app.agent.tools.web_search import perform_web_search

                        args = json.loads(tool_call.function.arguments)
                        search_query = args.get("query", "")
                        logger.info(f"Performing web search: {search_query}")

                        search_results = await perform_web_search(
                            query=search_query,
                            search_depth="basic",
                            max_results=5,
                            redis_focused=True,
                        )

                        if progress_callback:
                            await progress_callback("Analyzing results...")

                        tool_message: ChatCompletionToolMessageParam = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": search_results,
                        }
                        messages.append(tool_message)

                    except json.JSONDecodeError:
                        # Handle malformed tool arguments
                        tool_message: ChatCompletionToolMessageParam = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": "Error: Could not parse web search query",
                        }
                        messages.append(tool_message)
                    except Exception as e:
                        # Handle web search errors gracefully
                        logger.error(f"Web search error: {e}")
                        tool_message: ChatCompletionToolMessageParam = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": f"Web search encountered an error: {str(e)}. Please try rephrasing your question or rely on the knowledge base.",
                        }
                        messages.append(tool_message)
                else:
                    if progress_callback:
                        await progress_callback("Using memory tools...")

                    # Handle memory tools
                    memory_client = await get_memory_client()

                    try:
                        # Parse the LLM's arguments
                        args = json.loads(tool_call.function.arguments)

                        # CRITICAL: Always enforce the user_id in memory tool calls
                        # This ensures we never leave user association to chance
                        memory_tool_names = {
                            "search_memory",
                            "add_memory_to_working_memory",
                            "update_working_memory_data",
                            "get_working_memory",
                            "search_long_term_memory",
                            "memory_prompt",
                            "set_working_memory",
                        }

                        if tool_call.function.name in memory_tool_names:
                            # Force the user_id to always be the actual Slack user ID
                            args["user_id"] = user_id
                            logger.info(
                                f"Enforced user_id={user_id} for {tool_call.function.name}"
                            )

                        # Create function call object with enforced arguments
                        function_call = {
                            "name": tool_call.function.name,
                            "arguments": json.dumps(args),  # Use our modified args
                        }

                        # Execute the memory tool call using resolve_tool_call
                        result = await memory_client.resolve_tool_call(
                            tool_call=function_call,
                            session_id=session_id,
                            user_id=user_id,
                        )

                        if result["success"]:
                            tool_content = str(result)
                        else:
                            tool_content = f"Memory operation failed: {result.get('error', 'Unknown error')}"

                        # Add reflection instructions to the tool content
                        tool_content += "\n\nReflect on this memory tool result and your instructions about how to use memory tools. Make subsequent memory tool calls if necessary."

                        tool_message: ChatCompletionToolMessageParam = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_content,
                        }
                        messages.append(tool_message)

                    except json.JSONDecodeError:
                        # Handle malformed tool arguments
                        tool_message: ChatCompletionToolMessageParam = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": f"Error: Could not parse arguments for {tool_call.function.name}",
                        }
                        messages.append(tool_message)
                    except Exception as e:
                        # Handle memory tool errors gracefully
                        logger.error(f"Memory tool error: {e}")
                        tool_message: ChatCompletionToolMessageParam = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": f"Memory tool encountered an error: {str(e)}",
                        }
                        messages.append(tool_message)

        # Continue to next iteration if there were tool calls
        if message.tool_calls:
            continue

        # No tool calls, we have the final response
        break
    # Extract the response content
    response_content = ""
    if message.content:
        if isinstance(message.content, list):
            parts = []
            for item in message.content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(item.get("text", ""))
                    elif item.get("refusal"):
                        parts.append(item.get("refusal", ""))
                    else:
                        parts.append(str(item))
                elif isinstance(item, str):
                    parts.append(item)
            response_content = "\n".join(parts)
        else:
            response_content = str(message.content)

    # Parse the LLM response to get the text and org search decision
    response_text, use_org_search = _parse_llm_response(response_content)

    # If LLM decided to use org search, enhance the response
    if use_org_search:
        logger.info("LLM wanted to use org search, but org search is disabled")

    # Record metrics for this answer completion
    try:
        from app.utilities.metrics import get_token_metrics

        token_metrics = get_token_metrics()
        if token_metrics:
            token_metrics.record_answer_completion(
                model=CHAT_MODEL, total_tokens=total_tokens, tool_calls=total_tool_calls
            )
            logger.info(
                f"Recorded metrics for answer completion: model={CHAT_MODEL}, tokens={total_tokens}, tool_calls={total_tool_calls}"
            )
    except Exception as e:
        logger.warning(f"Failed to record metrics for answer completion: {e}")

    return response_text


def create_initial_message_without_search(
    query: str, thread_context: list[dict] | None = None
) -> str:
    """Create the initial message with user query and thread context, letting the model decide if it needs retrieval"""
    thread_history = ""
    if thread_context:
        thread_history = "\n\nSlack thread conversation history:\n"
        for msg in thread_context:
            thread_history += f"{msg['user']}: {msg['text']}\n"

    return f"""User question: {query}
{thread_history}

Please answer the user's question. If you need specific information to provide a
comprehensive answer, use the search_knowledge_base tool to gather relevant
information. To research a topic or find current information not in our
knowledge base, use the web_search tool. Use your memory tools to find
information about the user from past conversations and store memories
about the user for future conversations in working memory.
"""


def is_brief_satisfied_response(text: str) -> bool:
    """Check if a response is brief and indicates satisfaction/completion."""
    brief_satisfied_responses = [
        "sure",
        "thanks",
        "yep",
        "got it",
        "ok",
        "okay",
        "perfect",
        "great",
        "awesome",
        "cool",
        "sounds good",
        "thank you",
    ]
    return text.lower().strip() in brief_satisfied_responses


def _parse_llm_response(content: str) -> tuple[str, bool]:
    """Parse LLM response to extract response text and org search decision.

    Args:
        content: The LLM response content

    Returns:
        Tuple of (response_text, use_org_search)
    """
    try:
        json_content = json.loads(content)
        response_text = json_content.get("response", "")
        use_org_search = json_content.get("use_org_search", False)
        return response_text, use_org_search
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        import re

        json_match = re.search(r"```json\s*\n(.*?)\n```", content, re.DOTALL)
        if json_match:
            try:
                json_content = json.loads(json_match.group(1))
                response_text = json_content.get("response", "")
                use_org_search = json_content.get("use_org_search", False)
                return response_text, use_org_search
            except json.JSONDecodeError:
                pass

        # If JSON parsing fails, treat as plain text response and don't enhance
        logger.warning(f"Failed to parse LLM response as JSON: {content[:100]}...")
        return content, False
    except Exception as e:
        logger.error(f"Error parsing LLM response: {e}")
        return content, False


async def answer_question_bedrock(
    index: AsyncSearchIndex,
    vectorizer: OpenAITextVectorizer,
    query: str,
    session_id: str,
    user_id: str,
    thread_context: list[dict] | None = None,
    progress_callback=None,
) -> str:
    """Bedrock-based implementation of the agent loop using Converse API with tools."""
    client = get_bedrock_runtime_client()
    model_id = os.getenv(
        "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0"
    )
    logger.info(f"Using LLM provider=bedrock model={model_id}")

    initial_message = create_initial_message_without_search(query, thread_context)
    bedrock_messages: list[dict] = [
        {"role": "user", "content": [{"text": initial_message}]}
    ]

    tools_openai = [
        get_search_knowledge_base_tool(),
        get_web_search_tool(),
        *MemoryAPIClient.get_all_memory_tool_schemas(),
    ]
    tool_config = map_openai_tools_to_bedrock_tool_config(tools_openai)

    max_iterations = 25
    iteration = 0
    total_tokens = 0
    total_tool_calls = 0

    while iteration < max_iterations:
        iteration += 1
        response = client.converse(
            modelId=model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=bedrock_messages,
            toolConfig=tool_config,
        )

        usage = response.get("usage") or {}
        total_tokens += int(usage.get("inputTokens", 0)) + int(
            usage.get("outputTokens", 0)
        )

        output_message = response.get("output", {}).get("message", {})
        stop_reason = response.get("stopReason")

        if stop_reason == "tool_use":
            # Collect toolUse requests and produce toolResult blocks
            tool_result_blocks: list[dict] = []
            if progress_callback:
                await progress_callback("Using tools...")

            for block in output_message.get("content", []) or []:
                tool_use = block.get("toolUse") if isinstance(block, dict) else None
                if not tool_use:
                    continue
                name = tool_use.get("name")
                tool_use_id = tool_use.get("toolUseId")
                input_payload = tool_use.get("input") or {}
                total_tool_calls += 1

                try:
                    if name == "search_knowledge_base":
                        if progress_callback:
                            await progress_callback("Searching knowledge base...")
                        from app.agent.tools.search_knowledge_base import (
                            search_knowledge_base,
                        )

                        q = (input_payload or {}).get("query", "")
                        result_text = await search_knowledge_base(index, vectorizer, q)
                        tool_result_blocks.append(
                            {
                                "toolResult": {
                                    "toolUseId": tool_use_id,
                                    "content": [{"text": str(result_text)}],
                                    "status": "success",
                                }
                            }
                        )
                    elif name == "web_search":
                        if progress_callback:
                            await progress_callback("Searching the web...")
                        from app.agent.tools.web_search import perform_web_search

                        q = (input_payload or {}).get("query", "")
                        web_res = await perform_web_search(
                            query=q,
                            search_depth="basic",
                            max_results=5,
                            redis_focused=True,
                        )
                        tool_result_blocks.append(
                            {
                                "toolResult": {
                                    "toolUseId": tool_use_id,
                                    "content": [{"text": str(web_res)}],
                                    "status": "success",
                                }
                            }
                        )
                    else:
                        # Memory tools or others resolved via memory client
                        if progress_callback:
                            await progress_callback("Using memory tools...")
                        memory_client = await get_memory_client()
                        # Enforce user_id for memory tools
                        args = dict(input_payload or {})
                        memory_tool_names = {
                            "search_memory",
                            "add_memory_to_working_memory",
                            "update_working_memory_data",
                            "get_working_memory",
                            "search_long_term_memory",
                            "memory_prompt",
                            "set_working_memory",
                        }
                        if name in memory_tool_names:
                            args["user_id"] = user_id
                        function_call = {"name": name, "arguments": json.dumps(args)}
                        mem_res = await memory_client.resolve_tool_call(
                            tool_call=function_call,
                            session_id=session_id,
                            user_id=user_id,
                        )
                        tool_content = (
                            str(mem_res)
                            if isinstance(mem_res, (dict, list))
                            else str(mem_res)
                        )
                        tool_content += "\n\nReflect on this memory tool result and your instructions about how to use memory tools. Make subsequent memory tool calls if necessary."
                        tool_result_blocks.append(
                            {
                                "toolResult": {
                                    "toolUseId": tool_use_id,
                                    "content": [{"text": tool_content}],
                                    "status": "success",
                                }
                            }
                        )
                except Exception as e:
                    logger.error(f"Tool execution error for {name}: {e}")
                    tool_result_blocks.append(
                        {
                            "toolResult": {
                                "toolUseId": tool_use_id,
                                "content": [
                                    {"text": f"Error executing tool {name}: {str(e)}"}
                                ],
                                "status": "error",
                            }
                        }
                    )

            # Append assistant request and our tool results back to the conversation
            bedrock_messages.append(output_message)
            if tool_result_blocks:
                bedrock_messages.append({"role": "user", "content": tool_result_blocks})
            # Continue loop for model to produce next step
            continue

        # No tool use requested; treat as final answer
        final_text = bedrock_text_blocks_to_text(output_message.get("content", []))
        response_text, use_org_search = _parse_llm_response(final_text)
        if use_org_search:
            logger.info("LLM wanted to use org search, but org search is disabled")

        # Metrics
        try:
            from app.utilities.metrics import get_token_metrics

            token_metrics = get_token_metrics()
            if token_metrics:
                token_metrics.record_answer_completion(
                    model=model_id,
                    total_tokens=total_tokens,
                    tool_calls=total_tool_calls,
                )
                logger.info(
                    f"Recorded metrics for answer completion: model={model_id}, tokens={total_tokens}, tool_calls={total_tool_calls}"
                )
        except Exception as e:
            logger.warning(f"Failed to record metrics for answer completion: {e}")

        return response_text

    # Max iterations reached; return last assistant text if any
    last_text = (
        bedrock_text_blocks_to_text(output_message.get("content", []))
        if "output_message" in locals()
        else ""
    )
    return last_text or "I'm sorry, I couldn't complete the request."
