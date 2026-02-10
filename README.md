# Recursive Language Models Skill (RLM)

This repo contains a Codex/Claude Code compatible skill that applies the **Recursive Language Model (RLM)** workflow:

- keep huge context *outside* the root prompt (on disk / in the repo),
- map it cheaply with tools (`rg`, `git grep`, etc.),
- delegate chunk/snippet reading to **agent teams / subagents**,
- synthesize with strict evidence (file+line references, quotes).

## Quick Install

This repo's skill lives in `recursive-language-models/`.

Codex:

```bash
cp -R recursive-language-models ~/.codex/skills/recursive-language-models
```

Claude Code:

```bash
cp -R recursive-language-models ~/.claude/skills/recursive-language-models
```

## When To Use This Skill

Use this skill when:

- the relevant context is too large to paste into chat (large repos, long logs, big papers/policies, huge incident reports)
- you must be correct and traceable (every non-trivial claim needs evidence)
- you need coverage across many files/sections and "just looking at the obvious ones" is risky
- you want parallelism (multiple readers in an agent team) without losing rigor

## What Messages Trigger This Skill

These user messages should trigger loading/using this skill (examples):

- "This repo is huge. Add support for X everywhere it matters and don’t miss any call sites."
- "Here’s a 50MB log file. Find the root cause and quote the exact lines."
- "Read this long paper/policy and produce a summary + risk table with section references."
- "I can’t paste everything here, but it’s in the workspace files. Please inspect them with tools."
- "Use agent teams / subagents to read chunks and then synthesize."

In general: if the user says "too large", "can’t paste", "big repo", "long logs", "needs citations/evidence", or asks for parallel readers, this skill applies.

## How To Use (Fast Workflow)

1. **Externalize context**: keep the source in files/repo; do not paste everything into chat.
2. **Map first**: search/index to find the few sections that matter (`rg`, `git grep`, `rg --files`, `find`).
3. **Delegate**: give each subagent exactly one snippet/chunk and a strict JSON+evidence output format.
4. **Aggregate**: merge results into a single evidence ledger; note contradictions/gaps.
5. **Recurse**: only dispatch follow-ups for missing evidence (new excerpt/new chunk).
6. **Finish**: answer with evidence; if code changed, run tests/linters and rerun searches to confirm full coverage.

## Chunking Helper

If a file is too large to excerpt cleanly, chunk it for parallel readers:

```bash
python3 ~/.codex/skills/recursive-language-models/scripts/chunk_text.py path/to/file.txt \
  --out-dir out/chunks --max-chars 15000 --overlap-chars 200
```

For Claude Code, use the equivalent path under `~/.claude/skills/...`.

## Where The Skill Lives

- Skill entrypoint: `recursive-language-models/SKILL.md`
- Helper script: `recursive-language-models/scripts/chunk_text.py`
- Paper notes: `recursive-language-models/references/rlm-paper-summary.md`
