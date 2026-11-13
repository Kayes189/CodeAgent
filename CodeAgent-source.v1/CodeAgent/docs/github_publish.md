# GitHub Publication Guide

The repository is prepared GitHub-ready (source, tests, build scripts,
research notes, docs, `.gitignore`, MIT `LICENSE`). **No repository has been
created or pushed by the assistant** — no GitHub credentials were used. Run
the commands below yourself to publish.

## Pre-publish safety check
- [ ] Confirm no API key is present: the key lives only in the DPAPI store
      (`~/.codeagent/apikey.bin`), which is outside the repo and gitignored.
- [ ] `config.json`, `apikey.*`, `.env` are gitignored.
- [ ] `dist/`, `build/`, `*.exe` are gitignored (build artifacts, not source).
- [ ] No personal information in source or docs.

## Option A — GitHub CLI (`gh`)
```powershell
cd "C:\MASTER'S application!\acceptance letters\Task1\CodeAgent"
git init
git add .
git commit -m "CodeAgent: DeepSeek V4-Pro desktop coding agent + Space Fractions game"
gh repo create codeagent --public --source=. --remote=origin --push
```

## Option B — manual remote
```powershell
cd "C:\MASTER'S application!\acceptance letters\Task1\CodeAgent"
git init
git add .
git commit -m "CodeAgent: DeepSeek V4-Pro desktop coding agent"
git branch -M main
git remote add origin https://github.com/<your-username>/codeagent.git
git push -u origin main
```

## Including the game
The game is a sibling folder (`SpaceFractionsGame/`). Either publish it as a
second repository, or copy it under `CodeAgent/generated/SpaceFractionsGame/`
before committing if you want a single monorepo. The CI workflow expects the
sibling layout (`../SpaceFractionsGame`).

> Replace `<your-username>` and the repo name with your own. Do not reuse any
> URL until the repository actually exists.
