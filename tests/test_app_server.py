"""Explicit live Codex app-server check with >512 tools (billed; not a unittest)."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time


def fixture_tools(count):
    return [{"type": "function", "name": f"argon_echo_{number:04d}",
             "description": "Return the supplied text unchanged (test fixture).",
             "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}},
                             "required": ["text"], "additionalProperties": False}}
            for number in range(count)]


def t3_config(event_log):
    if not event_log:
        return {}
    config = None
    for line in Path(event_log).open(encoding="utf-8"):
        start = line.find("{")
        if start < 0:
            continue
        event = json.loads(line[start:]).get("event", {})
        payload = event.get("payload", {})
        if event.get("direction") == "outgoing" and payload.get("method") == "thread/start":
            config = payload.get("params", {}).get("config", {})
    if config is None:
        raise ValueError("No thread/start configuration in the supplied local T3 event log.")
    # This may contain private MCP connection data. Use only in memory, never
    # print, persist, or add it to test fixtures/the repository.
    return config


def run(launcher, base_url, count=530, event_log=None, timeout=180):
    if count <= 512:
        raise ValueError("Use more than 512 tools to exercise the Vertex limit.")
    config = t3_config(event_log)
    command = [str(Path(launcher).expanduser().resolve()), "-c",
               'model_providers.argon.base_url=' + json.dumps(base_url.rstrip("/") + "/v1"),
               "-c", "model_providers.argon.request_max_retries=0",
               "-c", "model_providers.argon.stream_max_retries=0", "app-server"]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with tempfile.TemporaryDirectory(prefix="argon-app-server-") as directory:
        with (Path(directory) / "stderr.log").open("w", encoding="utf-8") as errors:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                                       text=True, encoding="utf-8", creationflags=flags)
            events = queue.Queue()

            def read_events():
                try:
                    for line in process.stdout:
                        events.put(json.loads(line))
                except (OSError, ValueError) as error:
                    events.put(error)
                finally:
                    events.put(EOFError("Codex app-server closed stdout."))

            threading.Thread(target=read_events, daemon=True).start()
            deadline = time.monotonic() + timeout

            def send(value):
                process.stdin.write(json.dumps(value) + "\n")
                process.stdin.flush()

            def next_event():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Codex app-server check timed out.")
                try:
                    event = events.get(timeout=remaining)
                except queue.Empty as error:
                    raise TimeoutError("Codex app-server check timed out.") from error
                if isinstance(event, Exception):
                    raise event
                return event

            def result(request_id):
                while True:
                    event = next_event()
                    if event.get("id") == request_id:
                        if "error" in event:
                            raise RuntimeError(str(event["error"]))
                        return event["result"]

            try:
                send({"id": 1, "method": "initialize", "params": {
                    "clientInfo": {"name": "argon-app-server-check", "version": "1.0"},
                    "capabilities": {"experimentalApi": True}}})
                result(1)
                send({"method": "initialized", "params": {}})
                tools = fixture_tools(count)
                expected_tool = tools[-1]["name"]
                send({"id": 2, "method": "thread/start", "params": {
                    "model": "gemini-4-argon", "cwd": directory, "ephemeral": True,
                    "config": config, "dynamicTools": tools}})
                thread = result(2)["thread"]["id"]
                prompt = (f"Use exec to call tools.{expected_tool} with text ARGON_TOOL_OK. "
                          "Then reply with exactly the returned text. Do not call any other tools. "
                          "This is a synthetic read-only echo tool used for verification.")
                send({"id": 3, "method": "turn/start", "params": {
                    "threadId": thread, "model": "gemini-4-argon", "approvalPolicy": "never",
                    "sandboxPolicy": {"type": "readOnly"}, "input": [{"type": "text", "text": prompt}]}})
                turn_id = result(3)["turn"]["id"]
                calls = 0
                final = ""
                while True:
                    event = next_event()
                    method = event.get("method")
                    params = event.get("params", {})
                    if method == "item/tool/call":
                        if params.get("tool") != expected_tool or params.get("arguments") != {"text": "ARGON_TOOL_OK"}:
                            raise RuntimeError("Unexpected synthetic tool call.")
                        calls += 1
                        send({"id": event["id"], "result": {"success": True, "contentItems": [
                            {"type": "inputText", "text": "ARGON_TOOL_OK"}]}})
                        print(f"PASS: tool {count} in a catalog larger than 512 was invoked", flush=True)
                    elif method == "item/agentMessage/delta":
                        final += params.get("delta", "")
                    elif method == "error":
                        # Capacity and schema errors must be reported, not turned
                        # into a long sequence of billed automatic retries.
                        send({"id": 4, "method": "turn/interrupt", "params": {
                            "threadId": thread, "turnId": turn_id}})
                        raise RuntimeError(str(params.get("error", params)))
                    elif method == "turn/completed":
                        turn = params.get("turn", {})
                        if turn.get("error") or turn.get("status") != "completed":
                            raise RuntimeError(str(turn.get("error") or turn.get("status")))
                        break
                if calls != 1 or final.strip() != "ARGON_TOOL_OK":
                    raise RuntimeError(f"Expected one fixture call and ARGON_TOOL_OK, got {calls} calls and {final!r}.")
                print("PASS: actual Codex app-server tool result and completed streaming response", flush=True)
            finally:
                process.stdin.close()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        process.terminate()
                        process.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", required=True, help="Installed codex-argon or codex-argon.exe")
    parser.add_argument("--base-url", default="http://127.0.0.1:4000")
    parser.add_argument("--tool-count", type=int, default=530)
    parser.add_argument("--t3-event-log", help="Optionally reuse local T3 MCP configuration, in memory only")
    args = parser.parse_args()
    try:
        run(args.launcher, args.base_url, args.tool_count, args.t3_event_log)
    except (RuntimeError, OSError, ValueError, TimeoutError, EOFError) as error:
        parser.exit(1, f"FAIL: {error}\n")
