(() => {
  const $ = (id) => document.getElementById(id);
  const KIND_LABELS = { name: "이름", phone: "전화", rrn: "주민번호", address: "주소" };
  const state = { original: "", masked: "", maskToken: "", schemeId: "", draftToken: "", samples: [], lastAction: null };

  const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const highlight = (s) => escapeHtml(s).replace(/\[(이름|전화|주민번호|주소)[A-Z]+\]/g, "<mark>$&</mark>");

  function announce(message) { $("status").textContent = message; }

  function showError(message, retry) {
    const box = $("error");
    box.textContent = message + " ";
    if (retry) {
      const btn = document.createElement("button");
      btn.textContent = "다시 시도";
      btn.addEventListener("click", () => { hideError(); retry(); });
      box.appendChild(btn);
    }
    box.hidden = false;
  }
  function hideError() { $("error").hidden = true; }

  async function api(path, body) {
    let response;
    try {
      response = await fetch(path, { method: body ? "POST" : "GET", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    } catch (e) {
      throw new Error("네트워크 연결을 확인해 주세요.");
    }
    let data = {};
    try { data = await response.json(); } catch (e) { /* 본문 없음 */ }
    if (!response.ok) throw new Error((data.error && data.error.message) || "일시적인 문제가 발생했습니다. 다시 시도해 주세요.");
    return data;
  }

  function goto(step) {
    for (let i = 1; i <= 5; i++) {
      $("step" + i).hidden = i !== step;
      const li = document.querySelector(`#stepper li[data-step="${i}"]`);
      li.classList.toggle("active", i === step);
      li.classList.toggle("done", i < step);
      if (i === step) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function setBusy(button, busy, label) {
    if (!button.dataset.label) button.dataset.label = button.textContent;
    button.disabled = busy;
    button.textContent = busy ? label : button.dataset.label;
  }

  async function runMask(text) {
    hideError();
    state.lastAction = () => runMask(text);
    const btn = $("maskBtn");
    setBusy(btn, true, "마스킹 중…");
    try {
      const data = await api("/api/mask", { text });
      state.original = text;
      state.masked = data.masked_text;
      state.maskToken = data.mask_token;
      $("original").textContent = text;
      $("masked").innerHTML = highlight(data.masked_text);
      const parts = Object.entries(data.counts).map(([k, v]) => `${KIND_LABELS[k] || k} ${v}`);
      $("counts").textContent = parts.length ? "가린 항목: " + parts.join(", ") : "가릴 개인정보를 찾지 못했습니다. 직접 확인해 주세요.";
      $("warnings").textContent = data.warnings.join(" ");
      $("limits").textContent = data.limitations;
      goto(2);
      announce("마스킹 결과를 확인해 주세요.");
    } catch (e) {
      showError(e.message, () => runMask(text));
    } finally {
      setBusy(btn, false);
    }
  }

  function badges(target, data) {
    const list = [];
    if (data.is_fallback) {
      list.push('<span class="badge fallback">AI 미연결 · 규칙 기반 대체 결과 (AI가 만든 결과가 아님)</span>');
    } else {
      list.push('<span class="badge ai">AI 생성</span>');
      list.push(`<span class="badge">${escapeHtml(data.engine)}</span>`);
    }
    if (data.elapsed_ms) list.push(`<span class="badge">처리 시간 ${(data.elapsed_ms / 1000).toFixed(1)}초</span>`);
    list.push('<span class="badge">시연용 가상 데이터 · 자격 판정 아님</span>');
    target.innerHTML = list.join("");
  }

  // 대기 중에 경과 시간과 현재 단계를 보여 준다.
  function startProgress(message) {
    const el = $("progress");
    const started = Date.now();
    const render = () => { el.textContent = `${message} (${Math.floor((Date.now() - started) / 1000)}초)`; };
    render();
    el.hidden = false;
    const timer = setInterval(render, 500);
    return {
      set(text) { message = text; render(); },
      stop() { clearInterval(timer); el.hidden = true; },
    };
  }

  async function runMatch() {
    hideError();
    const btn = $("confirmBtn");
    setBusy(btn, true, "후보 찾는 중…");
    announce("제도 후보를 찾고 있습니다.");
    const progress = startProgress("Copilot 에이전트가 제도 목록 도구를 조회하며 후보를 찾는 중입니다");
    try {
      const data = await api("/api/match", { masked_text: state.masked, mask_token: state.maskToken });
      badges($("matchBadges"), data);
      const box = $("candidates");
      box.innerHTML = "";
      if (!data.candidates.length) {
        box.innerHTML = '<p class="notice">후보 없음. 메모의 상황에 일치하는 가상 제도를 찾지 못했습니다.</p>';
      }
      data.candidates.forEach((c) => {
        const div = document.createElement("div");
        div.className = "candidate";
        div.innerHTML = `<h3>${escapeHtml(c.scheme_id)} ${escapeHtml(c.name)} <span class="badge">${escapeHtml(c.category)}</span></h3>
          <p><b>일치 근거:</b> ${escapeHtml(c.reason)}</p>
          <p class="evidence">메모 인용: “${escapeHtml(c.evidence)}”</p>`;
        const pick = document.createElement("button");
        pick.className = "primary";
        pick.textContent = "이 제도로 초안 작성";
        pick.addEventListener("click", () => runDraft(c.scheme_id, pick));
        div.appendChild(pick);
        box.appendChild(div);
      });
      goto(3);
      announce("제도 후보가 표시되었습니다.");
    } catch (e) {
      showError(e.message, runMatch);
    } finally {
      progress.stop();
      setBusy(btn, false);
    }
  }

  function parseSse(block) {
    let event = "message";
    const dataLines = [];
    block.split("\n").forEach((line) => {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    });
    return { event, data: dataLines.length ? JSON.parse(dataLines.join("\n")) : {} };
  }

  async function runReview() {
    const box = $("review");
    box.hidden = false;
    box.innerHTML = "<h3>검토 에이전트 점검</h3><p>초안을 메모와 대조해 점검하는 중입니다…</p>";
    try {
      const data = await api("/api/review", { masked_text: state.masked, mask_token: state.maskToken, scheme_id: state.schemeId, draft_text: $("draft").value });
      const label = data.is_fallback ? "규칙 기반 점검 (AI 미연결)" : "AI 점검 · " + escapeHtml(data.engine);
      const body = data.issues.length
        ? "<ul>" + data.issues.map((i) => `<li>${escapeHtml(i.text)}${i.quote ? ` <span class="quote">“${escapeHtml(i.quote)}”</span>` : ""}</li>`).join("") + "</ul>"
        : "<p>점검에서 문제를 찾지 못했습니다. 그래도 승인 전에 담당자가 직접 확인해 주세요.</p>";
      box.innerHTML = `<h3>검토 에이전트 점검 <span class="badge ${data.is_fallback ? "fallback" : "ai"}">${label}</span></h3>${body}`;
    } catch (e) {
      box.innerHTML = "<h3>검토 에이전트 점검</h3><p>점검을 건너뛰었습니다. 담당자가 직접 확인해 주세요.</p>";
    }
  }

  async function runDraft(schemeId, button) {
    hideError();
    setBusy(button, true, "초안 작성 중…");
    announce("신청서 초안을 작성하고 있습니다.");
    const draft = $("draft");
    draft.value = "";
    draft.readOnly = true;
    $("review").hidden = true;
    $("draftBadges").innerHTML = "";
    $("approveBtn").disabled = true;
    state.schemeId = schemeId;
    state.draftToken = "";
    const progress = startProgress("Copilot 에이전트에 마스킹된 메모를 전달해 초안을 작성하는 중입니다");
    goto(4);
    try {
      const response = await fetch("/api/draft/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ masked_text: state.masked, mask_token: state.maskToken, scheme_id: schemeId }),
      });
      if (!response.ok) {
        let message = "일시적인 문제가 발생했습니다. 다시 시도해 주세요.";
        try { message = (await response.json()).error.message; } catch (e) { /* 본문 없음 */ }
        throw new Error(message);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finished = false;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let index;
        while ((index = buffer.indexOf("\n\n")) >= 0) {
          const { event, data } = parseSse(buffer.slice(0, index));
          buffer = buffer.slice(index + 2);
          if (event === "status") progress.set(data.message);
          else if (event === "delta") { draft.value += data.text; draft.scrollTop = draft.scrollHeight; progress.set("초안을 작성하는 중입니다"); }
          else if (event === "reset") draft.value = "";
          else if (event === "done") {
            finished = true;
            draft.value = data.draft;
            state.draftToken = data.draft_token;
            badges($("draftBadges"), data);
          }
        }
      }
      if (!finished) throw new Error("초안 작성이 중단되었습니다.");
      draft.readOnly = false;
      $("approveBtn").disabled = false;
      announce("초안이 표시되었습니다. 검토 후 승인해 주세요.");
      runReview();
    } catch (e) {
      goto(3);
      showError(e.message, () => runDraft(schemeId, button));
    } finally {
      progress.stop();
      draft.readOnly = false;
      setBusy(button, false);
    }
  }

  async function runApprove() {
    hideError();
    const btn = $("approveBtn");
    setBusy(btn, true, "승인 중…");
    try {
      const data = await api("/api/approve", { draft_text: $("draft").value, scheme_id: state.schemeId, draft_token: state.draftToken });
      $("approvedMsg").textContent = `승인되었습니다(데모). 승인 시각: ${data.approved_at}`;
      goto(5);
      announce("승인되었습니다.");
    } catch (e) {
      showError(e.message, runApprove);
    } finally {
      setBusy(btn, false);
    }
  }

  function restart() {
    hideError();
    Object.assign(state, { original: "", masked: "", maskToken: "", schemeId: "", draftToken: "" });
    $("memo").value = "";
    goto(1);
  }

  async function init() {
    try {
      const data = await api("/api/samples");
      state.samples = data.memos;
      data.memos.slice(0, 3).forEach((m) => {
        const b = document.createElement("button");
        b.textContent = `▶ ${m.title}`;
        b.addEventListener("click", () => { $("memo").value = m.text; runMask(m.text); });
        $("demoButtons").appendChild(b);
      });
      data.memos.forEach((m) => {
        const o = document.createElement("option");
        o.value = m.id;
        o.textContent = `${m.id}. ${m.title}`;
        $("sampleSelect").appendChild(o);
      });
    } catch (e) {
      showError("샘플을 불러오지 못했습니다. 메모를 직접 입력해 주세요.");
    }
  }

  $("sampleSelect").addEventListener("change", (e) => {
    const sample = state.samples.find((m) => String(m.id) === e.target.value);
    if (sample) $("memo").value = sample.text;
  });
  $("maskBtn").addEventListener("click", () => {
    const text = $("memo").value.trim();
    if (!text) { showError("메모를 입력하거나 샘플을 선택해 주세요."); return; }
    runMask(text);
  });
  $("backBtn").addEventListener("click", () => { hideError(); goto(1); });
  $("confirmBtn").addEventListener("click", runMatch);
  $("restart3").addEventListener("click", restart);
  $("backToCandidates").addEventListener("click", () => { hideError(); goto(3); });
  $("approveBtn").addEventListener("click", runApprove);
  $("restart5").addEventListener("click", restart);
  init();
})();
