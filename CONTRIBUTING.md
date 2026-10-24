# Contributing

Contributions to the production guides, examples, translations, and skill instructions are welcome.

## Make a focused change

Start from the current `main` branch and keep a change tied to a concrete production need. Put shared guidance in `SKILL.md` and detailed format or craft knowledge in `references/`. Link new references from an appropriate entry point.

Keep the skill usable with actual available tools. When adding an API or command example, identify its prerequisites and verify the supported inputs and output. Prefer portable file-based workflows and preserve editable production assets.

For changes to installation, invocation, or costs, keep the English and Chinese READMEs aligned. Examples should use sample paths and public information. Do not commit credentials, private recordings, customer data, or generated production media.

## Validate

Run from the repository root with Python 3:

```bash
python3 tools/check_skill.py
```

For tool-command changes, run the relevant example with disposable media and inspect the real output. For visual or sound changes, review a representative rendered passage and explain what was checked.

## Submit

Open a pull request that states the problem, the resulting behavior or guidance, and the relevant validation. Keep examples and screenshots limited to what helps review the change.

Contributions are provided under the repository's [MIT License](LICENSE).
