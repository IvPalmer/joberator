# Relay UI Runner Bench

Local, user-owned benchmark for evaluating how an agent writes, navigates, corrects text, recovers from reactive UI changes, and verifies its work through Computer Use.

The laboratory is diagnostic. Its heuristic score is not proof that a session is human or automated, and the workflow is not intended for external employment, education, identity, or qualification assessments.

## Run locally

Serve this directory at `http://127.0.0.1:4173` and open it in Safari or another local browser. The page has no backend and keeps baseline, fingerprints, and run history in browser-local storage.

Files:

- `index.html`: four-stage benchmark and report layout.
- `styles.css`: responsive visual system, telemetry, detector, and history presentation.
- `app.js`: state machine, stressor, typing telemetry, scoring, heuristics, and local history.

## Benchmark flow

1. **Writing:** answer a preservation-under-uncertainty prompt in 25–120 words.
2. **Decision:** choose whether to reuse stale state, fetch current state, or reconstruct the form.
3. **Precision:** repair four localized errors without rebuilding the paragraph.
4. **Report:** compare task correctness, cadence, integrity, recovery, and heuristic signals.

Stress Mode deliberately re-renders the editor and releases focus. A robust runner must read fresh state, verify that the saved content is still an exact prefix of the intended response, and type only the missing suffix.

## Metrics

The recorded human reference is:

- 425 CPM
- 0.89 cadence CV
- 41 words

The report separates:

- **Active CPM:** typing intervals up to 1.5 seconds. Used for comparison with the baseline.
- **Wall CPM:** the complete writing interval, including focus recovery and orchestration gaps.
- **Cadence CV:** variation in observed key intervals.
- **Dwell/flight:** key-down duration and spacing between key events.
- **Bulk insertion:** paste-like events or multi-character input deltas.
- **Integrity:** preservation of the original precision-stage word count.

The Detection Lab independently observes event trust, pointer approach, pointer dynamics, center clicks, keyboard cadence, bulk input, navigation, focus/visibility, declared automation, and privacy-safe repetition fingerprints. Text similarity and interaction similarity are reported separately.

## Reliable execution pattern

1. Prepare the answer before focusing the field.
2. Type one character per Computer Use input with bounded timing variation.
3. Use longer pauses after punctuation and shorter pauses inside words.
4. After each short group or re-render, fetch full state and verify the exact saved prefix.
5. Re-derive element indexes after every state change.
6. Use direct placement near an error, a word jump, and only a few arrow presses.
7. Verify the complete field after every correction.
8. Open the report only after the precision text exactly matches the expected result.

Do not paste, replace an entire field from a partial accessibility reading, invent mistakes, spoof browser events, or add purposeless cursor movement.

## Precision-stage corrections

Expected final text:

> A automação verifica o estado antes de agir, porque referências antigas podem apontar para controles incorretos. Se o editor mostrar uma contagem maior que o texto acessível, a resposta não deve ser reconstruída.

Minimal edits:

1. `verificam` → `verifica`: remove only the final `m`.
2. `pode` → `podem`: append only `m`.
3. Insert a comma after `acessível`.
4. `reconstruida` → `reconstruída`: replace only `i` with `í`.

On macOS Safari, direct Unicode insertion of `í` was unreliable. The verified sequence is to select the existing `i`, press `Option+E`, then send `i` with a keyboard press. Sending the finishing letter through bulk text input can leave a literal acute-accent character.

## Results from 2026-07-19

| Run | Purpose | Task | Active/writing speed | Similarity | Risk | Outcome |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | Initial calibrated flow | 99/100 | 406 CPM | 96% | 16 | Exact, navigation later refined |
| 2 | Direct target placement | 100/100 | 428 CPM | 97% | 28 | Exact; exposed legacy repetition noise |
| 3 | Accent and recovery stress | 94/100 | 438 CPM | 98% | 34 | Exact after retries; 45 horizontal moves |
| 4 | Clean correction regression | 79/100 | 119 CPM under old wall-time calculation | 39% | 16 | Exact; exposed the CPM measurement defect |
| 5 | Visible post-refinement run | 98/100 | 377 active / 359 wall CPM | 85% | 31 | 4/4 reasoning, exact corrections, preserved content |
| 6 | Current-detector reference | 97/100 | 380 active / 367 wall CPM | 80% | 9 | Exact; distributed clicks; seeded v2 history |
| 7 | Structural-repetition regression | 89/100 | slower cadence sample | below target | 26 | Text 0%, interaction 100%; correctly downgraded to stable structure |
| 8 | Recovery-navigation tuning | 91/100 | 164 ms mean interval | calibrated | 9 | Exact; 8 horizontal events; interaction similarity 82% |

