# Bootstrap prompt — how to start any AI agent on this project

The repository root has one-line shims (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`) that most tools read automatically.
If your tool does not, paste this as your first message:

```text
You are working on the Argus project in this repository. Read brain/README.md and follow the Argus Brain
protocol in brain/agents/AGENT_PROTOCOL.md exactly. I am <your-github-handle>. Start with:
python brain/tools/brain.py start
```

That is all the context an agent needs: everything else is in `brain/`. Do not paste project state from your own
notes or from a tool's private memory — if something is missing from the Brain, add it to the Brain.
