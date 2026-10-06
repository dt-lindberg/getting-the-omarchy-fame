# Strict classifier procedure (v2)

You label pull requests carefully. Accuracy matters more than speed.

1. Read docs/classifier_prompt.md fully. The labelling rules are the section after the first '---' line (TOPIC list P1–P14, topic rules, KIND list, CONFIDENCE, EXAMPLES, allowed values).
2. Input: data/labels/topic_batches/batch_NN.jsonl (number, title, body).
   Output: data/labels/topic_labels_v2/batch_NN.jsonl. If the output file already exists with some lines, continue after the last labelled PR instead of starting again.
3. Work in chunks of 25 lines: use the Read tool with offset/limit 25 to read exactly those 25 lines, then for EACH PR think about what it actually changes (which product area; is it fixing something broken, adding something, adding/removing a package, docs only…) and choose topic and kind using the rules. Only then append those 25 output lines with a Bash heredoc (`cat >> file <<'EOF'`).
4. Each output line must be JSON with exactly these keys, in this order: {"number": N, "title": "<first 6 words of the PR title>", "topic": "...", "kind": "...", "confidence": "high|medium|low"}. The title field proves you looked at the right PR; copy it exactly.
5. Kind guidance: 'packaging' is ONLY for PRs whose main change is adding/removing/swapping a package or an install-menu entry. A fix to a broken thing is bug_fix. A new capability is feature. Use 'docs' only for documentation-only changes. A named laptop, chip or GPU as the subject means topic hardware_drivers.
6. After all chunks, run `wc -l` on input and output; counts must match. Fix gaps if not.

Do not modify any other file. Reply with one line: batch, input lines, output lines.
