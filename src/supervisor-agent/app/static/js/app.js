(function() {
  // Main Application Logic
  // External dependencies check
  if (typeof marked !== 'undefined') {
    marked.setOptions({
      gfm: true,
      breaks: true,
      pedantic: false,
      sanitize: false,
      smartLists: true,
      smartypants: false
    });
  }
  if (typeof mermaid !== 'undefined') {
    mermaid.initialize({ startOnLoad: false, theme: 'dark' });
  }

  const endpoint = '/a2a/supervisor';
  const chatEl = document.getElementById('chat');
  const statusTextEl = document.getElementById('status-text');
  const statusTaskEl = document.getElementById('status-task');
  const statusIndicatorEl = document.getElementById('status-indicator');
  const statusProgressEl = document.getElementById('status-progress');
  const promptEl = document.getElementById('prompt');

  const sendBtn = document.getElementById('sendBtn');
  const clearBtn = document.getElementById('clearBtn');
  const stopBtn = document.getElementById('stopBtn');
  const micBtn = document.getElementById('micBtn');

  let streaming = false;
  let abortController = null;
  const SESSION_STORAGE_KEY = 'smart_supervisor_session_id';
  const MAX_MESSAGES = 50;

  /**
   * Rationale (Why): UUID format is required by backend Pydantic models.
   */
  function generateUUID() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }

  function getOrCreateSessionId() {
    try {
      let existing = localStorage.getItem(SESSION_STORAGE_KEY);
      const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[4][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
      if (existing && uuidRegex.test(existing)) return existing;
    } catch (e) {}
    
    const created = generateUUID();
    try {
      localStorage.setItem(SESSION_STORAGE_KEY, created);
    } catch (e) {}
    return created;
  }

  let session_id = getOrCreateSessionId();
  let a2uiEnabled = false; 
  let activeStreamTaskId = '';
  let statusTicking = false;
  let statusTargetProgress = 0;
  let statusDisplayProgress = 0;
  let statusLastUpdateAt = 0;

  function autoResizePrompt() {
    if (!promptEl) return;
    promptEl.style.height = 'auto';
    const nextHeight = Math.max(56, Math.min(180, promptEl.scrollHeight));
    promptEl.style.height = `${nextHeight}px`;
  }

  function updateStatusVisual(type) {
    if (!statusIndicatorEl || !statusProgressEl) return;
    statusIndicatorEl.className = 'status-dot';
    statusProgressEl.classList.remove('active');

    if (type === 'streaming') {
      statusIndicatorEl.classList.add('active', 'streaming');
      statusProgressEl.classList.add('active');
    } else if (type === 'pending') {
      statusIndicatorEl.classList.add('active', 'pending');
      statusProgressEl.classList.add('active');
    } else if (type === 'complete') {
      statusIndicatorEl.classList.add('active', 'complete');
    } else if (type === 'error') {
      statusIndicatorEl.classList.add('active', 'error');
    }
  }

  function animateStatusProgress() {
    if (!statusTicking || !statusProgressEl) return;
    const now = Date.now();
    if (now - statusLastUpdateAt > 1500 && statusTargetProgress < 94) {
      statusTargetProgress = Math.min(94, statusTargetProgress + 0.7);
    }
    if (statusDisplayProgress < statusTargetProgress) {
      statusDisplayProgress = Math.min(statusTargetProgress, statusDisplayProgress + 0.9);
    } else if (statusDisplayProgress > statusTargetProgress) {
      statusDisplayProgress = Math.max(statusTargetProgress, statusDisplayProgress - 1.2);
    }
    statusProgressEl.style.width = `${Math.max(0, Math.min(100, statusDisplayProgress)).toFixed(1)}%`;
    requestAnimationFrame(animateStatusProgress);
  }

  function beginStatusTicker() {
    if (statusTicking) return;
    statusTicking = true;
    statusLastUpdateAt = Date.now();
    requestAnimationFrame(animateStatusProgress);
  }

  function stopStatusTicker() {
    statusTicking = false;
  }

  function setStatus(text, type = 'ready', options = {}) {
    if (statusTextEl) statusTextEl.textContent = text;
    if (statusTaskEl) statusTaskEl.textContent = options.activity ? `· ${options.activity}` : '';

    if (type === 'streaming') {
      updateStatusVisual('streaming');
      statusLastUpdateAt = Date.now();
      if (typeof options.progress === 'number') {
        statusTargetProgress = Math.max(statusTargetProgress, Math.min(99, options.progress));
      } else if (statusTargetProgress < 14) {
        statusTargetProgress = 14;
      }
      beginStatusTicker();
      return;
    }

    if (type === 'pending') {
      stopStatusTicker();
      updateStatusVisual('pending');
      const pendingProgress = typeof options.progress === 'number'
        ? Math.min(99, Math.max(0, options.progress))
        : Math.max(82, statusDisplayProgress);
      statusTargetProgress = pendingProgress;
      statusDisplayProgress = pendingProgress;
      if (statusProgressEl) statusProgressEl.style.width = `${pendingProgress}%`;
      return;
    }

    stopStatusTicker();
    updateStatusVisual(type);

    if (type === 'complete') {
      statusTargetProgress = 100;
      statusDisplayProgress = 100;
      if (statusProgressEl) {
        statusProgressEl.style.width = '100%';
        setTimeout(() => {
          statusProgressEl.classList.remove('active');
        }, 1200);
      }
    } else if (type === 'error') {
      statusTargetProgress = Math.max(statusTargetProgress, 100);
      statusDisplayProgress = 100;
      if (statusProgressEl) statusProgressEl.style.width = '100%';
    } else {
      statusTargetProgress = 0;
      statusDisplayProgress = 0;
      if (statusProgressEl) statusProgressEl.style.width = '0%';
    }
  }

  function addMessage(role, content) {
    if (!chatEl) return null;
    const msg = document.createElement('div');
    msg.className = `msg ${role}`;
    msg.innerHTML = `
      <div class="avatar">${role === 'user' ? '👤' : '🤖'}</div>
      <div class="bubble">${content}</div>
    `;
    chatEl.appendChild(msg);
    chatEl.scrollTop = chatEl.scrollHeight;
    pruneMessages();
    return msg.querySelector('.bubble');
  }

  /**
   * Rationale (Why): Prevent DOM bloat and memory leaks in long-running sessions.
   */
  function pruneMessages() {
    if (!chatEl) return;
    const messages = chatEl.querySelectorAll('.msg');
    if (messages.length > MAX_MESSAGES) {
      const toRemove = messages.length - MAX_MESSAGES;
      for (let i = 0; i < toRemove; i++) {
        chatEl.removeChild(messages[i]);
      }
      console.log(`Pruned ${toRemove} messages to keep DOM lean.`);
    }
  }

  function createAiResponseShell() {
    const bubble = addMessage('ai', '');
    if (!bubble) return {};
    bubble.innerHTML = `
      <div class="supervisor-panel" style="display:none;">
        <div class="supervisor-head">
          <span class="supervisor-title">Supervisor Progress</span>
          <button class="supervisor-toggle" type="button">접기</button>
        </div>
        <div class="supervisor-progress-bar">
          <div class="supervisor-progress-fill" style="width: 0%"></div>
        </div>
        <div class="supervisor-current-stage"></div>
        <div class="supervisor-stream"></div>
      </div>
      <div class="review-panel" style="display:none;">
        <div class="review-title">HITL 승인 대기</div>
        <div class="review-desc"></div>
        <div class="review-progress">
          <div class="review-progress-label">
            <div class="review-progress-spinner"></div>
            <span class="review-progress-text">처리 중...</span>
          </div>
          <div class="review-progress-bar">
            <div class="review-progress-fill"></div>
          </div>
        </div>
        <div class="review-actions">
          <button class="btn approve" type="button">승인(APPROVE)</button>
          <button class="btn cancel" type="button">취소(CANCEL)</button>
        </div>
      </div>
      <div class="assistant-a2ui"></div>
      <div class="assistant-answer"></div>
    `;

    const panel = bubble.querySelector('.supervisor-panel');
    const stream = bubble.querySelector('.supervisor-stream');
    const toggle = bubble.querySelector('.supervisor-toggle');
    const answer = bubble.querySelector('.assistant-answer');
    const a2ui = bubble.querySelector('.assistant-a2ui');
    const progressFill = bubble.querySelector('.supervisor-progress-fill');
    const currentStage = bubble.querySelector('.supervisor-current-stage');
    const reviewPanel = bubble.querySelector('.review-panel');
    const reviewDesc = bubble.querySelector('.review-desc');
    const reviewProgress = bubble.querySelector('.review-progress');
    const reviewProgressText = bubble.querySelector('.review-progress-text');
    const reviewProgressFill = bubble.querySelector('.review-progress-fill');
    const approveBtn = bubble.querySelector('.btn.approve');
    const cancelBtn = bubble.querySelector('.btn.cancel');

    if (toggle) {
      toggle.addEventListener('click', () => {
        panel.classList.toggle('collapsed');
        toggle.textContent = panel.classList.contains('collapsed') ? '펼치기' : '접기';
      });
    }

    return {
      bubble, panel, stream, toggle, answer, a2ui, progressFill, currentStage,
      reviewPanel, reviewDesc, reviewProgress, reviewProgressText, reviewProgressFill,
      approveBtn, cancelBtn
    };
  }

  function renderAssistantMarkdown(target, text) {
    if (!target || typeof marked === 'undefined') return;
    let protectedText = text;
    const mathBlocks = [];
    const mathInlines = [];

    protectedText = protectedText.replace(/\\\[([\s\S]*?)\\\]/g, (match, content) => {
      mathBlocks.push(content);
      return `MATHBLOCK${mathBlocks.length - 1}MATHBLOCK`;
    });
    protectedText = protectedText.replace(/\$\$([\s\S]*?)\$\$/g, (match, content) => {
      mathBlocks.push(content);
      return `MATHBLOCK${mathBlocks.length - 1}MATHBLOCK`;
    });

    protectedText = protectedText.replace(/\\\((.*?)\\\)/g, (match, content) => {
      mathInlines.push(content);
      return `MATHINLINE${mathInlines.length - 1}MATHINLINE`;
    });
    protectedText = protectedText.replace(/\$([^\$\n]+?)\$/g, (match, content) => {
      mathInlines.push(content);
      return `MATHINLINE${mathInlines.length - 1}MATHINLINE`;
    });

    let parsedHtml = marked.parse(protectedText);

    parsedHtml = parsedHtml.replace(/MATHBLOCK(\d+)MATHBLOCK/g, (match, index) => {
      return `\\[${mathBlocks[index]}\\]`;
    });
    parsedHtml = parsedHtml.replace(/MATHINLINE(\d+)MATHINLINE/g, (match, index) => {
      return `\\(${mathInlines[index]}\\)`;
    });

    target.innerHTML = parsedHtml;
  }

  function parseSseFrames(buffer) {
    const normalized = buffer.replace(/\r\n/g, '\n');
    const chunks = normalized.split('\n\n');
    return {
      frames: chunks.slice(0, -1),
      rest: chunks[chunks.length - 1] || ''
    };
  }

  function parseFrame(frame) {
    const lines = frame.split('\n');
    let event = 'message';
    const dataLines = [];
    for (const line of lines) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    }
    return { event, data: dataLines.join('\n') };
  }

  function normalizeNestedSse(event, data) {
    if (event !== 'message' || !data) {
      return { event, data };
    }
    if (data.startsWith('event:') || data.includes('\ndata:')) {
      const nested = parseFrame(data);
      if (nested.data) return nested;
    }
    if (data === '[DONE]') return { event: 'done', data: '{"reason":"completed"}' };
    return { event: 'chunk', data };
  }

  function renderMath(element) {
    if (!element || !window.renderMathInElement) return;
    try {
      window.renderMathInElement(element, {
        delimiters: [
          {left: "$$", right: "$$", display: true},
          {left: "\\[", right: "\\]", display: true},
          {left: "$", right: "$", display: false},
          {left: "\\(", right: "\\)", display: false}
        ],
        throwOnError: false
      });
    } catch (e) { console.error('KaTeX render error:', e); }
  }

  async function renderMermaid(element) {
    if (!element || typeof mermaid === 'undefined') return;
    const mermaidBlocks = element.querySelectorAll('code.language-mermaid');
    for (let i = 0; i < mermaidBlocks.length; i++) {
      const code = mermaidBlocks[i].textContent;
      try {
        const id = `m-${Date.now()}-${i}`;
        const { svg } = await mermaid.render(id, code);
        const wrap = document.createElement('div');
        wrap.className = 'mermaid-diagram';
        wrap.innerHTML = svg;
        mermaidBlocks[i].parentElement.replaceWith(wrap);
      } catch (e) { console.warn('Mermaid render error:', e); }
    }
  }

  async function enhanceBubble(bubble) {
    renderMath(bubble);
    await renderMermaid(bubble);
  }

  function parseSupervisorProgress(line) {
    const pattern = /^\[supervisor\]\s+\[([^\]]+)\]\s+\[(\d+)%\]\s+(.+?)(?:\s+\{(.+)\})?$/;
    const match = line.match(pattern);
    if (!match) return null;
    const [, stage, progress, message, metadataStr] = match;
    const metadata = {};
    if (metadataStr) {
      metadataStr.split(',').forEach(entry => {
        const pair = entry.trim();
        if (!pair) return;
        const separatorIndex = pair.indexOf('=');
        if (separatorIndex < 0) return;
        const key = pair.slice(0, separatorIndex).trim();
        const value = pair.slice(separatorIndex + 1).trim();
        if (key) metadata[key] = value;
      });
    }
    return { stage, progress: parseInt(progress, 10), message, metadata };
  }

  function getStageLabel(stage) {
    const labels = {
      initializing: '🚀 초기화', analyzing: '🔍 분석', planning: '📋 계획',
      hitl: '🛡️ HITL 평가', hitl_waiting: '🧑 검토 대기', routing: '🎯 라우팅',
      invoking: '⚡ 실행', composing: '✨ 합성', completed: '✅ 완료', error: '❌ 오류'
    };
    return labels[stage] || stage;
  }

  function progressAgentDetail(progress) {
    if (!progress || !progress.metadata) return '';
    const md = progress.metadata;
    const parts = [];
    if (md.agentKey) parts.push(md.agentKey);
    if (md.method) parts.push(md.method);
    if (md.status) parts.push(md.status);
    if (parts.length === 0 && md.nodeType) parts.push(md.nodeType);
    return parts.join(' · ');
  }

  function stageLine(progress) {
    const detail = progressAgentDetail(progress);
    if (!detail) return `${getStageLabel(progress.stage)} - ${progress.message}`;
    return `${getStageLabel(progress.stage)} - ${progress.message} (${detail})`;
  }

  function isHitlWaitingProgress(progress) {
    if (!progress) return false;
    const stage = String(progress.stage || '').toLowerCase();
    const reviewStatus = String(progress.metadata?.reviewStatus || '').toUpperCase();
    return stage === 'hitl_waiting' || reviewStatus === 'WAITING_REVIEW';
  }

  function handleHitlWaitingProgress(ai, progress) {
    if (!isHitlWaitingProgress(progress)) return false;
    showHitlReviewPanel(ai, progress.metadata?.reason || progress.message, progress.metadata?.taskId || '');
    setStatus('HITL 승인 대기 중', 'pending', {
      progress: Math.max(Number(progress.progress || 0), 82),
      activity: '사용자 결정 대기'
    });
    return true;
  }

  function finalizeHitlWaitingUi(ai, message, opts = {}) {
    const activity = opts.activity || '사용자 결정 대기';
    if (ai.progressFill) ai.progressFill.style.width = '100%';
    if (ai.currentStage) ai.currentStage.textContent = `🧑 검토 대기 - ${message}`;
    setStatus('HITL 승인 대기 중', 'pending', { progress: 100, activity });
  }

  function applySupervisorProgress(ai, progress, opts = {}) {
    if (!progress) return 0;
    const previous = Number(opts.lastProgress || 0);
    const pct = Math.max(previous, Math.min(100, Number(progress.progress || 0)));
    if (ai.progressFill) {
      ai.progressFill.style.width = `${pct}%`;
      if (pct >= 100 || progress.stage === 'completed') {
        ai.progressFill.classList.add('completed');
      }
    }
    if (ai.currentStage) ai.currentStage.textContent = stageLine(progress);

    const detail = progressAgentDetail(progress);
    const waitingReview = isHitlWaitingProgress(progress);
    setStatus(
      detail ? `${getStageLabel(progress.stage)} (${detail}, ${pct}%)` : `${getStageLabel(progress.stage)} (${pct}%)`,
      waitingReview ? 'pending' : 'streaming',
      {
        progress: waitingReview ? Math.max(pct, 82) : pct,
        activity: waitingReview ? '사용자 결정 대기' : progress.message
      }
    );
    return pct;
  }

  async function rpcCall(method, params) {
    const mergedParams = { ...(params || {}) };
    if (!('session_id' in mergedParams) && session_id) mergedParams.session_id = session_id;
    const body = { jsonrpc: '2.0', id: `ui-rpc-${Date.now()}`, method, params: mergedParams };
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  }

  async function cancelActiveStreamTask(reason = 'stopped_from_ui') {
    if (!activeStreamTaskId) return false;
    const response = await rpcCall('tasks/cancel', { id: activeStreamTaskId, reason });
    if (response?.error) throw new Error(response.error.message || 'Task cancel failed');
    return true;
  }

  async function findLatestWaitingTaskId() {
    const listRes = await rpcCall('tasks/list', { limit: 30 });
    const tasks = listRes?.result?.tasks || [];
    return tasks.find(t => t.status === 'WAITING_REVIEW')?.id || '';
  }

  async function getTask(taskId) {
    const response = await rpcCall('tasks/get', { id: taskId });
    return response?.result || null;
  }

  async function waitForTaskTerminal(taskId, opts = {}) {
    const timeoutMs = Number(opts.timeoutMs || 120000);
    const intervalMs = Number(opts.intervalMs || 1000);
    const startedAt = Date.now();
    while (Date.now() - startedAt < timeoutMs) {
      const task = await getTask(taskId);
      const status = String(task?.status || '').toUpperCase();
      if (status === 'COMPLETED' || status === 'FAILED' || status === 'CANCELED') return task;
      await sleep(intervalMs);
    }
    throw new Error('승인 후 task 완료 대기 시간이 초과되었습니다.');
  }

  async function renderTaskOutcome(ai, task, decision) {
    if (task?.response) {
      const parsed = splitSupervisorPayload(String(task.response));
      if (parsed.logs.length > 0) {
        if (ai.panel) {
          ai.panel.style.display = 'block';
          ai.panel.classList.remove('collapsed');
        }
        if (ai.toggle) ai.toggle.textContent = '접기';
        await replaySupervisorLogs(ai, parsed.logs);
      }
      if (parsed.answer.trim().length > 0) {
        renderAssistantMarkdown(ai.answer, parsed.answer.trim());
        await enhanceBubble(ai.answer);
      }
      const parsedA2ui = tryParseA2ui(parsed.a2ui);
      if (parsedA2ui) renderA2ui(ai, parsedA2ui);
    } else if (decision === 'CANCEL') {
      renderAssistantMarkdown(ai.answer, '요청이 검토 단계에서 취소되었습니다.');
    }
  }

  async function streamReviewDecision(ai, taskId, decision) {
    try {
      const decideRes = await rpcCall('tasks/review/decide', {
        task_id: taskId, decision, session_id, comment: ''
      });

      if (decideRes.result && decideRes.result.stream_endpoint) {
          a2uiEnabled = !!decideRes.result.a2ui_enabled;
          activeStreamTaskId = taskId;
          const streamEndpoint = decideRes.result.stream_endpoint;
          const cursor = decideRes.result.initial_cursor;
          
          const payload = {
              jsonrpc: '2.0', id: `ui-rpc-${Date.now()}`,
              method: 'tasks/events',
              params: { task_id: taskId, session_id, cursor }
          };
          
          const res = await fetch(streamEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
            body: JSON.stringify(payload)
          });
          
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          let fullAnswer = '';
          let reasoningText = '';
          let reasoningDone = false;

          if (ai.panel) ai.panel.style.display = 'block';

          while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const frames = parseSseFrames(buffer);
            buffer = frames.remainder || frames.rest || '';

            for (const frame of frames.completeFrames || frames.frames) {
              const parsedOuter = parseFrame(frame);
              if (!parsedOuter) continue;
              
              const { event, data } = normalizeNestedSse(parsedOuter.event, parsedOuter.data);
              let parsed = data;
              if (typeof parsed === 'string') {
                try { parsed = JSON.parse(parsed); } catch {}
              }

              if (event === 'done' || event === 'error') {
                  finalizeHitlWaitingUi(ai, "완료");
                  if (fullAnswer) await enhanceBubble(ai.bubble);
                  setStatus(event === 'done' ? '처리 완료' : '에러 발생', event === 'done' ? 'complete' : 'error');
                  if (ai.panel) ai.panel.classList.add('collapsed');
                  if (ai.toggle) ai.toggle.textContent = '펼치기';
                  activeStreamTaskId = '';
                  return;
              }
              
              if (event === 'progress') {
                  const stage = parsed.stage || '';
                  const msg = parsed.message || '';
                  if (ai.currentStage) ai.currentStage.textContent = `⚙️ ${stage} - ${msg}`;
                  setStatus(`${stage}...`, 'streaming', { progress: 40 });
              }
              
              if (event === 'reasoning') {
                  const token = parsed.token || '';
                  reasoningText += token;
                  if (ai.panel) ai.panel.style.display = 'block'; 
                  if (ai.stream) {
                    ai.stream.textContent = reasoningText;
                    ai.stream.scrollTop = ai.stream.scrollHeight;
                  }
                  if (ai.currentStage) ai.currentStage.textContent = '🧠 LLM Reasoning...';
                  setStatus('추론 중...', 'streaming', { progress: 50 });
              }
              
              if (event === 'a2ui') {
                  if (ai.answer) ai.answer.innerHTML = '';
                  renderA2ui(ai, parsed);
                  setStatus('UI 렌더링 완료', 'streaming', { progress: 80 });
              }

              if (event === 'chunk') {
                  const agent = parsed.agent || '';
                  const answer = parsed.data?.answer || parsed.answer || '';
                  
                  if (answer && typeof answer === 'string') {
                      if (agent === 'supervisor') {
                          if (!reasoningDone && reasoningText) {
                              reasoningDone = true;
                              if (ai.currentStage) ai.currentStage.textContent = '✍️ 최종 답변 작성 중...';
                              setTimeout(() => {
                                  if (ai.panel && !ai.panel.classList.contains('collapsed')) {
                                      ai.panel.classList.add('collapsed');
                                      if (ai.toggle) ai.toggle.textContent = '펼치기';
                                  }
                              }, 2000); 
                          }
                          fullAnswer += answer;
                          renderAssistantMarkdown(ai.answer, fullAnswer);
                      } else {
                          if (ai.panel) ai.panel.style.display = 'block'; 
                          if (!reasoningText.includes(`[${agent}]`)) reasoningText += `\n[${agent}] `;
                          reasoningText += answer;
                          if (ai.stream) {
                            ai.stream.textContent = reasoningText;
                            ai.stream.scrollTop = ai.stream.scrollHeight;
                          }
                          setStatus(`${agent} 처리 중...`, 'streaming', { progress: 60 });
                      }
                      setStatus('응답 수신 중...', 'streaming', { progress: 70 });
                      if (chatEl) chatEl.scrollTop = chatEl.scrollHeight;
                  }
              }
            }
          }
      }
    } catch (err) {
      console.error(err);
      setStatus('에러 발생', 'error');
    }
  }

  async function handleReviewDecision(ai, taskId, decision) {
    if (ai.approveBtn) ai.approveBtn.disabled = true;
    if (ai.cancelBtn) ai.cancelBtn.disabled = true;
    if (ai.reviewProgress) ai.reviewProgress.classList.add('active');
    if (ai.reviewProgressText) ai.reviewProgressText.textContent = decision === 'APPROVE' ? '승인 처리 중...' : '취소 처리 중...';
    if (ai.reviewProgressFill) ai.reviewProgressFill.style.width = '30%';

    if (decision === 'APPROVE') setStatus('승인 후 실행 시작...', 'streaming');

    try {
      if (decision === 'APPROVE') {
        await streamReviewDecision(ai, taskId, decision);
        setTimeout(() => {
          if (ai.reviewProgress) ai.reviewProgress.classList.remove('active');
          if (ai.approveBtn) ai.approveBtn.style.display = 'none';
          if (ai.cancelBtn) ai.cancelBtn.style.display = 'none';
        }, 1000);
        return;
      }

      if (ai.reviewProgressFill) ai.reviewProgressFill.style.width = '50%';
      const decideRes = await rpcCall('tasks/review/decide', {
        task_id: taskId, decision, session_id,
        comment: decision === 'APPROVE' ? 'approved_from_ui' : 'canceled_from_ui',
        client_request_id: generateUUID()
      });

      a2uiEnabled = !!decideRes.result?.a2ui_enabled;
      if (ai.reviewProgressFill) ai.reviewProgressFill.style.width = '70%';

      if (decideRes?.error) {
        if (ai.reviewProgress) ai.reviewProgress.classList.remove('active');
        if (ai.reviewDesc) ai.reviewDesc.textContent = `결정 실패: ${decideRes.error.message}`;
        if (ai.approveBtn) ai.approveBtn.disabled = false;
        if (ai.cancelBtn) ai.cancelBtn.disabled = false;
        return;
      }

      const task = decideRes?.result?.task;
      let resolvedTask = task;
      let taskStatus = String(task?.status || '').toUpperCase();
      if (ai.reviewProgressFill) ai.reviewProgressFill.style.width = '90%';
      if (ai.reviewProgressText) ai.reviewProgressText.textContent = '결과 처리 중...';

      if (decision === 'APPROVE' && taskStatus !== 'COMPLETED') {
        if (ai.reviewProgressText) ai.reviewProgressText.textContent = '승인 후 실행 대기 중...';
        if (ai.reviewDesc) ai.reviewDesc.textContent = '승인은 완료되었습니다. 후속 실행 상태를 확인 중입니다.';
        resolvedTask = await waitForTaskTerminal(taskId);
        taskStatus = String(resolvedTask?.status || '').toUpperCase();
      }

      if (ai.reviewDesc) ai.reviewDesc.textContent = `결정 완료: ${decideRes.result?.review?.status || decision}`;
      await renderTaskOutcome(ai, resolvedTask, decision);
      if (ai.reviewProgressFill) ai.reviewProgressFill.style.width = '100%';
      if (ai.reviewProgressText) ai.reviewProgressText.textContent = '완료';

      if (decision === 'APPROVE' && taskStatus === 'COMPLETED') {
        if (ai.progressFill) {
          ai.progressFill.style.width = '100%';
          ai.progressFill.classList.add('completed');
        }
        if (ai.currentStage) ai.currentStage.textContent = '✅ 완료 - 승인 후 실행이 정상 완료되었습니다.';
        setTimeout(() => setStatus('완료', 'complete', { progress: 100, activity: '승인 후 실행 완료' }), 100);
      } else if (decision === 'CANCEL' && taskStatus === 'CANCELED') {
        if (ai.currentStage) ai.currentStage.textContent = '🛑 검토 취소 - 요청이 검토 단계에서 종료되었습니다.';
        setStatus('검토 취소', 'ready', { progress: 0, activity: '사용자 취소' });
      }

      setTimeout(() => {
        if (ai.reviewProgress) ai.reviewProgress.classList.remove('active');
        if (ai.approveBtn) ai.approveBtn.style.display = 'none';
        if (ai.cancelBtn) ai.cancelBtn.style.display = 'none';
      }, 1000);

    } catch (e) {
      if (ai.reviewProgress) ai.reviewProgress.classList.remove('active');
      if (ai.reviewDesc) ai.reviewDesc.textContent = `결정 처리 실패: ${e.message}`;
      if (ai.approveBtn) ai.approveBtn.disabled = false;
      if (ai.cancelBtn) ai.cancelBtn.disabled = false;
    }
  }

  function splitSupervisorPayload(payload) {
    const lines = String(payload || '').split('\n');
    const logs = [], answerLines = [], a2uiPayloads = [];
    for (const raw of lines) {
      const line = raw.trimEnd();
      if (line.trim().startsWith('[supervisor]')) logs.push(line.trim());
      else if (line.trim().startsWith('[[A2UI]]')) a2uiPayloads.push(line.trim().slice(8));
      else answerLines.push(raw);
    }
    return { logs, answer: answerLines.join('\n'), a2ui: a2uiPayloads.pop() || null };
  }

  function tryParseA2ui(raw) {
    return window.A2uiRenderer?.tryParseProtocolPayload(raw) || null;
  }

  function renderA2ui(ai, envelope) {
    return window.A2uiRenderer?.render(ai, envelope, {
      onUserAction(payload) { if (payload) void send(null, payload); }
    });
  }

  function buildA2uiClientCapabilities() {
    return { supportedCatalogIds: [window.A2uiRenderer?.STANDARD_CATALOG_ID || 'https://a2ui.org/specification/v0_8/standard_catalog_definition.json'] };
  }

  function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

  async function replaySupervisorLogs(ai, logs) {
    if (ai.stream) ai.stream.textContent = '';
    if (ai.progressFill) ai.progressFill.classList.remove('completed');
    let lastProgress = 0;
    for (const line of logs) {
      if (ai.stream) {
        ai.stream.textContent += (ai.stream.textContent ? '\n' : '') + line;
        ai.stream.scrollTop = ai.stream.scrollHeight;
      }
      const progress = parseSupervisorProgress(line);
      if (progress) lastProgress = applySupervisorProgress(ai, progress, { lastProgress });
      await sleep(90);
    }
  }

  function bindReviewTask(ai, taskId, reason) {
    if (ai.reviewDesc) ai.reviewDesc.textContent = `taskId=${taskId}${reason ? `, reason=${reason}` : ''}`;
    if (ai.approveBtn) {
      ai.approveBtn.style.display = '';
      ai.approveBtn.disabled = false;
      ai.approveBtn.onclick = () => handleReviewDecision(ai, taskId, 'APPROVE');
    }
    if (ai.cancelBtn) {
      ai.cancelBtn.style.display = '';
      ai.cancelBtn.disabled = false;
      ai.cancelBtn.onclick = () => handleReviewDecision(ai, taskId, 'CANCEL');
    }
  }

  function showHitlReviewPanel(ai, reason, preferredTaskId = '') {
    if (ai.reviewPanel) ai.reviewPanel.style.display = 'block';
    if (preferredTaskId) { bindReviewTask(ai, preferredTaskId, reason); return; }
    if (ai.reviewDesc) ai.reviewDesc.textContent = '리뷰 대기 task를 조회 중입니다...';
    if (ai.approveBtn) { ai.approveBtn.disabled = true; ai.approveBtn.style.display = ''; }
    if (ai.cancelBtn) { ai.cancelBtn.disabled = true; ai.cancelBtn.style.display = ''; }
    void (async () => {
      try {
        const taskId = await findLatestWaitingTaskId();
        if (!taskId) {
          if (ai.reviewDesc) ai.reviewDesc.textContent = '리뷰 대기 task를 찾지 못했습니다. 잠시 후 다시 시도해주세요.';
          return;
        }
        bindReviewTask(ai, taskId, reason);
      } catch (e) { if (ai.reviewDesc) ai.reviewDesc.textContent = `리뷰 대기 task 조회 실패: ${e.message}`; }
    })();
  }

  async function startSseSubscription(ai, taskId) {
    activeStreamTaskId = taskId;
    const streamEndpoint = '/a2a/supervisor/stream';
    setStatus('응답 생성 중...', 'streaming', { progress: 20 });
    
    const ssePayload = { 
      jsonrpc: '2.0', 
      id: generateUUID(), 
      method: 'tasks/events', 
      params: { task_id: taskId, session_id, cursor: '0' } 
    };

    try {
      const sseRes = await fetch(streamEndpoint, { 
        method: 'POST', 
        headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' }, 
        body: JSON.stringify(ssePayload) 
      });
      if (!sseRes.ok) throw new Error(`SSE HTTP ${sseRes.status}`);
      
      const reader = sseRes.body.getReader();
      const decoder = new TextDecoder();
      let sseBuf = '', fullAnswer = '', reasoningText = '', reasoningDone = false;
      
      while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          sseBuf += decoder.decode(value, { stream: true });
          const frames = parseSseFrames(sseBuf);
          sseBuf = frames.remainder || frames.rest || '';
          
          for (const frame of frames.completeFrames || frames.frames) {
              const parsedOuter = parseFrame(frame);
              if (!parsedOuter) continue;
              
              const { event, data } = normalizeNestedSse(parsedOuter.event, parsedOuter.data);
              let parsed = data;
              if (typeof parsed === 'string') { try { parsed = JSON.parse(parsed); } catch {} }
              
              if (event === 'done' || event === 'error') {
                  let a2uiRendered = false;
                  if (parsed?.results && Array.isArray(parsed.results)) {
                      for (const r of parsed.results) {
                          const raw = r.payload?.data;
                          if (raw && (raw.a2ui || raw.protocol === 'a2ui')) {
                              if (ai.answer) ai.answer.innerHTML = ''; 
                              renderA2ui(ai, raw.a2ui || raw); 
                              a2uiRendered = true; break;
                          }
                      }
                  }
                  if (!a2uiRendered && parsed?.final_answer) renderAssistantMarkdown(ai.answer, parsed.final_answer);
                  if (reasoningText && ai.panel) { ai.panel.classList.add('collapsed'); if (ai.toggle) ai.toggle.textContent = '펼치기'; }
                  await enhanceBubble(ai.bubble);
                  setStatus(event === 'done' ? '완료' : '에러', event === 'done' ? 'complete' : 'error');
                  
                  // Memory Cleanup: clear large temporary strings
                  fullAnswer = '';
                  reasoningText = '';
                  sseBuf = '';
                  
                  activeStreamTaskId = ''; streaming = false; return;
              }
              
              if (event === 'progress') {
                  if (ai.panel) ai.panel.style.display = 'block';
                  if (ai.currentStage) ai.currentStage.textContent = `⚙️ ${parsed.stage} - ${parsed.message}`;
                  setStatus(`${parsed.stage}...`, 'streaming', { progress: 40 });
              }
              if (event === 'reasoning') {
                  reasoningText += parsed.token || '';
                  if (ai.panel) ai.panel.style.display = 'block'; 
                  if (ai.stream) {
                    ai.stream.textContent = reasoningText;
                    ai.stream.scrollTop = ai.stream.scrollHeight;
                  }
                  if (ai.currentStage) ai.currentStage.textContent = '🧠 LLM Reasoning...';
                  setStatus('추론 중...', 'streaming', { progress: 50 });
              }
              if (event === 'a2ui') { if (ai.answer) ai.answer.innerHTML = ''; renderA2ui(ai, parsed); setStatus('UI 렌더링 완료', 'streaming', { progress: 80 }); }
              if (event === 'chunk') {
                  const agent = parsed.agent || '';
                  const answer = parsed.data?.answer || parsed.answer || '';
                  if (answer && typeof answer === 'string') {
                      if (agent === 'supervisor') {
                          if (!reasoningDone && reasoningText) {
                              reasoningDone = true; if (ai.currentStage) ai.currentStage.textContent = '✍️ 최종 답변 작성 중...';
                              setTimeout(() => { if (ai.panel && !ai.panel.classList.contains('collapsed')) { ai.panel.classList.add('collapsed'); if (ai.toggle) ai.toggle.textContent = '펼치기'; } }, 2000);
                          }
                          fullAnswer += answer; renderAssistantMarkdown(ai.answer, fullAnswer);
                      } else {
                          if (ai.panel) ai.panel.style.display = 'block'; 
                          if (!reasoningText.includes(`[${agent}]`)) reasoningText += `\n[${agent}] `;
                          reasoningText += answer; 
                          if (ai.stream) {
                            ai.stream.textContent = reasoningText;
                            ai.stream.scrollTop = ai.stream.scrollHeight;
                          }
                          setStatus(`${agent} 처리 중...`, 'streaming', { progress: 60 });
                      }
                      setStatus('응답 수신 중...', 'streaming', { progress: 70 });
                      if (chatEl) chatEl.scrollTop = chatEl.scrollHeight;
                  }
              }
          }
      }
    } catch (e) {
      console.error(e);
      setStatus('에러 발생', 'error');
      renderAssistantMarkdown(ai.answer, `스트리밍 오류: ${e.message}`);
    } finally {
      streaming = false;
    }
  }

  /**
   * Rationale (Why): Server-side voice orchestration calls this when task starts.
   * Handles both immediate streaming and HITL (review required) scenarios.
   */
  async function onVoiceTaskStarted(taskId, transcript, status, reviewReason) {
    if (streaming) return;
    addMessage('user', transcript.replace(/\n/g, '<br>'));
    streaming = true;
    abortController = new AbortController();
    const ai = createAiResponseShell();

    if (status === "WAITING_REVIEW") {
        activeStreamTaskId = taskId;
        showHitlReviewPanel(ai, reviewReason || '사용자 승인이 필요합니다.', taskId);
        setStatus('사용자 승인 대기 중', 'pending');
        streaming = false; // Stop initial loading state, wait for user action
        return;
    }

    await startSseSubscription(ai, taskId);
  }

  async function send(overrideText, actionPayload) {
    if (streaming) return;
    const isUiEventArg = overrideText && typeof overrideText === 'object' && typeof overrideText.type === 'string';
    const normalizedOverrideText = isUiEventArg ? null : overrideText;
    const isAction = !!actionPayload;
    const text = String(normalizedOverrideText ?? promptEl.value).trim();
    if (!isAction && !text) return;

    if (!isAction) addMessage('user', text.replace(/\n/g, '<br>'));
    if (!isAction && normalizedOverrideText == null) promptEl.value = '';
    autoResizePrompt();
    streaming = true;
    abortController = new AbortController();
    statusTargetProgress = 0; statusDisplayProgress = 0;
    setStatus('요청 전송 중...', 'streaming', { progress: 10, activity: 'Supervisor 호출 준비' });

    const ai = createAiResponseShell();
    const payload = { 
      jsonrpc: '2.0', 
      id: generateUUID(), 
      method: 'message/send', 
      params: { 
        session_id, 
        message: isAction ? JSON.stringify(actionPayload) : text,
        request_id: generateUUID() 
      } 
    };

    try {
      const res = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const rpcRes = await res.json();
      
      if (rpcRes.result && rpcRes.result.status === "WAITING_REVIEW") {
          a2uiEnabled = !!rpcRes.result.a2ui_enabled;
          activeStreamTaskId = rpcRes.result.task_id;
          showHitlReviewPanel(ai, rpcRes.result.review_reason || '사용자 승인이 필요합니다.', rpcRes.result.task_id);
          setStatus('사용자 승인 대기 중', 'pending');
          streaming = false; // Stopped waiting for stream, now waiting for user.
          return;
      }
      
      if (rpcRes.result && rpcRes.result.status === "STREAMING") {
          a2uiEnabled = !!rpcRes.result.a2ui_enabled;
          await startSseSubscription(ai, rpcRes.result.task_id);
          return;
      }
      setStatus('완료', 'complete');
    } catch (e) {
      console.error(e); setStatus('에러 발생', 'error'); renderAssistantMarkdown(ai.answer, `오류 발생: ${e.message}`);
      streaming = false;
    }
  }

  // Global Exports
  window.autoResizePrompt = autoResizePrompt;
  window.send = send;
  window.onVoiceTaskStarted = onVoiceTaskStarted;
  window.getSessionId = () => session_id;

  // Event Listeners
  if (sendBtn) sendBtn.addEventListener('click', () => send());
  if (stopBtn) {
    stopBtn.addEventListener('click', async () => {
      try { if (activeStreamTaskId) await cancelActiveStreamTask(); }
      catch (e) { console.warn('Cancel failed:', e); }
      finally { if (abortController) abortController.abort(); }
    });
  }
  if (clearBtn) {
    clearBtn.addEventListener('click', async () => {
      try {
        if (activeStreamTaskId) await cancelActiveStreamTask();
        if (abortController) abortController.abort();
        const res = await rpcCall('session/clear', { session_id });
        if (chatEl) chatEl.innerHTML = ''; 
        activeStreamTaskId = ''; streaming = false;
        setStatus('초기화됨', 'ready'); 
        addMessage('ai', '세션 히스토리를 초기화했습니다.');
      } catch (e) { setStatus(`초기화 실패: ${e.message}`, 'error'); }
    });
  }
  if (promptEl) {
    promptEl.addEventListener('keydown', (e) => {
      if (e.isComposing) return;
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    promptEl.addEventListener('input', autoResizePrompt);
    autoResizePrompt();
  }

  // Welcome message
  addMessage('ai', '안녕하세요. A2A Supervisor에 오신 것을 환영합니다. 무엇을 도와드릴까요?');
})();
