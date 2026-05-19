(function() {
  // Voice Interaction Logic (GPT-4o mini Realtime STT Path)
  let voiceActive = false;
  let voiceWs = null;
  let audioContext = null;
  let audioWorkletNode = null;
  let microphoneStream = null;
  let analyser = null;
  let animationFrameId = null;
  let finalized = false;

  const micBtn = document.getElementById('micBtn');
  const voiceLayer = document.getElementById('voiceLayer');
  const voiceTranscriptLarge = document.getElementById('voiceTranscriptLarge');
  const voiceOrb = document.getElementById('voiceOrb');
  const voiceWaveform = document.getElementById('voiceWaveform');
  const voiceCloseBtn = document.getElementById('voiceCloseBtn');

  // Inject Streaming Badge CSS
  const style = document.createElement('style');
  style.textContent = `
    @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
    .streaming-dot { width: 8px; height: 8px; background: #ef4444; border-radius: 50%; box-shadow: 0 0 8px #ef4444; animation: blink 1s infinite; }
    #streamingBadge { position: absolute; top: 30px; right: 30px; display: flex; align-items: center; gap: 10px; color: #ef4444; font-size: 11px; font-weight: 800; letter-spacing: 1.5px; font-family: monospace; z-index: 1001; background: rgba(0,0,0,0.3); padding: 5px 12px; border-radius: 20px; border: 1px solid rgba(239,68,68,0.3); }
  `;
  document.head.appendChild(style);

  async function initVoice() {
    if (voiceActive) {
      stopVoice();
      return;
    }

    // 1. Show UI Immediately
    if (voiceLayer) {
        voiceLayer.classList.add('active');
        voiceLayer.setAttribute('aria-hidden', 'false');
        
        if (!document.getElementById('streamingBadge')) {
            const badge = document.createElement('div');
            badge.id = 'streamingBadge';
            badge.innerHTML = '<span class="streaming-dot"></span> LIVE AUDIO STREAMING';
            voiceLayer.appendChild(badge);
        }
    }
    if (micBtn) micBtn.classList.add('active');
    if (voiceTranscriptLarge) voiceTranscriptLarge.textContent = '목소리를 분석하고 있습니다...';

    try {
      // 2. Start WebSocket and AudioContext in parallel with getUserMedia
      const currentSessionId = (typeof window.getSessionId === 'function') ? window.getSessionId() : '';
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProtocol}//${window.location.host}/a2a/supervisor/voice/stream?session_id=${currentSessionId}`;
      
      const wsPromise = new Promise((resolve, reject) => {
        const ws = new WebSocket(wsUrl);
        ws.onopen = () => resolve(ws);
        ws.onerror = (err) => reject(err);
      });

      if (!navigator.mediaDevices) {
        throw new Error('모바일 브라우저는 HTTPS(보안 연결)에서만 마이크 접근이 가능합니다. http:// 대신 https:// 로 접속해주세요.');
      }
      const streamPromise = navigator.mediaDevices.getUserMedia({
          audio: {
              channelCount: 1,
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true
          }
      });

      // Show connecting status
      if (voiceTranscriptLarge) voiceTranscriptLarge.textContent = 'LLM 연결 중...';

      const [stream, ws] = await Promise.all([streamPromise, wsPromise]);
      
      microphoneStream = stream;
      voiceWs = ws;
      
      // Rationale (Why): OpenAI(24kHz)와 Gemini(Resampling 지원) 모두를 수용하기 위해 24kHz 표준 사용
      audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }

      console.log('Voice WS connected', { session_id: currentSessionId });
      voiceActive = true;
      finalized = false;
      if (voiceTranscriptLarge) voiceTranscriptLarge.textContent = '듣고 있습니다. 무엇을 도와드릴까요?';
      await startAudioCapture(stream);

      voiceWs.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        const promptEl = document.getElementById('prompt');

        if (msg.type === 'transcript') {
          if (finalized) return;
          if (voiceTranscriptLarge) voiceTranscriptLarge.textContent = msg.text;
          // Rationale (Why): JS manual scaling is removed here as it's now handled 
          // in the drawWaveform loop using real-time audio volume for smoother feedback.
        } else if (msg.type === 'final_transcript') {
          if (finalized) return;
          finalized = true;
          if (commitTimeoutId) { clearTimeout(commitTimeoutId); commitTimeoutId = null; }

          if (voiceTranscriptLarge) voiceTranscriptLarge.textContent = msg.text;
          
          if (voiceOrb) {
              voiceOrb.style.transition = 'all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275)';
              voiceOrb.style.transform = 'scale(1.4)';
              voiceOrb.style.boxShadow = '0 0 80px rgba(59, 130, 246, 0.9)';
              voiceOrb.style.filter = 'brightness(1.5)';
          }

          // Rationale (Why): Doc 23 implementation - Server already triggered the task.
          // We just notify app.js to start watching the SSE stream.
          setTimeout(() => {
            if (voiceOrb) {
              voiceOrb.style.transition = 'all 0.4s ease';
              voiceOrb.style.transform = 'scale(1)';
              voiceOrb.style.boxShadow = '0 0 20px rgba(59, 130, 246, 0.5)';
            }
            if (msg.task_started && msg.task_id && window.onVoiceTaskStarted) {
                window.onVoiceTaskStarted(msg.task_id, msg.text, msg.status, msg.review_reason);
            } else if (window.send) {
                // Fallback to legacy client-side send if server trigger failed
                window.send();
            }
            // Ensure voice is stopped after task is triggered
            setTimeout(stopVoice, 1000);
          }, 400);
        } else if (msg.type === 'error') {
          console.error('Voice Error:', msg.message);
          alert('음성 인식 오류: ' + msg.message);
          stopVoice();
        }
      };

      voiceWs.onclose = () => { if (voiceActive) stopVoice(); };
      voiceWs.onerror = (err) => {
        console.error('Voice WS Error', err);
        stopVoice();
      };

    } catch (err) {
      console.error('Voice Initialization error', err);
      alert('음성 인식을 시작할 수 없습니다: ' + err.message);
      stopVoice();
    }
  }

  async function startAudioCapture(stream) {
    if (!audioContext || audioContext.state === 'closed') return;
    
    const source = audioContext.createMediaStreamSource(stream);
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);

    drawWaveform();

    try {
        // Rationale (Why): AudioWorkletProcessor with real-time preprocessing:
        // 1. High-pass filter (~100Hz) removes low-frequency rumble (fan/AC/hum)
        // 2. Noise gate suppresses sub-threshold background noise
        // 3. Adaptive gain normalizes speech level for consistent STT input
        await audioContext.audioWorklet.addModule('data:text/javascript,' + encodeURIComponent(`
          class AudioProcessor extends AudioWorkletProcessor {
            constructor() {
              super();
              this.hpX = 0;
              this.hpY = 0;
              this.gateThreshold = 0.003;
              this.hpAlpha = 0.97;
            }
            process(inputs, outputs, parameters) {
              const input = inputs[0][0];
              if (!input) return true;
              const len = input.length;
              // First pass: apply HPF and compute block peak/gate decision
              const filtered = new Float32Array(len);
              let blockPeak = 0;
              let sumSq = 0;
              let hx = this.hpX, hy = this.hpY;
              for (let i = 0; i < len; i++) {
                const s = input[i];
                const hp = this.hpAlpha * (hy + s - hx);
                hx = s;
                hy = hp;
                filtered[i] = hp;
                const abs = Math.abs(hp);
                if (abs > blockPeak) blockPeak = abs;
                sumSq += hp * hp;
              }
              this.hpX = hx;
              this.hpY = hy;
              // Apply noise gate + adaptive gain + PCM16 conversion
              const pcm16 = new Int16Array(len);
              if (blockPeak >= this.gateThreshold) {
                const rms = Math.sqrt(sumSq / len);
                const gain = Math.min(1.8, 0.2 / Math.max(0.01, rms));
                for (let i = 0; i < len; i++) {
                  let s = filtered[i] * gain;
                  s = Math.max(-1, Math.min(1, s));
                  pcm16[i] = s * 0x7FFF;
                }
              }
              this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
              return true;
            }
          }
          registerProcessor('audio-processor', AudioProcessor);
        `));

        if (!audioContext || audioContext.state === 'closed') return;

        audioWorkletNode = new AudioWorkletNode(audioContext, 'audio-processor');
        audioWorkletNode.port.onmessage = (event) => {
          if (voiceWs && voiceWs.readyState === WebSocket.OPEN) {
            voiceWs.send(event.data);
          }
        };

        source.connect(audioWorkletNode);
    } catch (e) {
        console.error('AudioWorklet setup failed', e);
        stopVoice();
    }
  }

  // Rationale (Why): Smoothed frequency values for silky bar animation (1-pole IIR filter)
  let smoothedFreqs = [];

  function drawWaveform() {
    if (!analyser || !voiceWaveform) return;

    const canvas = voiceWaveform;
    const ctx = canvas.getContext('2d');
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    // Prime smooth buffer on first call
    if (smoothedFreqs.length !== bufferLength / 2) {
      smoothedFreqs = new Array(bufferLength / 2).fill(0);
    }

    const draw = () => {
      if (!voiceActive || finalized) {
        if (animationFrameId) cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
        return;
      }
      animationFrameId = requestAnimationFrame(draw);

      analyser.getByteFrequencyData(dataArray);

      if (canvas.width !== canvas.clientWidth || canvas.height !== canvas.clientHeight) {
        canvas.width = canvas.clientWidth;
        canvas.height = canvas.clientHeight;
      }

      // Compute average volume
      let sum = 0;
      for (let i = 0; i < bufferLength; i++) sum += dataArray[i];
      const average = sum / bufferLength;

      // Pulse the orb with a soft glow ring
      if (voiceOrb) {
        const targetScale = 1 + (average / 256) * 0.5;
        voiceOrb.style.transform = `scale(${targetScale})`;
        const brightness = 1 + (average / 256) * 0.8;
        const spread = 40 + (average / 256) * 80;
        voiceOrb.style.boxShadow = `0 0 ${spread}px rgba(99, 102, 241, ${0.3 + (average / 256) * 0.5})`;
        voiceOrb.style.filter = `brightness(${brightness})`;
      }

      // Clear with a very faint trail for motion-blur effect
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const barCount = bufferLength / 2;
      const gap = 4;
      const totalGap = gap * barCount;
      const barWidth = (canvas.width - totalGap) / barCount / 2;
      const quietThreshold = 6;
      const isSilent = average < quietThreshold;

      // Build and smooth bar heights
      const barHeights = [];
      for (let i = 0; i < barCount; i++) {
        const raw = dataArray[i] / 255;
        // Weight toward lower frequencies for a fuller look
        const weighted = raw * (1 + 0.5 * (1 - i / barCount));
        const height = Math.min(1, weighted) * canvas.height * 0.65;
        barHeights.push(height);
      }

      // Apply 1-pole smoother: output = alpha * input + (1-alpha) * previous
      const alpha = isSilent ? 0.3 : 0.28;
      for (let i = 0; i < barCount; i++) {
        smoothedFreqs[i] = alpha * barHeights[i] + (1 - alpha) * smoothedFreqs[i];
        // Floor tiny values to zero to avoid idle jitter
        if (isSilent && smoothedFreqs[i] < 2) smoothedFreqs[i] = 0;
      }

      // Luminance gradient: hot (center) → cool (edges)
      const grad = ctx.createLinearGradient(0, canvas.height, 0, 0);
      if (average < quietThreshold) {
        grad.addColorStop(0, 'rgba(99, 102, 241, 0.15)');
        grad.addColorStop(0.5, 'rgba(139, 92, 246, 0.08)');
        grad.addColorStop(1, 'rgba(99, 102, 241, 0)');
      } else {
        const intensity = Math.min(1, average / 128);
        grad.addColorStop(0, `rgba(99, 102, 241, ${0.5 + intensity * 0.4})`);
        grad.addColorStop(0.3, `rgba(168, 85, 247, ${0.6 + intensity * 0.3})`);
        grad.addColorStop(0.6, `rgba(236, 72, 153, ${0.4 + intensity * 0.3})`);
        grad.addColorStop(1, 'rgba(99, 102, 241, 0)');
      }

      const barBottom = canvas.height - 80;

      // Draw bars – rising from bottom with rounded caps
      for (let i = 0; i < barCount; i++) {
        const h = smoothedFreqs[i];
        if (h < 1) continue;

        const x = totalGap / 2 + i * (barWidth * 2 + gap) + barWidth / 2;
        const x1 = x - barWidth;
        const y1 = barBottom - h;

        // Glow beneath each bar (wider, soft)
        ctx.shadowColor = `rgba(139, 92, 246, ${0.15 + (h / (canvas.height * 0.65)) * 0.25})`;
        ctx.shadowBlur = 12;

        // Main bar with rounded cap
        const radius = Math.min(barWidth / 2, 12);
        ctx.beginPath();
        ctx.moveTo(x1 + radius, barBottom);
        ctx.lineTo(x1 + radius, y1 + radius);
        ctx.quadraticCurveTo(x1 + radius, y1, x1, y1);
        ctx.lineTo(x1 + barWidth, y1);
        ctx.quadraticCurveTo(x1 + barWidth + radius, y1, x1 + barWidth + radius, y1 + radius);
        ctx.lineTo(x1 + barWidth + radius, barBottom);
        ctx.closePath();

        // Map height to gradient color stop position
        const stopPos = Math.min(1, h / (canvas.height * 0.65));
        const barGrad = ctx.createLinearGradient(x1, barBottom, x1, y1);
        barGrad.addColorStop(0, `rgba(99, 102, 241, ${0.3 + stopPos * 0.5})`);
        barGrad.addColorStop(0.5, `rgba(168, 85, 247, ${0.4 + stopPos * 0.4})`);
        barGrad.addColorStop(1, `rgba(236, 72, 153, ${0.2 + stopPos * 0.3})`);

        ctx.fillStyle = barGrad;
        ctx.fill();

        // Fine glow highlight overlay
        ctx.shadowBlur = 8;
        ctx.shadowColor = `rgba(168, 85, 247, ${0.05 + stopPos * 0.12})`;
        ctx.fill();
      }

      // Reset shadow for subsequent draws
      ctx.shadowBlur = 0;
      ctx.shadowColor = 'transparent';
    };
    draw();
  }

  function stopVoice() {
    voiceActive = false;
    _cleanupVoiceResources();
  }

  function _cleanupVoiceResources() {
    if (commitTimeoutId) { clearTimeout(commitTimeoutId); commitTimeoutId = null; }
    if (micBtn) micBtn.classList.remove('active');
    if (voiceLayer) {
      voiceLayer.classList.remove('active');
      voiceLayer.setAttribute('aria-hidden', 'true');
      const badge = document.getElementById('streamingBadge');
      if (badge) badge.remove();
    }

    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId);
      animationFrameId = null;
    }
    if (audioContext) {
      try { 
        if (audioContext.state !== 'closed') audioContext.close(); 
      } catch(e) {}
      audioContext = null;
    }
    if (microphoneStream) {
      microphoneStream.getTracks().forEach(track => track.stop());
      microphoneStream = null;
    }
    if (voiceWs) {
      if (voiceWs.readyState === WebSocket.OPEN || voiceWs.readyState === WebSocket.CONNECTING) voiceWs.close();
      voiceWs = null;
    }
  }

  // Rationale (Why): Safety timeout handle to prevent UI freeze if commit response never arrives
  let commitTimeoutId = null;

  function finishVoice() {
    if (!voiceActive || finalized) return;

    // Rationale (Why): Stop the waveform/draw loop immediately for instant UI feedback,
    // but do NOT set finalized=true here — that would suppress the pending
    // final_transcript response from the server. finalized is set only when the
    // actual transcript arrives in onmessage.
    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId);
      animationFrameId = null;
    }

    // Rationale (Why): Tell backend to manually commit the audio buffer and start analysis.
    if (voiceWs && voiceWs.readyState === WebSocket.OPEN) {
      voiceWs.send(JSON.stringify({ type: 'commit' }));
    }

    if (voiceTranscriptLarge) voiceTranscriptLarge.textContent = '분석 중입니다...';
    if (voiceOrb) {
      voiceOrb.style.animation = 'none';
      voiceOrb.style.transition = 'all 0.4s ease';
      voiceOrb.style.transform = 'scale(1.2)';
      voiceOrb.style.boxShadow = '0 0 40px rgba(99, 102, 241, 0.8)';
    }

    // Rationale (Why): Safety timeout — if server doesn't respond within 10s,
    // clean up and let user try again instead of being stuck on "분석 중입니다...".
    if (commitTimeoutId) clearTimeout(commitTimeoutId);
    commitTimeoutId = setTimeout(() => {
      if (!finalized) {
        console.warn('Voice commit timeout — no final_transcript received within 10s');
        if (voiceTranscriptLarge) voiceTranscriptLarge.textContent = '음성 인식 응답 시간이 초과되었습니다. 다시 시도해주세요.';
        setTimeout(stopVoice, 2000);
      }
      commitTimeoutId = null;
    }, 10000);
  }

  window.initVoice = initVoice;
  window.stopVoice = stopVoice;
  if (micBtn) micBtn.addEventListener('click', initVoice);
  if (voiceCloseBtn) voiceCloseBtn.addEventListener('click', stopVoice);

  // Rationale (Why): Click anywhere on overlay to finish speaking and start analysis.
  // Previous code only matched clicks on voiceLayer, aurora-bg, or transcript; taps on
  // orb or waveform canvas were silently ignored. Now any tap (except close btn) triggers finish.
  if (voiceLayer) {
    voiceLayer.addEventListener('click', (e) => {
      if (e.target.closest('#voiceCloseBtn')) return;
      finishVoice();
    });
  }
})();
