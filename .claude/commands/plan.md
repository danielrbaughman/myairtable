# Ultra-Plan

Ultrathink.

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

1. Create a plan to implement the feature described below. Use the `project-implementation-planner` agent for this task. If that's not available, use the `implementation-planner` agent instead.
2. The implementation should use Test-Driven-Design. DO NOT write code until there are tests to run against it. Follow the specific 4-layer naming convention documented in `tests/CLAUDE.md`:
3. After creating the first draft (v1), critique the plan and generate v2 of the plan. Use the `plan-critic` agent for this task.
4. Then present v2 of the plan to me for my review.
5. After I've consented to the final plan, save it to a local markdown file to maintain the plan between sessions. Do this before starting the implementation itself.

Use the following MCP tools to help you, both for planning and implementing the plan.
- Context7
- Sequential Thinking
- GitHub

Notes:
- Use the `web-researcher` agent to do any web lookups
- If the resulting plan is complex, break it down into tasks and use beads to handle those tasks.

$ARGUMENTS