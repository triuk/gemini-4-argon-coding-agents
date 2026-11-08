# Set up Argon from this repository

This is the installation procedure for an agent given a request such as
“Nastav mi podle tohoto repa Argon: https://github.com/triuk/gemini-4-argon-coding-agents”.
Perform the work, including verification. Fetch or clone this repo and read its AGENTS.md
when the user supplies only a link. Use the user's machine where Codex/T3 actually runs.

## 1. Discover the existing setup

- This procedure supports Linux, including a Linux environment inside WSL. On another OS,
  report that limitation and ask which Linux environment to use before changing files.
- Find `uv`, `gcloud`, and `codex`, including executables outside the current PATH. Reuse
  working installations. T3 may manage its own Codex executable; its configured Binary path
  is evidence, not a fixed `~/.local/bin/codex` assumption. Ensure the `codex-argon` launcher
  can resolve the real `codex` executable in T3's environment as well as the terminal.
- If a dependency is missing, install it using its official installation instructions and
  the machine's package manager or a user-local install. Request elevated access only when
  the environment requires it; do not make the user perform agent-runnable steps.
- Inspect the existing project file (`~/.config/argon-codex/vertex-project`, or legacy
  `~/.config/litellm/argon-codex-project`), active gcloud project and ADC quota project.
  Choose an unambiguous project; ask if no suitable project exists or candidates conflict.
  Treat `GOOGLE_APPLICATION_CREDENTIALS` as an explicit ADC override. Never display tokens
  or credential JSON, copy credentials into this repository, or ask for secrets in chat.
- Detect T3 from the running environment or its settings file. Read only relevant settings:
  active server settings path, existing Codex instance and its shared `homePath`. A remote
  T3 server needs files on that remote machine. Keep the normal OpenAI instance, login,
  global Codex config, other provider settings and current default model intact.

Done: tools, project, target machine, T3 settings path and shared Codex home are known.

## 2. Prepare Google access

Reuse valid Google Application Default Credentials. A normal `gcloud auth login` alone
does not authorize the proxy. If needed, run the ADC login command from README.md and let
the user complete browser sign-in. Continue after the command succeeds.

Enable `aiplatform.googleapis.com` on the chosen project if missing and set its ADC quota
project. If billing, model access or IAM permissions require the project owner, explain the
specific missing action and resume verification when it is resolved. Do not create a new
project, attach a billing account or purchase reserved capacity automatically.

Done: the chosen project has Vertex access and ADC is ready for a live check.

## 3. Install and configure

Run `VERTEX_PROJECT=<chosen-project> ./setup.sh --t3` for T3, or omit `--t3` for CLI-only use.
For a custom T3 server settings location, pass `--t3-settings <absolute-path>`.
For a nondefault shared Codex home, pass `--codex-home <absolute-path>`.
If the default Argon instance ID is occupied by another provider, choose a new
`--t3-instance <id>` rather than replacing it.

The installer merges the separate Argon instance, executable path, model and its
Low/Medium/High reasoning choices. Existing settings are backed up. Use the installed
launcher path in T3; a path into a temporary clone will break when the clone is removed.

Check the intended proxy port before starting. Reuse an existing compatible Argon proxy
only after confirming its config and schema hook. Leave an unknown listener alone; install
with `--port <free-port>` to store a matching port for the new proxy and launcher.
Keep the standard installation directories for T3. If the user requests a custom
`ARGON_CONFIG_DIR`, also provide that environment variable to the T3 instance.

Done: proxy files and launcher are installed; T3 has the separate Argon model with all
three reasoning options, while its OpenAI instance and default model are preserved.

## 4. Start and verify

Start the installed proxy. In an agent session, use a detached process with output appended
to `~/.config/argon-codex/argon.log`; do not leave it tied to a tool's timeout. Record its PID
and confirm `/health/liveliness` returns HTTP 200. Never stop another process by a broad
`pkill` pattern. Complete verification before offering automatic startup in step 5.

Run the offline tests from README.md, then `tests/test_proxy.py --base-url http://127.0.0.1:<port>`.
That live check exercises the problematic tool schemas, a tool result and streaming, and
sends three billed requests. Finally run the installed `codex-argon exec --ephemeral
--skip-git-repo-check 'Reply with the single word OK. Do not use tools.'` and require `OK`.

For T3, confirm the instance has `gemini-4-argon` with `reasoningEffort` choices
`low`, `medium`, `high`; refresh provider status if needed. Tell the user where to select
Argon and use **Restart agent session** when an existing conversation retains old metadata.

Report each check as passed or blocked. A running proxy or HTTP 200 before a streaming
error is not a successful model response. On 429, inspect the error and report capacity
as a remaining blocker; do not add a retry storm or claim that file installation solved it.
For 400 tool schema errors, inspect the installed hook and request shape before retrying.

Done: offline tests and live round trip pass, the actual Codex launcher replies `OK`, and
T3 exposes the model and three effort values. If a check is blocked, state the exact
remaining action instead of claiming the installation works.

## 5. Ask about automatic startup

After reporting the verification results, ask in the user's language:
“Chceš, aby se proxy automaticky spouštěla po přihlášení do systému?”
Make this the final setup question, not an extra requirement in the initial prompt.
If the user has already explicitly accepted or declined automatic startup, use that choice.
Wait for an answer before changing startup settings; silence leaves the manual setup intact.
If verification is blocked, resolve that blocker before offering automatic startup.

- **Yes:** configure a user systemd service for the installed `start-argon.sh`, using its
  absolute path, `Restart=on-failure` and `WantedBy=default.target`. Preserve any required
  ADC or custom environment overrides without copying credentials into the unit. Back up
  an existing unit before changing it. Replace only the verified manual proxy process for
  this installation, then run `systemctl --user daemon-reload` and enable/start the service.
  Confirm that it is enabled and active and that the configured health endpoint responds.
  Report the service name and commands for status, journal logs and `disable --now`.
  This starts at user login; boot before login requires a separate explicit request.
  If user systemd is unavailable, explain that limitation and agree on an alternative.
- **No:** leave startup settings unchanged and show the installed proxy's restart command,
  explaining that it must be run again after reboot.

Done: the user's startup choice has been handled and the resulting behavior is explained.
