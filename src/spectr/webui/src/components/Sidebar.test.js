import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Sidebar from './Sidebar';

jest.mock('./WatchlistDialog.js', () => {
  return function MockWatchlistDialog({ onClose }) {
    return (
      <div data-testid="mock-watchlist">
        Watchlist
        <button onClick={onClose}>Close</button>
      </div>
    );
  };
});

jest.mock('./SettingsDialog.js', () => {
  return function MockSettingsDialog({ onClose }) {
    return (
      <div data-testid="mock-settings">
        Settings
        <button onClick={onClose}>Close</button>
      </div>
    );
  };
});

describe('Sidebar - Voice Agent Feature', () => {
  const mockTickers = ['AAPL', 'GOOGL', 'MSFT'];
  const originalSpeechRecognition = window.SpeechRecognition;
  const originalWebkitSpeechRecognition = window.webkitSpeechRecognition;
  const originalAlert = window.alert;
  const originalAudio = window.Audio;
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;
  let recognitionInstance = null;

  class MockSpeechRecognition {
    constructor() {
      this.continuous = false;
      this.interimResults = false;
      this.lang = '';
      this.onstart = null;
      this.onresult = null;
      this.onerror = null;
      this.onend = null;
      recognitionInstance = this;
    }

    start() {
      if (this.onstart) {
        this.onstart();
      }
    }

    stop() {
      if (this.onend) {
        this.onend();
      }
    }
  }

  const emitFinalTranscript = (text) => {
    const event = {
      resultIndex: 0,
      results: [
        {
          0: { transcript: text },
          isFinal: true,
        },
      ],
    };
    recognitionInstance.onresult(event);
  };

  beforeEach(() => {
    jest.clearAllMocks();
    recognitionInstance = null;

    window.Audio = jest.fn().mockImplementation(() => {
      const audio = {
        onended: null,
        onerror: null,
        onpause: null,
        ended: false,
        currentTime: 0,
        play: jest.fn().mockImplementation(() => {
          setTimeout(() => {
            audio.ended = true;
            if (typeof audio.onended === 'function') {
              audio.onended();
            }
          }, 0);
          return Promise.resolve();
        }),
        pause: jest.fn().mockImplementation(() => {
          if (typeof audio.onpause === 'function') {
            audio.onpause();
          }
        }),
      };
      return audio;
    });
    URL.createObjectURL = jest.fn(() => 'blob:mock-audio-url');
    URL.revokeObjectURL = jest.fn();

    window.fetch = jest.fn().mockImplementation((url, options) => {
      if (url.includes('/api/profile/')) {
        const ticker = url.split('/').pop();
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ logo: `https://logo.com/${ticker}.png` }),
        });
      }

      if (url.includes('/api/watchlist')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ tickers: mockTickers, success: true }),
        });
      }

      if (url.includes('/api/voice-agent') && options?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, response: 'ok' }),
        });
      }

      if (url.includes('/api/voice-agent/tts') && options?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          blob: () => Promise.resolve(new Blob(['audio'], { type: 'audio/mpeg' })),
        });
      }

      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      });
    });

    window.SpeechRecognition = MockSpeechRecognition;
    window.webkitSpeechRecognition = MockSpeechRecognition;
    window.alert = jest.fn();
  });

  afterEach(() => {
    window.fetch.mockRestore();
    window.SpeechRecognition = originalSpeechRecognition;
    window.webkitSpeechRecognition = originalWebkitSpeechRecognition;
    window.alert = originalAlert;
    window.Audio = originalAudio;
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
  });

  test('renders sidebar with voice agent button', async () => {
    render(<Sidebar tickers={mockTickers} selectedTicker="AAPL" onSelect={() => {}} />);
    await waitFor(() => expect(screen.getByText('Voice Agent')).toBeInTheDocument());
  });

  test('clicking voice agent starts recognition and shows listening state', async () => {
    render(<Sidebar tickers={mockTickers} selectedTicker="AAPL" onSelect={() => {}} />);

    await userEvent.click(screen.getByText('Voice Agent'));

    expect(screen.getByText('Listening...')).toBeInTheDocument();
    expect(screen.getByTestId('recording-indicator')).toBeInTheDocument();
  });

  test('submits transcript when recognition ends and shows processing state', async () => {
    let resolveVoiceRequest;
    window.fetch = jest.fn().mockImplementation((url, options) => {
      if (url.includes('/api/profile/')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ logo: '' }) });
      }
      if (url.includes('/api/watchlist')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ tickers: mockTickers, success: true }) });
      }
      if (url.includes('/api/voice-agent/tts') && options?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          blob: () => Promise.resolve(new Blob(['audio'], { type: 'audio/mpeg' })),
        });
      }
      if (url.includes('/api/voice-agent') && options?.method === 'POST') {
        return new Promise((resolve) => {
          resolveVoiceRequest = resolve;
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    render(<Sidebar tickers={mockTickers} selectedTicker="AAPL" onSelect={() => {}} />);
    await userEvent.click(screen.getByText('Voice Agent'));

    await act(async () => {
      emitFinalTranscript('buy one share of aapl');
      recognitionInstance.onend();
    });

    await waitFor(() => {
      expect(window.fetch).toHaveBeenCalledWith(
        '/api/voice-agent',
        expect.objectContaining({ method: 'POST' })
      );
      expect(screen.getByText('Processing...')).toBeInTheDocument();
      expect(screen.getByTestId('processing-indicator')).toBeInTheDocument();
    });

    await act(async () => {
      resolveVoiceRequest({
        ok: true,
        json: () => Promise.resolve({ success: true, response: 'done' }),
      });
    });

    await waitFor(() => {
      expect(screen.getByText('Idle')).toBeInTheDocument();
    });
  });

  test('shows speech service unavailable when recognition network error occurs', async () => {
    render(<Sidebar tickers={mockTickers} selectedTicker="AAPL" onSelect={() => {}} />);

    await userEvent.click(screen.getByText('Voice Agent'));

    await act(async () => {
      recognitionInstance.onerror({ error: 'network' });
    });

    await waitFor(() => {
      expect(screen.getByText('Speech service unavailable')).toBeInTheDocument();
    });
  });

  test('opens markdown dialog when voice API returns markdown payload', async () => {
    window.fetch = jest.fn().mockImplementation((url, options) => {
      if (url.includes('/api/voice-agent/tts') && options?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          blob: () => Promise.resolve(new Blob(['audio'], { type: 'audio/mpeg' })),
        });
      }
      if (url.includes('/api/voice-agent') && options?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            success: true,
            response: 'done',
            markdown: {
              title: 'Market Summary',
              markdown: '## Highlights\n- AAPL up 2%',
            },
          }),
        });
      }
      if (url.includes('/api/profile/')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ logo: '' }) });
      }
      if (url.includes('/api/watchlist')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ tickers: mockTickers, success: true }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    render(<Sidebar tickers={mockTickers} selectedTicker="AAPL" onSelect={() => {}} />);
    await userEvent.click(screen.getByText('Voice Agent'));

    await act(async () => {
      emitFinalTranscript('show me summary');
      recognitionInstance.onend();
    });

    await waitFor(() => {
      expect(screen.getByText('Market Summary')).toBeInTheDocument();
      expect(screen.getByText(/Highlights/)).toBeInTheDocument();
      expect(screen.getByText(/AAPL up 2%/)).toBeInTheDocument();
    });
  });

  test('handles browser without speech recognition support', async () => {
    delete window.SpeechRecognition;
    delete window.webkitSpeechRecognition;

    render(<Sidebar tickers={mockTickers} selectedTicker="AAPL" onSelect={() => {}} />);
    await userEvent.click(screen.getByText('Voice Agent'));

    expect(window.alert).toHaveBeenCalledWith('Browser does not support speech recognition');
  });
});
