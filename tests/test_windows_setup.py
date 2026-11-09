"""Native Windows installation and real process-boundary regression checks (no cloud calls)."""
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest


REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "Native Windows process tests")
class WindowsSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory(prefix="argon-windows-tools-")
        cls.addClassCleanup(cls.shared.cleanup)
        root = Path(cls.shared.name)
        cls.fake = root / "fake codex.exe"
        cls.uv = root / "uv.exe"
        source = root / "capture.cs"
        source.write_text('''using System;
using System.IO;
using System.Text;
using System.Runtime.InteropServices;
class Capture {
  [DllImport("kernel32.dll")] static extern IntPtr GetConsoleWindow();
  static int Main(string[] args) {
    string capture = Environment.GetEnvironmentVariable("ARGON_CAPTURE");
    if (capture != null) {
      using (var file = new StreamWriter(capture, false, new UTF8Encoding(false))) {
        foreach (string arg in args) file.WriteLine(Convert.ToBase64String(Encoding.UTF8.GetBytes(arg)));
      }
    }
    if (Environment.GetEnvironmentVariable("ARGON_ECHO_STDIN") == "1") Console.WriteLine(Console.ReadLine());
    if (Environment.GetEnvironmentVariable("ARGON_FAKE_PROXY") == "1") {
      Console.WriteLine("CONSOLE_HANDLE=" + GetConsoleWindow().ToInt64());
      Console.WriteLine("PROXY_STDOUT"); Console.Error.WriteLine("PROXY_STDERR");
    }
    return 17;
  }
}''', encoding="utf-8")
        compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        if not compiler.exists():
            compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework/v4.0.30319/csc.exe"
        subprocess.run([str(compiler), "/nologo", "/target:exe", "/out:" + str(cls.fake), str(source)], check=True)
        cls.uv.write_bytes(cls.fake.read_bytes())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="argon-windows-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config with spaces \u017e"
        self.bin = self.root / "bin with spaces \u017e"
        self.launcher = self.bin / "codex-argon.exe"
        self.capture = self.root / "args"
        self.env = {**os.environ, "PYTHONUTF8": "1", "ARGON_CONFIG_DIR": str(self.config),
                    "ARGON_BIN_DIR": str(self.bin), "VERTEX_PROJECT": "example-project",
                    "ARGON_CODEX_BINARY": str(self.fake), "ARGON_CAPTURE": str(self.capture)}
        self.env.pop("ARGON_PORT", None)

    def setup(self, *args, **env):
        return subprocess.run([sys.executable, str(REPO / "scripts/setup_windows.py"), "--files-only", *args],
                              env={**self.env, **env}, text=True, encoding="utf-8", capture_output=True)

    def installed(self, *args):
        result = self.setup(*args)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def captured(self):
        return [base64.b64decode(line).decode("utf-8") for line in self.capture.read_text(encoding="utf-8").splitlines()]

    def test_install_rerun_saved_values_and_backups(self):
        self.installed("--port", "4012")
        self.assertEqual((self.config / "argon.yaml").read_bytes(), (REPO / "proxy/argon.yaml").read_bytes())
        self.assertFalse((self.config / ".venv").exists())
        self.assertEqual((self.config / "proxy-port").read_text(), "4012\n")
        before = self.launcher.read_bytes()
        result = self.setup(VERTEX_PROJECT="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.launcher.read_bytes(), before)
        self.assertFalse(list(self.config.glob("*.bak-*")))
        (self.config / "argon.yaml").write_text("old config\n")
        result = self.setup(VERTEX_PROJECT="other-project")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(next(self.config.glob("argon.yaml.bak-*")).read_text(), "old config\n")
        self.assertEqual(next(self.config.glob("vertex-project.bak-*")).read_text(), "example-project\n")
        self.assertEqual((self.config / "proxy-port").read_text(), "4012\n")

    def test_invalid_project_and_port_do_not_install(self):
        for override in ({"VERTEX_PROJECT": "bad/project"}, {"ARGON_PORT": "65536"}, {"ARGON_PORT": "4000/bad"}):
            with self.subTest(override=override):
                result = self.setup(**override)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.config.exists())
                self.assertFalse(self.bin.exists())

    def test_missing_explicit_codex_does_not_install(self):
        result = self.setup("--codex-binary", str(self.root / "missing.exe"))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.config.exists())

    def test_malformed_primary_t3_settings_fail_before_writing_files(self):
        settings = self.root / "malformed-primary.json"
        for invalid in ([], {"providerInstances": []}, {"providerInstances": {"codex": []}},
                        {"providerInstances": {"codex": {"config": []}}}):
            with self.subTest(settings=invalid):
                settings.write_text(json.dumps(invalid), encoding="utf-8")
                result = self.setup("--t3-settings", str(settings))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("T3", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(self.config.exists())
                self.assertFalse(self.bin.exists())
                self.assertEqual(json.loads(settings.read_text(encoding="utf-8")), invalid)

    def test_launcher_preserves_arguments_exit_code_and_provider_options(self):
        self.installed("--port", "4012")
        values = ["exec", "", 'spaces $literal %PATH% ! ^ & | < >', '"quotes" \\', "\u011b\u0161\u010d\u0159\u017e", "line1\nline2", "C:\\folder with space\\"]
        result = subprocess.run([str(self.launcher), *values], env=self.env, capture_output=True)
        self.assertEqual(result.returncode, 17, result.stderr)
        args = self.captured()
        self.assertEqual(args[-len(values):], values)
        prefix = args[:-len(values)]
        config = tomllib.loads("\n".join(prefix[i+1] for i, arg in enumerate(prefix) if arg == "-c"))
        self.assertEqual(config["model_provider"], "argon")
        self.assertTrue(config["features"]["code_mode"]["enabled"])
        self.assertTrue(config["features"]["code_mode_only"])
        self.assertFalse(config["model_providers"]["argon"]["requires_openai_auth"])
        self.assertEqual(config["model_providers"]["argon"]["base_url"], "http://127.0.0.1:4012/v1")
        self.assertEqual(config["model_providers"]["argon"]["wire_api"], "responses")

    def test_saved_codex_works_without_terminal_path_or_config_environment(self):
        self.installed()
        env = {k: v for k, v in self.env.items() if k not in ("ARGON_CODEX_BINARY", "ARGON_CONFIG_DIR", "XDG_CONFIG_HOME")}
        env["PATH"] = os.environ["WINDIR"]
        result = subprocess.run([str(self.launcher), "--version"], env=env, capture_output=True)
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(self.captured()[-1], "--version")

    def test_stdio_port_override_and_later_effort_override(self):
        self.installed()
        env = {**self.env, "ARGON_PORT": "4001", "ARGON_ECHO_STDIN": "1"}
        request = '{"id":1,"method":"initialize"}'
        result = subprocess.run([str(self.launcher), "app-server", "-c", 'model_reasoning_effort="high"'],
                                input=request + "\n", env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(result.stdout.strip(), request)
        args = self.captured()
        self.assertIn('model_providers.argon.base_url="http://127.0.0.1:4001/v1"', args)
        self.assertEqual(args[-3:], ["app-server", "-c", 'model_reasoning_effort="high"'])

    def test_both_launchers_reject_invalid_override(self):
        self.installed()
        for args in ([str(self.launcher)], [sys.executable, str(self.config / "argon_runtime.py"), "proxy"]):
            result = subprocess.run(args, env={**self.env, "ARGON_PORT": "4000/bad"}, capture_output=True)
            self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.capture.exists())

    def test_t3_merge_preserves_openai_default_other_instances_and_utf8(self):
        settings = self.root / "t3 settings.json"
        original = {"defaultModelSelection": {"instanceId": "codex", "model": "gpt-6.1-sol"},
                    "providerInstances": {"codex": {"driver": "codex", "config": {"homePath": str(self.root / "shared")}},
                                          "claude": {"driver": "claudeAgent", "enabled": True},
                                          "codex_argon_proxy": {"driver": "codex", "displayName": "M\u016fj Argon",
                                                                "config": {"binaryPath": "C:/old/codex-argon.exe", "customModels": ["another-model"]}}},
                    "unrelated": {"keep": True}}
        settings.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
        args = ("--t3", "--t3-settings", str(settings))
        self.installed(*args)
        updated = json.loads(settings.read_text(encoding="utf-8"))
        for key in ("defaultModelSelection", "unrelated"):
            self.assertEqual(updated[key], original[key])
        for key in ("codex", "claude"):
            self.assertEqual(updated["providerInstances"][key], original["providerInstances"][key])
        argon = updated["providerInstances"]["codex_argon_proxy"]
        self.assertEqual(argon["displayName"], "M\u016fj Argon")
        self.assertEqual(argon["config"]["homePath"], str(self.root / "shared"))
        self.assertEqual(argon["config"]["binaryPath"], str(self.launcher))
        self.assertIn("another-model", argon["config"]["customModels"])
        effort = argon["config"]["customModels"][-1]["capabilities"]["optionDescriptors"][0]
        self.assertEqual(effort["id"], "reasoningEffort")
        self.assertEqual([o["id"] for o in effort["options"]], ["low", "medium", "high"])
        self.assertEqual(json.loads(next(self.root.glob("*.bak-argon-*")).read_text(encoding="utf-8")), original)
        before = settings.read_bytes()
        self.installed(*args)
        self.assertEqual(before, settings.read_bytes())
        self.assertEqual(len(list(self.root.glob("*.bak-argon-*"))), 1)

    def test_t3_fresh_settings_custom_id_home_and_t3code_home(self):
        home = self.root / "shared home"
        result = self.setup("--t3", "--t3-instance", "my_argon", "--codex-home", str(home), T3CODE_HOME=str(self.root / "t3"))
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = json.loads((self.root / "t3/userdata/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["providerInstances"]["my_argon"]["config"]["homePath"], str(home))

    def test_t3_refuses_conflicts_before_installation(self):
        for instance in ({"driver": "claudeAgent"}, {"driver": "codex", "config": {"setupMode": "managed"}},
                         {"driver": "codex", "config": {"binaryPath": "C:/other/codex.exe"}}):
            with self.subTest(instance=instance):
                settings = self.root / "conflict.json"
                original = json.dumps({"providerInstances": {"codex_argon_proxy": instance}})
                settings.write_text(original)
                result = self.setup("--t3", "--t3-settings", str(settings))
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.config.exists())
                self.assertEqual(settings.read_text(), original)

    def test_t3_refuses_builtin_id_and_malformed_settings(self):
        settings = self.root / "settings.json"
        result = self.setup("--t3", "--t3-settings", str(settings), "--t3-instance", "codex")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(settings.exists())
        settings.write_text("{broken")
        result = self.setup("--t3", "--t3-settings", str(settings))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(settings.read_text(), "{broken")
        self.assertFalse(self.config.exists())

    def test_background_proxy_appends_both_streams_and_records_pid(self):
        self.installed()
        scripts = self.config / ".venv/Scripts"
        scripts.mkdir(parents=True)
        (scripts / "litellm.exe").write_bytes(self.fake.read_bytes())
        (scripts / "pythonw.exe").write_bytes(self.fake.read_bytes())
        log = self.config / "argon.log"
        log.write_text("existing log\n")
        with socket.socket() as port:
            port.bind(("127.0.0.1", 0))
            number = port.getsockname()[1]
        result = subprocess.run([sys.executable, str(self.config / "argon_runtime.py"), "proxy", "--background"],
                                env={**self.env, "ARGON_FAKE_PROXY": "1", "ARGON_PORT": str(number)}, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and "PROXY_STDERR" not in log.read_text():
            time.sleep(0.05)
        self.assertIn("existing log\n", log.read_text())
        self.assertIn("PROXY_STDOUT", log.read_text())
        self.assertIn("PROXY_STDERR", log.read_text())
        self.assertIn("CONSOLE_HANDLE=0", log.read_text())
        args = self.captured()
        self.assertEqual(args[:2], ["-c", "from litellm import run_server; run_server()"])
        self.assertGreater(int((self.config / "argon.pid").read_text()), 0)

    def test_proxy_leaves_unknown_listener_alone(self):
        self.installed()
        scripts = self.config / ".venv/Scripts"
        scripts.mkdir(parents=True)
        (scripts / "litellm.exe").write_bytes(self.fake.read_bytes())
        (scripts / "pythonw.exe").write_bytes(self.fake.read_bytes())
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            result = subprocess.run([sys.executable, str(self.config / "argon_runtime.py"), "proxy", "--background"],
                                    env={**self.env, "ARGON_PORT": str(listener.getsockname()[1])}, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((self.config / "argon.pid").exists())
            self.assertTrue(listener.fileno() >= 0)

    def test_powershell_bootstrap_passes_paths_flags_and_exit_status(self):
        result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO / "setup.ps1"),
                                 "-T3", "-FilesOnly", "-Port", "4012", "-CodexHome", str(self.root / "home with spaces")],
                                env={**self.env, "PATH": str(self.uv.parent) + os.pathsep + os.environ["PATH"]}, capture_output=True)
        self.assertEqual(result.returncode, 17, result.stderr)
        args = self.captured()
        self.assertIn("--no-project", args)
        self.assertIn("--files-only", args)
        self.assertIn("--t3", args)
        self.assertEqual(args[args.index("--port") + 1], "4012")
        self.assertEqual(args[args.index("--codex-home") + 1], str(self.root / "home with spaces"))


if __name__ == "__main__":
    unittest.main()
