# rlm-skill

Codex/Claude-Code compatible skill implementing the "Recursive Language Models" workflow: keep huge context on disk, map with tools, delegate chunk reading to agent teams/subagents, synthesize with evidence.

## Contents

- `recursive-language-models/` - the skill folder

## Install

Codex:

```bash
cp -R recursive-language-models ~/.codex/skills/recursive-language-models
```

Claude Code:

```bash
cp -R recursive-language-models ~/.claude/skills/recursive-language-models
```
