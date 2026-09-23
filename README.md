# 2026_AISP

### What AI tools we plan to use, and what we will use each for
- We will use codebase-memory-mcp to index our codebase.
- We will use Codex/Claude to generate an initial test skeleton for a new module and the Codex will test it first — a human always reviews the testing report to make sure it cover the edge cases before push the code.
- We will use Codex/Claude to draft the first pass of docstrings and API documentation — a human always reviews and edits before it's merged.

### How we will document AI interactions
- (Optional) Every prompt used to generate code that ends up in the repo goes in the prompt log: the prompt text, the model used.
- The PR description's 'what this PR does' field always names whether AI was involved, even in one sentence — it's not a copy of the full log entry, just a pointer to it.
- If AI adds a new module, function or changing the code skeleton, they should be written in DECISIONS.md

### How we will handle disagreements about AI output quality
- Every PR should be reviewed by at least one of other teammates, but if the PR change the DECISIONS.md, it should be reviewed by at least two of other teammates.
