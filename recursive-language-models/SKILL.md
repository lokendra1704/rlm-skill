---
name: recursive-language-models
description: Use when the relevant context is too large to fit in a single model context window (large repos, long logs, big papers/policies), when exact grep is insufficient and semantic retrieval (vector embeddings) is needed to find relevant snippets, or when code must be split by syntax (tree-sitter) for reliable chunk reading.
---

# Recursive Language Models

## Overview

Apply the Recursive Language Model (RLM) pattern from the MIT paper: keep the full context outside the root prompt, inspect it with tools, and recursively delegate chunk reading to subagents/agent teams, then synthesize with evidence.

## Workflow (RLM In A Coding Agent)

### 0) Set ground rules (before reading anything)

- Write the questions / acceptance criteria as a checklist.
- Decide an evidence format:
  - Code/docs: file path + line ranges.
  - Web: URL + section heading.
- Set budgets up front:
  - Max subagent calls.
  - Target chunk size for snippets (see "Chunking Guidance").

### 1) Externalize the context (do not paste it into chat)

- Put large inputs into files in the workspace (or point at existing repo files).
- Prefer plaintext forms you can grep:
  - Logs: `.txt`, `.log`
  - Docs: `.md`, `.txt` (convert PDFs if needed)
  - Codebase: the repo itself + `git` + search tools

### 2) Build a cheap "map" before deep reading

- Use fast tooling to locate candidate regions:
  - `rg -n "pattern1|pattern2" path/to/file`
  - `git grep -n "symbolName|flagName"`
  - `ls`, `find`, `rg --files` to understand scope
- If lexical search is insufficient (synonyms, domain terms, vague questions), use semantic retrieval (vector embeddings) to produce candidate files/chunks, then verify by opening the actual source and quoting evidence.
- Produce a short map you can act on:
  - list of files/sections to read next
  - a shortlist of line ranges
  - a set of chunk IDs (if chunking)

### 3) Recursively delegate chunk reading (agent teams / subagents)

Treat each subagent call as the paper's `llm_query(snippet, question_set)` primitive.

- Create N readers and assign each one:
  - exactly one snippet (a chunk or a tight excerpt)
  - the specific questions it must answer
  - a strict output schema with evidence (see template below)
- Prefer fewer, larger subagent calls (each answers multiple questions for a chunk) over many tiny calls.
- Cache results: do not ask two readers to analyze the same snippet unless you are verifying a disagreement.

### 4) Aggregate, verify, recurse

- Merge reader outputs into an evidence ledger.
- Identify gaps/contradictions.
- Recurse: dispatch follow-up readers only for missing pieces (new excerpts/new chunks), not the whole document again.

### 5) Produce the final output

- Answer in the requested format.
- Attach evidence to every non-trivial claim.
- Call out uncertainty explicitly; list what would resolve it (what to search, what to open, what to run).
- If this is a code change: run tests/linters and re-run your search to confirm you updated all call sites.

## Mapping The Paper To Real Tools

The MIT RLM paper describes a REPL environment with:
- `context`: the full data (too large to fit in the prompt)
- `llm_query(...)`: a function that calls another LLM on a subset of the data

In coding agents, map those primitives to:
- `context` -> files on disk (or a repo) + tool access (`rg`, `sed`, `python`, `git`, etc.)
- `llm_query` -> an agent team / subagent run on a snippet (or a separate model call)
- REPL -> your shell + a scripting language (usually Python)

## Agent Team Template (Recommended)

Use these roles (names optional):
- Coordinator (root): owns checklist/budgets; decides what to read next; synthesizes the final answer.
- Indexer: builds the initial map (grep results, TOC, chunk list, candidate line ranges).
- Readers (2-6): each reads assigned snippets/chunks and answers questions with evidence.
- Verifier (optional): cross-checks claims vs evidence; looks for contradictions and missing coverage.

