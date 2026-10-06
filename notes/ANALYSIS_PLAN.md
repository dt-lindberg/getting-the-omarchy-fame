# Analysis plan

Read `notes/BRIEF.md` first. Inputs are the tables in `data/derived/` built by `build_funnel.py` (`prs.parquet`, `events.parquet`, `snapshots.parquet`, `commits.parquet`, `area_activity_daily.parquet`) and the notes in `data/derived/funnel_summary.md`. Do not rebuild or modify those tables; if something is missing, derive it inside your own module and say so in your report.

## Shared conventions
- Population: community PRs created on or after 2025-06-26, unless stated. Keep the user's own PRs (`is_user_pr`) in the data but never let them drive a finding.
- Success = merged or absorbed. Open PRs are undecided: use survival / competing-risk methods or restrict to PRs with enough follow-up, never count them as failures.
- No look-ahead: use features as they stood at the decision point (open snapshot for stage 1, pre-attention snapshot where stated, state at engagement for stage 2).
- Effect sizes: average marginal effects in percentage points (pp) and rate ratios. Report 95% intervals from author-clustered standard errors (or an author-block bootstrap). No p-value tables.
- Stability: for every key finding, estimate it overall and per epoch (E1 2025-06-26, E2 2025-09-17, E3 2026-08-14, E4 2026-08-19; E3 is only five days long, so pool E3+E4 as "Quattro" where E3 alone is too small and say so), and within-author where possible (author fixed effects on authors with mixed outcomes, or a conditional logit).
- Mass closures: run key models with and without mass-closed PRs (and with the 2026-09-21 event alone excluded).
- Code: a package under `analysis/<name>/` plus a CLI `run_<name>.py`, files under ~250 lines, brief full-line comments only where non-trivial. Load the `python-coding-standards` skill first.

## Output contract (every analysis)
1. `data/results/<name>.json`: chart-ready data for the web page. Keep it small (aggregates, curves sampled at sensible points, rounded to 3 significant figures). Document its schema at the top of the findings file.
2. `notes/findings_<name>.md`: a findings table with, for each finding: id, one-sentence plain-English statement with the number, effect size + interval, funnel stage, stability (authors / epochs), under contributor's control (yes / partly / no), leakage or reverse-causality risk, and n. Then a short "what surprised me" section and a "caveats" section.
3. A report back of at most ~500 words with the 6–10 most important findings and anything that looks wrong in the data.

Write prose in British English, plainly, without jargon where a plain word works.

