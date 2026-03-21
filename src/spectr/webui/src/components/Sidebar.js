import React, { useState, useEffect, useRef } from 'react';
import SettingsDialog from './SettingsDialog';
import VoiceMarkdownDialog from './VoiceMarkdownDialog';
import StrategyDialog from './StrategyDialog';

function Sidebar({ tickers, selectedTicker, onSelect }) {
  const [collapsed, setCollapsed] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showStrategyDialog, setShowStrategyDialog] = useState(false);
  const [strategies, setStrategies] = useState([]);
  const [strategyCode, setStrategyCode] = useState('');
  const [selectedStrategy, setSelectedStrategy] = useState('');
  const [isVoiceActive, setIsVoiceActive] = useState(false);
  const [voiceProcessing, setVoiceProcessing] = useState(false);
  const [voiceSpeaking, setVoiceSpeaking] = useState(false);
  const [voiceError, setVoiceError] = useState('');
  const [showVoiceMarkdown, setShowVoiceMarkdown] = useState(false);
  const audioElementRef = useRef(null);
  const audioUrlRef = useRef(null);
  const [voiceMarkdown, setVoiceMarkdown] = useState({ title: '', markdown: '' });
  
  const [tickerDetails, setTickerDetails] = useState({});
  
  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const mediaChunksRef = useRef([]);
  const shouldSubmitOnEndRef = useRef(false);
  const transcriptRef = useRef('');

  const stopVoicePlayback = () => {
    const audio = audioElementRef.current;
    if (audio) {
      try {
        audio.pause();
        audio.currentTime = 0;
      } catch (e) {
        console.debug('[VoiceAgent] Failed to stop audio playback cleanly', e);
      }
      audioElementRef.current = null;
    }
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
    setVoiceSpeaking(false);
  };

  const playVoiceAudio = async (text) => {
    if (!text?.trim()) {
      return;
    }

    const response = await fetch('/api/voice-agent/tts', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ text }),
    });
    if (!response.ok) {
      let detail = `HTTP error! status: ${response.status}`;
      try {
        const errData = await response.json();
        detail = errData?.error || detail;
      } catch (e) {
        // Ignore JSON parsing failures and use status fallback.
      }
      throw new Error(detail);
    }

    const audioBlob = await response.blob();
    stopVoicePlayback();

    const audioUrl = URL.createObjectURL(audioBlob);
    audioUrlRef.current = audioUrl;
    const audio = new Audio(audioUrl);
    audioElementRef.current = audio;

    const resetPlaybackState = () => {
      setVoiceSpeaking(false);
      if (audioElementRef.current === audio) {
        audioElementRef.current = null;
      }
      if (audioUrlRef.current === audioUrl) {
        URL.revokeObjectURL(audioUrl);
        audioUrlRef.current = null;
      }
    };

    audio.onended = resetPlaybackState;
    audio.onerror = () => {
      resetPlaybackState();
      setVoiceError('Playback failed');
    };
    audio.onpause = () => {
      if (audio.ended) {
        return;
      }
      setVoiceSpeaking(false);
    };

    setVoiceSpeaking(true);
    try {
      await audio.play();
    } catch (e) {
      resetPlaybackState();
      throw e;
    }
  };

  const logSpeechRecognitionDiagnostic = (errorType, event) => {
    const context = {
      errorType: errorType || 'unknown',
      message: event?.message || null,
      timeStamp: event?.timeStamp || null,
      isSecureContext: window.isSecureContext,
      protocol: window.location?.protocol || null,
      host: window.location?.host || null,
      userAgent: navigator.userAgent,
    };

    let hint = 'Unknown speech recognition failure.';
    if (errorType === 'network') {
      hint = 'Browser speech service request failed. Common causes: blocked network, unsupported browser engine, or disabled speech service.';
    } else if (errorType === 'not-allowed' || errorType === 'service-not-allowed') {
      hint = 'Microphone or speech recognition permission is blocked for this site.';
    } else if (errorType === 'audio-capture') {
      hint = 'No usable microphone input device was found.';
    } else if (errorType === 'no-speech') {
      hint = 'Microphone started but no speech was detected before timeout.';
    } else if (errorType === 'aborted') {
      hint = 'Speech recognition was intentionally stopped.';
    }

    console.error('[VoiceAgent] Speech recognition failure', {
      ...context,
      hint,
    });
  };

  useEffect(() => {
    setTickerDetails({});
  }, [tickers]);

  useEffect(() => {
    const handleTickersUpdated = () => {
      fetch('/api/tickers')
        .then(res => res.json())
        .then(data => {
          if (data && data.length > 0) {
            setTickerDetails({});
          }
        })
        .catch(err => console.error('Failed to refresh tickers:', err));
    };

    window.addEventListener('tickersUpdated', handleTickersUpdated);

    return () => {
      window.removeEventListener('tickersUpdated', handleTickersUpdated);
    };
  }, []);

  useEffect(() => {
    if (tickers.length > 0) {
      const promises = tickers.map((ticker) =>
        fetch(`/api/profile/${ticker}`)
          .then(res => res.json())
          .then(data => {
            if (data && data.logo) {
              return { ticker, logo: data.logo };
            }
            return null;
          })
          .catch(err => {
            console.error(`Failed to fetch profile for ${ticker}:`, err);
            return null;
          })
      );
      
      Promise.all(promises).then(results => {
        const details = {};
        results.forEach(result => {
          if (result) {
            details[result.ticker] = result.logo;
          }
        });
        setTickerDetails(details);
      });
    }
  }, [tickers]);

  useEffect(() => {
    const loadStrategies = async () => {
      try {
        const res = await fetch('/api/strategies');
        const data = await res.json();
        setStrategies(data.strategies || []);
        if (data.current) {
          setSelectedStrategy(data.current);
          const codeRes = await fetch(`/api/strategies/${data.current}/code`);
          const codeData = await codeRes.json();
          if (codeData.success && codeData.code) {
            setStrategyCode(codeData.code);
          }
        } else if (data.strategies && data.strategies.length > 0) {
          setSelectedStrategy(data.strategies[0]);
        }
      } catch (err) {
        console.error('Failed to load strategies:', err);
      }
    };
    loadStrategies();
  }, []);

  const submitVoicePrompt = (text) => {
    if (!text) {
      return Promise.resolve();
    }

    setVoiceProcessing(true);
    setVoiceSpeaking(false);
    setVoiceError('');

    return fetch('/api/voice-agent', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ transcript: text }),
    })
      .then(res => {
        if (!res.ok) {
          return res.json().then(errData => {
            throw new Error(errData.error || `HTTP error! status: ${res.status}`);
          });
        }
        return res.json();
      })
      .then((data) => {
        const markdownPayload = data?.markdown;
        if (markdownPayload?.markdown) {
          setVoiceMarkdown({
            title: markdownPayload.title || 'Voice Agent Details',
            markdown: markdownPayload.markdown,
          });
          setShowVoiceMarkdown(true);
        }
        return playVoiceAudio(data?.response || '');
      })
      .then(() => {
        transcriptRef.current = '';
      })
      .catch(err => {
        console.error('Failed to submit voice prompt:', err);
        setVoiceError(`Processing failed: ${err.message}`);
        alert(`Speech recognition error: ${err.message}`);
        transcriptRef.current = '';
      })
      .finally(() => {
        setVoiceProcessing(false);
      });
  };

  const submitVoiceAudio = (audioBlob) => {
    if (!audioBlob || audioBlob.size === 0) {
      setVoiceError('No audio captured');
      return Promise.resolve();
    }

    const formData = new FormData();
    formData.append('audio', audioBlob, 'voice-input.webm');

    setVoiceProcessing(true);
    setVoiceSpeaking(false);
    setVoiceError('');

    return fetch('/api/voice-agent/audio', {
      method: 'POST',
      body: formData,
    })
      .then(res => {
        if (!res.ok) {
          return res.json().then(errData => {
            throw new Error(errData.error || `HTTP error! status: ${res.status}`);
          });
        }
        return res.json();
      })
      .then((data) => {
        const markdownPayload = data?.markdown;
        if (markdownPayload?.markdown) {
          setVoiceMarkdown({
            title: markdownPayload.title || 'Voice Agent Details',
            markdown: markdownPayload.markdown,
          });
          setShowVoiceMarkdown(true);
        }
        return playVoiceAudio(data?.response || '');
      })
      .catch(err => {
        console.error('[VoiceAgent] Audio transcription failed:', err);
        setVoiceError(`Processing failed: ${err.message}`);
      })
      .finally(() => {
        setVoiceProcessing(false);
      });
  };

  const stopAndReleaseMediaStream = () => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
    }
  };

  const startMediaRecording = async () => {
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
        throw new Error('MediaRecorder not supported');
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      mediaChunksRef.current = [];

      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          mediaChunksRef.current.push(event.data);
        }
      };

      recorder.onerror = (event) => {
        console.error('[VoiceAgent] MediaRecorder error', event);
        setIsVoiceActive(false);
        setVoiceError('Microphone capture failed');
        stopAndReleaseMediaStream();
      };

      recorder.onstop = () => {
        setIsVoiceActive(false);
        const recordedBlob = new Blob(mediaChunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        mediaChunksRef.current = [];
        mediaRecorderRef.current = null;
        stopAndReleaseMediaStream();
        submitVoiceAudio(recordedBlob);
      };

      recorder.start();
      setVoiceError('');
      setIsVoiceActive(true);
    } catch (e) {
      console.error('[VoiceAgent] Failed to start MediaRecorder', {
        error: e,
        hint: 'Check microphone permissions and browser media-capture support.',
      });
      setVoiceError('Unable to start microphone');
      setIsVoiceActive(false);
      mediaRecorderRef.current = null;
      stopAndReleaseMediaStream();
    }
  };

  useEffect(() => {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      console.warn('Web Speech API not supported in this browser');
      return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      setIsVoiceActive(true);
      setVoiceError('');
    };

    recognition.onresult = (event) => {
      let nextTranscript = transcriptRef.current;
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        const phrase = event.results[i][0].transcript || '';
        if (event.results[i].isFinal) {
          nextTranscript += `${phrase} `;
        }
      }
      transcriptRef.current = nextTranscript.trim();
    };

    recognition.onerror = (event) => {
      const errorType = event.error || 'unknown';
      logSpeechRecognitionDiagnostic(errorType, event);
      setIsVoiceActive(false);
      shouldSubmitOnEndRef.current = false;

      if (errorType === 'no-speech') {
        setVoiceError('No speech detected');
      } else if (errorType === 'network') {
        setVoiceError('Speech service unavailable');
      } else if (errorType === 'not-allowed' || errorType === 'service-not-allowed') {
        setVoiceError('Microphone permission denied');
      } else if (errorType !== 'aborted') {
        setVoiceError(`Recognition failed: ${errorType}`);
      }

      if (errorType === 'network' || errorType === 'no-speech' || errorType === 'aborted') {
        transcriptRef.current = '';
      }
    };

    recognition.onend = () => {
      setIsVoiceActive(false);
      const finalTranscript = transcriptRef.current.trim();
      if (shouldSubmitOnEndRef.current && finalTranscript) {
        shouldSubmitOnEndRef.current = false;
        submitVoicePrompt(finalTranscript);
      } else {
        shouldSubmitOnEndRef.current = false;
      }
    };

    recognitionRef.current = recognition;

    return () => {
      try {
        recognition.stop();
      } catch (e) {
        console.debug('Speech recognition stop on cleanup failed:', e);
      }
      recognitionRef.current = null;
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      mediaRecorderRef.current = null;
      mediaChunksRef.current = [];
      stopAndReleaseMediaStream();
      stopVoicePlayback();
    };
  }, []);

  const toggleVoiceAgent = () => {
    const canUseMediaRecorder = Boolean(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
    if (!recognitionRef.current && !canUseMediaRecorder) {
      alert('Browser does not support speech recognition');
      return;
    }

    if (voiceProcessing || voiceSpeaking) {
      stopVoicePlayback();
      return;
    }

    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      return;
    }

    if (isVoiceActive) {
      shouldSubmitOnEndRef.current = true;
      if (canUseMediaRecorder) {
        mediaRecorderRef.current?.stop();
      } else {
        recognitionRef.current.stop();
      }
    } else {
      transcriptRef.current = '';
      setVoiceError('');
      shouldSubmitOnEndRef.current = true;

      // Prefer local browser audio capture + server transcription to avoid
      // Web Speech API "network" failures on Chromium speech backends.
      if (canUseMediaRecorder) {
        startMediaRecording();
        return;
      }

      try {
        recognitionRef.current.start();
      } catch (e) {
        console.error('[VoiceAgent] Failed to start speech recognition', {
          error: e,
          isSecureContext: window.isSecureContext,
          protocol: window.location?.protocol || null,
          host: window.location?.host || null,
          hint: 'Check browser compatibility and microphone permissions. Speech recognition generally works best on Chromium-based browsers.',
        });
        shouldSubmitOnEndRef.current = false;
        setVoiceError('Unable to start microphone');
      }
    }
  };

  if (tickers.length === 0) {
    return (
      <div style={sidebarStyle}>
        <p style={{ textAlign: 'center', padding: '20px' }}>No tickers available</p>
      </div>
    );
  }

  return (
    <>
      <div style={collapsed ? collapsedStyle : sidebarStyle}>
        <button
          onClick={() => setCollapsed(!collapsed)}
          style={{
            ...toggleButtonStyle,
            alignSelf: collapsed ? 'center' : 'flex-end',
          }}
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? '»' : '«'}
        </button>

