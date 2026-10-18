"""Build app/index.html: the upload-and-compare app, with the sample traces embedded.

    python build_app.py            # embeds the sample sets below (harness, provider, dictionary comparisons)
    python -m http.server -d app   # then open http://localhost:8000

The app itself is static (one HTML file, no dependencies). It parses everything in the
browser, so you can also just open app/index.html from disk.
"""

import json
import pathlib

HERE = pathlib.Path(__file__).parent
SAMPLE_SETS = {
    "Harness: ADK vs LangGraph (both on Gemini 3.8 Flash)": ["adk__parallel.json", "langgraph__parallel.json"],
    "Provider: ADK on Gemini vs ADK on Claude": ["adk__parallel.json", "adk__parallel__claude-sonnet-5-5.json"],
    "Provider: LangGraph on Gemini vs LangGraph on Claude": ["langgraph__parallel.json", "langgraph__parallel__claude-sonnet-5-5.json"],
    "Same model, other dictionary: ADK native vs ADK + OpenInference": ["adk__parallel.json", "adk-openinference__parallel.json"],
}


def main() -> None:
    samples = {
        label: {name: json.loads((HERE / "traces" / name).read_text()) for name in names}
        for label, names in SAMPLE_SETS.items()
    }
    template = (HERE / "app" / "template.html").read_text()
    # </script> inside JSON would end the script tag early
    payload = json.dumps(samples).replace("</", "<\\/")
    (HERE / "app" / "index.html").write_text(template.replace("__SAMPLES__", payload))
    print(f"wrote app/index.html with {len(samples)} sample sets")


if __name__ == "__main__":
    main()
