"""Run one agent on one question and save its telemetry as plain JSON.

    python capture.py adk                  # ADK, native OpenTelemetry  -> GenAI conventions
    python capture.py langgraph            # LangGraph + OpenInference  -> OpenInference conventions
    python capture.py adk-openinference    # bonus: the SAME ADK agent with the OpenInference instrumentor
    python capture.py adk --question serial
    python capture.py adk --model claude-sonnet-5-5      # same harness, another provider

Writes traces/<agent>__<question>.json with:
    spans   one object per span: name, ids, parent, start/end, duration, attributes
    events  OpenTelemetry log records emitted during the run (where GenAI puts the words)
    session the framework's own record of the conversation (ADK session events,
            LangGraph checkpoint), which is NOT telemetry: it is what the agent
            reads back to continue the conversation

Nothing leaves your machine except the model calls: the exporters write to memory.
"""

import argparse
import asyncio
import json
import os
import pathlib
import sys

# ---- where the words go ------------------------------------------------------
# GenAI conventions (ADK): words go into separate log records ("events"), opt-in.
os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental")
os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "EVENT_ONLY")
# Keep ADK's own copy of the words off the spans, like Agent Runtime does in production.
os.environ.setdefault("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "false")
# OpenInference: words go on the spans (input.value / output.value), on by default.

from opentelemetry import _logs, trace  # noqa: E402
from opentelemetry.sdk._logs import LoggerProvider  # noqa: E402
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor  # noqa: E402
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter  # noqa: E402
from opentelemetry.sdk.resources import Resource  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from tools import QUESTIONS  # noqa: E402

span_store = InMemorySpanExporter()
log_store = InMemoryLogRecordExporter()


def setup_otel(service_name: str) -> TracerProvider:
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(span_store))
    trace.set_tracer_provider(provider)
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(SimpleLogRecordProcessor(log_store))
    _logs.set_logger_provider(logger_provider)
    return provider


SESSION = {}


async def run_adk(question: str) -> str:
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from adk_agent.agent import root_agent

    runner = InMemoryRunner(agent=root_agent, app_name="trip_concierge")
    session = await runner.session_service.create_session(app_name="trip_concierge", user_id="ana")
    answer = ""
    async for event in runner.run_async(
        user_id="ana",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=question)]),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            answer = "".join(p.text or "" for p in event.content.parts)
    # ADK's session: every event (user message, function calls, function responses,
    # final answer) plus state, as stored by the SessionService.
    stored = await runner.session_service.get_session(
        app_name="trip_concierge", user_id="ana", session_id=session.id
    )
    SESSION.update({"framework": "adk", "kind": "ADK Session (SessionService)",
                    "data": stored.model_dump(mode="json", exclude_none=True)})
    await runner.close()
    return answer.strip()


async def run_langgraph(question: str) -> str:
    from langgraph_agent import agent

    config = {"configurable": {"thread_id": "session-1"}, "metadata": {"session_id": "session-1", "user_id": "ana"}}
    state = await agent.ainvoke({"messages": [("user", question)]}, config=config)
    # LangGraph's session: the checkpoint for this thread (graph state + metadata).
    from langchain_core.messages import messages_to_dict

    snap = await agent.aget_state(config)
    SESSION.update({"framework": "langgraph", "kind": "LangGraph checkpoint (thread state)",
                    "data": {"thread_id": "session-1", "next": list(snap.next), "metadata": snap.metadata,
                             "created_at": snap.created_at,
                             "values": {"messages": messages_to_dict(snap.values["messages"])}}})
    content = state["messages"][-1].content
    if isinstance(content, list):
        content = " ".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content).strip()


def hex_id(value, width):
    return format(value, f"0{width}x") if value else None


def simplify(span) -> dict:
    """The parts of a span you actually look at. Everything else is plumbing."""
    return {
        "name": span.name,
        "trace_id": hex_id(span.context.trace_id, 32),
        "span_id": hex_id(span.context.span_id, 16),
        "parent_span_id": hex_id(span.parent.span_id, 16) if span.parent else None,
        "start_time_ns": span.start_time,
        "end_time_ns": span.end_time,
        "duration_ms": round((span.end_time - span.start_time) / 1e6, 1),
        "instrumentation": span.instrumentation_scope.name if span.instrumentation_scope else None,
        "attributes": {k: v for k, v in (span.attributes or {}).items()},
        "status": span.status.status_code.name,
    }


def simplify_log(item) -> dict:
    record = item.log_record
    return {
        "event_name": getattr(record, "event_name", None),
        "trace_id": hex_id(record.trace_id, 32),
        "span_id": hex_id(record.span_id, 16),
        "attributes": {k: v for k, v in (record.attributes or {}).items()},
        "body": record.body,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("agent", choices=["adk", "langgraph", "adk-openinference"])
    parser.add_argument("--question", choices=list(QUESTIONS), default="parallel")
    parser.add_argument("--model", default=None, help="Gemini (default) or a Claude model on Vertex AI")
    args = parser.parse_args()
    if args.model:
        os.environ["MODEL"] = args.model
    model = os.environ.get("MODEL", "gemini-3.8-flash")

    provider = setup_otel(f"trip-concierge-{args.agent}")
    question = QUESTIONS[args.question]

    if args.agent == "adk":
        answer = asyncio.run(run_adk(question))
    elif args.agent == "adk-openinference":
        from openinference.instrumentation.google_adk import GoogleADKInstrumentor

        GoogleADKInstrumentor().instrument(tracer_provider=provider)
        answer = asyncio.run(run_adk(question))
    else:
        from openinference.instrumentation.langchain import LangChainInstrumentor

        LangChainInstrumentor().instrument(tracer_provider=provider)
        answer = asyncio.run(run_langgraph(question))

    spans = sorted((simplify(s) for s in span_store.get_finished_spans()), key=lambda s: s["start_time_ns"])
    events = [simplify_log(r) for r in log_store.get_finished_logs()]
    suffix = "" if model.startswith("gemini") else f"__{model}"
    out = HERE / "traces" / f"{args.agent}__{args.question}{suffix}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(
        {"agent": args.agent, "model": model, "question": question,
         "answer": answer, "spans": spans, "events": events, "session": SESSION},
        indent=2, default=str,
    ))
    n_session = len(SESSION.get("data", {}).get("events", SESSION.get("data", {}).get("values", {}).get("messages", [])))
    print(f"{args.agent}: {len(spans)} spans, {len(events)} events, {n_session} session items -> {out.relative_to(HERE)}")
    print(f"answer: {answer}")


if __name__ == "__main__":
    main()
