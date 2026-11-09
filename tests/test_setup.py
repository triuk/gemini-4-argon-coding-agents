import os
import json
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest


REPO = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "POSIX installer; native Windows coverage is in test_windows_setup.py")
class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="argon-setup-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = self.root / "config with spaces"
        self.bin = self.root / "bin with spaces"
        self.env = {**os.environ, "ARGON_CONFIG_DIR": str(self.cfg),
                    "ARGON_BIN_DIR": str(self.bin), "VERTEX_PROJECT": "example-project"}

    def setup(self, *args, **env):
        return subprocess.run(["bash", str(REPO / "setup.sh"), "--files-only", *args],
                              env={**self.env, **env}, text=True, capture_output=True)

    def test_install_rerun_and_update_backup(self):
        first = self.setup()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual((self.cfg / "vertex-project").read_text(), "example-project\n")
        self.assertEqual((self.cfg / "argon.yaml").read_bytes(), (REPO / "proxy/argon.yaml").read_bytes())
        self.assertTrue(os.access(self.bin / "codex-argon", os.X_OK))
        self.assertFalse((self.cfg / ".venv").exists())
        rerun = self.setup(VERTEX_PROJECT="")
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        self.assertFalse(list(self.cfg.glob("*.bak-*")))
        (self.cfg / "argon.yaml").write_text("previous config\n")
        update = self.setup(VERTEX_PROJECT="other-project")
        self.assertEqual(update.returncode, 0, update.stderr)
        self.assertEqual(next(self.cfg.glob("argon.yaml.bak-*")).read_text(), "previous config\n")
        self.assertEqual(next(self.cfg.glob("vertex-project.bak-*")).read_text(), "example-project\n")

    def test_invalid_project_does_not_write_files(self):
        result = self.setup(VERTEX_PROJECT="bad/project")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.cfg.exists())
        self.assertFalse(self.bin.exists())

    def test_launcher_passes_real_config_overrides_and_arguments(self):
        self.assertEqual(self.setup().returncode, 0)
        capture = self.root / "args"
        fake = self.bin / "codex"
        fake.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@" > "$ARGON_CAPTURE"\n')
        fake.chmod(0o755)
        env = {**self.env, "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
               "ARGON_CAPTURE": str(capture), "ARGON_PORT": "4001"}
        prompt = "prompt with spaces and $literal"
        result = subprocess.run([str(self.bin / "codex-argon"), "exec", prompt], env=env)
        self.assertEqual(result.returncode, 0)
        args = capture.read_text().splitlines()
        config = tomllib.loads("\n".join(args[i+1] for i, arg in enumerate(args) if arg == "-c"))
        self.assertEqual(config["model_provider"], "argon")
        self.assertTrue(config["features"]["code_mode"]["enabled"])
        self.assertTrue(config["features"]["code_mode_only"])
        self.assertEqual(config["model_providers"]["argon"]["base_url"], "http://127.0.0.1:4001/v1")
        self.assertEqual(config["model_providers"]["argon"]["wire_api"], "responses")
        self.assertEqual(args[-2:], ["exec", prompt])

    def test_invalid_port_is_rejected_by_both_launchers(self):
        for name in ("proxy/start-argon.sh", "codex/codex-argon"):
            result = subprocess.run(["sh", str(REPO / name)],
                                    env={**self.env, "ARGON_PORT": "4000/bad"}, capture_output=True)
            self.assertEqual(result.returncode, 2)

    def test_saved_port_is_used_by_launcher_and_preserved_on_rerun(self):
        first = self.setup("--port", "4012")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual((self.cfg / "proxy-port").read_text(), "4012\n")
        again = self.setup()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual((self.cfg / "proxy-port").read_text(), "4012\n")
        fake = self.bin / "codex"
        fake.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@"\n')
        fake.chmod(0o755)
        env = {k: v for k, v in self.env.items() if k != "ARGON_PORT"}
        env["PATH"] = str(self.bin) + os.pathsep + os.environ["PATH"]
        result = subprocess.run([str(self.bin / "codex-argon"), "--help"],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('base_url="http://127.0.0.1:4012/v1"', result.stdout)

    def test_invalid_saved_port_does_not_install(self):
        result = self.setup("--port", "65536")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.cfg.exists())

    def test_t3_merge_effort_backup_shared_home_and_idempotency(self):
        settings = self.root / "t3 settings.json"
        original = {
            "defaultModelSelection": {"instanceId": "codex", "model": "gpt-6.1-sol"},
            "providerInstances": {
                "codex": {"driver": "codex", "config": {"homePath": "/shared/codex"}},
                "claude": {"driver": "claudeAgent", "enabled": True},
                "codex_argon_proxy": {"driver": "codex", "displayName": "My Argon",
                                      "config": {"binaryPath": "/old/codex-argon", "customModels": ["another-model"]}},
            },
            "unrelated": {"keep": True},
        }
        settings.write_text(json.dumps(original))
        settings.chmod(0o640)
        args = ("--t3", "--t3-settings", str(settings))
        result = self.setup(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        updated = json.loads(settings.read_text())
        self.assertEqual(updated["defaultModelSelection"], original["defaultModelSelection"])
        self.assertEqual(updated["providerInstances"]["codex"], original["providerInstances"]["codex"])
        self.assertEqual(updated["providerInstances"]["claude"], original["providerInstances"]["claude"])
        self.assertEqual(updated["unrelated"], original["unrelated"])
        argon = updated["providerInstances"]["codex_argon_proxy"]
        self.assertEqual(argon["displayName"], "My Argon")
        self.assertEqual(argon["config"]["homePath"], "/shared/codex")
        self.assertEqual(argon["config"]["binaryPath"], str(self.bin / "codex-argon"))
        models = argon["config"]["customModels"]
        self.assertIn("another-model", models)
        effort = models[-1]["capabilities"]["optionDescriptors"][0]
        self.assertEqual(effort["id"], "reasoningEffort")
        self.assertEqual([option["id"] for option in effort["options"]], ["low", "medium", "high"])
        self.assertEqual(settings.stat().st_mode & 0o777, 0o640)
        backup = next(self.root.glob("t3 settings.json.bak-argon-*"))
        self.assertEqual(json.loads(backup.read_text()), original)
        before = settings.read_bytes()
        again = self.setup(*args)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(before, settings.read_bytes())
        self.assertEqual(len(list(self.root.glob("t3 settings.json.bak-argon-*"))), 1)

    def test_t3_creates_fresh_settings_with_explicit_instance_and_home(self):
        settings = self.root / "fresh" / "settings.json"
        result = self.setup("--t3", "--t3-settings", str(settings), "--t3-instance", "my_argon",
                            "--codex-home", str(self.root / "shared home"))
        self.assertEqual(result.returncode, 0, result.stderr)
        instance = json.loads(settings.read_text())["providerInstances"]["my_argon"]
        self.assertEqual(instance["config"]["homePath"], str(self.root / "shared home"))
        self.assertEqual(settings.stat().st_mode & 0o777, 0o600)

    def test_t3_refuses_conflicting_or_managed_instance_before_installing(self):
        for instance in ({"driver": "claudeAgent"},
                         {"driver": "codex", "config": {"setupMode": "managed"}},
                         {"driver": "codex", "config": {"binaryPath": "/usr/bin/codex"}}):
            with self.subTest(instance=instance):
                settings = self.root / "conflict.json"
                original = json.dumps({"providerInstances": {"codex_argon_proxy": instance}})
                settings.write_text(original)
                result = self.setup("--t3", "--t3-settings", str(settings))
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.cfg.exists())
                self.assertEqual(settings.read_text(), original)

    def test_t3_refuses_builtin_codex_instance_id(self):
        settings = self.root / "settings.json"
        result = self.setup("--t3", "--t3-settings", str(settings), "--t3-instance", "codex")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.cfg.exists())
        self.assertFalse(settings.exists())

    def test_t3_refuses_malformed_settings_without_writing(self):
        settings = self.root / "invalid.json"
        settings.write_text("{broken")
        result = self.setup("--t3", "--t3-settings", str(settings))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.cfg.exists())
        self.assertEqual(settings.read_text(), "{broken")


if __name__ == "__main__":
    unittest.main()
