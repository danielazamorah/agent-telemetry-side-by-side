"""Compare the telemetry two frameworks wrote for the same question.

    python compare.py                      # parallel question, ADK vs LangGraph
    python compare.py --question serial

Prints a "Rosetta" table (same fact, two dictionaries) and writes viewer.html,
one self-contained page with four panels:
  1. the span trees side by side
  2. one model call, raw JSON, the same facts highlighted in the same color
  3. where the words are (ADK: a separate event; LangGraph: on the span)
  4. the Rosetta table
"""

import argparse
import html
import json
import pathlib

HERE = pathlib.Path(__file__).parent

# fact -> (color, how to find it in GenAI/ADK, how to find it in OpenInference)
FACTS = [
    ("what kind of step", "#7c4dff", "gen_ai.operation.name", "openinference.span.kind"),
    ("which model", "#1a73e8", "gen_ai.request.model", "llm.model_name"),
    ("tokens in", "#1e8e3e", "gen_ai.usage.input_tokens", "llm.token_count.prompt"),
    ("tokens out", "#1e8e3e", "gen_ai.usage.output_tokens", "llm.token_count.completion"),
    ("which conversation", "#b06000", "gen_ai.conversation.id", "session.id"),
    ("what the user said", "#c5221f", "gen_ai.input.messages", "input.value"),
    ("what the model said", "#c5221f", "gen_ai.output.messages", "output.value"),
]
COLOR_OF = {}
for _, color, a, b in FACTS:
    COLOR_OF[a] = color
    COLOR_OF[b] = color


def load(agent, question):
    return json.loads((HERE / "traces" / f"{agent}__{question}.json").read_text())


def kind(span):
    a = span["attributes"]
    if "openinference.span.kind" in a:
        return a["openinference.span.kind"]
    n = span["name"]
    if n.startswith("invoke_agent"):
        return "AGENT"
    if n.startswith("execute_tool") and "merged" not in n:
        return "TOOL"
    if n.startswith(("call_llm", "generate_content")):
        return "LLM"
    return "CHAIN"


def first_model_span(trace):
    for s in trace["spans"]:
        if s["name"].startswith("generate_content") or s["attributes"].get("openinference.span.kind") == "LLM":
            return s
    return None


def tree_rows(trace):
    ids = {s["span_id"]: s for s in trace["spans"]}
    t0 = min(s["start_time_ns"] for s in trace["spans"])
    total = max(s["end_time_ns"] for s in trace["spans"]) - t0
    rows = []
    for s in trace["spans"]:
        depth, p = 0, s
        while p["parent_span_id"] in ids:
            p = ids[p["parent_span_id"]]
            depth += 1
        rows.append((depth, s, (s["start_time_ns"] - t0) / total, (s["end_time_ns"] - s["start_time_ns"]) / total, total / 1e6))
    return rows


def find(trace, key, model_span):
    """Value of a fact: on the model span, else in the event linked to it (ADK words)."""
    if key in model_span["attributes"]:
        return "span", model_span["attributes"][key]
    for ev in trace.get("events", []):
        if ev.get("span_id") == model_span["span_id"] and key in ev["attributes"]:
            return "event", ev["attributes"][key]
    # session lives on the root span in OpenInference
    for s in trace["spans"]:
        if key in s["attributes"]:
            return f"span: {s['name']}", s["attributes"][key]
    return None, None


def short(v, n=90):
    v = v if isinstance(v, str) else json.dumps(v)
    return v if len(v) <= n else v[: n - 1] + "…"


KIND_COLOR = {"AGENT": "#7c4dff", "LLM": "#1a73e8", "TOOL": "#1e8e3e", "CHAIN": "#9aa0a6"}


def render_tree(trace, title):
    rows = "".join(
        f'<div class="trow"><div class="tname" style="padding-left:{8 + d * 18}px">{html.escape(s["name"][:38])}</div>'
        f'<div class="ttrack"><div class="tbar" style="left:{left * 100:.1f}%;width:{max(w * 100, 0.6):.1f}%;background:{KIND_COLOR[kind(s)]}"></div></div>'
        f'<div class="tms">{s["duration_ms"]:,.0f} ms</div></div>'
        for d, s, left, w, _ in tree_rows(trace)
    )
    return f'<div class="card"><h3>{html.escape(title)}</h3><div class="sub">{len(trace["spans"])} spans</div>{rows}</div>'


