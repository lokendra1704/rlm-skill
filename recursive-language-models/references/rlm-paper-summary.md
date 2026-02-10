# Recursive Language Models (MIT) - Paper Notes

Paper: "Recursive Language Models" (Alex L. Zhang, Tim Kraska, Omar Khattab), arXiv:2512.24601 (latest revision v2: 2026-01-28).

These notes are a paraphrased, implementation-oriented summary to support the `recursive-language-models` skill.

## The Core Idea

An RLM reframes an LLM from a single "answer the question given the whole prompt" function into a program that:
- keeps the full context *outside* the root prompt (in an external environment),
- uses a REPL/tooling loop to inspect the context on demand,
- recursively calls LLMs on *small* relevant slices (subcalls),
- aggregates subcall outputs into the final answer.

The point is to expand the *effective* context window without forcing the root model to ingest all tokens at once.

## The Two Primitives

The paper centers on two primitives (names vary by implementation):
- **`context`**: the full data (often too large to paste into a prompt).
- **`llm_query(snippet, ...)`**: a function to run a separate LLM call on a snippet of the context (or, in agent tooling, dispatch a subagent/team member).

Together with a REPL, this enables "inspect -> delegate -> aggregate -> recurse".

## Practical Design Choices

- **Map before you read**: do a cheap scan (search/TOC/index) to find candidate regions before detailed analysis.
- **Chunking**: split large context into manageable chunks; optionally add overlap to reduce boundary issues.
- **Batch questions per chunk**: to reduce call overhead, ask each subcall to answer multiple questions for the same snippet.
- **Budgeting**: set a cap on number of subcalls and chunk size; favor fewer calls when possible.
- **Evidence discipline**: subcalls should return exact evidence from their snippet; the root should not invent content outside inspected text.

## Mapping To Coding Agents (Codex / Claude Code)

If you are using a coding agent with tool access, the mapping is straightforward:
- `context` -> files on disk, code repositories, logs in the workspace
- REPL -> shell commands and small scripts (`rg`, `git grep`, `python3 -c ...`, etc.)
- `llm_query` -> agent team members/subagents (preferred) or separate model calls

The root agent should stay "thin": it owns planning/synthesis/verification and only loads small excerpts into its own context.