{!collapsed && (
            <div style={sidebarContentStyle}>
              <ProfileSection onClick={() => setShowSettings(true)} />
              <StrategiesSection onClick={() => setShowStrategyDialog(true)} />
              <VoiceAgentSection
                isActive={isVoiceActive}
                voiceProcessing={voiceProcessing}
                voiceSpeaking={voiceSpeaking}
                voiceError={voiceError}
                onClick={toggleVoiceAgent}
              />
            </div>
          )}
      </div>

      {showSettings && (
        <SettingsDialog onClose={() => setShowSettings(false)} />
      )}

      {showStrategyDialog && (
        <StrategyDialog
          open={showStrategyDialog}
          onClose={() => setShowStrategyDialog(false)}
          strategies={strategies}
          selectedStrategy={selectedStrategy}
          strategyActive={false}
          autoTradeEnabled={false}
          tradeAmount=""
          strategyCode={strategyCode}
          codeLoading={false}
          codeError=""
          onStrategySelect={(name) => {
            setSelectedStrategy(name);
            Promise.all([
              fetch(`/api/strategies/${name}`, { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ deactivatePrevious: true })
              }).then(res => res.json()),
              fetch(`/api/strategies/${name}/code`).then(res => res.json())
            ])
              .then(([selectData, codeData]) => {
                if (codeData && codeData.code) {
                  setStrategyCode(codeData.code);
                }
              })
              .catch(err => console.error('Failed to load strategy:', err));
          }}
          onToggleStrategy={() => {}}
          onToggleAutoTrade={() => {}}
          onTradeAmountChange={() => {}}
          onCodeChange={(code) => setStrategyCode(code)}
          onFormatCode={() => {
            fetch('/api/strategies/format-code', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ code: strategyCode }),
            })
              .then(res => res.json())
              .then(data => {
                if (data.code) {
                  setStrategyCode(data.code);
                }
              })
              .catch(err => console.error('Failed to format code:', err));
          }}
          onSaveCode={() => {
            fetch(`/api/strategies/${selectedStrategy}/code`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ code: strategyCode }),
            })
              .catch(err => console.error('Failed to save code:', err));
          }}
        />
      )}

      {showVoiceMarkdown && (
        <VoiceMarkdownDialog
          title={voiceMarkdown.title}
          markdown={voiceMarkdown.markdown}
          onClose={() => setShowVoiceMarkdown(false)}
        />
      )}
    </>
  );
}

