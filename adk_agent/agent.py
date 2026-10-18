"""The trip concierge, written with Google ADK.

ADK has OpenTelemetry built in: you do not add anything to get spans.
They follow the OpenTelemetry GenAI semantic conventions (gen_ai.*).
"""

import os

from google.adk.agents import LlmAgent

from tools import INSTRUCTION, convert_currency, get_events, get_weather

root_agent = LlmAgent(
    name="trip_concierge",
    model=os.environ.get("MODEL", "gemini-3.8-flash"),
    instruction=INSTRUCTION,
    tools=[get_weather, get_events, convert_currency],
)
