import os

html_file = 'app/static/index.html'

with open(html_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove model select
old_model_select = """        <select id="model">
          <option value="openai">OpenAI (default)</option>
          <option value="gpt-4o-mini">GPT-4o Mini</option>
          <option value="gemini">Gemini</option>
          <option value="gemini-lite">Gemini Lite</option>
          <option value="mistral">Mistral</option>
          <option value="mistral-large-latest">Mistral Large Latest</option>
        </select>"""
content = content.replace(old_model_select, "")

# 2. Add sessionId and remove modelEl JS references
content = content.replace(
    "const modelEl = document.getElementById('model');", 
    ""
)

if "let sessionId =" not in content:
    content = content.replace(
        "let abortController = null;",
        "let abortController = null;\n    let sessionId = 'sess-' + Date.now() + '-' + Math.floor(Math.random() * 1000);"
    )

content = content.replace(
    "const endpoint = `/a2a/supervisor?model=${modelSelect.value}&stream=${useStream}&userId=${userId}`;",
    "const endpoint = useStream ? '/a2a/supervisor/stream' : '/a2a/supervisor';"
)

content = content.replace(
    "const userId = 'user-123';",
    ""
)

# 3. Fix `send()` fetch
old_send_fetch = """        const payload = {
          jsonrpc: '2.0',
          id: requestId,
          method: 'message/stream',
          params: {
            model: modelEl.value || 'openai',
            message: isAction ? buildActionMessagePayload(actionPayload) : buildTextMessagePayload(text)
          }
        };

        const res = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream'
          },
          body: JSON.stringify(payload),
          signal: abortController.signal
        });

        if (!res.ok) {
          const err = await res.text();
          throw new Error(`HTTP ${res.status}: ${err}`);
        }

        const contentType = (res.headers.get('content-type') || '').toLowerCase();
        if (!contentType.includes('text/event-stream')) {
          const body = await res.text();
          throw new Error(`Non-SSE response: ${body}`);
        }

        setStatus('응답 수신 중...', 'streaming', { progress: 16, activity: 'SSE 스트림 연결됨' });
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parsed = parseSseFrames(buffer);
          buffer = parsed.rest;

          for (const frame of parsed.completeFrames) {
            const eventObj = parseFrame(frame);
            if (!eventObj) continue;

            if (eventObj.event === 'progress') {
              applySupervisorProgress(ai, eventObj.data);
            } else if (eventObj.event === 'chunk') {
              const textContent = eventObj.data.data?.answer || '';
              if (textContent) {
                enqueueAssistantChars(textContent);
              }
            } else if (eventObj.event === 'done' || eventObj.event === 'error') {
              // Finish stream
            }
          }
        }"""

new_send_fetch = """        const payload = {
          jsonrpc: '2.0',
          id: requestId,
          method: 'message/send',
          params: {
            session_id: sessionId,
            message: isAction ? JSON.stringify(actionPayload) : text
          }
        };

        const res = await fetch('/a2a/supervisor', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (!res.ok) { throw new Error(`HTTP ${res.status}`); }
        const rpcRes = await res.json();
        
        if (rpcRes.result && rpcRes.result.status === "WAITING_REVIEW") {
            showHitlReviewPanel(ai, rpcRes.result.review_reason || '사용자 승인이 필요합니다.', rpcRes.result.task_id);
            setStatus('사용자 승인 대기 중', 'pending');
            return;
        }
        
        finalizeHitlWaitingUi(ai, "완료");"""

content = content.replace(old_send_fetch, new_send_fetch)

# 4. Fix streamReviewDecision()
old_stream_review = """    async function streamReviewDecision(ai, taskId, decision) {
      const requestId = `ui-review-${Date.now()}`;
      const payload = {
        jsonrpc: '2.0',
        id: requestId,
        method: 'tasks/review/decide/stream',
        params: {
          id: taskId,
          decision,
          reason: decision === 'APPROVE' ? 'approved_from_ui' : 'canceled_from_ui',
          decisionId: `ui-decision-${Date.now()}`
        }
      };

      const res = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream'
        },
        body: JSON.stringify(payload),
        signal: abortController.signal
      });

      if (!res.ok) {
        const err = await res.text();
        throw new Error(`HTTP ${res.status}: ${err}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parsed = parseSseFrames(buffer);
        buffer = parsed.rest;

        for (const frame of parsed.completeFrames) {
          const eventObj = parseFrame(frame);
          if (!eventObj) continue;

          if (eventObj.event === 'progress') {
            applySupervisorProgress(ai, eventObj.data);
          } else if (eventObj.event === 'chunk') {
            const textContent = eventObj.data.data?.answer || '';
            if (textContent) {
              ai.fullContent += textContent;
              renderAssistantMarkdown(ai.textEl, ai.fullContent);
            }
          }
        }
      }

      try {
        const resolvedTask = await waitForTaskTerminal(taskId);
        if (resolvedTask) {
          renderTaskOutcome(ai, resolvedTask, decision);
        } else {
          finalizeHitlWaitingUi(ai, "승인됨 (진행 완료)");
        }
      } catch (e) {
        finalizeHitlWaitingUi(ai, "승인됨 (상태 확인 불가)");
      }
    }"""

new_stream_review = """    async function streamReviewDecision(ai, taskId, decision) {
      try {
        const decideRes = await rpcCall('tasks/review/decide', {
          task_id: taskId,
          session_id: sessionId,
          decision: decision,
          reason: ''
        });

        if (decideRes.result && decideRes.result.stream_endpoint) {
            const streamEndpoint = decideRes.result.stream_endpoint;
            const cursor = decideRes.result.initial_cursor;
            
            const payload = {
                jsonrpc: '2.0',
                id: `ui-rpc-${Date.now()}`,
                method: 'tasks/events',
                params: {
                    task_id: taskId,
                    cursor: cursor
                }
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

            while (true) {
              const { value, done } = await reader.read();
              if (done) break;
              
              buffer += decoder.decode(value, { stream: true });
              const frames = parseSseFrames(buffer);
              buffer = frames.remainder || frames.rest || '';

              for (const frame of frames.completeFrames) {
                const eventObj = parseFrame(frame);
                if (!eventObj) continue;
                if (eventObj.event === 'done' || eventObj.event === 'error') {
                    finalizeHitlWaitingUi(ai, "완료");
                    setStatus('처리 완료', 'complete');
                    return;
                }
                if (eventObj.event === 'progress') {
                    applySupervisorProgress(ai, eventObj.data);
                } else if (eventObj.event === 'chunk') {
                    const content = eventObj.data.data?.answer || '';
                    if (content) {
                        ai.fullContent += content;
                        renderAssistantMarkdown(ai.textEl, ai.fullContent);
                    }
                }
              }
            }
        }
      } catch (err) {
        console.error(err);
        setStatus('에러 발생', 'error');
      }
    }"""

content = content.replace(old_stream_review, new_stream_review)

# 5. Fix clearBtn
content = content.replace(
    "await fetch('/a2a/supervisor/clear', { method: 'POST' });",
    "sessionId = 'sess-' + Date.now() + '-' + Math.floor(Math.random() * 1000);"
)

with open(html_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("HTML patched accurately.")
