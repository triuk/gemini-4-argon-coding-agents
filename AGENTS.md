# Scope

This fork targets Codex CLI and T3 Code on Linux using Vertex AI ADC.

## Install from a repository link

When a user asks to set up Argon using this repo, follow [docs/agent-setup.md](docs/agent-setup.md).
Carry out discovery, installation, T3 configuration when applicable, proxy startup and checks.
The request authorizes those local setup steps. Ask only for missing choices or actions the
user must perform, such as Google browser sign-in; keep working on independent steps.

## Change this repository

Read README.md before changing installation behavior. Keep the default Codex config and other
agents' settings intact; provider overrides belong in the separate codex-argon launcher.

# Verification

Run offline tests with the installed proxy environment as documented in README.md.
Changes to schema normalization need regression coverage through the real LiteLLM hook.
Live checks use billed Vertex requests; report their results separately from offline tests.
Test new proxy configurations on a separate port before replacing a running installation.
