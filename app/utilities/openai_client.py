import logging
from typing import Optional

from opentelemetry import trace

from app.utilities.metrics import get_token_metrics

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class InstrumentedOpenAIClient:
    """OpenAI client wrapper with instrumentation."""

    def __init__(self):
        import openai

        self._client = openai.OpenAI()

    def chat(self):
        return InstrumentedChatCompletions(self._client.chat)

    def embeddings(self):
        return self._client.embeddings

    def models(self):
        return self._client.models


class InstrumentedChatCompletions:
    """Chat completions wrapper with token usage tracking."""

    def __init__(self, chat_completions):
        self._chat_completions = chat_completions

    def create(self, *args, **kwargs):
        """Create a chat completion with token usage tracking."""
        response = self._chat_completions.create(*args, **kwargs)

        # Record token usage if available
        if response.usage:
            try:
                token_metrics = get_token_metrics()
                if token_metrics:
                    token_metrics.record_answer_completion(
                        model=kwargs.get("model", "unknown"),
                        total_tokens=response.usage.total_tokens or 0,
                        tool_calls=(
                            len(response.choices[0].message.tool_calls)
                            if response.choices[0].message.tool_calls
                            else 0
                        ),
                    )
            except Exception as e:
                logger.warning(f"Failed to record token usage: {e}")

        return response


# Global client instance
_client: Optional[InstrumentedOpenAIClient] = None


def get_instrumented_client() -> InstrumentedOpenAIClient:
    """Get an instrumented OpenAI client."""
    return InstrumentedOpenAIClient()