const sidebarStyle = {
  width: '200px',
  backgroundColor: '#161b22',
  borderRight: '1px solid #30363d',
  display: 'flex',
  flexDirection: 'column',
  position: 'relative',
};

const collapsedStyle = {
  width: '40px',
  backgroundColor: '#161b22',
  borderRight: '1px solid #30363d',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
};

const toggleButtonStyle = {
  padding: '10px',
  background: 'none',
  border: 'none',
  color: '#8b949e',
  cursor: 'pointer',
  fontSize: '16px',
  width: '40px',
};

const sidebarContentStyle = {
  flex: 1,
  overflowY: 'auto',
  overflowX: 'hidden',
  display: 'flex',
  flexDirection: 'column',
  padding: '0 8px 8px',
};



const profileIconOnlyStyle = {
  padding: '10px',
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  color: '#c9d1d9',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  borderRadius: '6px',
  transition: 'background-color 0.2s, color 0.2s',
};

const strategiesIconOnlyStyle = {
  padding: '10px',
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  color: '#8b949e',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  borderRadius: '6px',
  transition: 'background-color 0.2s, color 0.2s',
};

function StrategiesIconOnly({ onClick }) {
  return (
    <div
      onClick={onClick}
      style={strategiesIconOnlyStyle}
      title="Open Strategy Settings"
      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#238636'; e.currentTarget.style.color = '#ffffff'; }}
      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = '#8b949e'; }}
    >
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d="M19.14 12.94a7.8 7.8 0 0 0 .05-.94 7.8 7.8 0 0 0-.05-.94l2.03-1.58a.5.5 0 0 0 .12-.64l-1.92-3.32a.5.5 0 0 0-.6-.22l-2.39.96a7.2 7.2 0 0 0-1.63-.94l-.36-2.54a.5.5 0 0 0-.49-.42h-3.84a.5.5 0 0 0-.49.42l-.36 2.54c-.58.23-1.13.54-1.63.94l-2.39-.96a.5.5 0 0 0-.6.22L2.7 8.84a.5.5 0 0 0 .12.64l2.03 1.58a7.8 7.8 0 0 0-.05.94c0 .32.02.63.05.94L2.82 14.52a.5.5 0 0 0-.12.64l1.92 3.32a.5.5 0 0 0 .6.22l2.39-.96c.5.4 1.05.71 1.63.94l.36 2.54a.5.5 0 0 0 .49.42h3.84a.5.5 0 0 0-.49-.42l.36-2.54c.58-.23 1.13-.54 1.63-.94l2.39.96a.5.5 0 0 0 .6-.22l1.92-3.32a.5.5 0 0 0-.12-.64l-2.03-1.58ZM12 15.5A3.5 3.5 0 1 1 12 8a3.5 3.5 0 0 1 0 7.5Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

