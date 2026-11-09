"""Install native Windows Argon files and optionally merge a separate T3 instance."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from configure_t3 import configure


REPO = Path(__file__).resolve().parents[1]


def saved_value(config, name, default=""):
    path = config / name
    return path.read_text(encoding="utf-8-sig").strip() if path.exists() else default


def resolve_codex(explicit, config, settings_path):
    if explicit:
        candidates = [explicit]
    else:
        settings = json.loads(settings_path.read_bytes()) if settings_path.exists() else {}
        if not isinstance(settings, dict):
            raise ValueError("T3 settings must be a JSON object.")
        providers = settings.get("providerInstances", {})
        if not isinstance(providers, dict):
            raise ValueError("T3 providerInstances must be a JSON object.")
        primary = providers.get("codex", {})
        if not isinstance(primary, dict) or not isinstance(primary.get("config", {}), dict):
            raise ValueError("The primary T3 Codex instance and its config must be JSON objects.")
        primary = primary.get("config", {})
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        candidates = [os.environ.get("ARGON_CODEX_BINARY"), saved_value(config, "codex-binary"),
                      primary.get("binaryPath"), shutil.which("codex.exe"),
                      local / "Programs/OpenAI/Codex/bin/codex.exe"]
    for item in candidates:
        if item:
            path = Path(item).expanduser().resolve()
            if path.suffix.lower() == ".exe" and path.is_file() and path.name.lower() != "codex-argon.exe":
                return path
    raise ValueError("Real Codex .exe not found. Pass -CodexBinary <absolute-path-to-codex.exe>; .cmd shims are not supported.")


def compiler_path():
    windir = Path(os.environ.get("WINDIR", "C:/Windows"))
    for arch in ("Framework64", "Framework"):
        path = windir / "Microsoft.NET" / arch / "v4.0.30319/csc.exe"
        if path.is_file():
            return path
    raise ValueError("The .NET Framework C# compiler is missing; install .NET Framework 4.x before setup.")


def write_file(path, content, stamp):
    before = path.read_bytes() if path.exists() else None
    if before == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if before is not None:
        backup = path.with_name(path.name + ".bak-" + stamp)
        shutil.copy2(path, backup)
        print(f"Backup: {backup}")
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install_launcher(config, binary_dir, python, compiler, stamp):
    source = (REPO / "windows/launcher.cs").read_text(encoding="utf-8")
    source = source.replace("__ARGON_PYTHON__", json.dumps(str(python)))
    source = source.replace("__ARGON_RUNTIME__", json.dumps(str(config / "argon_runtime.py")))
    source = source.encode("utf-8")
    saved_source = config / "codex-argon.cs"
    launcher = binary_dir / "codex-argon.exe"
    if launcher.exists() and saved_source.exists() and saved_source.read_bytes() == source:
        return launcher
    with tempfile.TemporaryDirectory(prefix="argon-compile-") as temp:
        temp = Path(temp)
        source_file = temp / "launcher.cs"
        compiled = temp / "codex-argon.exe"
        source_file.write_bytes(source)
        subprocess.run([str(compiler), "/nologo", "/target:exe", "/out:" + str(compiled), str(source_file)], check=True)
        write_file(launcher, compiled.read_bytes(), stamp)
    # Record the source only after successfully installing the matching executable.
    write_file(saved_source, source, stamp)
    return launcher


def install(args):
    if os.name != "nt":
        raise ValueError("Use setup.sh on Linux; setup.ps1 is for native Windows.")
    config = Path(os.environ.get("ARGON_CONFIG_DIR") or Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "argon-codex").expanduser().resolve()
    binary_dir = Path(os.environ.get("ARGON_BIN_DIR") or Path.home() / ".local/bin").expanduser().resolve()
    project = os.environ.get("VERTEX_PROJECT") or saved_value(config, "vertex-project")
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project):
        raise ValueError("Set VERTEX_PROJECT to a Google Cloud project ID (6-30 lowercase letters, digits or hyphens).")
    port = args.port or os.environ.get("ARGON_PORT") or saved_value(config, "proxy-port", "4000")
    if not re.fullmatch(r"[1-9][0-9]{0,4}", port) or int(port) > 65535:
        raise ValueError("Invalid proxy port (1-65535).")
    settings = Path(args.t3_settings).expanduser().resolve()
    launcher = binary_dir / "codex-argon.exe"
    if args.t3:
        configure(settings, args.t3_instance, launcher, args.codex_home, check=True)
    codex = resolve_codex(args.codex_binary, config, settings)
    compiler = compiler_path()
    uv = args.uv or shutil.which("uv.exe")
    if not uv:
        candidate = Path.home() / ".local/bin/uv.exe"
        uv = str(candidate) if candidate.is_file() else None
    if not args.files_only and not uv:
        raise ValueError("Install uv first: https://docs.astral.sh/uv/getting-started/installation/")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f") + f"-{os.getpid()}"
    config.mkdir(parents=True, exist_ok=True)
    python = config / ".venv/Scripts/python.exe"
    if not args.files_only:
        if not python.is_file():
            subprocess.run([uv, "venv", "--python", "3.12", str(config / ".venv")], check=True)
        subprocess.run([uv, "pip", "install", "--python", str(python), "-r", str(REPO / "requirements.txt")], check=True)
    for relative, name in (("proxy/argon.yaml", "argon.yaml"), ("proxy/argon_hooks.py", "argon_hooks.py"),
                           ("windows/argon_runtime.py", "argon_runtime.py"), ("windows/start-argon.ps1", "start-argon.ps1")):
        write_file(config / name, (REPO / relative).read_bytes(), stamp)
    for name, value in (("vertex-project", project), ("proxy-port", port), ("codex-binary", str(codex))):
        write_file(config / name, (value + "\n").encode("utf-8"), stamp)
    # Files-only launchers can still run Codex without proxy dependencies. Full
    # installs use the stable installed venv, never a process-local uv run path.
    launcher = install_launcher(config, binary_dir, python if python.is_file() else Path(sys.executable), compiler, stamp)
    if args.t3:
        configure(settings, args.t3_instance, launcher, args.codex_home)
    print(f"Installed. Start proxy: powershell -NoProfile -ExecutionPolicy Bypass -File \"{config / 'start-argon.ps1'}\"")
    print(f"Then run: {launcher}")
    if args.files_only:
        print("Proxy dependencies skipped (-FilesOnly). Run setup without that flag before starting the proxy.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files-only", action="store_true")
    parser.add_argument("--t3", action="store_true")
    parser.add_argument("--t3-settings", default=str(Path(os.environ.get("T3CODE_HOME") or Path.home() / ".t3") / "userdata/settings.json"))
    parser.add_argument("--t3-instance", default="codex_argon_proxy")
    parser.add_argument("--codex-home")
    parser.add_argument("--codex-binary")
    parser.add_argument("--port")
    parser.add_argument("--uv")
    args = parser.parse_args()
    try:
        install(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Windows setup failed: {error}\n")


if __name__ == "__main__":
    main()
