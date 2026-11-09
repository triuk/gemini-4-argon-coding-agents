# Set up Argon from this repository

This is the installation procedure for an agent given a request such as
“Nastav mi podle tohoto repa Argon: https://github.com/triuk/gemini-4-argon-coding-agents”.
Perform the work, including verification. Fetch or clone this repo and read its AGENTS.md
when the user supplies only a link. Use the user's machine where Codex/T3 actually runs.

## 1. Discover the existing setup

- This procedure supports Linux and native Windows. Use setup.sh on Linux and setup.ps1
  on Windows. Use WSL only when the user's T3 agent actually runs inside that environment.
  macOS is not covered; report that limitation before changing files there.
- Find `uv`, `gcloud`, and `codex`, including executables outside the current PATH. Reuse
  working installations. T3 may manage its own Codex executable; its configured Binary path
  is evidence, not a fixed `~/.local/bin/codex` assumption. Ensure the `codex-argon` launcher
  can resolve the real `codex` executable in T3's environment as well as the terminal.
  On Windows use `Get-Command`, the configured T3 Binary path, and user-local tool locations.
  Resolve a real `codex.exe`, not a `.cmd` shim, and pass `-CodexBinary` when needed. Install
  Google Cloud CLI using the official Windows installer or WinGet without `--scope user`.
  The Windows setup bootstrap finds user-local uv even when the agent's PATH is stale.
- If a dependency is missing, install it using its official installation instructions and
  the machine's package manager or a user-local install. Request elevated access only when
  the environment requires it; do not make the user perform agent-runnable steps.
- Never display tokens or credential JSON, copy credentials into this repository, or ask
  for secrets in chat. Treat `GOOGLE_APPLICATION_CREDENTIALS` as an explicit ADC override.
- Detect T3 from the running environment or its settings file. Read only relevant settings:
  active server settings path, existing Codex instance and its shared `homePath`. A remote
  T3 server needs files on that remote machine. Keep the normal OpenAI instance, login,
  global Codex config, other provider settings and current default model intact.

Done: tools, target machine, T3 settings path and shared Codex home are known.

## 2. Prepare Google access

Always run `gcloud auth login --update-adc`, even when an account or ADC already exists.
Let the user complete Google browser sign-in and wait for the command to succeed before
using the account or selecting a project. This signs in the CLI and updates ADC for the
proxy. Do not assume existing credentials belong to the intended account. If
`GOOGLE_APPLICATION_CREDENTIALS` is set, it overrides these ADC: identify that fact and
resolve the intended credential source with the user before proceeding.

Inspect accessible projects, the existing project file (`~/.config/argon-codex/vertex-project`,
or legacy `~/.config/litellm/argon-codex-project`), active gcloud project and ADC quota
project. Choose an unambiguous suitable project; ask if candidates conflict or no suitable
project exists.

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

On native Windows, use PowerShell instead:

```powershell
$env:VERTEX_PROJECT = '<chosen-project>'
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -T3
```

The equivalent Windows options are `-T3Settings`, `-T3Instance`, `-CodexHome`, `-Port`,
and `-FilesOnly`. `-CodexBinary <absolute-path-to-codex.exe>` records the real executable
for T3's environment. Windows setup compiles a native `codex-argon.exe` with the local
.NET Framework 4.x compiler and installs a `Scripts/python.exe` environment. It does not
modify the global PowerShell execution policy or require a Linux shell.

The installer merges the separate Argon instance, executable path, model and its
Low/Medium/High reasoning choices. Existing settings are backed up. Use the installed
launcher path in T3; a path into a temporary clone will break when the clone is removed.

Check the intended proxy port before starting. Reuse an existing compatible Argon proxy
only after confirming its config and schema hook. Leave an unknown listener alone; install
with `--port <free-port>` to store a matching port for the new proxy and launcher.
Keep the standard installation directories for T3. On Linux, if the user requests a custom
`ARGON_CONFIG_DIR`, also provide that environment variable to the T3 instance. The Windows
native launcher embeds the installed runtime's location, so a custom config directory does
not require that variable in T3 unless overriding the installed location.