const settingsIconOnlyStyle = {
  padding: '10px',
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  color: '#8b949e',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  borderRadius: '6px',
  transition: 'background-color 0.2s, color 0.2s',
};

function ProfileIconOnly({ onClick }) {
  return (
    <div
      onClick={onClick}
      style={profileIconOnlyStyle}
      title="Open Settings"
      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#238636'; e.currentTarget.style.color = '#ffffff'; }}
      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = '#c9d1d9'; }}
    >
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d="M12 12C14.2091 12 16 10.2091 16 8C16 5.79086 14.2091 4 12 4C9.79086 4 8 5.79086 8 8C8 10.2091 9.79086 12 12 12Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M20 21C20 17.134 16.765 14 12 14C7.235 14 4 17.134 4 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

function SettingsIconOnly({ onClick }) {
  return (
    <div
      onClick={onClick}
      style={settingsIconOnlyStyle}
      title="Open Settings"
      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#238636'; e.currentTarget.style.color = '#ffffff'; }}
      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = '#8b949e'; }}
    >
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d="M12 15C13.6569 15 15 13.6569 15 12C15 10.3431 13.6569 9 12 9C10.3431 9 9 10.3431 9 12C9 13.6569 10.3431 15 12 15Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M19.4 15A1.65 1.65 0 0 0 19.73 16.82L19.79 16.88A2 2 0 1 1 16.96 19.71L16.9 19.65A1.65 1.65 0 0 0 15.08 19.32A1.65 1.65 0 0 0 14.08 20.83V21A2 2 0 1 1 10.08 21V20.91A1.65 1.65 0 0 0 9.08 19.4A1.65 1.65 0 0 0 7.26 19.73L7.2 19.79A2 2 0 1 1 4.37 16.96L4.43 16.9A1.65 1.65 0 0 0 4.76 15.08A1.65 1.65 0 0 0 3.25 14.08H3A2 2 0 1 1 3 10.08H3.09A1.65 1.65 0 0 0 4.6 9.08A1.65 1.65 0 0 0 4.27 7.26L4.21 7.2A2 2 0 1 1 7.04 4.37L7.1 4.43A1.65 1.65 0 0 0 8.92 4.76H9.01A1.65 1.65 0 0 0 10.01 3.25V3A2 2 0 1 1 14.01 3V3.09A1.65 1.65 0 0 0 15.01 4.6A1.65 1.65 0 0 0 16.83 4.27L16.89 4.21A2 2 0 1 1 19.72 7.04L19.66 7.1A1.65 1.65 0 0 0 19.33 8.92V9.01A1.65 1.65 0 0 0 20.84 10.01H21A2 2 0 1 1 21 14.01H20.91A1.65 1.65 0 0 0 19.4 15Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

