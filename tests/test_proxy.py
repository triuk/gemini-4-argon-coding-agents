"""Live Responses API check: schemas, tool round trip, streaming (three billed calls)."""
import argparse
import json
import sys
import urllib.error
import urllib.request


TOOLS = [
    {"type": "function", "name": "echo", "description": "Echo a text value.",
     "parameters": {"type": "object", "properties": {
         "text": {"type": "string"},
         "query": {"anyOf": [{"type": "string"}, {"type": "string", "enum": [""]}]},
         "target": {"oneOf": [{"type": "string"}, {"type": "object", "properties": {"id": {"type": "string"}}}]},
     }, "required": ["text"]}},
    {"type": "function", "name": "finish", "description": "Finish with code or a summary.",
     "parameters": {"oneOf": [
         {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
         {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
     ]}},
]


def call(base, body, stream=False):
    request = urllib.request.Request(
        base.rstrip("/") + "/v1/responses", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode()
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP {error.code}: {error.read().decode()[:800]}") from error
    if not stream:
        return json.loads(raw)
    return [json.loads(line[6:]) for line in raw.splitlines()
            if line.startswith("data: ") and line[6:] != "[DONE]"]


def text(result):
    return "".join(part.get("text", "") for item in result.get("output", [])
                   for part in item.get("content", []) if part.get("type") == "output_text")


def run(base):
    fields = {"model": "gemini-4-argon", "store": False,
              "reasoning": {"effort": "low"}, "parallel_tool_calls": False}
    prompt = "Call echo with text ARGON_TOOL_OK and query an empty string. Use the tool."
    first = call(base, {**fields, "tools": TOOLS, "input": prompt,
                        "tool_choice": {"type": "function", "name": "echo"}})
    calls = [item for item in first.get("output", []) if item.get("type") == "function_call"]
    if len(calls) != 1 or calls[0]["name"] != "echo":
        raise RuntimeError("Expected one echo function call; got " + str(first.get("output")))
    function = calls[0]
    if json.loads(function["arguments"]).get("text") != "ARGON_TOOL_OK":
        raise RuntimeError("Tool arguments did not match the requested text.")
    print("PASS: nested unions, root union, empty enum, function call", flush=True)

    replay = [{"role": "user", "content": prompt}] + first["output"]
    replay.append({"type": "function_call_output", "call_id": function["call_id"], "output": "ARGON_TOOL_OK"})
    second = call(base, {**fields, "tools": TOOLS, "tool_choice": "none", "input": replay,
                         "instructions": "Repeat the tool result exactly."})
    if "ARGON_TOOL_OK" not in text(second):
        raise RuntimeError("The response did not contain the tool result.")
    print("PASS: function result round trip", flush=True)

    events = call(base, {**fields, "stream": True, "input": "Reply with the single word OK."}, stream=True)
    errors = [event for event in events if event.get("type") in ("error", "response.failed", "response.incomplete")]
    completed = [event for event in events if event.get("type") == "response.completed"]
    if errors or not completed or "OK" not in text(completed[-1].get("response", {})):
        raise RuntimeError("Stream did not complete with OK: " + str(errors or events[-2:]))
    print("PASS: streaming completed with OK", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:4000")
    args = parser.parse_args()
    try:
        run(args.base_url)
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
