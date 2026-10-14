"""Tool schemas — what the LLM sees."""

AGENT_PULSE = {
    "name": "agent_pulse",
    "description": (
        "Report live performance telemetry of this Hermes session: tokens per "
        "second, context-window occupancy, the current provider's remaining quota "
        "or credit balance, mean request latency, and the tool currently running. "
        "Use it when the user asks how fast the agent is going, how full the "
        "context window is, or how much quota the active provider has left. "
        "Read-only; costs nothing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "detail": {
                "type": "string",
                "enum": ["summary", "full"],
                "description": (
                    "'summary' (default) returns the headline numbers; 'full' adds "
                    "the per-sample breakdown and raw counters."
                ),
            }
        },
        "required": [],
    },
}
