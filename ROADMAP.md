# Roadmap

This is a **plan**, not a claim that the listed features already exist. Priorities may change after testing on more export variants. Work on the DIL renderer should be isolated from the stable archival path.

## P0 — Stability, data safety, reproducibility

- Expand synthetic fixtures for differing export schemas, branches, Library metadata and missing assets.
- Add repeatable cross-platform end-to-end tests (including a real browser and restoration interactions).
- Review the loopback server and generated HTML for injection, cross-origin and path-traversal threats.
- Document deterministic backup and restore procedures for existing manually recovered archives.
- Validate optional dependencies, third-party license notices and release provenance.

## P1 — Accuracy and observability

- Improve distinctions between exact, inferred and unresolved asset-to-message bindings.
- Expose confidence and evidence for heuristic associations in archive reports and UI.
- Compare generated Markdown with expected output for code, mathematical expressions, tables and recovered links.
- Support more export schema variants without changing the current archive format.

## P2 — Intelligent UI research and localization

- Prototype a **separate** AST-based DIL parser and typed component renderer; do not replace the stable renderer without regression tests.
- Improve complex DIL templates, SVG, code labels and dynamic UI fallbacks.
- Introduce **RU/EN localization** via externalized UI strings without altering archival or recovery behavior. Preserve the original Russian UX as the default until translations are verified.
- Add documentation and evaluation fixtures for component fidelity. OpenAI's original closed renderer is not assumed to be available.

## P3 — Optional exports and developer experience

- Explore exporting a chat and its attachments as a portable ZIP while preserving references.
- Add configurable source/output directories (currently script-relative paths) after backward-compatibility tests.
- Add optional GitHub issue templates / CI only once representative tests are stable.

## Out of scope for the current baseline

- Hosting users' private archives as a public SaaS.
- Executing arbitrary JavaScript found in exported DIL or conversation messages.
- Claiming 1:1 compatibility with the native ChatGPT Intelligent UI runtime.