const profileSectionStyle = {
  padding: '10px',
  cursor: 'pointer',
  color: '#c9d1d9',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: '10px',
  borderRadius: '6px',
  transition: 'background-color 0.2s, color 0.2s',
};

const strategiesSectionStyle = {
  ...profileSectionStyle,
};

function StrategiesSection({ onClick }) {
  return (
    <div
      onClick={onClick}
      style={strategiesSectionStyle}
      title="Open Strategy Settings"
      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#238636'; e.currentTarget.style.color = '#ffffff'; }}
      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = '#c9d1d9'; }}
    >
      <span style={{ fontWeight: '500', fontSize: '14px' }}>Strategies</span>
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d="M19.14 12.94a7.8 7.8 0 0 0 .05-.94 7.8 7.8 0 0 0-.05-.94l2.03-1.58a.5.5 0 0 0 .12-.64l-1.92-3.32a.5.5 0 0 0-.6-.22l-2.39.96a7.2 7.2 0 0 0-1.63-.94l-.36-2.54a.5.5 0 0 0-.49-.42h-3.84a.5.5 0 0 0-.49.42l-.36 2.54c-.58.23-1.13.54-1.63.94l-2.39-.96a.5.5 0 0 0-.6.22L2.7 8.84a.5.5 0 0 0 .12.64l2.03 1.58a7.8 7.8 0 0 0-.05.94c0 .32.02.63.05.94L2.82 14.52a.5.5 0 0 0-.12.64l1.92 3.32a.5.5 0 0 0 .6.22l2.39-.96c.5.4 1.05.71 1.63.94l.36 2.54a.5.5 0 0 0 .49.42h3.84a.5.5 0 0 0-.49-.42l.36-2.54c.58-.23 1.13-.54 1.63-.94l2.39.96a.5.5 0 0 0 .6-.22l1.92-3.32a.5.5 0 0 0-.12-.64l-2.03-1.58ZM12 15.5A3.5 3.5 0 1 1 12 8a3.5 3.5 0 0 1 0 7.5Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

