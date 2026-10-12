# Testing and evaluation

## Reproducible checks in this repository

```bash
python3 -m unittest discover -s tests -v
python3 check_package.py
python3 -m compileall -q -f *.py
```

The synthetic smoke test exercises a minimal conversation graph with a service message, builds the archive in a temporary directory and checks derived Markdown, metadata, rebuild protection, token-scoped local HTTP and the title-based download filename. It does not contain private user conversations or media. `compileall` checks top-level Python modules; use `python3 -m compileall -q vendor` to check vendored Python files as well.

Optional JavaScript syntax checks require Node.js:

```bash
node --check archive_chat_actions.js
node --check archive_calendar_stats.js
```

The expected runtime has no pip requirements. A real-browser test requires an installed browser and should be reported separately from parser/unit tests.

## Evidence and interpretation

- **User confirmed:** The sequential updates through `v7.3.16.1` operated on the user's actual Windows archive, including the repair of list metadata and Markdown filenames. This is user-reported acceptance, **not** an automated QA certification.
- **Historical release notes:** The included Russian `docs/RELEASE_TESTS_*.md` record synthetic checks during packaging. They are preserved as historical claims; their full test artifacts are not bundled here.
- **New executable checks:** `tests/` contains synthetic data-free tests that can be run again by any contributor.
- **Not verified:** Every combination of large-shard exports and media; all browsers and operating systems; full original OpenAI DIL fidelity; absolute safety of HTML content from untrusted sources.

## Manual regression checklist

1. Build from a throwaway export, check that a second full build is refused.
2. Verify search, timeline filters, statistics and list metadata.
3. Inspect a code-heavy and formula-heavy conversation in both UI modes.
4. Check prompts, assistant replies, code, full-chat copy and Unicode Markdown download name.
5. Confirm a genuinely missing attachment is marked missing; manually restore a known file with matching size and inspect its original message placement.
6. Confirm restored media are not duplicated on subsequent server startups.
7. Test `QUESTION` navigation and `archived` status on source-confirmed cases.
8. Compare counts across Library reports, metadata and manually restored files.

**Privacy:** Never attach real exported chats or private screenshots to public bug reports. Create a minimized synthetic reproduction instead.
