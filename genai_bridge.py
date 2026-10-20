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
"""Bridge OpenInference spans onto the OpenTelemetry GenAI keys read by Agent Platform.

Out of the box, Agent Runtime's LanggraphAgent(enable_tracing=True) wires
openinference-instrumentation-langchain, which records conversations under
`session.id` and token counts under `llm.token_count.*`. The Agent Platform
console's Session view groups spans by `gen_ai.conversation.id` and sums
`gen_ai.usage.*` on `gen_ai.operation.name = "generate_content"` spans.

Calling `install_genai_bridge()` inside `model_builder` (after Agent Runtime's
default exporter setup has created the `TracerProvider`) keeps all OpenInference
attributes and resource identifiers intact while stamping the four `gen_ai.*`
keys the console expects, so Session view lights up for LangGraph deployments too.
"""

from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.trace import Status, StatusCode


class GenAIBridgeSpanProcessor(SpanProcessor):
    """Copies OpenInference span attributes onto their OpenTelemetry GenAI equivalents."""

    def on_end(self, span) -> None:
        a = dict(span.attributes or {})
        if "session.id" in a and "gen_ai.conversation.id" not in a:
            a["gen_ai.conversation.id"] = str(a["session.id"])
        kind = a.get("openinference.span.kind")
        if (span.parent is None or span.name == "LangGraph") and "gen_ai.operation.name" not in a:
            a["gen_ai.operation.name"] = "invoke_agent"
            a.setdefault("gen_ai.agent.name", "trip_concierge_langgraph")
        elif kind == "LLM":
            a.setdefault("gen_ai.operation.name", "generate_content")
            if "llm.model_name" in a:
                a.setdefault("gen_ai.request.model", str(a["llm.model_name"]))
            prompt = int(a.get("llm.token_count.prompt") or 0)
            comp = int(a.get("llm.token_count.completion") or 0)
            reas = int(a.get("llm.token_count.completion_details.reasoning") or 0)
            a.setdefault("gen_ai.usage.input_tokens", prompt)
            a.setdefault("gen_ai.usage.output_tokens", comp + reas)
            if reas:
                a.setdefault("gen_ai.usage.reasoning.output_tokens", reas)
        elif kind == "TOOL":
            a.setdefault("gen_ai.operation.name", "execute_tool")
            a.setdefault("gen_ai.tool.name", str(a.get("tool.name") or span.name))
        if getattr(span, "_attributes", None) is not None:
            span._attributes.update(a)
        # OpenInference marks success as OK; OTel asks instrumentations to leave it UNSET,
        # and the console counts any non-UNSET status as an error.
        if span.status.status_code == StatusCode.OK:
            span._status = Status(StatusCode.UNSET)


def install_genai_bridge() -> None:
    """Prepend GenAIBridgeSpanProcessor to the active TracerProvider before export."""
    import opentelemetry.trace

    tp = opentelemetry.trace.get_tracer_provider()
    multi = getattr(tp, "_active_span_processor", None)
    if multi is not None and hasattr(multi, "_span_processors"):
        if not any(type(p).__name__ == "GenAIBridgeSpanProcessor" for p in multi._span_processors):
            multi._span_processors = [GenAIBridgeSpanProcessor(), *multi._span_processors]