If your environment does not support true subagents:
- Simulate `llm_query` by running the same prompt sequentially, but enforce strict snippet boundaries and return JSON "as if" it came from a separate agent.

## Subagent Prompt Template (Use As `llm_query`)

Provide:
- `CHUNK_ID`: stable identifier
- `SNIPPET`: the only text the reader may use
- `QUESTIONS`: the questions to answer

Constraints for the reader:
- Only use the provided snippet.
- If the snippet does not contain an answer, say so and propose a follow-up search pattern.
- Prefer quoting short, relevant substrings for evidence (not long dumps).

Return JSON:

```json
{
  "chunk_id": "chunk_0007",
  "answers": [
    {
      "question": "What caused the failure?",
      "answer": "…",
      "evidence": [
        { "source": "context/incident.txt", "lines": "120-148", "quote": "…" }
      ]
    }
  ],
  "contradictions": [
    { "claim_a": "…", "claim_b": "…", "evidence": [{ "source": "…", "lines": "…", "quote": "…" }] }
  ],
  "missing": [
    { "question": "…", "why_missing": "Not present in snippet", "follow_up_rg": "pattern to search" }
  ]
}
```

## Evidence Ledger Template

Maintain a single place where the Coordinator aggregates outputs:

| Claim | Evidence | Confidence | Notes |
| --- | --- | --- | --- |
| … | `path/to/file:120-148` | high/med/low | … |

## Chunking Guidance

- Start small. Increase chunk size only if readers remain reliable.
- Reasonable starting points (character counts, not tokens):
  - ~32k token models: 10k-20k chars per chunk
  - larger-context models: increase gradually (ensure the snippet + instructions fit)
- Add overlap (100-300 chars) to reduce boundary losses.
- Keep chunk IDs stable so you can cache and cross-reference.

Use the helper script to split a text file into chunks + an index:
- Common install locations:
  - Codex: `~/.codex/skills/recursive-language-models/scripts/chunk_text.py`
  - Claude Code: `~/.claude/skills/recursive-language-models/scripts/chunk_text.py`
- Run:
  - `python3 /path/to/chunk_text.py --help`

## Quick Reference

- Map first:
  - `rg -n "pattern1|pattern2" path/to/file`
  - `git grep -n "symbolName|flagName"`
- Semantic map (optional):
  - build/query a vector index over chunk texts to get candidate chunk IDs
- Extract tight evidence:
  - `nl -ba path/to/file | sed -n 'START,ENDp'`
- Chunk for parallel readers:
  - `python3 /path/to/chunk_text.py path/to/file --out-dir out/chunks --max-chars 15000 --overlap-chars 200`
- For code: prefer syntax-aware splitting (tree-sitter) so chunks do not cut mid-function/class (see "Code Splitting With Tree-sitter").
  - `python3 /path/to/split_code_treesitter.py path/to/repo --out-dir out/code-chunks --force`
- Delegate:
  - one snippet per reader
  - require JSON output with evidence
- Aggregate:
  - update one evidence ledger
  - recurse only on gaps

## Semantic Retrieval (Vector Embeddings) (Optional)

Use semantic retrieval when the query is concept-level and **terminology differs** across the codebase/docs (e.g., "rate limiting" implemented as "throttle/quota/burst"). Treat semantic results as *candidates*, not evidence.

Workflow:

1. Produce chunks:
   - Docs/logs: use `chunk_text.py`.
   - Code: use tree-sitter splitting (see below).
2. Build a vector index over chunk texts (any provider: local or hosted; any store: FAISS/Chroma/pgvector/etc.).
3. Query the index with the user's question. Retrieve top-k chunk IDs with scores.
4. Verify each candidate:
   - open the original file lines and extract quotes,
   - reject false positives,
   - recurse only on gaps.

Minimal output schema to request from your "Indexer" role:

