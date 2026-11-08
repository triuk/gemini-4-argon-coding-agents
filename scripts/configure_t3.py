"""Merge the verified Argon instance into T3 settings without changing other instances."""
import argparse
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile


MODEL_FILE = Path(__file__).resolve().parents[1] / "codex/t3-model.json"


def merged_settings(settings, instance_id, launcher, codex_home=None):
    if not instance_id.strip() or instance_id == "codex":
        raise ValueError("Choose a separate Argon instance ID; the default Codex instance is preserved.")
    result = deepcopy(settings)
    if not isinstance(result, dict):
        raise ValueError("T3 settings must be a JSON object.")
    providers = result.setdefault("providerInstances", {})
    if not isinstance(providers, dict):
        raise ValueError("providerInstances must be an object.")
    existed = instance_id in providers
    instance = providers.setdefault(instance_id, {"driver": "codex", "displayName": "Argon proxy"})
    if not isinstance(instance, dict) or instance.get("driver") != "codex":
        raise ValueError("Requested instance already belongs to another driver; choose --instance.")
    config = instance.setdefault("config", {})
    if not isinstance(config, dict):
        raise ValueError("Instance config must be an object.")
    if config.get("setupMode") == "managed":
        raise ValueError("Requested instance is managed by T3; choose a separate --instance.")
    models = config.setdefault("customModels", [])
    if not isinstance(models, list):
        raise ValueError("customModels must be an array.")
    model = json.loads(MODEL_FILE.read_text())
    matching = [i for i, item in enumerate(models)
                if item == model["slug"] or isinstance(item, dict) and item.get("slug") == model["slug"]]
    if existed and not matching and Path(config.get("binaryPath", "")).name != "codex-argon":
        raise ValueError("Existing Codex instance is not recognized as Argon; choose another --instance.")
    if len(matching) > 1:
        raise ValueError("Duplicate Argon models; remove duplicates before retrying.")
    if matching:
        current = models[matching[0]]
        models[matching[0]] = {**(current if isinstance(current, dict) else {}), **model}
    else:
        models.append(model)
    instance["enabled"] = True
    config.update(binaryPath=str(launcher), setupMode="existing")
    if codex_home is not None:
        config["homePath"] = str(Path(codex_home).expanduser().resolve())
    elif "homePath" not in config:
        primary = providers.get("codex", {})
        primary_config = primary.get("config", {}) if isinstance(primary, dict) else {}
        if not isinstance(primary_config, dict):
            raise ValueError("The primary Codex instance config must be an object.")
        config["homePath"] = primary_config.get("homePath", "")
    return result


def configure(settings_path, instance_id, launcher, codex_home=None, check=False):
    path = Path(settings_path).expanduser().resolve()
    launcher = Path(launcher).expanduser().resolve()
    before = path.read_bytes() if path.exists() else None
    settings = json.loads(before) if before is not None else {}
    result = merged_settings(settings, instance_id, launcher, codex_home)
    if check:
        return
    if not launcher.is_file() or not os.access(launcher, os.X_OK):
        raise ValueError("Launcher is missing or not executable; run setup.sh first.")
    if result == settings:
        print(f"T3 already configured: {instance_id}")
        return
    # Refuse to overwrite a concurrent T3 save between read and write.
    current = path.read_bytes() if path.exists() else None
    if current != before:
        raise ValueError("T3 settings changed during setup; retry.")
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    if before is not None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = path.with_name(path.name + ".bak-argon-" + stamp)
        shutil.copy2(path, backup)
        print(f"Backup: {backup}")
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.chmod(temp, mode)
        if (path.read_bytes() if path.exists() else None) != before:
            raise ValueError("T3 settings changed during setup; retry.")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    print(f"T3 configured: {instance_id}, Gemini 4 Argon, Low / Medium / High")
    print("Refresh provider status; restart the agent session in an existing T3 thread.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", required=True)
    parser.add_argument("--instance", default="codex_argon_proxy")
    parser.add_argument("--launcher", required=True)
    parser.add_argument("--codex-home")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        configure(args.settings, args.instance, args.launcher, args.codex_home, args.check)
    except (ValueError, OSError) as error:
        parser.exit(1, f"T3 setup failed: {error}\n")
