"""Windows launcher runtime; installed alongside argon.yaml, with no checkout dependency."""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys


def read_port(config):
    saved = config / "proxy-port"
    port = os.environ.get("ARGON_PORT") or (saved.read_text(encoding="utf-8").strip() if saved.exists() else "4000")
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("Invalid proxy port (1-65535).")
    return str(int(port))


def codex_command(config, port, args):
    binary = os.environ.get("ARGON_CODEX_BINARY") or (config / "codex-binary").read_text(encoding="utf-8").strip()
    if Path(binary).suffix.lower() != ".exe" or not Path(binary).is_file():
        raise ValueError("Codex executable missing; rerun setup.ps1 -CodexBinary <path-to-codex.exe>.")
    return [binary, "-m", "gemini-4-argon",
            "-c", 'model_provider="argon"',
            "-c", 'model_reasoning_effort="low"',
            # Keep every MCP/T3 tool accessible through exec rather than sending
            # hundreds of separate declarations to Vertex (512 maximum).
            "-c", "features.code_mode.enabled=true",
            "-c", "features.code_mode_only=true",
            "-c", 'model_providers.argon.name="Argon (Vertex ADC)"',
            "-c", f'model_providers.argon.base_url="http://127.0.0.1:{port}/v1"',
            "-c", 'model_providers.argon.wire_api="responses"',
            "-c", 'model_providers.argon.requires_openai_auth=false', *args]


def proxy_command(config, port, env, background=False):
    binary = config / ".venv/Scripts/litellm.exe"
    if not binary.is_file():
        raise ValueError("LiteLLM missing; run setup.ps1 without -FilesOnly.")
    project = (config / "vertex-project").read_text(encoding="utf-8").strip()
    env.update(VERTEXAI_PROJECT=project, VERTEXAI_LOCATION="global",
               PYTHONPATH=str(config) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""),
               LITELLM_TELEMETRY="False", LITELLM_LOCAL_MODEL_COST_MAP="True", PYTHONUTF8="1")
    command = [str(binary)]
    if background:
        # DETACHED_PROCESS on the console-script shim does not prevent its
        # interpreter child from allocating a new console. Bypass that shim and
        # use the GUI interpreter throughout the venv launcher chain instead.
        python = config / ".venv/Scripts/pythonw.exe"
        if not python.is_file():
            raise ValueError("pythonw.exe missing; recreate the Windows proxy environment with setup.ps1.")
        command = [str(python), "-c", "from litellm import run_server; run_server()"]
    return [*command, "--config", str(config / "argon.yaml"), "--host", "127.0.0.1", "--port", port]


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ("codex", "proxy"):
        raise ValueError("Expected codex or proxy.")
    mode, *args = args
    # The native launcher records this installed runtime's absolute path. A custom
    # install therefore also works in T3 without inherited terminal environment.
    config = Path(__file__).resolve().parent
    if mode == "codex" and os.environ.get("ARGON_CONFIG_DIR"):
        config = Path(os.environ["ARGON_CONFIG_DIR"]).expanduser().resolve()
    try:
        port = read_port(config)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    env = dict(os.environ)
    if mode == "codex":
        return subprocess.call(codex_command(config, port, args), env=env)
    parser = argparse.ArgumentParser(description="Start the installed Argon proxy on loopback.")
    parser.add_argument("--background", action="store_true", help="Detach, append argon.log, and record argon.pid.")
    options = parser.parse_args(args)
    command = proxy_command(config, port, env, background=options.background)
    # Refuse to add another process when this or an unknown listener holds the port.
    with socket.socket() as check:
        check.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        check.bind(("127.0.0.1", int(port)))
    if options.background:
        with (config / "argon.log").open("ab", buffering=0) as output:
            child = subprocess.Popen(command, env=env, cwd=config, stdin=subprocess.DEVNULL,
                                     stdout=output, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
        (config / "argon.pid").write_text(str(child.pid) + "\n", encoding="utf-8")
        print(f"Started PID {child.pid}; log: {config / 'argon.log'}")
        return 0
    return subprocess.call(command, env=env)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print(f"Argon: {error}", file=sys.stderr)
        sys.exit(1)