Done: proxy files and launcher are installed; T3 has the separate Argon model with all
three reasoning options, while its OpenAI instance and default model are preserved.

## 4. Start and verify

Start the installed proxy. In an agent session, use a detached process with output appended
to `~/.config/argon-codex/argon.log`; do not leave it tied to a tool's timeout. Record its PID
and confirm `/health/liveliness` returns HTTP 200. Never stop another process by a broad
`pkill` pattern. Complete verification before offering automatic startup in step 5.

On Windows, start the installed proxy using:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.config\argon-codex\start-argon.ps1" -Background
```

Use the actual installation path if customized. This detaches the process, appends both
output streams to `argon.log`, and records `argon.pid`. Allow LiteLLM to initialize before
checking health. If replacing this installation, verify the PID and process tree before
`taskkill /PID <verified-pid> /T /F`; leave every other listener alone.

Run the offline tests from README.md, then `tests/test_proxy.py --base-url http://127.0.0.1:<port>`.
That live check exercises the problematic tool schemas, a tool result and streaming, and
sends three billed requests. Finally run the installed `codex-argon exec --ephemeral
--skip-git-repo-check 'Reply with the single word OK. Do not use tools.'` and require `OK`.
On Windows use `.venv/Scripts/python.exe` for the tests and the installed
`~/.local/bin/codex-argon.exe` for the final check. Run the native Windows offline tests;
the POSIX installer tests are intentionally selected only on Linux. Test a changed proxy
installation on a separate free port before replacing a verified running one.

For T3 also run `tests/test_app_server.py --launcher <installed-codex-argon-path>
--base-url http://127.0.0.1:<port>` as documented in README.md. It uses the real Codex
app-server, advertises 530 synthetic tools, calls the last one through Code Mode and
requires a completed streamed reply containing its result. This is billed separately.
A plain `OK` check alone cannot detect failures caused by a large T3 tool catalog.
Keep the Code Mode overrides in the separate Argon launcher; never silently drop tools.
The full Code Mode catalog must move to instructions when its description exceeds the
proxy's conservative description budget. Exercise the actual LiteLLM proxy hook route `aresponses`.

On Windows confirm background startup has no visible console for the proxy or its
interpreter descendants. The runtime must use `pythonw.exe` with `CREATE_NO_WINDOW`;
detaching `litellm.exe` alone can still open a console in its child process. Foreground
startup deliberately retains terminal output.

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

- **Yes, on Linux:** configure a user systemd service for the installed `start-argon.sh`, using its
  absolute path, `Restart=on-failure` and `WantedBy=default.target`. Preserve any required
  ADC or custom environment overrides without copying credentials into the unit. Back up
  an existing unit before changing it. Replace only the verified manual proxy process for
  this installation, then run `systemctl --user daemon-reload` and enable/start the service.
  Confirm that it is enabled and active and that the configured health endpoint responds.
  Report the service name and commands for status, journal logs and `disable --now`.
  This starts at user login; boot before login requires a separate explicit request.
  If user systemd is unavailable, explain that limitation and agree on an alternative.
- **Yes, on Windows:** create a per-user startup entry in the current user's Startup folder
  (`[Environment]::GetFolderPath('Startup')`) that invokes the installed `start-argon.ps1
  -Background` at login. Use a hidden launcher, for example a small WScript `.vbs` entry
  calling PowerShell with `-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File`
  and the quoted absolute script path. Back up an existing entry before changing it.
  Preserve required user environment overrides without embedding credentials. Test the
  entry by replacing only this installation's verified proxy process, then confirm the
  saved PID, health endpoint and log. Report the entry's path and how to remove it. This
  starts at login; it does not monitor crashes or start before login. Do not use systemd
  or register an administrator/system-wide service on Windows.
- **No:** leave startup settings unchanged and show the installed proxy's restart command,
  explaining that it must be run again after reboot.

Done: the user's startup choice has been handled and the resulting behavior is explained.
