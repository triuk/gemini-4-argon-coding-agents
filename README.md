# Gemini 4 Argon in Codex CLI and T3 Code

## First: sign up for Google Cloud

Go to [Google Cloud Free](https://cloud.google.com/free) and click **Get started for free**
to sign up before continuing with the setup below.

**You must be a new Google Cloud customer to qualify for the $300 welcome credit.**
This requirement applies to the free-trial offer; existing customers can use their
eligible paid Google Cloud project for this setup. See the linked page for Google's
current offer and eligibility terms.

![Google Cloud signup page showing the $300 free credit offer for new customers](docs/images/google-cloud-free-signup.png)

## How it works

This fork keeps the setup verified on Linux on 8 November 2026:

```text
codex-argon → LiteLLM (127.0.0.1:4000, Responses API) → Vertex AI (global)
```

Authentication uses your Google account through Application Default Credentials (ADC).
The proxy uses `vertex_ai/gemini-4-argon`. Installation adds a separate `codex-argon`
command and keeps your normal Codex configuration intact.

## Set it up with one prompt

Give an agent with terminal access to the target Linux computer this prompt:

> Nastav mi podle tohoto repa Argon: https://github.com/triuk/gemini-4-argon-coding-agents
> Používám T3 Code. Přečti AGENTS.md a proveď celý postup v docs/agent-setup.md
> včetně spuštění proxy a ověření. OpenAI chci dál používat vedle Argonu.

The shorter request “Nastav mi podle tohoto repa Argon: [link]” is enough when the agent
can discover the existing T3 installation and Google project. The [agent setup procedure](docs/agent-setup.md)
covers discovery, dependencies, ADC, installation, T3 models, startup and actual API checks.
After verification, the agent asks whether to start the proxy automatically at login and
configures it if you agree. Otherwise, it gives you the manual restart command.
The agent may still need your project choice, browser sign-in, or owner-only billing/IAM
action. It reports such blockers explicitly; cloning the repo alone does not grant access.

This repo's installation supports Linux. T3 Code integration and the three effort choices
were verified on 9 November 2026. macOS and native Windows setup are not included.

## Set up another computer

You need Linux, [uv](https://docs.astral.sh/uv/getting-started/installation/),
[Google Cloud CLI](https://cloud.google.com/sdk/docs/install), and Codex CLI on `PATH`.
Your Google Cloud project must have billing, Vertex AI enabled, and access to this model.
Your Google account needs permission to use Vertex AI and the project's quota.

Clone this fork:

```bash
git clone https://github.com/triuk/gemini-4-argon-coding-agents.git
cd gemini-4-argon-coding-agents
```

Sign in on the new computer, replacing `your-project-id` below:

```bash
gcloud auth login
gcloud services enable aiplatform.googleapis.com --project=your-project-id
gcloud auth application-default login --project=your-project-id
gcloud auth application-default set-quota-project your-project-id
```

`gcloud auth login` authorizes the CLI; the **application-default** login authorizes the
proxy. Follow the browser sign-in when prompted. Existing ADC users can skip the logins.
See [Google's ADC documentation](https://docs.cloud.google.com/sdk/gcloud/reference/auth/application-default/login).

Install the proxy and launcher:

```bash
VERTEX_PROJECT=your-project-id ./setup.sh
```

The installer creates an isolated Python 3.12 environment with the verified LiteLLM and
Google Gen AI versions from `requirements.txt`. It writes proxy files under
`~/.config/argon-codex/` and the launcher at `~/.local/bin/codex-argon`.
Add `~/.local/bin` to `PATH` if needed, or use the full launcher path below.
Re-running setup reuses the environment and saves changed files as `<file>.bak-<timestamp>-<pid>`.

## Start and check

Run the proxy in one terminal:

```bash
~/.config/argon-codex/start-argon.sh
```

Run Codex in another:

```bash
~/.local/bin/codex-argon
```

Or run one short check:

```bash
~/.local/bin/codex-argon exec --ephemeral --skip-git-repo-check 'Reply OK without tools.'
```

The launch overrides select Argon, the local Responses endpoint and low reasoning effort.
They use the same `-c` provider settings as [Codex custom providers](https://learn.chatgpt.com/docs/config-file/config-advanced).
The normal `codex` command keeps using your existing settings. Stop the proxy with Ctrl+C;
start it again after reboot. To keep a log, redirect its output in that terminal:

```bash
~/.config/argon-codex/start-argon.sh > ~/.config/argon-codex/argon.log 2>&1
```

## T3 Code and reasoning effort

Use this command instead of the CLI-only install:

```bash
VERTEX_PROJECT=your-project-id ./setup.sh --t3
```

It creates or updates a separate **Argon proxy** Codex instance and registers
**Gemini 4 Argon** with **Low / Medium / High** effort. The original OpenAI instance,
login and default model stay as they were. Changes to T3 settings are backed up, and
re-running the command keeps a single Argon entry.

After starting the proxy, refresh provider status in T3 and select **Argon proxy →
Gemini 4 Argon** from the thread's model picker. Use **Restart agent session** in the
command palette if an existing conversation retains old metadata. Select the desired
effort beside the model. The launcher's `low` is the fallback; T3's per-turn choice takes
precedence. LiteLLM maps these choices to Gemini's `thinkingLevel`.

The default settings file is `~/.t3/userdata/settings.json` (or under `T3CODE_HOME`).
Use `--t3-settings /path/to/userdata/settings.json` for a different server location,
`--t3-instance my_argon` for a different instance ID, or `--codex-home /path/to/.codex`
to match an existing OpenAI instance's shared home. Compatible Codex instances sharing
that home can continue the same T3 thread. Run setup on the computer hosting the agent.

For manual configuration, add **Codex → Configure manually** in **Settings → Providers**,
set **Binary path** to the absolute installed `codex-argon` path, and use the same
**CODEX_HOME path** as OpenAI. Merge [`codex/t3-model.json`](codex/t3-model.json) as one
entry in `providerInstances.<argon-instance>.config.customModels`. Explicit model
capabilities are necessary: an unregistered model can work while hiding the effort control.
See [T3's Codex guide](https://github.com/pingdotgg/t3code/blob/main/docs/user/providers-codex.md)
and [custom model documentation](https://github.com/pingdotgg/t3code/blob/main/docs/user/composer.md#custom-models).

## Why the schema hook is needed

Codex sends tool declarations even when the prompt requests no tool calls. Gemini rejects
some of their JSON Schema constructs. `proxy/argon_hooks.py` adapts declarations only:

- converts `oneOf` to `anyOf`;
- merges root object unions into an object, keeping fields required in every branch;
- replaces enums containing an empty string and empty-string `const` with description hints.

These conversions relax some constraints in the model's declaration. The tool server still
validates the original schema. Messages and tool results pass through unchanged.

## Tests

After installing, run the offline regression tests from the repository:

```bash
~/.config/argon-codex/.venv/bin/python -m unittest discover -s tests -v
```

With the proxy running, exercise schema compatibility, a tool round trip and streaming.
This sends three small, billed requests to Vertex AI:

```bash
~/.config/argon-codex/.venv/bin/python tests/test_proxy.py
```

For a parallel trial alongside an existing proxy on port 4000, install with `--port 4001`.
Both launchers read that saved port. `ARGON_PORT` can temporarily override it for one
launch; apply the same override to both commands. The live test accepts
`--base-url http://127.0.0.1:4001`.

## Troubleshooting

| Error | Action |
|---|---|
| `401` or expired credentials | Run `gcloud auth application-default login` again. Check whether `GOOGLE_APPLICATION_CREDENTIALS` overrides your ADC. |
| `403` | Check the selected project's billing, Vertex AI API and account permissions. |
| `404` for the model | Check model access; this setup uses the `global` endpoint. |
| `429 Resource exhausted` | Retry later or inspect the project's quota/capacity. A running proxy cannot resolve an upstream capacity limit. |
| `400` naming a tool schema | Check that the installed hook matches the repo, then restart the proxy. |
| Port 4000 already in use | Reuse a verified compatible proxy, or install with `--port 4001`. |
| Effort selector missing in T3 | Re-run `./setup.sh --t3`, refresh provider status, then restart the agent session. |

## Files and removal

`setup.sh --files-only` writes files without installing dependencies or starting anything.
`ARGON_CONFIG_DIR` and `ARGON_BIN_DIR` can override the installation directories;
`XDG_CONFIG_HOME` is respected for the default config directory.
When using a custom `ARGON_CONFIG_DIR` with T3, set that variable in the instance's environment too.
There are no embedded credentials, machine-specific paths or Google project IDs in the repo.
To remove the installation, stop its proxy and remove `~/.config/argon-codex/` and
`~/.local/bin/codex-argon`. Remove its T3 provider instance if you used `--t3`.
To undo a later file update, restore its adjacent `.bak-*` copy.

Based on [Itsme23476/gemini-4-argon-coding-agents](https://github.com/Itsme23476/gemini-4-argon-coding-agents).
