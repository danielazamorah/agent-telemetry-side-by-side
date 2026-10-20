# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""The same trip concierge, written with LangGraph.

LangGraph has no OpenTelemetry of its own. The usual way to trace it is the
community OpenInference instrumentor (it is also what Agent Runtime's
LanggraphAgent template turns on with enable_tracing=True).
"""

import os

from langchain_core.tools import tool
from langchain_google_vertexai import ChatVertexAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent

from tools import INSTRUCTION, convert_currency, get_events, get_weather

MODEL = os.environ.get("MODEL", "gemini-3.8-flash")

if MODEL.startswith("claude"):
    # Same harness, different provider: Claude through the Anthropic SDK.
    from langchain_google_vertexai.model_garden import ChatAnthropicVertex

    llm = ChatAnthropicVertex(
        model_name=MODEL,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.environ.get("CLAUDE_LOCATION", os.environ.get("GOOGLE_CLOUD_LOCATION", "global")),
        # no temperature: the current Anthropic SDK's messages.create() no longer accepts it
        max_tokens=1024,
    )
else:
    llm = ChatVertexAI(
        model_name=MODEL,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        temperature=0,
    )

agent = create_react_agent(
    llm,
    [tool(get_weather), tool(get_events), tool(convert_currency)],
    prompt=INSTRUCTION,
    # The checkpointer is LangGraph's "session": it saves the graph state per thread_id.
    checkpointer=InMemorySaver(),
)
