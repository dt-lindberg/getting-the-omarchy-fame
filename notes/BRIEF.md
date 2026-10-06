# Omarchy triage study: shared brief

Every agent working in this project reads this first.

## Goal
Reverse-engineer how community pull requests to Omarchy (GitHub `omacom/omarchy`, formerly `basecamp/omarchy`, default branch `quattro`) get triaged, so contributors can decide what to submit, how to present it, when to submit it, and how to respond once maintainers engage.

This is **not** a model of PR quality. It models triage under limited maintainer attention: a PR must first be noticed, then chosen.

Funnel:
submitted / edited → attention → maintainer engagement → author response / revision → merged, absorbed, rejected, superseded, self-closed, mass-closed, or still open.

## Ground rules
- Strictly read-only on GitHub. Never comment, react, label, edit, close or open anything.
- Do not run the Omarchy repo's tests.
- Do not modify anything in `/home/dt-lindberg/Projects/omarchy-pr-stats/` (earlier work) or `/home/dt-lindberg/Projects/omarchy/` (the user's clone; `git log` / `git show` reads are fine, no checkouts, no fetch-with-prune, no branch changes).
- Python via `uv run` in `/home/dt-lindberg/Projects/omarchy-triage` (pandas, numpy, statsmodels, lifelines, scikit-learn, matplotlib, pyarrow installed). Prefer parquet for large derived tables.
- Brief full-line comments only for non-trivial code. Files under ~250 lines; split into a package when larger. British English in prose.
- No look-ahead: any feature used at a decision point uses only information available at that moment.

## Populations and definitions
- Core/maintainers: dhh, ryanrhughes, spencerbull, bjarneo, ErikMelton, birkskyum, emirb (anyone who merged someone else's PR; re-check). Bots: omarchybot, copilot*, dependabot, github-actions, greptile-apps, *[bot]. Everyone else is community.
- Success = direct merge OR absorbed (folded into another PR with the original author credited). Keep the two distinguishable.
- Closure dispositions: maintainer rejection; duplicate / superseded / fixed elsewhere; self-close (closed by the PR author); bot/admin close; mass closure; still open (= undecided, never a failure).
- Mass closure: 21 Sep 2026 is a special event (hundreds of PRs). Other days with ≥50 closures are also flagged. Treat these as events, not independent rejections.

## Epochs (all history analysed; never assume one stable regime)
- E1: 2025-06-26 public launch / Omarchy 1.x
- E2: 2025-09-17 Omarchy 3.0
- E3: 2026-08-14 Omarchy 4 / Quattro
- E4: 2026-08-19 Omarchy becomes an institution (core-team governance, funding, foundation-style stewardship)
Special operational events (e.g. 21 Sep 2026 mass closure) are flags, not epochs. Surface other strong behavioural breakpoints if the data shows them.

## Analyses
1. Getting noticed: among PRs not yet attended by a maintainer, what is associated with getting maintainer attention (time-to-first-maintainer-interaction, survival style)?
2. Converting attention: once a maintainer engages, what is associated with merge/absorption?
3. Responding to feedback: after a maintainer comment/review/changes-requested, which author actions are associated with eventual acceptance?
4. Timing and context: competing PRs, backlog, maintainer focus (dhh activity in the same code area), recent maintainer activity, arrival rate, epoch.
5. Disposition: what distinguishes acceptance from rejection, duplicate/superseded, self-close, mass-close, unresolved (competing-risks cumulative incidence).

Report interpretable effect sizes (percentage points, rate ratios), not p-values. The data is the full population, so uncertainty is about generalising to future PRs. Robustness: within-author comparisons, epoch-by-epoch estimates, time-based holdout, competition clusters, with/without mass closures, author-clustered uncertainty.

For each important finding record: size, funnel stage, stability across authors/epochs, whether it is under the contributor's control, and leakage/reverse-causality risk.

## Data already available (read-only)
- `data/snapshot/prs_{open,merged,closed}.jsonl.gz`: all 6,962 PRs as of 2026-10-06 09:17 UTC with title, body (current), author, dates, size, labels, files(first 100), reviews(first 30, no timestamps), comments(first 50 with createdAt).
- `data/snapshot/prs_v1_features.csv.gz`: earlier feature table (absorbed detection lives here: columns outcome, absorbed_by, absorbed_via, absorbed_loose). Reuse ideas, not blindly.
- `data/snapshot/community_for_topics.jsonl.gz`: community PRs with title + first 600 body chars.
- Local git clone with full history: `$OMARCHY_REPO`, default `../omarchy` (`origin/quattro`).

## Layout of this project
- `data/raw/`: new API pulls (timeline events, edit histories). Git-ignored.
- `data/derived/`: tables built by scripts (parquet/CSV).
- `data/labels/`: LLM-assigned labels (topics, closure reasons), one file per batch plus a merged file.
- `notes/`: this brief, taxonomy, findings, playbook.
