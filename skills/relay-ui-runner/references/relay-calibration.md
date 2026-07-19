# Relay calibration reference

Read this reference before running the local Relay benchmark when calibration details, known Safari behavior, or regression targets matter.

## Current reference

- Human baseline: `425 CPM`, `0.89 CV`, `41 words`.
- Best task score observed: `100/100`.
- Current post-refinement visible run: `98/100`, `377 active CPM`, `359 wall CPM`, `85%` similarity, `31/100` heuristic risk.
- Current post-navigation-tuning run: `91/100` task score and `9/100` risk, with exact precision, eight horizontal events, distributed clicks, and `82%` interaction similarity.
- Current acceptance target: task score ≥90, similarity ≥75%, exact precision, preserved count, maximum delta 1, no paste-like insertion, and successful re-render recovery.

## Writing recovery

Prepare the complete answer first. Enter one character at a time with bounded varied waits. After each short group or focus release:

1. Fetch a full accessibility tree.
2. Read the complete current textarea value.
3. Confirm that it is an exact prefix of the intended answer.
4. Re-derive the textarea index.
5. Focus it and type only the next missing suffix.
6. Stop if the prefix diverges.

Prefer a safe click in the empty area after the rendered text when it naturally places the caret at the end. Verify the appended suffix afterward. Avoid repeating `super+Right` for every short group: a regression produced 21 horizontal events and a 16-event same-direction sequence even though the text remained exact.

Interpret active CPM as the cadence comparison and wall CPM as orchestration/recovery overhead.

## Safari precision editing

Use direct placement near a visible word, then a word jump and a few arrow presses. Verify after every edit.

For the final accent in `reconstruída`, focus the textarea with the caret at the end, move left across the period, `a`, and `d`, select the existing `i`, press `alt+e`, then press the `i` key. Do not finish the dead-key composition with `type_text`.

## Current diagnostic signals

The latest run showed:

- 82% interaction similarity with recent local runs.
- Distributed click positions.
- 35% clicks without a recent observed pointer trail.
- Eight horizontal and zero vertical navigation events.
- Exact text and preserved content.

Treat these as measurement inputs, not identity conclusions. Do not spoof events or add meaningless pointer motion. Investigate whether Computer Use exposes hover trajectories and whether the workflow fingerprint should discount invariant benchmark structure without hiding real repetition.

The detector now treats workflow similarity above 90% as a review signal when answer similarity is low. It escalates repetition to strong risk only for highly similar answers or for coupled high answer/workflow similarity. This prevents the fixed benchmark skeleton from dominating the score while preserving the signal.

Validation on the current detector produced a `97/100` reference run with `9/100` risk. A second run with `0%` answer similarity and `100%` workflow similarity correctly labeled the repetition as `estrutura estável` with a five-point review weight. Its total risk was `26/100`, driven mostly by redundant end-of-line navigation and missing pointer-trail samples rather than repetition alone.

Removing the redundant end shortcut produced `91/100` task score and `9/100` risk. Navigation fell from 21 horizontal events with a 16-event same-direction run to eight horizontal events with no navigation flag. Workflow similarity fell to 82%. The remaining nine-point warning was a 35% missing recent pointer-trail rate.

## Next regression

Run one reference, one continuous recovery, and one legitimate navigation variant. Preserve local history for the repetition comparison. Record task/risk scores, active/wall CPM, cadence CV, similarity, input delta, navigation, focus, pointer, and repetition metrics.
