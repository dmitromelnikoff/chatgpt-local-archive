# Security and privacy

## Publication boundary

This repository contains **program source and third-party runtime files only**. A user's OpenAI export is **not** an example fixture. Do not commit or upload:

- `conversations*.json`, manifests (including `library_files.json`), original `.dat` media or exported files.
- `ChatGPT_Local_Archive/`, `ChatGPT_Generated_Files/`, `recovered_files.json`, generated chat Markdown or screenshots containing identifiable conversations.
- Live credentials, browser tokens, cookies, private documents, proprietary internal URLs or personally identifiable information.

`.gitignore` is a safety net rather than a guarantee. Check `git status --short`, `git ls-files` and `git diff --cached --name-only` before pushing. Files already tracked by Git remain tracked even after adding ignore rules.

## Runtime trust model

The viewer is intended for **one person on their own computer**. The HTTP server binds to `127.0.0.1`, uses a random URL prefix per run, and requires this prefix for requests. Restoring files requires deliberate user selection in the browser. This is not an audited authentication system and should **not** be exposed through reverse proxies, tunnels or public ports.

User exports may contain **untrusted HTML, SVG, DIL, file names and links**. Some content is filtered, escaped or sandboxed, but end-to-end browser content security has not been independently audited. Handle third-party or tampered exports with caution.

The original ChatGPT link opens `chatgpt.com` upon user action; it is not a background upload. Browser extensions and external software may have access to files/content on the user's machine.

## Secret response plan

If a real API key, access token or password is accidentally committed, **revoke or rotate it**, then investigate commit history, forks and caches. Editing or deleting the current file alone does not invalidate an exposed credential. Do not put real secrets in issue reports.

The present application uses **no API key or `.env` configuration**, so `.env.example` is intentionally not included.

## Safe development practices

- Use synthetic JSON in tests; never add a real export to fixtures.
- Before sharing a bug reproduction, remove titles, prompts, emails, URLs, IDs and media from logs and screenshots.
- Keep the bundled third-party copyright and license notices when redistributing.
- Test changes to recovery and HTML patching in disposable temporary directories first.