## A. Getting noticed and converting attention (`attention`)
1. Stage 1, attention. Event: first maintainer engagement (`first_maintainer_engagement`, excluding the terminal close/merge). Competing event: decision without prior engagement (silent close or silent merge). Censoring: still open at fetch time.
   - Cumulative incidence of engagement by day 1, 3, 7, 14, 30, 90, overall and per epoch (Aalen–Johansen; `lifelines` has `AalenJohansenFitter`).
   - Model: discrete-time model of P(engaged within 14 days) among PRs with ≥ 14 days of follow-up or a decision, on open-snapshot presentation features, size and areas, topic/kind, author history (shrunk rate, prior PRs, first PR), context (backlog, arrivals, maintainer activity, dhh/core focus on the PR's areas, competition), epoch. Report AMEs in pp.
   - Author edits before attention: does editing the title or body after opening (before any maintainer engagement) go with faster engagement? Use a daily person-period (discrete-time hazard) with a time-varying "edited since open" flag, so that edits are only credited for the days after they happen.
   - Community and bot attention first: does a community comment, reaction or omarchybot review before maintainer engagement go with faster maintainer engagement? (time-varying, same approach)
2. Stage 2, conversion. Among PRs with maintainer engagement, P(success), using features at the moment of engagement (pre-attention snapshot, context at that time) plus how the engagement looked (who engaged, substantive vs lightweight, changes requested). AMEs in pp.
3. Decomposition: P(success) = P(engaged) × P(success | engaged) + P(silent merge). For each key feature, show which stage it acts in (a two-bar "attention vs conversion" effect chart). Per epoch.
4. Score the user's three PRs (#12814, #14148, #14220): their predicted P(engaged within 14 days) and P(success | engaged), and where they are now in the funnel. Store under `user_prs` in the JSON.

## B. Responding to feedback, rewrites and triage artefacts (`feedback`)
1. Among PRs with substantive maintainer feedback before resolution: which author responses go with success? Responded at all; response latency buckets (< 6 h, 6–24 h, 1–3 days, 3–7 days, > 7 days, never); response kinds (pushed commits, replied, force-pushed, edited body or title); how many rounds. Use AMEs, and a within-author comparison (author fixed effects among authors with ≥ 2 feedback episodes and mixed outcomes). Condition on feedback type (changes requested vs comment vs approval-style).
2. Reverse causality check: a maintainer who has already decided to merge may ask for small changes; separate "requested changes" from "approved with comments" and look at the time from the last author response to the decision.
3. Maintainer rewrites: share of accepted community PRs whose title (and body) a maintainer changed, by epoch and by maintainer. Characterise rewrites: length change, removal of prefixes like `fix:` or `[x]`, change to the imperative mood, wording that describes user-visible outcome. Curate 20 striking before → after title pairs (diverse, real, with PR numbers) for the page.
4. Triage artefacts: for labels (verified, ready, bug, enhancement, duplicate), omarchybot reviews, maintainer reactions, review requests, assignments: rate of success with and without, AND the median timing of the artefact relative to the decision (hours before decision). The point is to show these appear late and are consequences of triage. Chart-ready: per artefact, success rate with/without and the timing distribution.

## C. Timing, context, dispositions and epochs (`context`)
1. Competition: in competition clusters, success rate for the first PR vs later PRs; effect of `competing_open_at_creation`; how often a cluster ends in a success at all; median time gap between competing PRs.
2. Context effects at creation: backlog size, arrivals in the previous 7 days, maintainer activity in the previous 7 days, dhh/core focus on the same areas in the previous 14 days (commits + merged core PRs), weekday and hour (UTC). AMEs in pp, per epoch.
3. Dispositions: cumulative incidence curves for each disposition (merged, absorbed, superseded or duplicate, self-closed, maintainer-rejected, bot/admin, mass-closed) over days since opening, per epoch. Composition of the 2026-09-21 mass closure: PR age, whether they ever had maintainer attention, topic, author history; compare with PRs left open that day.
4. Breakpoints: weekly series from 2025-06 to 2026-10 of community PRs opened, P(maintainer engagement within 7 days) among PRs opened that week, success rate among decided PRs opened that week, maintainer merges of community PRs, and core commits. Find the strongest change points (simple binary segmentation on the weekly series, implement it yourself) and compare them with the four given epoch boundaries. Report any strong breakpoint that the epochs miss.
5. Robustness: fit the stage 1 and stage 2 models (re-implement a compact version, or import from `analysis/attention` if it exists by the time you run) on PRs opened before 2026-08-14 and test on those after (calibration and AUC). Report which effects keep their sign and rough size across the split.
6. Headline numbers for the page (store under `headline` in the JSON): total PRs, community PRs, decided, success rate overall and per epoch, median hours to first maintainer engagement per epoch, share of community PRs that never got maintainer attention before closing, size of the 2026-09-21 mass closure, current open community backlog.

## Data notes from the funnel build (read before modelling)
- Bulk actions: 5,250 events are flagged `bulk` (same actor, type and detail on 20+ PRs within one minute), e.g. ryanrhughes's review requests on 2026-09-08 and omarchybot's bug/enhancement labels in late September. Use `first_maintainer_engagement_nobulk` / `h_maintainer_engagement_nobulk` as THE attention event in all models; report the bulk-inclusive version only as a sensitivity check.
- Silent decisions: `silent_decision` includes closes with a one-line comment in the same second (`has_terminal_comment`). `silent_no_comment` is the truly wordless subset. Treat a decision with only a terminal comment as "decided without prior engagement".
- Mass close of 2026-09-21: 270 PRs carry `mass_close_event`; most have disposition `superseded_duplicate` because of precedence. Filter on the flag, not on the disposition.
- omarchybot closes "at the maintainer's request" are `bot_admin_closed` (or `superseded_duplicate` when the comment says so). Treat them as maintainer decisions routed through a bot in the disposition analysis and say so.
- Absorbed: strict detection finds none in E1; early "gave you commit credit" closes are in `superseded_duplicate`. Report absorbed and superseded both separately and combined where it matters.
- `other_closed` (10 PRs) = closed by a non-core org member (csfh etc.).
- Competition clusters: transitive clusters chain through absorbing PRs (largest 258). Use `direct_competitors` and `direct_competitors_open_at_creation` (one hop) for competition effects; use clusters only descriptively.
- Only 11 accepted community PRs had a maintainer title rewrite. Use maintainer body edits too, and report the rarity itself as a finding (rewrites are NOT a major triage mechanism here) rather than forcing 20 examples; show what exists.
- Substantive maintainer feedback is very rare in E3/E4 (48 PRs) versus E1/E2 (416). Say so plainly; the feedback analysis is mostly about E1/E2, and its stability across epochs cannot be tested well.
- Three PRs (#5442, #5471, #5869) are 404 and missing. 75 PRs have partial areas (over 100 files).
- Funnel counts (community, all epochs): submitted 6,336 → any interaction 5,932 → maintainer engagement 1,868 (bulk-inclusive) → substantive feedback 464 → success 940; open 2,665 (2,361 of them in E4).

## Merged run (supersedes the A/B/C split above)
One agent does all three analyses, with a trimmed scope to save tokens. Earlier agents were cut off mid-way; their partial code is in analysis/context/ (competition.py, data.py, effects.py, stats.py) and analysis/feedback/ (constants.py, load.py). Reuse what is sound, rewrite what is not.

Keep (in this priority order; stop after item 6 if running long and report what's missing):
1. Headline + sankey + dispositions by epoch (C.3, C.6, sankey counts), including the 2026-09-21 mass-close composition.
2. Stage 1 attention: Aalen–Johansen cumulative incidence of first maintainer engagement (nobulk) by epoch; one discrete-time logistic model of P(engaged within 14 days) with AMEs in pp.
3. Stage 2 conversion: P(success | engaged) model with AMEs; the "attention vs conversion" decomposition for the key features.
4. KIND and TOPIC as a main thread: for each kind (bug_fix, feature, performance, security, docs, refactor, packaging) and each topic: n, P(engaged within 14 d), P(success | engaged), overall success among decided, and how this changed by epoch. Make a small table the page can draw as a heatmap or dot matrix.
5. Context: competition (first vs later among direct competitors), backlog, dhh/core focus on the same area in the previous 14 days, recent maintainer activity. AMEs, overall and per epoch.
6. Feedback (E1/E2 mostly): response latency buckets and response kinds vs success; triage artefacts (labels, omarchybot reviews, review requests, maintainer reactions): success with/without and median timing before the decision. Maintainer rewrites: count + all examples that exist. Up to 12 `voices` quotes (as in B).
7. Weekly series + simple binary-segmentation breakpoints (C.4).
8. Robustness: with/without mass-closed PRs, and per-epoch estimates for the stage 1 and 2 models (already part of 2 and 3). Skip the time-based holdout and within-author fixed-effects models unless cheap.
9. The user's three PRs (#12814, #14148, #14220): predicted P(engaged in 14 d), P(success | engaged), current position.

Outputs: one file data/results/analysis.json with top-level keys headline, sankey, dispositions, attention, conversion, decomposition, kind_topic, context, feedback, artefacts, rewrites, voices, weekly, breakpoints, robustness, user_prs; and one notes/findings.md with the findings table described in the output contract. Package analysis/core/ with CLI run_analysis.py. Be token-frugal: don't print large tables to the console; inspect with small summaries.
