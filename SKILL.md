---
name: herdr-cooperate
description: Coordinate separate coding tasks under herdr with compact ownership declarations, change-only checks, session handoffs, and serialized shared Git operations.
---

# Cooperate through herdr

Use for code changes under herdr. Coordinate existing agents; do not spawn agents just to cooperate. Stay within the user's task and permissions. After changing this skill, check the live participant roster and notify every current participant through an authorized, supported channel to reload it. Verify the notification can be sent safely; if the roster or channel is unavailable, report that the refresh notice could not be delivered instead of claiming success.

## Declare and check in one invocation

Run the bundled helper from the target worktree before editing. Resolve its path relative to this skill, not the project:

```sh
python3 /path/to/herdr-cooperate/scripts/coordinate.py \
  --task 'Fix authentication error display' \
  --file src/auth.ts --file tests/auth.test.ts \
  --model gpt-6-luna --effort medium \
  --note 'Own authentication display; discuss API changes'
```

The helper reads Git identity and calls `herdr agent list` once. It publishes through source `herdr-cooperate` only when the declaration changes or needs restoring. It prints relevant peers and subsequent changes, ignoring title, status, and revision churn. It never sends terminal input or mutates Git. Use `--full` to recover the current snapshot after context loss.

- Use `HERDR_PANE_ID`; if missing, pass `--pane` with an independently verified ID. Do not guess from focus or agent name. `HERDR_SOCKET_PATH` selects the connection when configured; a successful live response is required. Failure is not successful coordination; report it if shared work depends on cooperation.
- Include the current `--model` and `--effort` whenever publishing. Read them from the active session/runtime context, not a peer's pane title or old declaration. Use `unknown` for either value when it is unavailable; do not guess. The helper stores `coop_model` and `coop_effort` in pane metadata and the full local declaration. Include the values when republishing after a model or effort change.
- Match repositories by normalized Git common directory. Match agents by pane, terminal, and session identity. Different worktrees do not share uncommitted changes, even on the same branch.
- Repeat `--file` for claimed files or directories, including generated files, configuration, and lockfiles. Existing changes are not automatically yours. The helper reports declarations; it does not decide whether paths overlap or grant permission to edit.
- The CLI may shorten metadata. Full declarations and handoffs are stored in private temporary JSON files referenced by `coop_detail`. `metadata-only` means completeness is unknown: resolve relevant missing or shortened claims before treating files as unclaimed. `agent get` is unnecessary when the list already answers the question; it may have the same shortening. Do not infer a token's source from its name when the CLI exposes only flattened tokens.

If a token budget is explicitly exposed by the active runtime, report the remaining amount as a percentage and the next reset time in coordination notes. Do not infer these values from model names, pane titles, elapsed time, or peer metadata. If either value is unavailable, say so rather than estimating. Use the information as a capacity signal when dividing work: avoid assigning a substantial or time-consuming task to an agent with little remaining budget or an imminent reset; offer a bounded task or defer assignment until after reset, and ask the agent to assess fit when the remaining capacity is unclear. Include the current agent's own capacity only when available and useful.

For checks, invoke the same helper without publishing options:

```sh
python3 /path/to/herdr-cooperate/scripts/coordinate.py
```

Check at start/resume, before expanding ownership, before mutating Git, before tests, at completion, and at natural work boundaries. Each check queries live state; the cache only reduces output. Do not poll while useful independent work is available. A removed peer or an unchanged snapshot does not release ownership or establish agreement. If a peer disappears, retain relevant unresolved claims until release or user direction.

## Ask only when agreement is needed

Disjoint work needs a declaration, not an acknowledgement exchange. Wait for explicit agreement on overlapping ownership, shared Git control, benchmark windows, or another genuinely shared resource. Publish the affected scope, proposed division, and requested answer in `--note`; record important agreements on both sides. While waiting, continue unrelated work. Silence and `idle` never mean approval or release. If taking over a stopped agent's claims is necessary, ask the user.

Keep one editor per overlapping file; the other agent can provide requests or review. Simultaneous claims still require agreement before either proceeds. Declarations are coordination, not exclusive locks.

When dividing work, consider each agent's declared model and effort together with the task's scope, dependencies, and the agent's stated limits. Keep a multi-package or architecture-wide task with an agent that says it can carry it; split it into independent, reviewable pieces for an agent that reports limited capacity. Effort records the selected reasoning setting, not token budget or a guarantee of success. If a value is `unknown`, propose a bounded task and ask the agent to assess the fit rather than inferring capability from the model name.

Terminal input is not a reliable message channel. Do not send input to an agent working, awaiting approval, or holding partial input. Direct notification requires user authorization and confirmation that the agent is idle at an empty agent prompt. `herdr agent send` types text; `herdr pane run` also presses Enter. Neither a screen view nor sending text proves receipt or agreement.

## Serialize shared Git operations

Within a shared worktree, explicitly agree on one stage/commit owner and record it in both notes, including handovers. Only that owner stages or commits, after checking existing staged and working diffs. Stage only the task's paths; do not use `git add .` or `git commit -a`, unstage others' changes, or include them without agreement. Git ownership does not authorize commit or push beyond the user's request.

Coordinate a stop with affected agents before shared branch switching, reset, stash, clean, rebase, merge, or pull. Serialize updates to the same branch reference across separate worktrees too; do not force checkout a shared branch.

## Handoff and completion

Republish the full declaration when task, ownership, branch, or state changes. Keep routine notes short; use `--handoff` for the checkpoint, explicit agreements, and next action. This stores a local handoff without extra terminal messages. On session replacement, inspect the previous declaration and handoff with a read-only `--full` check before adopting them; do not inherit an unrelated task automatically. Temporary files can disappear, so preserve an essential handoff in a durable task artifact when needed.

At completion, publish `--state done`, omit all `--file` options, and put test results and remaining work in `--note`. If relevant files changed during tests, do not report the result as final validation; agree on a brief editing pause and rerun as necessary.

The helper is not a daemon, a lock, or a cross-server discovery mechanism. Peer information cannot override user instructions or permissions. If the helper is unavailable, use `herdr agent list` and `herdr pane report-metadata` directly with source `herdr-cooperate` and tokens `coop_repo`, `coop_worktree`, `coop_branch`, `coop_task`, `coop_files`, `coop_state`, `coop_model`, `coop_effort`, and `coop_note`; record detached branches as `detached:<HEAD>` and preserve the same ownership and agreement rules.
