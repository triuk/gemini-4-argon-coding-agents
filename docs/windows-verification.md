# Native Windows verification

Verified on 9 November 2026 on Windows 10 Pro x64, using native PowerShell and Windows
processes. T3 Code and Codex ran on Windows; WSL was not used.

## Environment

| Component | Version |
|---|---|
| T3 Code | 0.1.7 |
| Codex CLI | 0.166.0 |
| uv | 0.13.7 |
| Proxy Python | 3.12.16 |
| LiteLLM | 1.108.3 |
| Google Gen AI | 3.0.0 |
| Google Cloud SDK | 592.0.0 |

## Offline checks

After the consistency review, the installed proxy environment ran
`python -m unittest discover -s tests -v`: 27 tests passed; 11 POSIX installer tests
were skipped on Windows. The passing tests
include the real LiteLLM schema hook, native executable argument/stdio forwarding and
exit codes, paths with spaces and Unicode, T3 merge/backups/idempotency, preservation
of OpenAI/default settings, saved executable/port resolution, detached combined logging,
and rejection of an unknown listener without replacing it.

The Linux installer was retained. Its tests were not executed on Linux in this Windows
session. The CI matrix is configured for Linux and Windows; remote CI results are
reported in GitHub Actions separately from these local Windows checks.

## Live checks

After Google browser sign-in with `gcloud auth login --update-adc`, the selected existing
project had billing and Vertex AI enabled, and ADC's quota project was set.

The complete `setup.ps1` installation was tested separately on port 4001 before updating
the standard port-4000 installation. The installed YAML, schema hook and runtime matched
the repository. `tests/test_proxy.py` passed all three billed calls: problematic schema
declarations and an actual function call, a function-result round trip, and completed
streaming with `OK`. The installed native `codex-argon.exe exec --ephemeral
--skip-git-repo-check 'Reply with the single word OK. Do not use tools.'` also returned `OK`.

The standard installation was then updated with `setup.ps1 -T3`. Its health endpoint
returned HTTP 200 and its installed Codex launcher returned `OK`. T3 exposed
`gemini-4-argon` with `low`, `medium`, and `high` effort. The original global Codex
configuration's SHA-256 remained unchanged, and the Argon instance shared the existing
Codex home. No Google credentials or machine-specific project IDs were added to the repo.

After explicit user opt-in, a per-user `Argon Codex proxy.vbs` Startup entry was created
to call the installed `start-argon.ps1 -Background` with a hidden PowerShell window.
The verified manual proxy was stopped, this entry was invoked, and its new PID, appended
log, and HTTP-200 health response were confirmed. An actual logout/reboot was not performed.
This entry starts the proxy at login; it does not monitor crashes. Disable future login
startup by removing this entry from the user's Startup folder; stop the current verified
proxy separately if needed.

## Follow-up: large catalogs and console windows

The original small live test missed two conditions found in a new T3 conversation:
Vertex rejected more than 512 function declarations, and the detached console-script
launcher let its Python descendants allocate a visible console.

Both launchers now enable Codex Code Mode only for Argon. Its full catalog remains
available through `exec`. The proxy hook moves oversized tool descriptions into Responses
instructions, keeping every definition and the existing instructions. The hook handles
LiteLLM's actual `aresponses` route; otherwise the long Code Mode description would still
fail with `GENERIC_STRING_INVALID_TOO_LONG`.

On a separate port, `tests/test_app_server.py` used the real Codex app-server and the MCP
configuration from T3, plus 530 synthetic tools. The model invoked tool 530 through Code
Mode, received its result, and completed a streamed reply with `ARGON_TOOL_OK`. This check
uses the real Vertex model and billed calls, not a mocked response.

The background proxy now directly invokes LiteLLM's entry point through `pythonw.exe`
with `CREATE_NO_WINDOW`, bypassing the `litellm.exe` console-script shim. Win32 checks
confirmed visible consoles on the original interpreter descendants and no attached
console on either of the replacement GUI-interpreter processes. The offline Windows
regression also verifies both output streams, a zero console handle and the GUI launch
command. `tests/check_windows_console.py --pid <verified-pid>` checks a running proxy's
entire descendant tree without making model requests.

After deploying the same verified files to the main port, the existing login Startup
entry launched the fixed proxy. Its health endpoint returned 200, and the live console
checker confirmed no visible console on the proxy or its interpreter descendant. The
original OpenAI global configuration remained unchanged. A repeated 530-tool model check
on the main port was blocked by Vertex `429 RESOURCE_EXHAUSTED`; this is recorded separately
from the successful port-4001 round trip, not counted as a pass. The active verification
process was stopped. The explicit app-server checker now disables provider request/stream
retries and interrupts its turn immediately on an error; that behavior has offline coverage.

The user subsequently confirmed that the corrected Argon chat works in T3. The earlier
429 remains a historical verification result, rather than a current installation blocker.
