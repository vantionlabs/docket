"""The document agent: PydanticAI, structured GroundedAnswer output.

The model comes from `app.llm.providers.chat_model()` (openai / anthropic /
azure via config), so swapping provider is a config change, not a code
change. The agent is a lazily-built module singleton; each turn runs with
fresh AgentDeps.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from app.agent.deps import AgentDeps
from app.agent.output import GroundedAnswer
from app.agent.tools import read_chunk, search_documents
from app.config import settings
from app.llm.providers import chat_model, model_settings

_INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text()


@lru_cache
def get_agent() -> Agent[AgentDeps, GroundedAnswer]:
    agent: Agent[AgentDeps, GroundedAnswer] = Agent(
        chat_model(),
        model_settings=model_settings(),
        deps_type=AgentDeps,
        output_type=GroundedAnswer,
        instructions=_INSTRUCTIONS,
    )
    agent.tool(search_documents)
    agent.tool(read_chunk)
    return agent


def run_turn(question: str, history: list[dict], deps: AgentDeps) -> GroundedAnswer:
    """Run one turn synchronously (called from a worker thread).

    `history` is a list of {"role": "user"|"assistant", "content": str}
    prior messages, folded into the prompt for conversational context.
    """
    prompt = question
    if history:
        lines = [f"{m['role']}: {m['content']}" for m in history[-10:]]
        prompt = "Conversation so far:\n" + "\n".join(lines) + f"\n\nuser: {question}"

    result = get_agent().run_sync(
        prompt,
        deps=deps,
        usage_limits=UsageLimits(request_limit=settings.agent_request_limit),
    )
    _record_agent_usage(result, deps)
    return result.output


def _record_agent_usage(result, deps: AgentDeps) -> None:
    from app.observability.usage import record_run_usage

    record_run_usage(
        result, operation="chat", model=settings.chat_model, user_id=deps.user_id
    )
