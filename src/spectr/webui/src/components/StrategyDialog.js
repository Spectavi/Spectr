import React, { useMemo, useRef, useCallback } from 'react';
import hljs from 'highlight.js/lib/core';
import python from 'highlight.js/lib/languages/python';
import 'highlight.js/styles/github-dark.css';

hljs.registerLanguage('python', python);

function StrategyDialog({
  open,
  onClose,
  strategies,
  selectedStrategy,
  strategyActive,
  autoTradeEnabled,
  tradeAmount,
  strategyCode,
  codeLoading,
  codeError,
  onStrategySelect,
  onToggleStrategy,
  onToggleAutoTrade,
  onTradeAmountChange,
  onCodeChange,
  onFormatCode,
  onSaveCode,
}) {
  const textareaRef = useRef(null);
  const highlightRef = useRef(null);

  const highlightedCode = useMemo(() => {
    const source = strategyCode || '# Select a strategy to view code';
    try {
      return hljs.highlight(source, { language: 'python' }).value;
    } catch (err) {
      return hljs.highlightAuto(source).value;
    }
  }, [strategyCode]);

  const syncScroll = useCallback(() => {
    if (!textareaRef.current || !highlightRef.current) return;
    const textarea = textareaRef.current;
    const highlight = highlightRef.current;

    const textareaMaxTop = textarea.scrollHeight - textarea.clientHeight;
    const highlightMaxTop = highlight.scrollHeight - highlight.clientHeight;
    const topRatio = textareaMaxTop > 0 ? textarea.scrollTop / textareaMaxTop : 0;
    highlight.scrollTop = topRatio * Math.max(highlightMaxTop, 0);

    const textareaMaxLeft = textarea.scrollWidth - textarea.clientWidth;
    const highlightMaxLeft = highlight.scrollWidth - highlight.clientWidth;
    const leftRatio = textareaMaxLeft > 0 ? textarea.scrollLeft / textareaMaxLeft : 0;
    highlight.scrollLeft = leftRatio * Math.max(highlightMaxLeft, 0);
  }, []);

  if (!open) return null;

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={dialogStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>
          <h2 style={{ margin: 0, fontSize: '18px' }}>Strategy Settings</h2>
          <button onClick={onClose} style={closeButtonStyle} aria-label="Close strategy dialog">x</button>
        </div>

	        <div style={topRowStyle}>
	          <div style={controlBlockStyle}>
	            <label style={labelStyle}>Strategy</label>
	            <select
	              value={selectedStrategy}
	              onChange={(e) => onStrategySelect(e.target.value)}
	              style={{ ...inputStyle, width: '150px' }}
	            >
              <option value="">Select strategy...</option>
              {strategies.map((strategy) => (
                <option key={strategy} value={strategy}>
                  {strategy}
                </option>
              ))}
            </select>
          </div>

          <div style={controlBlockStyle}>
            <label style={labelStyle}>Status</label>
	            <button
	              onClick={onToggleStrategy}
	              style={{
	                ...actionButtonStyle,
	                width: '100px',
	                backgroundColor: strategyActive ? '#238636' : '#da3633',
	              }}
	            >
              {strategyActive ? 'Deactivate' : 'Activate'}
            </button>
          </div>
        </div>

	        <div style={bottomRowStyle}>
	          <div style={controlBlockStyle}>
	            <label style={labelStyle}>Trade Amount (USD)</label>
	            <input
              type="number"
              min="0"
              step="0.01"
	              value={tradeAmount}
	              onChange={(e) => onTradeAmountChange(e.target.value)}
	              style={{ ...inputStyle, width: '150px' }}
	              placeholder="0.00"
	            />
	          </div>

	          <div style={{ ...controlBlockStyle, width: '100px' }}>
	            <label style={{ ...labelStyle, whiteSpace: 'nowrap' }}>Auto-Trade</label>
	            <button
              onClick={onToggleAutoTrade}
              aria-pressed={autoTradeEnabled}
              title={autoTradeEnabled ? 'Disable auto-trade' : 'Enable auto-trade'}
              style={{
                ...toggleSwitchStyle,
                backgroundColor: autoTradeEnabled ? '#238636' : '#30363d',
              }}
            >
              <span
                style={{
                  ...toggleKnobStyle,
                  transform: autoTradeEnabled ? 'translateX(24px)' : 'translateX(0)',
                }}
              />
            </button>
          </div>
        </div>

        <div style={editorHeaderStyle}>
          <h3 style={{ margin: 0, fontSize: '16px' }}>Python Strategy Editor</h3>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button onClick={onFormatCode} style={{ ...miniButtonStyle, backgroundColor: '#6e40c9' }}>
              Format
            </button>
            <button onClick={onSaveCode} style={{ ...miniButtonStyle, backgroundColor: '#238636' }}>
              Save
            </button>
          </div>
        </div>

        {codeLoading && <div style={mutedTextStyle}>Loading strategy code...</div>}
        {codeError && <div style={errorTextStyle}>{codeError}</div>}

        <div style={editorPaneStyle}>
          <pre ref={highlightRef} style={highlightLayerStyle} aria-hidden="true">
            <code dangerouslySetInnerHTML={{ __html: highlightedCode }} />
          </pre>
          <textarea
            ref={textareaRef}
            value={strategyCode}
            onChange={(e) => onCodeChange(e.target.value)}
            onScroll={syncScroll}
            spellCheck={false}
            style={textareaStyle}
            placeholder="Strategy code"
          />
        </div>
      </div>
    </div>
  );
}

