# Collaboration Coordination

Source of truth for who is working on what in this repo across Claude sessions
and machines. Update your row before starting a branch and when you close it.

## Rules

- **Branch per task.** Never code directly on the default branch (`main` or `master`).
- **One owner per branch.** Handoffs must be agreed in the row's Notes column.
- **PR-only merges.** Direct pushes to the default branch are blocked by the
  global pre-push hook.
- **Leader-only writes.** On any machine, only the first Claude session on
  that machine can push/merge/deploy (enforced by the global hook + the
  `claude-allow-write` deploy guard).
- **Allowed git identities.** Pushes require `user.email` to match the allowed
  contributors list. Configure on each contributor's machine via shell profile:
  ```
  export CLAUDE_COLLAB_ALLOWED_EMAILS="alice@team.com,bob@team.com"
  ```
  `user.name` can be any display label.

## Active branches

| Branch | Machine | Owner | Started (UTC) | Status | Worktree path |
|--------|---------|-------|---------------|--------|---------------|

## Recently closed (last 30 days)

| Branch | Owner | Merged at | PR |
|--------|-------|-----------|----|

## Module ownership (to avoid simultaneous edits)

Carve up the repo by area. Two sessions should not be editing the same area
simultaneously — they will merge-conflict.

| Area | Owner / branch |
|------|----------------|
| `app/admin/*` | _unassigned_ |
| `app/api/*` | _unassigned_ |
| `app/(storefront)/*` | _unassigned_ |
| `lib/*` | _unassigned_ |
| `scripts/*` | _unassigned_ |
| migrations / db schema | _unassigned_ |

## Conventions

- Branch names: `feature/<scope>`, `bugfix/<scope>`, `hotfix/<scope>`, `chore/<scope>`
- Worktree path: `../<repo>__<branch_slug>` (created by `claude-worktree`)
- One PR per branch; rebase on the default branch before requesting merge.
- After merge: `git worktree remove <path>` and move the row to "Recently closed".
