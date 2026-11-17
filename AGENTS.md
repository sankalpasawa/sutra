# Sutra repository: instructions for AI agents

**Changing anything under `sutra-pro/` (Sutra Pro: the app, its desktop shell, its releases)? Read [sutra-pro/AGENTS.md](sutra-pro/AGENTS.md) first and follow it.** In short:

1. Try a change in a local **beta** app: `cd sutra-pro && scripts/py scripts/install_app.py beta` installs "Sutra Pro Beta" beside the released Sutra Pro (its own data folder; it is never published).
2. Push your work to GitHub: the branch, then `main` once CI is green.
3. Release only when the owner asks: `scripts/py scripts/release.py` publishes the release on GitHub and then installs it on this Mac.

The older Sutra product's own instructions are in [CLAUDE.md](CLAUDE.md) and [START-HERE.md](START-HERE.md).
