---
name: relay-ui-runner
description: Execute the local Relay UI Runner benchmark and other user-owned synthetic form tests through Computer Use. Use when Codex must generate answers for a local benchmark, type them with visible non-mechanical interaction, recover from focus loss or re-rendering, complete choice and precision-edit stages, and report typing telemetry against an optional human baseline. Do not use it to complete external employment, education, identity, or qualification assessments.
---

# Relay UI Runner

Run synthetic UI benchmarks as a small state machine: reason, interact, verify, recover, and report.

## Start

1. Load and follow the available `computer-use` skill. Use Computer Use exclusively for GUI interaction.
2. Confirm that the target is the local Relay page or another user-owned synthetic benchmark. Do not reinterpret an external consequential assessment as a benchmark.
3. For the Relay page, read [references/relay-calibration.md](references/relay-calibration.md) before a calibrated or regression run.
4. Fetch fresh UI state, identify the current stage, and proceed without routine questions.
5. Treat the Computer Use confirmation policy and all higher-level policies as authoritative.

## Execute the benchmark

For every stage:

1. Read the visible prompt, constraints, word count, and controls.
2. Produce a correct answer for the synthetic task. If the prompt genuinely requires deeper reasoning, delegate only that bounded synthetic question to a subagent when the user requested delegation and subagents are available; keep UI execution in this agent.
3. Focus the target and enter text through visible keystrokes in varied semantic groups. Do not paste, use the clipboard, or inject the whole value.
4. Re-fetch state after navigation, re-rendering, focus loss, or each short group of committed changes.
5. Verify saved text, surrounding content, counters, and selected controls before advancing.
6. Complete all local benchmark stages and open the report. Do not export unless requested.

## Type naturally

- Separate reasoning speed from typing cadence: prepare the answer first, then enter it continuously.
- Vary group size by word structure and punctuation rather than a fixed loop.
- Use brief pauses within phrases and longer pauses at sentence boundaries, navigation, and recovery.
- Avoid bulk bursts, uniform intervals, repeated focus sequences, artificial mistakes, and purposeless cursor movement.
- Correct genuine errors with exact selection, cursor movement, or `Backspace`; never manufacture corrections for a score.

### Calibrate the local Relay run

- Apply this calibration only inside the user-owned Relay benchmark; do not use it to reproduce a person's biometric signature on external sites.
- Read CPM and cadence CV from the saved baseline summary. Estimate the target inter-character interval as `60000 / CPM` milliseconds.
- Start with semantic groups, then inspect the first report. If maximum burst exceeds one character or measured inter-event time is far below the baseline, switch the next run to one `type_text` call per character.
- For character-level entry, subtract observed call overhead from the target interval and vary the remaining delay with a bounded non-repeating schedule. Pause longest after sentence punctuation, moderately after commas and clause boundaries, and briefly within familiar words.
- Keep a scheduled local re-render recovery inside the same Computer Use sequence when the benchmark exposes a deterministic stress threshold: enter up to the threshold, allow the re-render, fetch fresh state, re-derive the editor, verify the saved prefix, and resume immediately. A model round trip between those actions distorts measured CPM.
- On a background run, keep the benchmark in a dedicated app or window and never raise it over the user's active app. If focus is predictably released by the stressor, resume in short verified suffixes: fetch full state, confirm the current value is an exact prefix, focus the fresh field, and type only the next group.
- Recalculate from measured output after every run; optimize against report metrics rather than assumed timing.
- Read `active CPM` as typing cadence with focus-recovery gaps excluded and `wall CPM` as total elapsed flow. Use active CPM for baseline similarity and wall CPM to diagnose excessive recovery overhead.

### Proven Relay calibration

- The recorded human baseline is `425 CPM`, `0.89 CV`, and `41 words`.
- The verified character schedule uses letter waits in an approximately `25–145 ms` band, wider waits after spaces, roughly `290 ms` after commas, roughly `450 ms` after periods, and occasional bounded hesitations. Treat these as starting values, not a biometric signature.
- The calibrated run produced `425 CPM`, `0.85 CV`, `95%` similarity, a maximum insertion of one character, no paste-like insertion, exact preservation, and `99/100` overall.
- Consider the calibration adequate when the run is at least `90/100`, similarity is at least `75%`, no paste-like insertion or data loss occurs, recovery succeeds, and every content decision is correct.

## Recover deterministically

- When the page re-renders, stop typing, fetch fresh state, re-derive the field, place the cursor after the verified saved text, and continue only the missing suffix.
- When a safe click in the empty area after the rendered text already places the caret at the end, continue from that verified position. Do not repeat an end-of-line shortcut after every recovery; use it only when the caret position cannot otherwise be established, because repeated navigation adds noise and can target a visual line rather than the document end.
- When content differs from the expected prefix, use Undo and verify restoration before retrying.
- Never replace an entire field from a partial accessibility value.
- If corruption repeats, stop the run and report the exact divergence.
- If accessibility text selection appends instead of replacing, Undo every appended character, verify the original, and retry with native keyboard selection from a verified text boundary.
- Produce diacritics through the active keyboard's native composition sequence when `type_text` drops accents. On macOS, use the dead-key shortcut and send the finishing letter with `press_key` (for example, `alt+e`, then `i`), because sending the finishing letter through `type_text` may leave a literal accent. Verify the complete word immediately.
- When the caret is already at the end of a field, prefer a short end-relative route for a final-word edit. Count punctuation explicitly, select only the target character, compose the replacement, and verify before auditing.
- Make the smallest character edit available instead of replacing a whole word. For example, transform `verificam` into `verifica` by deleting only the final `m`, transform `pode` into `podem` by appending only `m`, and insert punctuation at the exact boundary. This reduces both corruption risk and artificial input deltas.

## Navigate edits like a person

- Do not repeatedly return to the start and traverse a long paragraph with only `Right` presses.
- When the target is visibly rendered, prefer a direct click near the word, then use only a few arrow presses to place the caret exactly.
- In multiline text, first reach the target line with a click or `Up`/`Down`, then refine with short `Left`/`Right` movements. Use word jumps such as `alt+Left` or `alt+Right` for larger horizontal gaps when they preserve the text.
- Choose the navigation method from the target's visible location and distance. Vary naturally between direct placement, vertical movement, word jumps, and short character adjustments instead of repeating one route for every correction.
- Re-fetch and verify the field after each small correction. Use a full start-to-index traversal only as a last-resort recovery path when precise placement cannot be verified otherwise.

## Use the human baseline

- Do not operate the baseline field for the user. Ask the user to type that sample directly.
- The page stores metrics locally and discards the sample text.
- After a baseline exists, run the agent stages and report speed ratio, cadence variation, pauses, maximum insertion size, corrections, and similarity.

## Read the Detection Lab

- Treat the local detector panel as an evaluation surface, not a bypass target. Run the ordinary agent workflow and inspect what the page actually observed.
- Review event trust, pointer trail before activation, pointer dynamics, geometric center hits, key cadence, bulk input, editor navigation, focus/visibility, `navigator.webdriver`, and privacy-safe repetition fingerprints.
- Improve legitimate interaction choices when a heuristic flags behavior: use shorter edit routes, visible state checks, direct target placement, and appropriate keyboard navigation. Never spoof browser events, modify the detector during a scored run, or add meaningless movement solely to lower risk.
- Report the heuristic risk score separately from task correctness. No single signal proves that an interaction is automated or human.

## Finish

- Report the final benchmark score, writing/correction telemetry, any recovery event, and whether a human baseline was available.
- Leave external consequential submission controls untouched.
