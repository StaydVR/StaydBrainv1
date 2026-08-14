"""Registration surface for the standalone agent-brain Hermes plugin."""

from . import plugin, schemas, tools


def register(ctx) -> None:
    ctx.register_tool(
        name="agent_brain_recall",
        toolset="agent-brain",
        schema=schemas.AGENT_BRAIN_RECALL,
        handler=tools.agent_brain_recall,
    )
    ctx.register_tool(
        name="agent_brain_remember",
        toolset="agent-brain",
        schema=schemas.AGENT_BRAIN_REMEMBER,
        handler=tools.agent_brain_remember,
        check_fn=plugin.writes_available,
    )
    ctx.register_hook("pre_llm_call", plugin.pre_llm_call)
    ctx.register_hook("pre_tool_call", plugin.pre_tool_call)
    ctx.register_command(
        "agent-brain",
        handler=plugin.status_text,
        description="Show local Agent Brain plugin status",
        args_hint="status",
    )


__all__ = ["register"]
