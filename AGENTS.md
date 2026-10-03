# OpenAI Codex / OpenCode Agent Guidelines

## Repository Context

This repository is the RPC Gateway for the LilyGo T-Embed CC1101 Plus.

It provides a Docker-based gateway between the
`momentum-t-embed-cc1101-rpc` firmware, MCP clients, and the browser-based
gateway interface.

The project can be worked on by both OpenAI Codex and OpenCode. Agents must
preserve enough state for another agent to continue without access to the
previous conversation.

## Authoritative Sources

The current repository contents and project documentation are authoritative.

Important documentation:

- `README.md` - Project overview and quick start
- `USER_GUIDE.md` - User and operational documentation
- `USB-SETUP.md` - USB device setup
- `HTTPS.md` - Traefik/LAN HTTPS deployment

Important implementation files:

- `gateway.py`
- `usb_remote.py`
- `web_ui.py`
- `web_files.py`
- `web.html`
- `tests/test_gateway.py`
- `compose.yaml`
- `compose.traefik-lan.yaml`
- `Dockerfile`

Do not rely on HANDOFF.md for permanent technical documentation when the
information can be obtained from the repository itself.

## Before Starting Work

Before making changes:

1. Run `git status`.
2. Run `git log --oneline -10`.
3. Read `HANDOFF.md` if it exists.
4. Inspect all existing uncommitted changes.
5. Read the documentation relevant to the requested task.
6. Inspect the relevant implementation and tests before changing behavior.

If the working tree already contains changes, determine their purpose before
editing overlapping files.

Never discard, overwrite, reset, clean, or stash another agent's or the user's
changes merely to obtain a clean working tree.

## Working Guidelines

### Preserve Existing Work

- Preserve existing uncommitted changes.
- Work around unrelated changes whenever practical.
- If existing changes conflict with the requested task, report the conflict
  rather than silently replacing them.
- Do not use destructive Git operations without explicit user authorization.

### Scope

- Make only changes required for the current task.
- Preserve existing functionality unless changing it is part of the request.
- Existing files may be added, modified, moved, or removed when legitimately
  required by the task.
- Treat deletion, replacement, and history rewriting with particular care.
- Do not perform unrelated cleanup or refactoring without a clear reason.

### Security

Never commit:

- passwords
- API keys
- authentication tokens
- private keys
- local credentials
- other secrets

Do not expose secrets in logs, documentation, test output, or handoff notes.

Preserve the project's existing security boundaries unless the requested task
explicitly requires a change.

### Documentation

Before modifying behavior, understand the existing implementation and relevant
documentation.

If a change affects user-visible behavior, configuration, deployment, or
operation, update the appropriate documentation as part of the same task.

Do not duplicate large amounts of permanent project documentation in
`HANDOFF.md`.

## Testing and Verification

After making changes:

1. Run the relevant existing tests.
2. For gateway changes, use the existing test suite where applicable:

   `pytest tests/test_gateway.py`

3. Run any additional verification relevant to the change.
4. Review `git diff`.
5. Review `git status`.
6. Ensure only intended files were changed.
7. Report tests or checks that could not be performed.

Do not claim that tests passed unless they were actually executed successfully.

## Git Safety

- Do not use `git reset --hard` without explicit user authorization.
- Do not use `git clean` without explicit user authorization.
- Do not force-push.
- Do not rewrite published history unless explicitly requested.
- Do not discard another agent's changes.
- Do not automatically stash existing changes.
- Do not push changes to a remote repository unless the user has authorized
  the push.

Creating a local commit is allowed when it is part of the requested workflow,
but review the changes first.

## HANDOFF.md

`HANDOFF.md` represents temporary transferable working state between Codex and
OpenCode.

Before handing work to another agent, update it with:

- current objective
- completed work
- unfinished work
- files changed
- tests and verification performed
- known problems or blockers
- important decisions that are not obvious from the code
- recommended next action
- current branch and relevant Git state

Keep `HANDOFF.md` concise.

Do not turn it into a duplicate README or permanent project manual.

## Continuing Previous Work

When the user asks to continue previous work:

1. Read this `AGENTS.md`.
2. Read `HANDOFF.md`.
3. Inspect `git status`.
4. Inspect recent Git history.
5. Inspect the files referenced by the handoff.
6. Verify that the handoff still matches the actual repository state.
7. Continue from the repository state rather than restarting the task.

The repository state takes precedence over stale handoff information.

## Before Finishing

Before completing a task:

1. Run relevant tests and checks.
2. Review `git diff`.
3. Review `git status`.
4. Update relevant project documentation.
5. Update `HANDOFF.md` if another agent may continue the work.
6. Clearly record anything that remains unfinished.

The next agent should be able to understand what happened without needing
access to the previous agent's chat history.