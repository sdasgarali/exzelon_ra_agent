# Plan — Dark mode readability fix (2026-10-09)

## Problem
User report: in dark theme some words are not visible (e.g. Add Mailbox wizard, step 3: Role select,
phone placeholder). Root cause: dark mode is Tailwind `darkMode: 'class'`, but ~1,000 className uses in
30 dashboard files carry light-only colors with no `dark:` variant (`bg-white` 136, `text-gray-700` 243,
`text-gray-600` 168, `text-gray-800` 103, `text-gray-900` 98, `bg-gray-50` 97, ...). In dark mode the body
text color becomes light grey (globals.css `.dark { --foreground-rgb }`), and form controls inherit it
(Tailwind preflight `color: inherit`) while staying white -> light text on white = invisible.
Worst files: mailboxes (228), settings (139), warmup (92), leads (90), templates (64), contacts (49).

## Approach — global dark-mode safety net in `frontend/src/app/globals.css`
Per-class remaps that apply ONLY when the element has no explicit dark variant, so pages that are
already dark-aware are untouched:
`.dark .bg-white:not([class*="dark:bg-"]) { background: gray-800 }` (same for text-/border- families).
- Surfaces: bg-white -> gray-800, bg-gray-50 -> gray-900/60, bg-gray-100 -> gray-700/…
- Text: text-gray-900/800/700 -> gray-100/200/300, text-gray-600/500 -> gray-400
- Borders: border-gray-100/200/300, plain `border`, divide-gray-* -> gray-700
- Form controls with no dark classes: dark field bg, light text, readable placeholder, `color-scheme: dark`
  so native dropdown option lists render dark too.
- Tinted light panels/badges (bg-{color}-50/100) -> translucent dark tint; matching text-{color}-700/800/900 -> {color}-300.
- Hover states (hover:bg-gray-50/100) -> dark equivalents.
Why global vs per-file: ~1,000 edits across 30 files is high-risk churn; one CSS layer fixes every page,
including modals, and covers future pages. Marketing pages are light-only and are not under `.dark`
selectors that matter (no theme toggle there) — verify.

## Tasks
- [x] 1. Baseline dark-mode contrast scan of all 30 dashboard pages (local, read-only) — `scratchpad/dark-audit.js`
      (2026-10-09) 298 items < 3:1 on 15/30 pages: settings 217, pipelines 12, clients 11, dashboard 9, leads 9,
      validation 8, contacts/mailboxes/outreach 7, templates 5, icp-wizard 3, warmup 2, deals 1.
      Causes: 229 = light surface (bg-white/gray-50/gray-100, no dark variant) + inherited light text;
      ~40 = text-gray-700/800/900 on dark surface (page titles dark-on-dark); native selects white w/ light text.
      Local DB is near-empty, so prod (more rows/modals) has more instances of the same patterns.
      Prod scan blocked: .env.test SA/ADMIN credentials return 401 on neuraleads.ai.
- [x] 2. Add safety-net layer to globals.css (generator: scratchpad gen-dark-css.js); marketing root marked `.light-only`;
      auth pages (login/signup/forgot/reset/verify) logo `on="light"` -> `on="auto"` (dark wordmark was on the dark .card)
- [x] 3. Re-scan: 298 -> 2 (both = white step numbers on cyan/orange-500 circles in Pipelines; same in light mode,
      not a dark-mode issue). Screenshots OK: settings, mailboxes, Add Mailbox, Manage Roles, login, signup, marketing.
- [x] 4. Light mode: every rule is scoped under `.dark`, so light mode cannot change; mailboxes light screenshot OK
- [x] 5. build OK; jest 82/82 (login test updated: auto logo renders 2 imgs); `next lint` not configured in repo (prompts)
- [ ] 6. Branch `fix/dark-mode-readability`, commit, PR; deploy only on user OK

## Acceptance
- No text/field value below 3:1 contrast in dark mode on any dashboard page.
- Light mode visually unchanged.
- Native select dropdown options readable in dark mode.
