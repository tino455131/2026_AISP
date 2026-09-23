# 2026_AISP

### What AI tools we plan to use, and what we will use each for
- We will use codebase-memory-mcp to index our codebase.
- We will use Codex/Claude to generate an initial test skeleton for a new module and the Codex will test it first — a human always reviews the testing report to make sure it cover the edge cases before push the code.
- We will use Codex/Claude to draft the first pass of docstrings and API documentation — a human always reviews and edits before it's merged.

### How we will document AI interactions
- Every prompt used to generate code that ends up in the repo goes in the prompt log: the prompt text, the model used, what it produced, what you changed and why.
- The PR description's 'what this PR does' field always names whether AI was involved, even in one sentence — it's not a copy of the full log entry, just a pointer to it.
- If AI adds a new module, function or changing the code skeleton, they should be written in DECISIONS.md

### How we will handle disagreements about AI output quality
- Every PR should be reviewed by at least one of other teammates, but if the PR change the DECISIONS.md, it should be reviewed by at least two of other teammates.

## Problem Grounding
- Who specifically has the collaboration problem you are addressing?:
  -   Project leaders and the members they coordinate in hierarchical project teams.
- What do they currently do instead of your tool?
  -   Leaders manually monitor progress, coordinate tasks through meetings or messaging tools, and often handle overlooked tasks reactively, use project manager app (e.g. Notion) and update the content manually.
- What would be observably different about their collaboration if your tool worked?
  -   Teams identify required tasks earlier, spend less time coordinating next steps, have clearer task ownership, miss fewer tasks, and experience lower coordination-related cognitive load.

## Evaluation Plan
- Project: Team Leader AI Assistant
- Workflow: The AI Assistant first interprets the team's current progress and generates potential action items. After the team leader reviews and confirms these suggestions, the AI Assistant delegates the approved tasks to the AI agents of the respective team members. Each member's AI agent then communicates the assigned task to the corresponding team member and supports its execution.
- Success Definition: We will consider the system effective if its suggestions are sufficiently useful to improve collaborative outcomes (e.g., problem identification, discussion efficiency, output quality, and willingness to communicate) while reducing the cognitive load of both team leaders and team members.
- Target Users: Teams with a hierarchical organizational structure.
- Method: task performance, pre- and post-study surveys, brief interviews, and analysis of AI-agent chat histories.
- Minimum evidence threshold: 2 team with the same teamleader and member.
