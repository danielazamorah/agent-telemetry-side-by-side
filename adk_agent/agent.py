"""The trip concierge, written with Google ADK.

ADK has OpenTelemetry built in: you do not add anything to get spans.
They follow the OpenTelemetry GenAI semantic conventions (gen_ai.*).

Same harness, any model: set MODEL to a Gemini model (default) or to a Claude
model on Vertex AI (for example claude-sonnet-5-5). Claude goes through ADK's
Claude class (Anthropic SDK on Vertex AI); Gemini goes through google-genai.
"""

import os

from google.adk.agents import LlmAgent

from tools import INSTRUCTION, convert_currency, get_events, get_weather

MODEL = os.environ.get("MODEL", "gemini-3.8-flash")

if MODEL.startswith("claude"):
    from google.adk.models.anthropic_llm import Claude

    model = Claude(model=MODEL)
else:
    model = MODEL

root_agent = LlmAgent(
    name="trip_concierge",
    model=model,
    instruction=INSTRUCTION,
    tools=[get_weather, get_events, convert_currency],
)
