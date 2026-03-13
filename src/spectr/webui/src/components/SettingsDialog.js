import React, { useState } from 'react';
import PortfolioDialog from './PortfolioDialog';

function SettingsDialog({ onClose }) {
  const [activeTab, setActiveTab] = useState('portfolio');

  return (
    <div style={overlayStyle}>
      <div style={dialogStyle}>
        <div style={sidebarStyle}>
          <button
            onClick={() => setActiveTab('portfolio')}
            style={{
              ...sidebarButtonStyle,
              backgroundColor: activeTab === 'portfolio' ? '#238636' : 'transparent',
              color: activeTab === 'portfolio' ? '#ffffff' : '#c9d1d9',
            }}
          >
            Portfolio
          </button>
        </div>
        <div style={contentStyle}>
          {activeTab === 'portfolio' && (
            <PortfolioDialog embedded showCloseButton={false} />
          )}
        </div>
        <button onClick={onClose} style={xButtonStyle}>×</button>
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
  backgroundColor: 'rgba(0, 0, 0, 0.7)',
  zIndex: 1000,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  overflowY: 'auto',
  padding: '20px',
  boxSizing: 'border-box',
};

const dialogStyle = {
  backgroundColor: '#161b22',
  border: '1px solid #30363d',
  borderRadius: '8px',
  padding: '24px',
  maxWidth: '1100px',
  width: '90%',
  display: 'flex',
  overflow: 'visible',
  position: 'relative',
};

const sidebarStyle = {
  width: '150px',
  borderRight: '1px solid #30363d',
  paddingRight: '20px',
  marginRight: '20px',
};

const sidebarButtonStyle = {
  width: '100%',
  padding: '12px 8px',
  marginBottom: '8px',
  borderRadius: '6px',
  border: 'none',
  cursor: 'pointer',
  fontSize: '14px',
  fontWeight: '500',
  textAlign: 'left',
};

const contentStyle = {
  flex: 1,
  overflow: 'visible',
};

const closeButtonStyle = {
  alignSelf: 'flex-end',
  backgroundColor: '#da3633',
  color: '#ffffff',
  border: 'none',
  padding: '8px 16px',
  borderRadius: '6px',
  cursor: 'pointer',
  fontSize: '14px',
  fontWeight: '600',
  marginLeft: '16px',
  height: 'fit-content',
};

const xButtonStyle = {
  position: 'absolute',
  top: '24px',
  right: '24px',
  width: '32px',
  height: '32px',
  backgroundColor: '#30363d',
  color: '#c9d1d9',
  border: 'none',
  borderRadius: '6px',
  cursor: 'pointer',
  fontSize: '20px',
  fontWeight: 'bold',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  lineHeight: 1,
};

export default SettingsDialog;
