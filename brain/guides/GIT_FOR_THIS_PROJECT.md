# Git for this project — the only commands you need

`brain.py` runs most of the session commands for you. These are the ones you will see, each explained.

| # | Command | What it does | When |
|---|---|---|---|
| 1 | `git clone https://github.com/agenticteam03/argus_production.git` | copies the repository to your laptop | once |
| 2 | `git status` | shows changed, new and staged files, and your branch | any time; before every commit |
| 3 | `git checkout main` then `git pull` | switches to `main` and brings it up to date | start of a session (`brain.py start` does it) |
| 4 | `git checkout -b task/T-0013-langgraph-skeleton` | creates your task branch from where you are (be on `main`) | start of a task |
| 5 | `git checkout task/T-0013-langgraph-skeleton` | switches to an existing branch (e.g. from a handoff) | continuing a task |
| 6 | `git add <files>` | stages the files for the next commit (prefer naming files over `git add .`) | before a commit |
| 7 | `git commit -m "T-0013: …"` | records a checkpoint locally | after each verified step |
| 8 | `git push -u origin task/T-0013-langgraph-skeleton` | uploads the branch (CI runs) | after each commit |
| 9 | `git diff` / `git diff --staged` | shows what you changed / what will be committed | before committing |
| 10 | `git log --oneline -5` | the last 5 commits | to know where you are |
| 11 | `gh pr create` / `gh pr list` / `gh pr checkout <n>` | create, list and check out pull requests | task complete / review |

## Never run (without the team)

- `git push --force` (rewrites shared history), `git reset --hard` (throws away work), `git commit` on `main`.
- `git add .` when `output.bash`, a `.env` or a secret could be in the folder (they are gitignored, but check `git status`).

## If you are stuck

- "Your branch is behind" → `git pull`.
- A merge conflict → stop and ask the agent to explain both sides before choosing.
- You committed something secret → **do not push**; stop and tell the team (`policies/SECURITY.md`).
