# Third-party notices

This project bundles local copies of runtime dependencies for an offline installation.

| Dependency | Bundled location | License notice |
| --- | --- | --- |
| Mistune 3.2.1 | `vendor/mistune/` | BSD 3-Clause — see [`LICENSE_Mistune.txt`](../LICENSE_Mistune.txt) |
| MathJax browser runtime | `viewer/mathjax-tex-svg.js` | Apache License 2.0 — see [`LICENSE_MathJax.txt`](../LICENSE_MathJax.txt) |

The source archive includes their corresponding license texts. Third-party copyright and license obligations are separate from the **not-yet-selected license of the project's own code**. The presence of these files does not mean the main project has adopted BSD-3-Clause or Apache-2.0.

When updating bundled runtime files, verify exact upstream versions, license compatibility and any additional NOTICE requirements before publishing a new release. No dependency download is performed at runtime.
