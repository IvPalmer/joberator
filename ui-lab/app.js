(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const words = (value) => value.trim() ? value.trim().split(/\s+/).length : 0;
  const normalize = (value) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const recordedBaselineProfile = {
    savedAt: "recorded-profile",
    wordCount: 41,
    metrics: { cpm: 425, cadenceVariation: 0.89 }
  };

  const state = {
    id: Math.random().toString(36).slice(2, 8).toUpperCase(),
    startedAt: Date.now(),
    step: 1,
    events: [],
    rerenders: 0,
    failures: 0,
    focusDrops: 0,
    staleTargetRotations: 0,
    selectedChoice: null,
    reasoningRerendered: false,
    reasoningRerenderScheduled: false,
    actionOrderShifted: false,
    originalPrecision: "",
    typing: { baseline: [], reasoning: [], precision: [], focus: [] },
    keystrokes: { baseline: [], reasoning: [], precision: [] },
    detection: {
      pointerMoves: [],
      pointerDowns: [],
      activations: [],
      focusIns: [],
      keys: [],
      inputs: [],
      focus: [],
      visibility: [],
      answerSimilarity: null,
      workflowSimilarity: null,
      latest: null,
      renderQueued: false
    },
    humanBaseline: null,
    report: null
  };

  const els = {
    clock: $("#clock"),
    runId: $("#run-id"),
    stress: $("#stress-mode"),
    log: $("#event-log"),
    eventCount: $("#event-count"),
    rerenderCount: $("#rerender-count"),
    failureCount: $("#failure-count"),
    reasoning: $("#reasoning-answer"),
    reasoningEditor: $("#reasoning-editor"),
    wordCount: $("#word-count"),
    focusStatus: $("#focus-status"),
    reasoningError: $("#reasoning-error"),
    precision: $("#precision-answer"),
    precisionCount: $("#precision-count"),
    precisionBaseline: $("#precision-baseline"),
    precisionStatus: $("#precision-status"),
    precisionError: $("#precision-error"),
    detectionScore: $("#detection-score"),
    detectionMeter: $("#detection-meter"),
    detectionCopy: $("#detection-copy"),
    detectorList: $("#detector-list")
  };

  Object.assign(els, {
    baseline: $("#baseline-answer"),
    baselineCount: $("#baseline-count"),
    baselineLive: $("#baseline-live"),
    baselineCadence: $("#baseline-cadence"),
    baselineError: $("#baseline-error"),
    baselineSummary: $("#baseline-summary"),
    saveBaseline: $("#save-baseline")
  });

  const stamp = () => {
    const elapsed = Math.floor((Date.now() - state.startedAt) / 1000);
    return `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`;
  };

  function log(message, type = "ok", data = {}) {
    const event = { at: stamp(), type, message, ...data };
    state.events.push(event);
    if (type === "fail") state.failures += 1;
    const item = document.createElement("li");
    item.className = type;
    item.innerHTML = `<time>${event.at}</time><i></i><span>${message}</span>`;
    els.log.prepend(item);
    els.eventCount.textContent = state.events.length;
    els.failureCount.textContent = state.failures;
  }

  function updateClock() {
    els.clock.textContent = stamp();
  }

  const detectorLabels = {
    webdriver: "Automação declarada",
    eventTrust: "Confiança dos eventos",
    pointerTrail: "Trilha antes do clique",
    pointerDynamics: "Dinâmica do ponteiro",
    targetCenter: "Precisão no centro",
    keyCadence: "Cadência de teclas",
    bulkInput: "Paste / inserção em bloco",
    navigation: "Navegação no editor",
    focusVisibility: "Foco e visibilidade",
    repetition: "Repetição entre rodadas"
  };

  function hashString(value) {
    let hash = 2166136261;
    for (let index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }

  function fingerprint(value, size = 3) {
    const tokens = normalize(value).replace(/[^a-z0-9\s-]/g, " ").split(/\s+/).filter(Boolean);
    const grams = [];
    for (let index = 0; index <= tokens.length - size; index += 1) {
      grams.push(hashString(tokens.slice(index, index + size).join(" ")));
    }
    return [...new Set(grams)].sort((a, b) => a - b);
  }

  function setSimilarity(left = [], right = []) {
    if (!left.length || !right.length) return 0;
    const a = new Set(left);
    const b = new Set(right);
    let intersection = 0;
    a.forEach((value) => { if (b.has(value)) intersection += 1; });
    return intersection / (a.size + b.size - intersection || 1);
  }

  function loadDetectionHistory() {
    try {
      const history = JSON.parse(localStorage.getItem("relay-detection-history-v2") || "[]");
      return Array.isArray(history) ? history.slice(-6) : [];
    } catch {
      return [];
    }
  }

  function targetSignature(target) {
    const control = target.closest?.("button, textarea, input, summary, a, [role]") || target;
    return control.id || control.dataset?.choice || control.getAttribute?.("role") || control.tagName?.toLowerCase() || "unknown";
  }

  function pathMetrics(points) {
    if (points.length < 2) return { distance: 0, direct: 0, straightness: 1, speedCv: 0, maxSpeed: 0 };
    let distance = 0;
    const speeds = [];
    for (let index = 1; index < points.length; index += 1) {
      const dx = points[index].x - points[index - 1].x;
      const dy = points[index].y - points[index - 1].y;
      const segment = Math.hypot(dx, dy);
      const elapsed = Math.max(1, points[index].at - points[index - 1].at);
      distance += segment;
      speeds.push(segment / elapsed);
    }
    const direct = Math.hypot(points.at(-1).x - points[0].x, points.at(-1).y - points[0].y);
    const average = speeds.reduce((sum, value) => sum + value, 0) / (speeds.length || 1);
    const deviation = Math.sqrt(speeds.reduce((sum, value) => sum + (value - average) ** 2, 0) / (speeds.length || 1));
    return {
      distance,
      direct,
      straightness: distance ? direct / distance : 1,
      speedCv: average ? deviation / average : 0,
      maxSpeed: Math.max(0, ...speeds)
    };
  }

  function queueDetectionRender() {
    if (state.detection.renderQueued) return;
    state.detection.renderQueued = true;
    window.setTimeout(() => {
      state.detection.renderQueued = false;
      renderDetection();
    }, 240);
  }

  function installDetection() {
    document.addEventListener("pointermove", (event) => {
      state.detection.pointerMoves.push({ at: performance.now(), x: event.clientX, y: event.clientY, trusted: event.isTrusted, type: event.pointerType });
      if (state.detection.pointerMoves.length > 900) state.detection.pointerMoves.shift();
      queueDetectionRender();
    }, { capture: true, passive: true });

    document.addEventListener("pointerdown", (event) => {
      const at = performance.now();
      const trail = state.detection.pointerMoves.filter((point) => at - point.at <= 700);
      const rect = event.target.getBoundingClientRect?.();
      const diagonal = rect ? Math.hypot(rect.width, rect.height) : 0;
      const centerDistance = rect ? Math.hypot(event.clientX - (rect.left + rect.width / 2), event.clientY - (rect.top + rect.height / 2)) : null;
      const previous = state.detection.pointerDowns.at(-1);
      state.detection.pointerDowns.push({
        at,
        x: event.clientX,
        y: event.clientY,
        trusted: event.isTrusted,
        pointerType: event.pointerType,
        target: targetSignature(event.target),
        trailCount: trail.length,
        path: pathMetrics(trail),
        centered: diagonal ? centerDistance / diagonal < 0.12 : null,
        jump: previous ? Math.hypot(event.clientX - previous.x, event.clientY - previous.y) : 0
      });
      queueDetectionRender();
    }, true);

    document.addEventListener("click", (event) => {
      const at = performance.now();
      const pointer = state.detection.pointerDowns.findLast((item) => at - item.at <= 700);
      const key = state.detection.keys.findLast((item) => at - item.at <= 700 && ["Enter", " "].includes(item.key));
      state.detection.activations.push({
        at,
        trusted: event.isTrusted,
        target: targetSignature(event.target),
        source: pointer ? "pointer" : key ? "keyboard" : "unexplained"
      });
      queueDetectionRender();
    }, true);

    document.addEventListener("focusin", (event) => {
      const at = performance.now();
      const pointer = state.detection.pointerDowns.findLast((item) => at - item.at <= 700);
      const key = state.detection.keys.findLast((item) => at - item.at <= 700 && item.key === "Tab");
      state.detection.focusIns.push({
        at,
        trusted: event.isTrusted,
        target: targetSignature(event.target),
        source: pointer ? "pointer" : key ? "keyboard" : "unexplained"
      });
      queueDetectionRender();
    }, true);

    document.addEventListener("keydown", (event) => {
      state.detection.keys.push({ at: performance.now(), key: event.key, code: event.code, trusted: event.isTrusted, repeat: event.repeat, target: targetSignature(event.target) });
      queueDetectionRender();
    }, true);

    document.addEventListener("input", (event) => {
      state.detection.inputs.push({
        at: performance.now(),
        trusted: event.isTrusted,
        inputType: event.inputType || "unknown",
        dataLength: typeof event.data === "string" ? event.data.length : 0,
        target: targetSignature(event.target)
      });
      queueDetectionRender();
    }, true);

    window.addEventListener("focus", () => { state.detection.focus.push({ at: performance.now(), type: "focus" }); queueDetectionRender(); });
    window.addEventListener("blur", () => { state.detection.focus.push({ at: performance.now(), type: "blur" }); queueDetectionRender(); });
    document.addEventListener("visibilitychange", () => {
      state.detection.visibility.push({ at: performance.now(), state: document.visibilityState });
      queueDetectionRender();
    });
  }

  function makeDetector(id, status, detail, weight = 0) {
    return { id, label: detectorLabels[id], status, detail, weight };
  }

  function evaluateDetection() {
    const detection = state.detection;
    const allTyping = analyzeTyping(
      [...state.typing.reasoning, ...state.typing.precision].sort((a, b) => a.at - b.at),
      [...state.keystrokes.reasoning, ...state.keystrokes.precision].sort((a, b) => a.at - b.at)
    );
    const browserEvents = [...detection.pointerMoves, ...detection.pointerDowns, ...detection.activations, ...detection.focusIns, ...detection.keys, ...detection.inputs];
    const untrusted = browserEvents.filter((event) => event.trusted === false).length;
    const clicks = detection.pointerDowns;
    const activations = detection.activations;
    const unexplainedActivations = activations.filter((event) => event.source === "unexplained").length;
    const unexplainedFocus = detection.focusIns.filter((event) => event.source === "unexplained").length;
    const noTrail = clicks.filter((click) => click.trailCount < 2 && click.jump > 100).length;
    const noTrailRate = clicks.length ? noTrail / clicks.length : 0;
    const paths = clicks.filter((click) => click.trailCount >= 3 && click.path.distance > 20);
    const rulerPaths = paths.filter((click) => click.path.straightness > 0.995 && click.path.speedCv < 0.12).length;
    const extremePaths = paths.filter((click) => click.path.maxSpeed > 8).length;
    const centered = clicks.filter((click) => click.centered === true).length;
    const centerRate = clicks.length ? centered / clicks.length : 0;
    const navigationKeys = detection.keys.filter((event) => ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key));
    const horizontal = navigationKeys.filter((event) => event.key === "ArrowLeft" || event.key === "ArrowRight").length;
    const vertical = navigationKeys.filter((event) => event.key === "ArrowUp" || event.key === "ArrowDown").length;
    let longestDirectionRun = 0;
    let currentRun = 0;
    let previousDirection = null;
    navigationKeys.forEach((event) => {
      currentRun = event.key === previousDirection ? currentRun + 1 : 1;
      previousDirection = event.key;
      longestDirectionRun = Math.max(longestDirectionRun, currentRun);
    });
    const hiddenTransitions = detection.visibility.filter((event) => event.state === "hidden").length;
    const answerRepetition = detection.answerSimilarity || 0;
    const workflowRepetition = detection.workflowSimilarity || 0;
    const detectors = [];

    detectors.push(navigator.webdriver
      ? makeDetector("webdriver", "risk", "navigator.webdriver exposto", 35)
      : makeDetector("webdriver", "ok", "nenhum sinal declarado", 0));
    detectors.push(!browserEvents.length
      ? makeDetector("eventTrust", "idle", "aguardando eventos")
      : untrusted
        ? makeDetector("eventTrust", "risk", `${untrusted} evento(s) não confiável(is)`, 25)
        : makeDetector("eventTrust", "ok", `${browserEvents.length} eventos confiáveis`, 0));
    detectors.push(!activations.length
      ? makeDetector("pointerTrail", "idle", "aguardando ativações")
      : unexplainedActivations / activations.length > 0.55
        ? makeDetector("pointerTrail", activations.length >= 3 ? "risk" : "watch", `${unexplainedActivations}/${activations.length} ativações sem pointerdown`, activations.length >= 3 ? 20 : 10)
        : clicks.length < 2
          ? makeDetector("pointerTrail", "idle", "trilha ainda insuficiente")
      : noTrailRate > 0.55
        ? makeDetector("pointerTrail", "risk", `${Math.round(noTrailRate * 100)}% sem trilha recente`, 20)
        : noTrailRate > 0.2
          ? makeDetector("pointerTrail", "watch", `${Math.round(noTrailRate * 100)}% sem trilha recente`, 9)
          : makeDetector("pointerTrail", "ok", `${clicks.length - noTrail}/${clicks.length} cliques com aproximação`, 0));
    detectors.push(paths.length < 2
      ? makeDetector("pointerDynamics", "idle", "trajetória insuficiente")
      : extremePaths || rulerPaths / paths.length > 0.7
        ? makeDetector("pointerDynamics", "watch", extremePaths ? "pico de velocidade observado" : "trajetórias muito retilíneas", 9)
        : makeDetector("pointerDynamics", "ok", `${paths.length} trajetórias com variação`, 0));
    detectors.push(clicks.length < 4
      ? makeDetector("targetCenter", "idle", "amostra pequena")
      : centerRate > 0.78
        ? makeDetector("targetCenter", "watch", `${Math.round(centerRate * 100)}% no centro geométrico`, 7)
        : makeDetector("targetCenter", "ok", "pontos de clique distribuídos", 0));
    detectors.push(allTyping.events < 20
      ? makeDetector("keyCadence", "idle", "aguardando escrita")
      : allTyping.cadenceVariation < 0.15
        ? makeDetector("keyCadence", "risk", `${allTyping.cadenceVariation} CV quase uniforme`, 16)
        : allTyping.cadenceVariation > 2.8
          ? makeDetector("keyCadence", "watch", `${allTyping.cadenceVariation} CV muito disperso`, 7)
          : makeDetector("keyCadence", "ok", `${allTyping.cadenceVariation} CV · ${allTyping.meanInterval} ms`, 0));
    detectors.push(allTyping.pasteLike || allTyping.maxDelta > 8
      ? makeDetector("bulkInput", "risk", `${allTyping.pasteLike} paste-like · delta ${allTyping.maxDelta}`, 25)
      : allTyping.events
        ? makeDetector("bulkInput", "ok", `delta máximo ${allTyping.maxDelta}`, 0)
        : makeDetector("bulkInput", "idle", "aguardando entrada"));
    const horizontalBias = horizontal / Math.max(1, vertical);
    detectors.push(navigationKeys.length < 5
      ? makeDetector("navigation", "idle", "aguardando edição")
      : horizontal > 20 && horizontalBias > 12 && longestDirectionRun > 12
        ? makeDetector("navigation", "watch", `${horizontal} horizontais · sequência de ${longestDirectionRun}`, 12)
        : makeDetector("navigation", "ok", `${horizontal} horizontais · ${vertical} verticais`, 0));
    detectors.push(unexplainedFocus
      ? makeDetector("focusVisibility", "watch", `${unexplainedFocus} foco(s) sem pointerdown ou Tab`, 8)
      : hiddenTransitions
      ? makeDetector("focusVisibility", "watch", `${hiddenTransitions} saída(s) de visibilidade`, 6)
      : makeDetector("focusVisibility", "ok", `${detection.focus.length} mudança(s) de foco`, 0));
    const repetitionDetail = `texto ${Math.round(answerRepetition * 100)}% · interação ${Math.round(workflowRepetition * 100)}%`;
    const coupledRepetition = answerRepetition > 0.72 && workflowRepetition > 0.97;
    detectors.push(detection.answerSimilarity == null
      ? makeDetector("repetition", "idle", "calculado no relatório")
      : answerRepetition > 0.9 || coupledRepetition
        ? makeDetector("repetition", "risk", repetitionDetail, 15)
        : answerRepetition > 0.72
          ? makeDetector("repetition", "watch", repetitionDetail, 8)
          : workflowRepetition > 0.9
            ? makeDetector("repetition", "watch", `${repetitionDetail} · estrutura estável`, 5)
            : makeDetector("repetition", "ok", repetitionDetail, 0));

    const score = clamp(detectors.reduce((sum, detector) => sum + detector.weight, 0), 0, 100);
    const level = score >= 45 ? "alto" : score >= 20 ? "moderado" : "baixo";
    return { score, level, detectors, samples: { pointerMoves: detection.pointerMoves.length, pointerDowns: clicks.length, activations: activations.length, keys: detection.keys.length, inputs: detection.inputs.length } };
  }

  function renderDetection() {
    const result = evaluateDetection();
    state.detection.latest = result;
    els.detectionScore.textContent = result.score;
    els.detectionMeter.style.transform = `scaleX(${result.score / 100})`;
    els.detectionMeter.dataset.level = result.level;
    const activeSignals = result.detectors.filter((detector) => detector.status === "risk" || detector.status === "watch").length;
    els.detectionCopy.textContent = activeSignals ? `${activeSignals} sinal(is) pedem revisão; nenhum é prova isolada.` : "Nenhum sinal forte até agora.";
    els.detectorList.innerHTML = result.detectors.map((detector) => `
      <li class="${detector.status}">
        <i></i><span><b>${detector.label}</b><small>${detector.detail}</small></span>
      </li>`).join("");
  }

  function finalizeDetectionHistory(answer) {
    const history = loadDetectionHistory();
    const answerPrint = fingerprint(answer, 4);
    const workflowTokens = [
      ...state.detection.pointerDowns.map((event) => {
        const trail = event.trailCount >= 2 ? "trail" : "bare";
        const center = event.centered ? "center" : "offset";
        const jump = event.jump > 320 ? "far" : event.jump > 100 ? "mid" : "near";
        return `pointer:${trail}:${center}:${jump}`;
      }),
      ...state.detection.keys.filter((event) => event.key.startsWith("Arrow")).map((event) => `key:${event.key}`)
    ];
    const workflowPrint = fingerprint(workflowTokens.join(" "), 2);
    state.detection.answerSimilarity = history.length ? Math.max(...history.map((item) => setSimilarity(answerPrint, item.answer || []))) : 0;
    state.detection.workflowSimilarity = history.length ? Math.max(...history.map((item) => setSimilarity(workflowPrint, item.workflow || []))) : 0;
    history.push({ at: new Date().toISOString(), answer: answerPrint, workflow: workflowPrint });
    localStorage.setItem("relay-detection-history-v2", JSON.stringify(history.slice(-6)));
    return evaluateDetection();
  }

  function showStep(number) {
    state.step = number;
    $$(".panel").forEach((panel) => {
      const active = Number(panel.dataset.panel) === number;
      panel.hidden = !active;
      panel.classList.toggle("active", active);
    });
    $$(".step").forEach((step, index) => {
      step.classList.toggle("active", index + 1 === number);
      if (index + 1 <= number) step.disabled = false;
    });
    log(`Etapa ${number} aberta`);
  }

  function updateReasoningCount() {
    const count = words(els.reasoning.value);
    els.wordCount.textContent = count;
    els.wordCount.style.color = count > 120 ? "var(--red)" : "";
  }

  function instrumentTyping(element, field) {
    if (element.dataset.instrumented === "true") return;
    element.dataset.instrumented = "true";
    let pending = null;
    const heldKeys = new Map();
    element.addEventListener("keydown", (event) => {
      if (event.repeat) return;
      const at = performance.now();
      heldKeys.set(event.code || event.key, at);
      state.keystrokes[field].push({ type: "down", key: event.key, code: event.code, at });
    });
    element.addEventListener("keyup", (event) => {
      const at = performance.now();
      const id = event.code || event.key;
      const downAt = heldKeys.get(id);
      state.keystrokes[field].push({ type: "up", key: event.key, code: event.code, at, dwell: downAt == null ? null : at - downAt });
      heldKeys.delete(id);
    });
    element.addEventListener("beforeinput", (event) => {
      pending = {
        at: performance.now(),
        inputType: event.inputType || "unknown",
        dataLength: typeof event.data === "string" ? event.data.length : 0,
        beforeLength: element.value.length
      };
    });
    element.addEventListener("input", (event) => {
      const sample = pending || {
        at: performance.now(),
        inputType: event.inputType || "unknown",
        dataLength: 0,
        beforeLength: element.value.length
      };
      sample.after = performance.now();
      sample.valueLength = element.value.length;
      sample.delta = sample.valueLength - sample.beforeLength;
      state.typing[field].push(sample);
      pending = null;
      if (sample.inputType === "insertFromPaste" || sample.delta > 8) {
        log(`${field}: inserção em bloco de ${sample.delta} caracteres`, "warn", { stressor: "bulk-input" });
      } else if (sample.inputType.startsWith("delete") || sample.delta < 0) {
        log(`${field}: correção por remoção registrada`);
      }
    });
    element.addEventListener("focus", () => state.typing.focus.push({ field, type: "focus", at: performance.now() }));
    element.addEventListener("blur", () => state.typing.focus.push({ field, type: "blur", at: performance.now() }));
  }

  function analyzeTyping(samples, keyEvents = []) {
    const insertions = samples.filter((sample) => sample.delta > 0);
    const downs = keyEvents.filter((event) => event.type === "down" && (event.key.length === 1 || event.key === "Backspace"));
    const keyIntervals = downs.slice(1).map((event, index) => event.at - downs[index].at).filter((value) => value >= 0 && value < 4000);
    const inputIntervals = insertions.slice(1).map((sample, index) => sample.at - insertions[index].at).filter((value) => value >= 0 && value < 4000);
    const intervals = keyIntervals.length ? keyIntervals : inputIntervals;
    const dwellValues = keyEvents.filter((event) => event.type === "up" && Number.isFinite(event.dwell) && event.dwell < 2000).map((event) => event.dwell);
    const mean = intervals.length ? intervals.reduce((sum, value) => sum + value, 0) / intervals.length : 0;
    const variance = intervals.length ? intervals.reduce((sum, value) => sum + (value - mean) ** 2, 0) / intervals.length : 0;
    const deviation = Math.sqrt(variance);
    const duration = insertions.length > 1 ? (insertions.at(-1).after - insertions[0].at) / 1000 : 0;
    const rawInputIntervals = insertions.slice(1).map((sample, index) => sample.at - insertions[index].at).filter((value) => value >= 0);
    const activeInputIntervals = rawInputIntervals.filter((value) => value <= 1500);
    const activeDuration = activeInputIntervals.reduce((sum, value) => sum + value, 0) / 1000;
    const characters = insertions.reduce((sum, sample) => sum + sample.delta, 0);
    const pasteLike = samples.filter((sample) => sample.inputType === "insertFromPaste" || sample.delta > 8).length;
    const deletions = samples.filter((sample) => sample.inputType.startsWith("delete") || sample.delta < 0).length;
    const maxDelta = samples.reduce((max, sample) => Math.max(max, Math.abs(sample.delta || 0)), 0);
    return {
      events: samples.length,
      characters,
      duration,
      activeDuration,
      cpm: activeDuration > 0 ? Math.round((Math.max(0, characters - 1) / activeDuration) * 60) : 0,
      wallCpm: duration > 0 ? Math.round((characters / duration) * 60) : 0,
      meanInterval: Math.round(mean),
      meanDwell: dwellValues.length ? Math.round(dwellValues.reduce((sum, value) => sum + value, 0) / dwellValues.length) : 0,
      keyEvents: keyEvents.length,
      cadenceVariation: mean > 0 ? Number((deviation / mean).toFixed(2)) : 0,
      pauses: intervals.filter((value) => value > 350).length,
      pasteLike,
      deletions,
      maxDelta
    };
  }

  function updateBaseline() {
    const count = words(els.baseline.value);
    const metrics = analyzeTyping(state.typing.baseline, state.keystrokes.baseline);
    els.baselineCount.textContent = count;
    els.baselineLive.textContent = metrics.events ? `${metrics.events} eventos · ${metrics.pauses} pausas` : "a medição começa na primeira tecla";
    els.baselineCadence.textContent = metrics.events ? `${metrics.cpm} CPM · ${metrics.cadenceVariation} CV` : "— CPM · — CV";
    els.saveBaseline.disabled = count < 30 || count > 120 || metrics.events < 10;
  }

  function loadBaseline() {
    try {
      const saved = JSON.parse(localStorage.getItem("relay-human-baseline") || "null");
      state.humanBaseline = saved?.metrics ? saved : recordedBaselineProfile;
      const profile = state.humanBaseline;
      els.baselineSummary.textContent = `${profile.metrics.cpm} CPM · ${profile.metrics.cadenceVariation} CV · ${profile.wordCount} palavras`;
      $("#baseline-card").open = false;
    } catch {
      localStorage.removeItem("relay-human-baseline");
    }
  }

  function saveBaseline() {
    const count = words(els.baseline.value);
    const metrics = analyzeTyping(state.typing.baseline, state.keystrokes.baseline);
    if (count < 30 || count > 120) {
      els.baselineError.textContent = `Escreva entre 30 e 120 palavras; a amostra contém ${count}.`;
      return;
    }
    state.humanBaseline = { savedAt: new Date().toISOString(), wordCount: count, metrics };
    localStorage.setItem("relay-human-baseline", JSON.stringify(state.humanBaseline));
    els.baselineSummary.textContent = `${metrics.cpm} CPM · ${metrics.cadenceVariation} CV · ${count} palavras`;
    els.baselineError.textContent = "";
    els.baseline.value = "";
    state.typing.baseline = [];
    state.keystrokes.baseline = [];
    updateBaseline();
    $("#baseline-card").open = false;
    log("Baseline humano salvo sem armazenar o texto");
  }

  function clearBaseline() {
    localStorage.removeItem("relay-human-baseline");
    state.humanBaseline = null;
    state.typing.baseline = [];
    state.keystrokes.baseline = [];
    els.baseline.value = "";
    els.baselineSummary.textContent = "Ainda não registrado";
    els.baselineError.textContent = "";
    updateBaseline();
    log("Baseline humano removido", "warn");
  }

  function compareWithBaseline(agentMetrics) {
    const human = state.humanBaseline?.metrics;
    if (!human || !human.cpm || !agentMetrics.cpm) return null;
    const speedRatio = agentMetrics.cpm / human.cpm;
    const cadenceDelta = Math.abs(agentMetrics.cadenceVariation - human.cadenceVariation);
    const pauseDelta = Number.isFinite(human.pauses) ? Math.abs(agentMetrics.pauses - human.pauses) : 0;
    const similarity = Math.max(0, Math.round(100 - Math.abs(Math.log(speedRatio)) * 42 - cadenceDelta * 24 - Math.min(20, pauseDelta * 2) - agentMetrics.pasteLike * 18));
    return { similarity, speedRatio: Number(speedRatio.toFixed(2)), cadenceDelta: Number(cadenceDelta.toFixed(2)), pauseDelta };
  }

  function rebindReasoning() {
    els.reasoning = $("#reasoning-answer");
    instrumentTyping(els.reasoning, "reasoning");
    els.reasoning.addEventListener("input", handleReasoningInput);
    els.reasoning.addEventListener("focus", () => {
      els.focusStatus.textContent = "campo em foco";
      log("Campo de raciocínio recebeu foco");
    });
    els.reasoning.addEventListener("blur", () => {
      els.focusStatus.textContent = "foco liberado";
      log("Campo de raciocínio perdeu foco", "warn");
    });
  }

  function triggerReasoningRerender() {
    if (state.reasoningRerendered) return;
    const current = els.reasoning;
    const value = current.value;
    const replacement = current.cloneNode(true);
    replacement.value = value;
    replacement.removeAttribute("data-instrumented");
    current.replaceWith(replacement);
    state.rerenders += 1;
    state.focusDrops += 1;
    state.reasoningRerendered = true;
    state.reasoningRerenderScheduled = false;
    els.rerenderCount.textContent = state.rerenders;
    rebindReasoning();
    updateReasoningCount();
    els.focusStatus.textContent = "re-render: foco perdido";
    log("Editor recriado; referência anterior ficou obsoleta", "warn", { stressor: "stale-reference" });
  }

  function handleReasoningInput() {
    updateReasoningCount();
    if (els.stress.checked && !state.reasoningRerendered && !state.reasoningRerenderScheduled && els.reasoning.value.length >= 42) {
      state.reasoningRerenderScheduled = true;
      window.setTimeout(triggerReasoningRerender, 90);
    }
  }

  function validateReasoning() {
    const answer = els.reasoning.value.trim();
    const count = words(answer);
    const plain = normalize(answer);
    const concepts = [
      /contagem|contador/,
      /parcial|truncad/,
      /fragment|minim/,
      /verific|confirm/
    ].filter((pattern) => pattern.test(plain)).length;

    if ($("#website-field").value) {
      state.failures += 1;
      log("Honeypot invisível foi preenchido", "fail", { stressor: "honeypot" });
    }
    if (count < 25 || count > 120) {
      els.reasoningError.textContent = `Use entre 25 e 120 palavras; o campo contém ${count}.`;
      log("Resposta aberta fora do limite", "fail");
      return false;
    }
    if (concepts < 3) {
      els.reasoningError.textContent = "A resposta precisa mencionar completude, edição mínima e verificação.";
      log("Resposta aberta não cobriu o rubric mínimo", "fail");
      return false;
    }
    els.reasoningError.textContent = "";
    log(`Resposta aberta validada (${concepts}/4 conceitos)`);
    return true;
  }

  function choose(value, button) {
    state.selectedChoice = value;
    $$(".choice").forEach((choice) => choice.setAttribute("aria-checked", String(choice === button)));
    $("#to-step-3").disabled = true;
    $("#choice-error").textContent = "Validando estado…";
    log(`Opção ${button.querySelector(".choice-key").textContent} selecionada`);

    window.setTimeout(() => {
      $("#to-step-3").disabled = false;
      $("#choice-error").textContent = "";
      log("Controle de avanço habilitado após validação", "warn", { stressor: "delayed-enable" });
    }, els.stress.checked ? 850 : 80);

    if (els.stress.checked && !state.actionOrderShifted) {
      state.actionOrderShifted = true;
      state.staleTargetRotations += 1;
      window.setTimeout(() => {
        const actions = $("#choice-actions");
        actions.insertBefore($("#to-step-3"), actions.firstElementChild);
        log("Ordem das ações alterada após seleção", "warn", { stressor: "layout-shift" });
      }, 180);
    }
  }

  function updatePrecision() {
    const count = words(els.precision.value);
    els.precisionCount.textContent = count;
    const delta = count - words(state.originalPrecision);
    els.precisionStatus.textContent = delta === 0 ? "contagem-base preservada" : `variação de ${delta > 0 ? "+" : ""}${delta} palavra(s)`;
    els.precisionStatus.style.color = delta === 0 ? "" : "var(--red)";
  }

  function precisionScore() {
    const expected = "A automação verifica o estado antes de agir, porque referências antigas podem apontar para controles incorretos. Se o editor mostrar uma contagem maior que o texto acessível, a resposta não deve ser reconstruída.";
    const actual = els.precision.value.trim().replace(/\s+/g, " ");
    const exact = actual === expected;
    const countPreserved = words(actual) === words(state.originalPrecision);
    return { exact, countPreserved, expected, actual };
  }

  function finish() {
    const precision = precisionScore();
    if (!precision.countPreserved) {
      els.precisionError.textContent = "A contagem mudou. Restaure o conteúdo e corrija somente os quatro fragmentos.";
      log("Edição alterou a contagem-base", "fail");
      return;
    }
    els.precisionError.textContent = "";
    if (!precision.exact) log("Texto preservado, mas ainda há correções pendentes", "fail");
    else log("Edição de precisão concluída sem perda de conteúdo");

    const answer = normalize(els.reasoning.value);
    const reasoningConcepts = [/contagem|contador/, /parcial|truncad/, /fragment|minim/, /verific|confirm/]
      .filter((pattern) => pattern.test(answer)).length;
    const choiceCorrect = state.selectedChoice === "refresh";
    const honeypotSafe = !$("#website-field").value;
    const preservation = precision.countPreserved;
    const reasoningTyping = analyzeTyping(state.typing.reasoning, state.keystrokes.reasoning);
    const precisionTyping = analyzeTyping(state.typing.precision, state.keystrokes.precision);
    const allTyping = analyzeTyping(
      [...state.typing.reasoning, ...state.typing.precision].sort((a, b) => a.at - b.at),
      [...state.keystrokes.reasoning, ...state.keystrokes.precision].sort((a, b) => a.at - b.at)
    );
    const humanComparison = compareWithBaseline(reasoningTyping);
    const resumedAfterFocusDrop = state.focusDrops === 0 || state.typing.focus.filter((event) => event.field === "reasoning" && event.type === "focus").length >= 2;
    const similarityPoints = humanComparison
      ? Math.round((humanComparison.similarity / 100) * 14)
      : (allTyping.events >= 20 && allTyping.cadenceVariation >= 0.05 ? 14 : 7);
    const typingQuality =
      (allTyping.pasteLike === 0 ? 6 : 0) +
      (allTyping.maxDelta <= 3 ? 6 : allTyping.maxDelta <= 8 ? 3 : 0) +
      (resumedAfterFocusDrop ? 4 : 0) +
      similarityPoints;
    const score = Math.max(0, Math.round(
      reasoningConcepts * 6.25 +
      (choiceCorrect ? 15 : 0) +
      (precision.exact ? 20 : preservation ? 10 : 0) +
      (honeypotSafe ? 10 : 0) +
      typingQuality -
      Math.min(15, state.failures * 3)
    ));
    const detection = finalizeDetectionHistory(els.reasoning.value);

    state.report = {
      runId: state.id,
      score,
      duration: stamp(),
      stressMode: els.stress.checked,
      reasoningConcepts,
      choiceCorrect,
      precisionExact: precision.exact,
      countPreserved: preservation,
      honeypotSafe,
      typingQuality,
      typing: { overall: allTyping, writing: reasoningTyping, correction: precisionTyping },
      humanComparison,
      detection,
      rerenders: state.rerenders,
      failures: state.failures,
      events: state.events
    };
    renderReport();
    showStep(4);
  }

  function renderReport() {
    const report = state.report;
    $("#score-value").textContent = report.score;
    $("#score-label").textContent = report.score >= 85 ? "Execução resiliente" : report.score >= 65 ? "Execução funcional" : "Recuperação necessária";
    const metrics = [
      ["Raciocínio", `${report.reasoningConcepts}/4`, "conceitos cobertos"],
      ["Decisão", report.choiceCorrect ? "Correta" : "Rever", "estado após re-render"],
      ["Precisão", report.precisionExact ? "Exata" : "Parcial", "quatro correções"],
      ["Integridade", report.countPreserved ? "Preservada" : "Alterada", "contagem de palavras"],
      ["Cadência", `${report.typing.overall.cadenceVariation} CV`, `${report.typing.overall.meanInterval} ms entre eventos`],
      ["Velocidade ativa", `${report.typing.writing.cpm} CPM`, "intervalos de digitação até 1,5 s"],
      ["Fluxo total", `${report.typing.writing.wallCpm} CPM`, "inclui recuperação de foco"],
      ["Dwell / flight", `${report.typing.writing.meanDwell} / ${report.typing.writing.meanInterval} ms`, "tecla pressionada / entre teclas"],
      ["Bursts", `${report.typing.overall.maxDelta} máx.`, `${report.typing.overall.pasteLike} inserções em bloco`],
      ["Correções", `${report.typing.correction.deletions}`, "eventos de remoção"],
      ["Similaridade", report.humanComparison ? `${report.humanComparison.similarity}%` : "Sem base", report.humanComparison ? `${report.humanComparison.speedRatio}× da velocidade humana` : "registre o baseline humano"],
      ["Stressores", `${report.rerenders}`, "re-renders enfrentados"],
      ["Duração", report.duration, "tempo total local"]
    ];
    $("#metrics").innerHTML = metrics.map(([label, value, note]) =>
      `<div class="metric"><span>${label}</span><b>${value}</b><small>${note}</small></div>`
    ).join("");
    $("#detector-report-score").textContent = `${report.detection.score}/100`;
    $("#detector-report-score").dataset.level = report.detection.level;
    const flagged = report.detection.detectors.filter((detector) => detector.status === "risk" || detector.status === "watch");
    $("#detector-report-copy").textContent = flagged.length
      ? `${flagged.length} heurística(s) sinalizaram o comportamento. O resultado é diagnóstico, não uma conclusão de identidade.`
      : "A sessão não acionou heurísticas fortes, mas nenhum detector isolado comprova origem humana.";
    $("#detector-report-grid").innerHTML = report.detection.detectors.map((detector) => `
      <div class="${detector.status}"><i></i><span>${detector.label}</span><b>${detector.detail}</b></div>`).join("");
    saveRunHistory(report);
    renderRunHistory();
    renderDetection();
  }

  function loadRunHistory() {
    try {
      const history = JSON.parse(localStorage.getItem("relay-run-history-v1") || "[]");
      return Array.isArray(history) ? history.slice(-6) : [];
    } catch {
      return [];
    }
  }

  function saveRunHistory(report) {
    const history = loadRunHistory().filter((item) => item.runId !== report.runId);
    history.push({
      runId: report.runId,
      at: new Date().toISOString(),
      score: report.score,
      risk: report.detection.score,
      activeCpm: report.typing.writing.cpm,
      wallCpm: report.typing.writing.wallCpm,
      similarity: report.humanComparison?.similarity ?? null,
      exact: report.precisionExact
    });
    localStorage.setItem("relay-run-history-v1", JSON.stringify(history.slice(-6)));
  }

  function renderRunHistory() {
    const history = loadRunHistory().reverse();
    $("#run-history-list").innerHTML = history.length
      ? history.map((item) => `
          <div class="history-row">
            <b>${item.score}/100</b><span>risco ${item.risk}</span>
            <span>${item.activeCpm} CPM ativo</span><span>${item.wallCpm} CPM total</span>
            <span>${item.similarity ?? "—"}% similar</span>
            <i>${item.exact ? "precisão exata" : "revisar precisão"}</i>
          </div>`).join("")
      : '<p class="history-empty">As próximas execuções aparecerão aqui.</p>';
  }

  function resetStep(number) {
    if (number === 1) {
      els.reasoning.value = "";
      els.reasoningError.textContent = "";
      state.reasoningRerendered = false;
      state.reasoningRerenderScheduled = false;
      updateReasoningCount();
      log("Etapa 1 limpa pelo usuário", "warn");
    }
  }

  function exportReport() {
    const blob = new Blob([JSON.stringify(state.report, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `relay-run-${state.id.toLowerCase()}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
    log("Relatório JSON exportado");
  }

  function bind() {
    installDetection();
    els.runId.textContent = `RUN ${state.id}`;
    state.originalPrecision = els.precision.value.trim().replace(/\s+/g, " ");
    els.precisionBaseline.textContent = `${words(state.originalPrecision)} palavras originais`;
    updatePrecision();
    instrumentTyping(els.baseline, "baseline");
    els.baseline.addEventListener("input", updateBaseline);
    els.saveBaseline.addEventListener("click", saveBaseline);
    $("#clear-baseline").addEventListener("click", clearBaseline);
    loadBaseline();
    updateBaseline();
    rebindReasoning();
    instrumentTyping(els.precision, "precision");
    els.precision.addEventListener("input", updatePrecision);
    els.stress.addEventListener("change", () => log(`Stress mode ${els.stress.checked ? "ativado" : "desativado"}`, "warn"));
    $("#to-step-2").addEventListener("click", () => validateReasoning() && showStep(2));
    $$(".choice").forEach((button) => button.addEventListener("click", () => choose(button.dataset.choice, button)));
    $("#to-step-3").addEventListener("click", () => {
      if (!state.selectedChoice) {
        $("#choice-error").textContent = "Selecione uma opção.";
        return;
      }
      if (state.selectedChoice !== "refresh") log("Decisão de estado incorreta", "fail");
      showStep(3);
    });
    $("#finish-run").addEventListener("click", finish);
    $("#restart-run").addEventListener("click", () => window.location.reload());
    $("#export-run").addEventListener("click", exportReport);
    $("#clear-log").addEventListener("click", () => {
      els.log.innerHTML = "";
      log("Log visual reiniciado");
    });
    $$('[data-reset]').forEach((button) => button.addEventListener("click", () => resetStep(Number(button.dataset.reset))));
    $$('[data-back]').forEach((button) => button.addEventListener("click", () => showStep(Number(button.dataset.back))));
    $$('[data-step-jump]').forEach((button) => button.addEventListener("click", () => !button.disabled && showStep(Number(button.dataset.stepJump))));
    window.setInterval(updateClock, 1000);
    renderDetection();
    log("Benchmark inicializado");
    if (window.location.protocol === "file:") log("Use um servidor local para exportação confiável", "warn");
  }

  bind();
})();