def render_json(obj, highlight=True, limit=110):
    lines = []
    for k, v in obj.items():
        color = COLOR_OF.get(k) if highlight else None
        val = html.escape(short(v, limit))
        key = html.escape(k)
        style = f' style="background:{color}22;border-left:4px solid {color}"' if color else ""
        lines.append(f'<div class="jl"{style}><span class="jk">"{key}"</span>: <span class="jv">{val}</span></div>')
    return '<div class="json">{' + "".join(lines) + "}</div>"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default="parallel")
    args = parser.parse_args()
    adk, lg = load("adk", args.question), load("langgraph", args.question)
    adk_model, lg_model = first_model_span(adk), first_model_span(lg)
    adk_event = next((e for e in adk.get("events", []) if e["span_id"] == adk_model["span_id"]), None)

    # 1. Rosetta, printed
    print(f'Question: {adk["question"]}\n')
    print(f'{"fact":<22}{"ADK (GenAI conventions)":<58}{"LangGraph (OpenInference)"}')
    rosetta_rows = ""
    for fact, color, gk, ok in FACTS:
        gw, gv = find(adk, gk, adk_model)
        ow, ov = find(lg, ok, lg_model)
        print(f"{fact:<22}{gk + ' = ' + short(gv, 26):<58}{ok + ' = ' + short(ov, 30)}")
        rosetta_rows += (
            f'<tr><td><b style="color:{color}">{fact}</b></td>'
            f'<td><code>{gk}</code><div class="v">{html.escape(short(gv, 70))}</div><div class="w">on the {gw or "(nowhere)"}</div></td>'
            f'<td><code>{ok}</code><div class="v">{html.escape(short(ov, 70))}</div><div class="w">on the {ow or "(nowhere)"}</div></td></tr>'
        )

    # 2. viewer.html
    lg_attrs = {k: v for k, v in lg_model["attributes"].items() if not k.startswith(("llm.tools.", "llm.input_messages.", "llm.output_messages."))}
    lg_hidden = len(lg_model["attributes"]) - len(lg_attrs)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Same agent, two telemetry dictionaries</title>