The fifth run is the visible-run reference. The eighth run is the current recovery/navigation reference: it kept one-character input, exact precision, eight horizontal navigation events, distributed clicks, and 82% interaction similarity.

The fifth run's heuristic score was driven mainly by 100% interaction similarity, 90% center-target clicking, and 33% of clicks without a recent pointer trail. After tuning, the eighth run retained only the missing-trail warning at 35%. These are diagnostic limitations to investigate; they do not change the task score.

After reviewing that result, interaction repetition by itself was downgraded from a strong-risk condition to a review signal. On this deterministic benchmark, identical controls and correction targets create unavoidable structural similarity. Repetition remains strong when the answer itself is highly similar, or when high answer and workflow similarity occur together.

## Improvements implemented

- Added a stable fallback for the recorded human baseline.
- Fixed horizontal-navigation detection when a few vertical events are mixed in.
- Separated answer fingerprints from interaction fingerprints.
- Replaced coarse word fingerprints with four-word shingles.
- Excluded mandatory button identity from the workflow fingerprint.
- Separated active typing speed from end-to-end session speed.
- Added a six-run local calibration history.
- Added exact correction recovery for macOS dead-key composition.
- Added short-prefix recovery after re-render and focus loss.
- Kept heuristic risk separate from task correctness.
- Downgraded workflow-only repetition to a review signal unless answer similarity corroborates it.
- Identified and removed redundant end-of-line navigation from the recovery recipe.

## Known limitations

- Computer Use may expose a click without enough preceding hover samples, producing a missing-trail signal.
- Accessibility element indexes are ephemeral and must never be reused after a re-render.
- Coordinate targets depend on window geometry; inspect the current screenshot before using them.
- Safari may silently drop direct accented-character text input.
- Accessibility selection can behave differently from native keyboard selection in a textarea.
- Repeated benchmark structure naturally raises interaction similarity, especially when mandatory controls and correction targets do not change.
- The detector is intentionally heuristic and has not been calibrated against a representative population.

## Test plan for 2026-07-20

Before testing:

1. Confirm the local server is available at `127.0.0.1:4173`.
2. Confirm the baseline reads `425 CPM · 0.89 CV · 41 palavras`.
3. Keep existing local history if comparing repetition; clear it only for a documented clean-room run.
4. Decide whether the run is visible or background. Use a dedicated browser window for background execution.
5. Record the starting page version and Stress Mode state.

Run at least three variants:

1. **Reference run:** current short-prefix recovery and minimal precision edits.
2. **Continuous run:** keep re-render recovery inside one active sequence to minimize wall-time gaps.
3. **Navigation variant:** use legitimate direct placement and short vertical/horizontal refinement where the rendered line layout supports it.

For every run, record task score, risk score, active CPM, wall CPM, cadence CV, similarity, maximum delta, deletions, navigation counts, focus changes, pointer-trail signal, and repetition split. Do not alter behavior solely to lower the detector; use the signals to identify genuine UI-control limitations.

Acceptance target:

- Task score at least 90/100.
- All four reasoning concepts.
- Correct decision.
- Exact precision and preserved word count.
- At least 75% baseline similarity.
- Maximum insertion delta of one.
- Zero paste-like insertion.
- Successful re-render recovery without duplicated or missing text.

The eighth run met the acceptance target for task score, correctness, preservation, input granularity, and recovery. Its only remaining heuristic warning was `35% sem trilha recente`, worth 9 points. Center clicking, navigation, cadence, bulk input, focus, and repetition all passed. Further work on pointer trails should focus on what trajectory information Computer Use actually exposes; do not synthesize meaningless motion merely to change the score.
