"""Build app/index.html: the upload-and-compare app, with the sample traces embedded.

    python build_app.py            # embeds traces/adk__parallel.json and traces/langgraph__parallel.json
    python -m http.server -d app   # then open http://localhost:8000

The app itself is static (one HTML file, no dependencies). It parses everything in the
browser, so you can also just open app/index.html from disk.
"""

import json
import pathlib

HERE = pathlib.Path(__file__).parent
SAMPLES = ["adk__parallel.json", "langgraph__parallel.json"]


def main() -> None:
    samples = {name: json.loads((HERE / "traces" / name).read_text()) for name in SAMPLES}
    template = (HERE / "app" / "template.html").read_text()
    # </script> inside JSON would end the script tag early
    payload = json.dumps(samples).replace("</", "<\\/")
    (HERE / "app" / "index.html").write_text(template.replace("__SAMPLES__", payload))
    print(f"wrote app/index.html with {len(samples)} samples")


if __name__ == "__main__":
    main()