<style>
body{{margin:0;background:#fff;color:#1f1f1f;font-family:"Google Sans",Inter,Roboto,Arial,sans-serif}}
main{{max-width:1500px;margin:0 auto;padding:48px 40px 80px}}
h1{{font-size:44px;font-weight:600;margin:0 0 8px}} h2{{font-size:28px;font-weight:600;margin:56px 0 6px}}
.lead{{font-size:20px;color:#5f6368;max-width:1100px;line-height:1.5}}
.eyebrow{{font-size:14px;letter-spacing:.14em;text-transform:uppercase;color:#1a73e8;font-weight:600;margin-top:56px}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:18px}}
.card{{background:#f6f8fa;border-radius:18px;padding:22px 24px}}
.card h3{{margin:0;font-size:20px}} .sub{{color:#5f6368;font-size:14px;margin:4px 0 12px}}
.trow{{display:flex;align-items:center;height:30px}}
.tname{{width:300px;font-family:"Roboto Mono",Menlo,monospace;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.ttrack{{flex:1;position:relative;height:16px}} .tbar{{position:absolute;top:2px;height:12px;border-radius:4px}}
.tms{{width:80px;text-align:right;font-size:12px;color:#5f6368}}
.json{{font-family:"Roboto Mono",Menlo,monospace;font-size:13px;line-height:1.55;background:#0f1720;color:#e6edf3;border-radius:14px;padding:18px 20px;overflow:hidden}}
.jl{{padding:1px 8px;border-left:4px solid transparent;margin-left:8px}} .jk{{color:#79c0ff}} .jv{{color:#e6edf3}}
.note{{font-size:15px;color:#5f6368;margin-top:10px}}
table{{border-collapse:collapse;width:100%;margin-top:14px;font-size:15px}}
th{{text-align:left;color:#5f6368;font-size:13px;text-transform:uppercase;letter-spacing:.06em;padding:10px;border-bottom:2px solid #e3e6ea}}
td{{padding:12px 10px;border-bottom:1px solid #e3e6ea;vertical-align:top}}
code{{font-family:"Roboto Mono",Menlo,monospace;font-size:13px;background:#eef1f5;padding:2px 6px;border-radius:5px}}
.v{{font-family:"Roboto Mono",Menlo,monospace;font-size:12px;color:#3c4043;margin-top:6px;word-break:break-all}} .w{{font-size:12px;color:#9aa0a6;margin-top:2px}}
.legend span{{display:inline-block;margin-right:18px;font-size:14px;color:#5f6368}} .legend b{{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}}
.big{{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:18px}}
.goal{{background:#f6f8fa;border-radius:18px;padding:24px}} .goal h3{{margin:0 0 10px;font-size:22px}} .goal p{{font-size:16px;line-height:1.55;margin:6px 0}}
</style></head><body><main>
<div class="eyebrow">Same agent · same question · two frameworks</div>
<h1>Two dictionaries for the same telemetry</h1>
<p class="lead">Question: “{html.escape(adk["question"])}” Both frameworks emit OpenTelemetry: a tree of spans with ids, parents and timestamps. What differs is the <b>names of the attributes</b>, and <b>where the words go</b>.</p>

<div class="eyebrow">1 · The shape</div><h2>Both are a tree of spans</h2>
<div class="legend">{"".join(f'<span><b style="background:{c}"></b>{k}</span>' for k, c in KIND_COLOR.items())}</div>
<div class="two">{render_tree(adk, "ADK · native OpenTelemetry")}{render_tree(lg, "LangGraph · OpenInference instrumentor")}</div>
<p class="note">Same story: decide, call two tools at the same time, answer. LangGraph writes more spans because it traces each graph node and LangChain runnable.</p>

<div class="eyebrow">2 · One model call, raw JSON</div><h2>Same facts, different keys</h2>
<div class="legend">{"".join(f'<span><b style="background:{c}"></b>{f}</span>' for f, c, _, _ in FACTS[:5])}</div>
<div class="two">
<div><h3>ADK · <code>{html.escape(adk_model["name"])}</code></h3>{render_json(adk_model["attributes"])}</div>
<div><h3>LangGraph · <code>{html.escape(lg_model["name"])}</code></h3>{render_json(lg_attrs)}<p class="note">+ {lg_hidden} more keys: every message and tool schema flattened into <code>llm.input_messages.N.*</code>, <code>llm.output_messages.N.*</code>, <code>llm.tools.N.*</code>.</p></div>
</div>

<div class="eyebrow">3 · Where the words go</div><h2>A separate event, or on the span</h2>
<div class="two">
<div><h3>ADK · event linked by <code>span_id</code> (opt-in)</h3>{render_json({"event_name": adk_event["event_name"], "trace_id": adk_event["trace_id"], "span_id": adk_event["span_id"], **{k: v for k, v in adk_event["attributes"].items() if k in ("user.id", "gen_ai.input.messages", "gen_ai.output.messages")}}) if adk_event else "<p>no event captured</p>"}
<p class="note">Words only exist if you set <code>OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY</code>. The span stays small and safe; the transcript is a log you can store and protect separately.</p></div>
<div><h3>LangGraph · on the span (default)</h3>{render_json({k: lg_model["attributes"][k] for k in ("input.value", "output.value") if k in lg_model["attributes"]})}
<p class="note">On by default. Easy to read in one place; also means every trace backend that stores the span stores the conversation.</p></div>
</div>

<div class="eyebrow">4 · The Rosetta table</div><h2>Same fact, two names</h2>
<table><thead><tr><th>fact</th><th>OpenTelemetry GenAI (ADK)</th><th>OpenInference (LangGraph)</th></tr></thead><tbody>{rosetta_rows}</tbody></table>

<div class="eyebrow">5 · Why two dictionaries exist</div>
<div class="big">
<div class="goal"><h3>OpenTelemetry GenAI conventions</h3><p><b>Who:</b> the OpenTelemetry project (GenAI SIG), vendor neutral.</p><p><b>For:</b> any observability backend: Cloud Trace, Datadog, Grafana.</p><p><b>Style:</b> <code>gen_ai.*</code>, numbers on spans, words as opt-in events, privacy first.</p><p><b>Status:</b> still marked Development in the spec, so names still move.</p></div>
<div class="goal"><h3>OpenInference</h3><p><b>Who:</b> Arize and the community, open source.</p><p><b>For:</b> LLM debugging and evaluation tools (Phoenix, Arize, eval pipelines).</p><p><b>Style:</b> span kinds (AGENT, LLM, TOOL, CHAIN, RETRIEVER), words on the span, one place to read everything.</p><p><b>Status:</b> stable, widely used, instrumentors for many frameworks.</p></div>
</div>
<p class="lead" style="margin-top:28px">The framework doesn't decide the dictionary, the instrumentor does: the same ADK agent with the OpenInference instrumentor writes OpenInference (see <code>traces/adk-openinference__*.json</code>). So, pick the dictionary your tools read, or normalize both at rest with SQL.</p>
</main></body></html>"""
    (HERE / "viewer.html").write_text(page)
    print(f"\nwrote viewer.html")


if __name__ == "__main__":
    main()
