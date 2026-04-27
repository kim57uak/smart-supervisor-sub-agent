import json

def get_function_bounds(content, func_name):
    # Find the start of the function
    start_idx = content.find(f"async function {func_name}(")
    if start_idx == -1:
        return -1, -1
        
    # Find the first '{' after start_idx
    brace_idx = content.find('{', start_idx)
    if brace_idx == -1:
        return -1, -1
        
    brace_count = 1
    i = brace_idx + 1
    
    while i < len(content) and brace_count > 0:
        if content[i] == '{':
            brace_count += 1
        elif content[i] == '}':
            brace_count -= 1
        i += 1
        
    return start_idx, i

html_file = 'app/static/index.html'

with open(html_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Patch send() function
send_start, send_end = get_function_bounds(content, 'send')
if send_start != -1:
    new_send = """async function send(overrideText, actionPayload) {
      if (streaming) return;
      const isUiEventArg = overrideText && typeof overrideText === 'object' && typeof overrideText.type === 'string';
      const normalizedOverrideText = isUiEventArg ? null : overrideText;
      const isAction = !!actionPayload;
      const text = String(normalizedOverrideText ?? promptEl.value).trim();
      if (!isAction && !text) return;

      if (!isAction) {
        addMessage('user', text.replace(/\\n/g, '<br>'));
      }
      if (!isAction && normalizedOverrideText == null) {
        promptEl.value = '';
      }
      autoResizePrompt();
      streaming = true;
      abortController = new AbortController();
      statusTargetProgress = 0;
      statusDisplayProgress = 0;
      setStatus('요청 전송 중...', 'streaming', { progress: 10, activity: 'Supervisor 호출 준비' });

      const ai = createAiResponseShell();
      
      const payload = {
        jsonrpc: '2.0',
        id: `ui-${Date.now()}`,
        method: 'message/send',
        params: {
          session_id: sessionId,
          message: isAction ? JSON.stringify(actionPayload) : text
        }
      };

      try {
        const res = await fetch('/a2a/supervisor', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const rpcRes = await res.json();
        
        if (rpcRes.result && rpcRes.result.status === "WAITING_REVIEW") {
            showHitlReviewPanel(ai, rpcRes.result.review_reason || '사용자 승인이 필요합니다.', rpcRes.result.task_id);
            setStatus('사용자 승인 대기 중', 'pending');
            return;
        }
        
        finalizeHitlWaitingUi(ai, "완료");
        setStatus('완료', 'complete');
      } catch (e) {
        console.error(e);
        setStatus('에러 발생', 'error');
        renderAssistantMarkdown(ai.textEl, `오류 발생: ${e.message}`);
      } finally {
        streaming = false;
      }
    }"""
    content = content[:send_start] + new_send + content[send_end:]

# 2. Patch streamReviewDecision
stream_start, stream_end = get_function_bounds(content, 'streamReviewDecision')
if stream_start != -1:
    new_stream = """async function streamReviewDecision(ai, taskId, decision) {
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

            ai.panel.style.display = 'block';

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
                
                if (event === 'done' || event === 'error') {
                    finalizeHitlWaitingUi(ai, "완료");
                    setStatus('처리 완료', 'complete');
                    ai.panel.classList.add('collapsed');
                    ai.toggle.textContent = '펼치기';
                    return;
                }
                
                if (event === 'progress') {
                    applySupervisorProgress(ai, data);
                    ai.stream.textContent += `[progress] ${data.stage} - ${data.message || ''}\\n`;
                    ai.stream.scrollTop = ai.stream.scrollHeight;
                } else if (event === 'chunk') {
                    const textContent = data.data?.answer || data.answer || data;
                    if (textContent && typeof textContent === 'string') {
                        ai.fullContent += textContent;
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
    content = content[:stream_start] + new_stream + content[stream_end:]

with open(html_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("HTML patched using AST-like brace matching successfully.")