const overlayStyle = {
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  backgroundColor: 'rgba(1, 4, 9, 0.8)',
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'center',
  zIndex: 1200,
  padding: '20px',
};

const dialogStyle = {
  width: 'min(850px, 100%)',
  maxHeight: '90vh',
  overflow: 'auto',
  backgroundColor: '#0d1117',
  border: '1px solid #30363d',
  borderRadius: '10px',
  padding: '16px',
  color: '#c9d1d9',
};

const headerStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: '12px',
};

const closeButtonStyle = {
  border: 'none',
  borderRadius: '6px',
  width: '30px',
  height: '30px',
  backgroundColor: '#30363d',
  color: '#c9d1d9',
  cursor: 'pointer',
};

const topRowStyle = {
  display: 'flex',
  gap: '16px',
  flexWrap: 'wrap',
  alignItems: 'flex-end',
  marginBottom: '12px',
};

const bottomRowStyle = {
  display: 'flex',
  gap: '16px',
  flexWrap: 'wrap',
  alignItems: 'flex-end',
  marginBottom: '16px',
};

const controlBlockStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: '8px',
};

const labelStyle = {
  fontSize: '13px',
  color: '#8b949e',
};

const inputStyle = {
  width: '100%',
  border: '1px solid #30363d',
  borderRadius: '6px',
  backgroundColor: '#161b22',
  color: '#c9d1d9',
  padding: '10px',
};

const actionButtonStyle = {
  border: 'none',
  borderRadius: '6px',
  color: '#ffffff',
  fontWeight: 600,
  cursor: 'pointer',
  padding: '10px',
};

const toggleSwitchStyle = {
  width: '52px',
  height: '28px',
  borderRadius: '999px',
  border: '1px solid #30363d',
  cursor: 'pointer',
  padding: '2px',
  display: 'inline-flex',
  alignItems: 'center',
  transition: 'background-color 0.2s ease',
};

const toggleKnobStyle = {
  width: '22px',
  height: '22px',
  borderRadius: '50%',
  backgroundColor: '#ffffff',
  transition: 'transform 0.2s ease',
};

const editorHeaderStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  marginBottom: '10px',
};

const miniButtonStyle = {
  border: 'none',
  borderRadius: '6px',
  color: '#ffffff',
  fontWeight: 600,
  cursor: 'pointer',
  padding: '8px 12px',
};

const mutedTextStyle = {
  color: '#8b949e',
  marginBottom: '8px',
};

const errorTextStyle = {
  color: '#f85149',
  marginBottom: '8px',
};

const editorPaneStyle = {
  position: 'relative',
  minHeight: '420px',
  border: '1px solid #30363d',
  borderRadius: '8px',
  backgroundColor: '#0b1220',
  overflow: 'hidden',
};

const textareaStyle = {
  position: 'absolute',
  inset: 0,
  minHeight: '100%',
  margin: 0,
  resize: 'vertical',
  border: 'none',
  borderRadius: 0,
  backgroundColor: 'transparent',
  color: 'transparent',
  caretColor: '#c9d1d9',
  fontSize: '13px',
  lineHeight: 1.45,
  padding: '12px',
  overflow: 'auto',
  whiteSpace: 'pre',
  fontFamily: "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace",
  boxSizing: 'border-box',
};

const highlightLayerStyle = {
  position: 'absolute',
  inset: 0,
  minHeight: '420px',
  margin: 0,
  pointerEvents: 'none',
  overflow: 'auto',
  padding: '12px',
  fontSize: '13px',
  lineHeight: 1.45,
  whiteSpace: 'pre',
  fontFamily: "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace",
  boxSizing: 'border-box',
};

export default StrategyDialog;