function ProfileSection({ onClick }) {
  return (
    <div
      onClick={onClick}
      style={profileSectionStyle}
      title="Open Settings"
      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#238636'; e.currentTarget.style.color = '#ffffff'; }}
      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = '#c9d1d9'; }}
    >
      <span style={{ fontWeight: '500', fontSize: '14px' }}>User Profile</span>
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d="M12 12C14.2091 12 16 10.2091 16 8C16 5.79086 14.2091 4 12 4C9.79086 4 8 5.79086 8 8C8 10.2091 9.79086 12 12 12Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M20 21C20 17.134 16.765 14 12 14C7.235 14 4 17.134 4 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

function VoiceAgentSection({ isActive, voiceProcessing, voiceSpeaking, voiceError, onClick }) {
  const statusText = voiceSpeaking ? 'Speaking...' : (voiceProcessing ? 'Processing...' : (isActive ? 'Listening...' : (voiceError || 'Idle')));
  const indicator = voiceSpeaking ? 'speaking-indicator' : (voiceProcessing ? 'processing-indicator' : 'recording-indicator');
  const iconColor = voiceError ? '#f85149' : (isActive || voiceProcessing || voiceSpeaking ? '#4af62c' : '#c9d1d9');

  return (
    <div
      onClick={onClick}
      style={{
        ...profileSectionStyle,
        opacity: isActive || voiceProcessing || voiceSpeaking || voiceError ? '1' : '0.7',
      }}
      title={isActive ? "Stop Voice Agent" : "Start Voice Agent"}
      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#238636'; e.currentTarget.style.color = '#ffffff'; }}
      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = iconColor; }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '2px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontWeight: '500', fontSize: '14px' }}>Voice Agent</span>
          {(isActive || voiceProcessing || voiceSpeaking) && (
            <div data-testid={indicator}
              style={{
                width: '8px',
                height: '8px',
                backgroundColor: isActive ? '#f85149' : (voiceSpeaking ? '#3b82f6' : '#4af62c'),
                borderRadius: '50%',
                animation: isActive
                  ? 'pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite'
                  : (voiceSpeaking ? 'pulse 0.8s cubic-bezier(0.4, 0, 0.6, 1) infinite' : 'pulse 0.8s cubic-bezier(0.4, 0, 0.6, 1) infinite'),
              }}
            />
          )}
        </div>
        <span
          style={{
            fontSize: '11px',
            color: voiceError ? '#f85149' : (voiceSpeaking ? '#3b82f6' : '#8b949e'),
          }}
        >
          {statusText}
        </span>
      </div>
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill={isActive ? "#4af62c" : "none"}
        stroke={isActive ? "#4af62c" : "currentColor"}
        strokeWidth="2"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
        <line x1="12" y1="19" x2="12" y2="23" />
        <line x1="8" y1="23" x2="16" y2="23" />
      </svg>
    </div>
  );
}

