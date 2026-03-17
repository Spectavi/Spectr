import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github-dark.css';

function VoiceMarkdownDialog({ markdown, title, onClose }) {
  return (
    <div style={overlayStyle}>
      <div style={dialogStyle}>
        <div style={headerStyle}>
          <h2 style={titleStyle}>{title || 'Voice Agent Details'}</h2>
          <button onClick={onClose} style={closeButtonStyle} aria-label="Close markdown dialog">×</button>
        </div>
        <div style={contentStyle} className="voice-markdown-content">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
            components={{
              a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
            }}
          >
            {markdown || 'No content provided.'}
          </ReactMarkdown>
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
  backgroundColor: 'rgba(0, 0, 0, 0.72)',
  zIndex: 1200,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '20px',
  boxSizing: 'border-box',
};

const dialogStyle = {
  width: 'min(980px, 96vw)',
  maxHeight: '88vh',
  backgroundColor: '#0d1117',
  border: '1px solid #30363d',
  borderRadius: '10px',
  display: 'flex',
  flexDirection: 'column',
  boxShadow: '0 16px 48px rgba(0, 0, 0, 0.45)',
};

const headerStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  borderBottom: '1px solid #30363d',
  padding: '14px 16px',
};

const titleStyle = {
  margin: 0,
  fontSize: '16px',
  color: '#e6edf3',
};

const closeButtonStyle = {
  width: '30px',
  height: '30px',
  border: '1px solid #30363d',
  borderRadius: '6px',
  backgroundColor: '#161b22',
  color: '#c9d1d9',
  fontSize: '20px',
  lineHeight: '1',
  cursor: 'pointer',
};

const contentStyle = {
  padding: '18px 20px 20px',
  overflowY: 'auto',
  color: '#c9d1d9',
  lineHeight: 1.55,
};

export default VoiceMarkdownDialog;
