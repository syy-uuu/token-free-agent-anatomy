# Notice

The commits dated 2026-04-23 through 2026-05-08 in this repository's history
modify exercise files (`agents/s02_tool_use.py` through `agents/s06_context_compact.py`,
`skills/agent-builder/`, `skills/mcp-builder/`, `skills/pdf/`) that originate from
[shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code),
a teaching repository for building a coding-agent harness from scratch.

That project is MIT licensed:

```
MIT License

Copyright (c) 2024 shareAI Lab

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Those exercise files were superseded on 2026-05-27 by a from-scratch ReAct rewrite
(see the `init:v1.0 ReAct` commit onward), which is this project's own code and is
what the current `main` branch contains.

## Timeline

- **2026-04-23 – 2026-05-08 — Learning**: worked through the shareAI-lab/learn-claude-code
  curriculum session by session (tool use, todo planning, subagents, skill loading,
  context compaction), modifying the exercise files noted above. In parallel, ran a
  small standalone experiment reproducing just the agent loop
  (`initial commit-set up start`, `original set up`).
- **2026-05-27 — Rewrite**: started this project over from scratch with a ReAct-based
  architecture instead of continuing on the tutorial's scaffolding (`init:v1.0 ReAct`).
- **2026-05-27 – 2026-06-02 — Iteration**: daily build-out of the planner/executor split,
  logging, prompt tuning, and bug fixes (`stage2 start` through `lateest test`).
- **2026-07-17 — Wrap-up**: final pass on `main.py` and the README (`stage2` through the
  last `Update README.md`).
- **2026-08-21 — Housekeeping**: restored this repository's full commit history, which
  had previously been squashed down to 4 commits when it was first published, and added
  this notice.