const voiceProcessingStyle = {
  position: 'absolute',
  top: '-4px',
  right: '-4px',
  width: '10px',
  height: '10px',
  backgroundColor: '#f85149',
  borderRadius: '50%',
  animation: 'pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite',
};

const voiceProcessingActiveStyle = {
  position: 'absolute',
  top: '-4px',
  right: '-4px',
  width: '10px',
  height: '10px',
  backgroundColor: '#4af62c',
  borderRadius: '50%',
  animation: 'pulse 0.8s cubic-bezier(0.4, 0, 0.6, 1) infinite',
};

function VoiceAgentIconOnly({ isActive, voiceProcessing, voiceSpeaking, voiceError, onClick }) {
  const indicator = voiceSpeaking ? 'speaking-indicator' : (voiceProcessing ? 'processing-indicator' : 'recording-indicator');
  const iconColor = voiceError ? '#f85149' : (isActive || voiceSpeaking ? '#4af62c' : (voiceProcessing ? '#3b82f6' : '#c9d1d9'));

  return (
 <div
        onClick={onClick}
        style={profileIconOnlyStyle}
        title={isActive ? "Stop Voice Agent" : "Start Voice Agent"}
        onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#238636'; e.currentTarget.style.color = (isActive || voiceSpeaking) ? '#4af62c' : (voiceProcessing ? '#ffffff' : '#ffffff'); }}
        onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = iconColor; }}
      >
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill={isActive ? "#4af62c" : "none"}
          stroke={isActive ? "#4af62c" : "currentColor"}
          strokeWidth="2"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
          <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
          <line x1="12" y1="19" x2="12" y2="23" />
          <line x1="8" y1="23" x2="16" y2="23" />
        </svg>
        {(isActive || voiceProcessing || voiceSpeaking) && (
          <div data-testid={indicator} style={
            voiceSpeaking ? {
              position: 'absolute',
              top: '-4px',
              right: '-4px',
              width: '10px',
              height: '10px',
              backgroundColor: '#3b82f6',
              borderRadius: '50%',
              animation: 'pulse 0.8s cubic-bezier(0.4, 0, 0.6, 1) infinite',
            } : (voiceProcessing ? voiceProcessingActiveStyle : voiceProcessingStyle)
          } />
        )}
      </div>
  );
}

const tickerListStyle = {
  listStyle: 'none',
  padding: '0',
  margin: '0',
};

const tickerItemStyle = {
  padding: '8px',
  cursor: 'pointer',
  textAlign: 'center',
  transition: 'background-color 0.2s',
};

export default Sidebar;
