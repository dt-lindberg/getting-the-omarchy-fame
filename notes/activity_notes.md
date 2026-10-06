# Maintainer activity on `origin/quattro`: regime notes

Source: `data/derived/commits.parquet` (6,784 commits, 2025-05-26 to 2026-10-05), `weekly_activity.csv` (ISO weeks, Monday start).
Core = dhh, ryanrhughes, spencerbull, bjarneo, ErikMelton, emirb, birkskyum (bots excluded). Weeks are by `committed_at` (when the work was done); `core_landed_commits` counts by the date the commit reached quattro.

## Caveats that matter for modelling
- quattro history is mostly assembled from long-lived branches (`dev`, `rc`, `omarchy-4`, `omarchy-shell`), merged in batches. A commit's `committed_at` is when work happened; `landed_at` is when it reached quattro. 894 commits landed on 2026-06-08 alone. For "maintainer focus" use `committed_at`; for "what was visible on quattro" use `landed_at`.
- `Merge pull request #N from basecamp/dev|rc` are release merges, not PR merges (`is_integration_merge`); their PR numbers are not attached to the commits they carry.
- Squash/rebase merges of community PRs are authored by the PR author and committed by "GitHub", so who merged them is invisible in git. Use `mergedBy` from the PR data for that.
- "Direct" = core commit with no `(#N)` in its subject and not inside a `Merge pull request` branch (`via_pr_any` false).

## Regimes and breakpoints
1. 2025-05-26 to 2025-06-22: pre-launch, dhh only, 22-76 commits/week, all direct.
2. 2025-06-23 to 2025-09-21 (E1): dhh dominant (80-90% of core commits), 100-230 core commits/week, mostly direct via `dev` merges; PR-merge commits start the week of 2025-06-23. Peak weeks 2025-08-18 and 08-25 (206, 226 core commits; 100 on 2025-08-24).
3. 2025-09-22 to 2025-12-31 (E2 onward): drop to 16-93 core commits/week. dhh share falls (1 commit in week of 2025-09-22, 19 in 10-06, ryanrhughes takes 102 commits in Oct 2025). Quiet: weeks of 2025-12-01 (2 commits) and 12-22 (15); dhh gaps 2025-12-01 to 12-08 and 12-24 to 12-30.
4. 2026-01 to 2026-04: bursty dhh-only work. Bursts: week of 2026-01-05 (100), 2026-02-16 (221, 92 on 2026-02-21, 17 PR merges), quiet 2026-03-16 (8), 2026-04-06 (16). spencerbull's first commit 2026-03-26.
5. 2026-04-27 to 2026-06-07: heaviest period. 144 (04-27), 210 (05-04), 297 (05-11), 301 (05-18), 153 (06-01) core commits/week, almost all direct (omarchy-4 / omarchy-shell development; 113 commits on 2026-06-04). PR merges by core fall to 0-1/week from 2026-05-18 (last PR merge 2026-06-03).
6. 2026-06-08 to 2026-07-12: after the 06-08 merges of `omarchy-4`, `dev`, `omarchy-shell` into quattro, activity is low and direct: 28, 21, 28, 57, 9 commits/week, zero PR merges and almost no community commits (none 06-15 to 07-12). The longest dhh gap is 2026-06-08 to 06-18 (9 days); ryanrhughes goes quiet after 2026-06-21 (6 commits in July). Late June (06-22 to 07-05) is dhh alone.
7. 2026-07-13 to 2026-08-16: restart. PR merging resumes the week of 2026-07-13 (3), peaks the week of 2026-07-20 (226 core commits, 12 PR merges). dhh still ~50-80% direct (week of 2026-08-10: 64 direct of 121).
8. From 2026-08-17 (E3 2026-08-14, E4 2026-08-19): sharp regime change. Core direct commits fall from 64/week (08-10) to 12 (08-17) then 0-3/week; core commits via PR 35-114/week. dhh's PR-routed share of commits: 15% in July, 54% in August, 94% in September. dhh commits drop to 7-48/week (week 08-31: 7) while ErikMelton (from 2026-08-26), spencerbull (67 in Sep) and bjarneo (22 in Sep) join. PR merge commits by core peak at 33 (week 08-24) and 26-32 in weeks 09-07 and 09-21. Maintainer focus is therefore no longer visible as "dhh direct commits"; use PR merge data too.
9. Smaller dips: 2026-09-14 week (38 core commits) and 2026-09-21 to 09-24 dhh gap (4 days) around the 21 Sep mass closure; core activity that week is normal (98).

Largest single days (core commits): 2026-06-04 (113), 2025-08-24 (100), 2026-02-21 (92), 2026-05-14 (89), 2025-08-25 (88).
