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

      const streamPromise = navigator.mediaDevices.getUserMedia({ 
          audio: {
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
          const scale = 1 + (msg.text.length % 5) * 0.05;
          if (voiceOrb) voiceOrb.style.transform = `scale(${scale})`;
        } else if (msg.type === 'final_transcript') {
          if (finalized) return;
          finalized = true;
          
          if (voiceTranscriptLarge) voiceTranscriptLarge.textContent = msg.text;
          
          if (voiceOrb) {
              voiceOrb.style.animation = 'none';
              voiceOrb.style.transform = 'scale(1.4)';
              voiceOrb.style.boxShadow = '0 0 60px rgba(59, 130, 246, 0.9)';
          }

          // Rationale (Why): Doc 23 implementation - Server already triggered the task.
          // We just notify app.js to start watching the SSE stream.
          setTimeout(() => {
            stopVoice();
            if (msg.task_started && msg.task_id && window.onVoiceTaskStarted) {
                window.onVoiceTaskStarted(msg.task_id, msg.text, msg.status, msg.review_reason);
            } else if (window.send) {
                // Fallback to legacy client-side send if server trigger failed
                window.send();
            }
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
        // Rationale (Why): Using explicit process(inputs, outputs, parameters) for strict browser compliance
        await audioContext.audioWorklet.addModule('data:text/javascript,' + encodeURIComponent(`
          class AudioProcessor extends AudioWorkletProcessor {
            process(inputs, outputs, parameters) {
              const input = inputs[0][0];
              if (input) {
                const pcm16 = new Int16Array(input.length);
                for (let i = 0; i < input.length; i++) {
                  pcm16[i] = Math.max(-1, Math.min(1, input[i])) * 0x7FFF;
                }
                this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
              }
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

  function drawWaveform() {
    if (!analyser || !voiceWaveform) return;

    const canvas = voiceWaveform;
    const ctx = canvas.getContext('2d');
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const draw = () => {
      if (!voiceActive) {
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

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      let sum = 0;
      for(let i=0; i<bufferLength; i++) sum += dataArray[i];
      const average = sum / bufferLength;
      const sensitivity = 5; 
      const isSilent = average < sensitivity;

      const barWidth = (canvas.width / bufferLength) * 2.5;
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        let barHeight = (dataArray[i] / 255) * canvas.height;
        if (isSilent) barHeight = 1.5;

        const gradient = ctx.createLinearGradient(0, canvas.height, 0, 0);
        gradient.addColorStop(0, 'rgba(59, 130, 246, 0.1)');
        gradient.addColorStop(0.5, 'rgba(147, 51, 234, 0.6)');
        gradient.addColorStop(1, 'rgba(59, 130, 246, 0.8)');
        ctx.fillStyle = gradient;
        
        const y = (canvas.height - barHeight) / 2;
        ctx.beginPath();
        ctx.roundRect(x, y, barWidth - 1, barHeight, 10);
        ctx.fill();
        x += barWidth;
      }
    };
    draw();
  }

  function stopVoice() {
    voiceActive = false;
    _cleanupVoiceResources();
  }

  function _cleanupVoiceResources() {
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

  function finishVoice() {
    if (!voiceActive || finalized) return;
    
    // Rationale (Why): Tell backend to manually commit the audio buffer and start analysis.
    if (voiceWs && voiceWs.readyState === WebSocket.OPEN) {
      voiceWs.send(JSON.stringify({ type: 'commit' }));
    }
    
    if (voiceTranscriptLarge) voiceTranscriptLarge.textContent = '분석 중입니다...';
    if (voiceOrb) {
      voiceOrb.style.animation = 'none';
      voiceOrb.style.transform = 'scale(1.2)';
      voiceOrb.style.boxShadow = '0 0 40px rgba(99, 102, 241, 0.8)';
    }
    
    // We don't call stopVoice yet, because we need to wait for 'final_transcript' 
    // message from WebSocket to trigger the task.
  }

  window.initVoice = initVoice;
  window.stopVoice = stopVoice;
  if (micBtn) micBtn.addEventListener('click', initVoice);
  if (voiceCloseBtn) voiceCloseBtn.addEventListener('click', stopVoice);

  // Rationale (Why): Click anywhere on overlay to finish speaking and start analysis.
  if (voiceLayer) {
    voiceLayer.addEventListener('click', (e) => {
      // Only finish if clicking the background itself or non-interactive elements
      if (e.target === voiceLayer || e.target.classList.contains('aurora-bg') || e.target === voiceTranscriptLarge) {
        finishVoice();
      }
    });
  }
})();
