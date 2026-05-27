# OpenClaude Tool Usage Rules

## Environment Notes

The current environment runs on:

```text
node:22-slim
```

A Python virtual environment is already activated before OpenClaude starts:

```bash
source /work/.venv/bin/activate
```

When Python is needed, prefer:

```bash
python
pip
```

Do not use absolute paths such as:

```bash
/usr/bin/python3
/usr/bin/pip3
```

unless there is a clear reason, because doing so may bypass the activated virtual environment.

---

## Purpose

This file defines how OpenClaude should use the provided tools when working inside the `/work` repository.

General coding behavior, such as thinking before coding, keeping changes simple, making surgical edits, and verifying the goal, is already covered by the integrated `andrej-karpathy-skills` rules.

Do not duplicate that workflow here.  
Focus on using the available tools correctly and efficiently.

---

## Tool Usage Policy

OpenClaude must use the provided tools instead of guessing, manually scanning too much code, or making unsupported assumptions.

Use the right tool for the right job:

- `agentmemory`: retrieve and save project-specific technical knowledge.
- `semble`: search the current codebase semantically.
- `filesystem`: read and edit files inside `/work`.
- `searxng`: search public web information when external documentation or up-to-date information is needed.

---

## `agentmemory`

Use `agentmemory` to retrieve and store useful technical knowledge across sessions.

Use it before starting a complex or repeated task when the answer may depend on:

- previous fixes,
- repository conventions,
- architecture decisions,
- known environment issues,
- test/build commands,
- dependency or runtime quirks.

Examples of useful queries:

```text
How is the backend started in this project?
Known import issues in this container
Frontend folder structure conventions
How Prisma migrations are handled here
How GPU support is configured for Podman
```

After completing a non-trivial fix or discovering an important project rule, save a memory containing:

- the issue,
- the root cause,
- the correct fix,
- relevant files or modules,
- commands used to verify the result.

Never store secrets, API keys, passwords, tokens, private keys, or sensitive user data.

---

## `semble`

Use `semble` as the primary tool for finding relevant code in the repository.

Prefer:

```text
semble search
```

over broad manual scanning or wide `grep` usage.

Use `semble` to find:

- business logic,
- functions,
- classes,
- components,
- API routes,
- services,
- repositories,
- tests,
- config related to a feature or bug.

After finding a likely location, use related-code exploration when needed to understand callers, dependencies, tests, and nearby flow.

Do not read the whole repository without a clear target.

---

## `filesystem`

Use `filesystem` to read and modify files only after locating the relevant area.

Rules:

- Read only files that are relevant to the task.
- Read enough surrounding context before editing.
- Make small, localized changes.
- Do not rewrite large files when only a small edit is needed.
- After editing, read back the changed section to verify the result.
- Do not edit unrelated files.
- Do not leave temporary debug code behind.

Remove only debug code, unused imports, unused variables, or dead code introduced by your own changes unless the user explicitly asks for broader cleanup.

---

## `searxng`

Use `searxng` when the task requires public information outside the repository.

Use it for:

- official documentation,
- framework or library behavior,
- CLI changes,
- dependency issues,
- error messages from external tools,
- release notes,
- public issue trackers,
- configuration examples from reliable sources.

Prioritize official sources:

- official documentation,
- official repositories,
- release notes,
- maintainers’ issue discussions.

Do not use `searxng` as a replacement for reading the local codebase.

Never search or send secrets, tokens, passwords, private keys, customer data, or other sensitive content to external search tools.

Relationship between tools:

```text
semble  -> search inside the current repository
searxng -> search public information outside the repository
```

---

## Testing and Verification

After making changes, run the most relevant verification command for the task.

Examples:

```bash
npm test
npm run test
npm run build
npm run lint
npm run typecheck
python -m pytest
pytest
ruff check .
python -m compileall .
```

Choose commands based on the project and the changed area.

Prefer focused checks near the changed code instead of unnecessarily heavy commands.

If a command cannot be run, report clearly:

- the command attempted,
- why it failed or could not run,
- what was still verified,
- what the user should run next.

Never claim that tests passed unless they were actually run and passed.

---

## Git and Diff Rules

Before finishing, inspect the diff when possible:

```bash
git diff
```

Check for:

- unrelated changes,
- accidental formatting changes,
- leaked secrets,
- leftover debug code,
- temporary files,
- overly broad edits.

Do not commit unless the user explicitly asks.

If committing is requested, use Conventional Commits:

```text
fix(api): handle missing user id
feat(auth): add refresh token endpoint
docs(agent): update tool usage rules
chore(docker): simplify startup script
```

Do not commit a broken state.

---

## Security Rules

Never write real secrets into the repository.

Do not hardcode:

- API keys,
- passwords,
- real database URLs,
- JWT secrets,
- private keys,
- access tokens,
- refresh tokens.

Use environment variables, `.env`, secret managers, or documented placeholders.

If adding a new environment variable, update the relevant example file or documentation, but never include the real value.

---

## User Communication

Final responses should be short and focused.

Report:

- what was changed,
- which files were changed,
- what verification was run,
- what could not be verified,
- any important limitation or next step.

Be transparent when context is missing or verification could not be completed.

Do not promise background work. All work must be completed and reported in the current session.