```json
{
  "query": "natural language question",
  "top_k": [
    { "chunk_id": "…", "source": "path/to/file", "lines": "Lx-Ly", "score": 0.73 }
  ],
  "notes": "treat as candidates; verify with evidence"
}
```

## Code Splitting With Tree-sitter (Optional)

Use tree-sitter splitting when chunking code for subagent readers or semantic indexing. The goal is to split on **syntax boundaries** (functions/classes/modules) so each reader sees a coherent unit.

Helper script:
- Codex: `~/.codex/skills/recursive-language-models/scripts/split_code_treesitter.py`
- Claude Code: `~/.claude/skills/recursive-language-models/scripts/split_code_treesitter.py`

Dependencies (optional):
- `python3 -m pip install tree_sitter tree_sitter_languages`

Example:

```bash
python3 /path/to/split_code_treesitter.py path/to/repo --out-dir out/code-chunks --force
```

If tree-sitter is unavailable, fall back to `chunk_text.py` and keep chunks small; expect lower reader accuracy on code.

## Example: Long Incident Report Q&A (Map -> Delegate -> Aggregate)

Goal: answer multiple questions about `context/incident.txt` without loading the whole file into the root prompt.

1. Map quickly:

```bash
rg -n "error|timeout|exception|root cause|mitigation" context/incident.txt
```

2. Extract tight excerpts for readers (use line numbers):

```bash
nl -ba context/incident.txt | sed -n '120,220p'
```

3. Chunk if needed (for parallel readers):

```bash
python3 /path/to/chunk_text.py context/incident.txt --out-dir context/chunks --max-chars 15000 --overlap-chars 200
```

4. Dispatch readers (agent team members) with:
- `SNIPPET`: one excerpt or one chunk file
- `QUESTIONS`: 3-8 questions per reader
- required JSON schema (above)

5. Aggregate into the evidence ledger; recurse only on gaps.

## Rationalizations To Block (And What To Do Instead)

| Excuse | Reality | Do This Instead |
| --- | --- | --- |
| "Paste the full doc here" | Root context is the bottleneck | Keep it on disk; extract snippets with tools |
| "I'll give a high-level summary" | Summaries without evidence fail accuracy requirements | Map first, then answer with quoted evidence |
| "I can't provide line numbers" | Tools can produce line-numbered excerpts | Use `nl -ba` + `sed -n` (or equivalent) |
| "Subagents are overkill" | Parallel chunk reading is the point of RLM | Use an agent team for readers + verifier |
| "I'll have one reader scan the whole thing" | Single-pass reading is fragile and often exceeds budgets | Map first, then split into focused excerpts/chunks |
| "I'll trust the reader summary" | Summaries can drop critical details | Require evidence quotes + verify key claims |
| "Grep didn't find it, so it doesn't exist" | False negatives happen (synonyms, domain naming) | Use semantic retrieval or broaden search patterns, then verify |
| "Vector search results are proof" | Embeddings retrieve similar text, not ground truth | Open the cited lines and quote evidence from the real source |
| "Char chunking is fine for code" | Chunks can cut mid-function/class and confuse readers | Use tree-sitter splitting for code chunks |

## Common Mistakes

- Reading everything sequentially before doing any mapping.
- Treating semantic retrieval results as evidence without verification.
- Building a vector index once and forgetting it is stale after code changes.
- Delegating without a strict schema (results become hard to aggregate).
- Running too many subagent calls (cost/time blowups). Batch questions per chunk.
- Answering with weak traceability (no file+line evidence).
- Re-reading the same snippet repeatedly instead of caching.

## Red Flags (Stop And Re-Plan)

- "I'll just answer from memory." (You have not inspected the source.)
- "It is probably in the obvious file." (You have not searched.)
- "Grep didn't find it, so it doesn't exist." (Widen search; use semantic retrieval; verify.)
- "No time for evidence." (Then the answer is not reliable.)
- "Let me paste the whole thing." (Externalize context; use snippets.)
