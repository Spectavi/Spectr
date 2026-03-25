import React, { useState, useEffect } from 'react';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable';

function WatchlistDialog({ onClose, tickers, onAddTicker, onRemoveTicker, onReorderTicker }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedSuggestion, setSelectedSuggestion] = useState(-1);
  const [items, setItems] = useState(tickers);
  const [tickerDetails, setTickerDetails] = useState({});

  useEffect(() => {
    setItems(tickers);
  }, [tickers]);

  useEffect(() => {
    if (items.length > 0) {
      const promises = items.map((ticker) =>
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
  }, [items]);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  function SortableItem({ ticker, rowIndex }) {
    const { attributes, listeners, setNodeRef, transform } = useSortable({ id: ticker });

    const style = {
      transform: transform ? `translateY(${transform.y}px)` : undefined,
      ...watchlistItemStyle(rowIndex),
    };

    return (
      <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
        <div style={{ display: 'flex', alignItems: 'center', flex: 1, paddingLeft: '4px' }}>
          <div style={{ width: '32px', height: '32px', flexShrink: 0, marginRight: '10px' }}>
            {tickerDetails[ticker] && (
              <img
                src={tickerDetails[ticker]}
                alt={`${ticker} logo`}
                style={{
                  width: '100%',
                  height: '100%',
                  borderRadius: '4px',
                  objectFit: 'contain',
                }}
              />
            )}
          </div>
          <span>{ticker}</span>
        </div>
        <button
          onClick={() => onRemoveTicker(ticker)}
          style={deleteButtonStyle}
        >
          Delete
        </button>
      </div>
    );
  }

  const handleDragEnd = (event) => {
    const { active, over } = event;

    if (!over || active.id === over.id) {
      return;
    }

    const oldIndex = items.indexOf(active.id);
    const newIndex = items.indexOf(over.id);

    if (oldIndex !== -1 && newIndex !== -1 && oldIndex !== newIndex) {
      const newItems = arrayMove(items, oldIndex, newIndex);
      setItems(newItems);
      onReorderTicker?.(newItems);
    }
  };

  useEffect(() => {
    if (searchQuery.length >= 2) {
      const timer = setTimeout(() => {
        fetch(`/api/search-tickers?query=${encodeURIComponent(searchQuery)}`)
          .then(response => response.json())
          .then(data => {
            setSuggestions(Array.isArray(data) ? data : (data && data.data) || []);
            setShowSuggestions(true);
          })
          .catch(err => console.error('Search error:', err));
      }, 300);
      
      return () => clearTimeout(timer);
    } else {
      setShowSuggestions(false);
      setSuggestions([]);
    }
  }, [searchQuery]);

  const handleSuggestionClick = (symbol) => {
    onAddTicker(symbol);
    setSearchQuery('');
    setShowSuggestions(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedSuggestion(prev => 
        prev < suggestions.length - 1 ? prev + 1 : 0
      );
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedSuggestion(prev => prev > 0 ? prev - 1 : -1);
    } else if (e.key === 'Enter' && selectedSuggestion >= 0) {
      e.preventDefault();
      handleSuggestionClick(suggestions[selectedSuggestion].symbol);
    }
  };

  const rootStyle = {
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
  };

  const dialogStyle = {
    backgroundColor: '#161b22',
    border: '1px solid #30363d',
    borderRadius: '8px',
    padding: '24px',
    width: '500px',
    maxHeight: '90vh',
    display: 'flex',
    flexDirection: 'column',
  };

  const headerStyle = {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: '20px',
  };

  const titleStyle = {
    margin: 0,
    color: '#c9d1d9',
    fontSize: '20px',
    flex: 1,
  };

  const closeButtonStyle = {
    background: 'none',
    border: 'none',
    color: '#8b949e',
    cursor: 'pointer',
    fontSize: '24px',
    padding: '5px 10px',
    lineHeight: 1,
  };

  const searchContainerStyle = {
    marginBottom: '20px',
    position: 'relative',
  };

  const resultsContainerStyle = {
    maxHeight: '250px',
    overflowY: 'auto',
    backgroundColor: '#0d1117',
    borderRadius: '6px',
    border: '1px solid #30363d',
    position: 'absolute',
    top: '100%',
    left: 0,
    right: 0,
    zIndex: 100,
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.5)',
  };

  const watchlistContainerStyle = {
    flex: 1,
    overflowY: 'auto',
    backgroundColor: '#0d1117',
    borderRadius: '6px',
    border: '1px solid #30363d',
    marginBottom: '20px',
  };

const watchlistItemStyle = (index) => ({
  padding: '10px 14px',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  borderBottom: '1px solid #30363d',
  backgroundColor: index % 2 === 0 ? '#0d1117' : '#161b22',
});

  const deleteButtonStyle = {
    backgroundColor: '#da3633',
    color: '#ffffff',
    border: 'none',
    padding: '6px 12px',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '12px',
    fontWeight: '500',
  };

  const noResultsStyle = {
    padding: '10px 14px',
    color: '#8b949e',
    textAlign: 'center',
  };

  const inputStyle = {
    width: '100%',
    padding: '10px 14px',
    fontSize: '16px',
    backgroundColor: '#0d1117',
    border: '1px solid #30363d',
    borderRadius: '6px',
    color: '#c9d1d9',
    outline: 'none',
    boxSizing: 'border-box',
  };

  return (
    <div style={rootStyle}>
      <div style={dialogStyle}>
        <div style={headerStyle}>
          <h2 style={titleStyle}>Watchlist</h2>
          <button onClick={onClose} style={closeButtonStyle}>
            ×
          </button>
        </div>

        <div style={searchContainerStyle}>
          <input
            type="text"
            placeholder="Search tickers..."
            autoFocus
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
            style={inputStyle}
          />
{showSuggestions && suggestions.length > 0 && (
             <div style={resultsContainerStyle}>
               {suggestions.map((result, index) => (
 <div
                    key={result.symbol || index}
                    onMouseDown={() => handleSuggestionClick(result.symbol)}
                    onMouseEnter={() => setSelectedSuggestion(index)}
                    style={{
                      padding: '10px 14px',
                      cursor: 'pointer',
                      borderBottom: '1px solid #30363d',
                      backgroundColor: index % 2 === 0 ? '#0d1117' : '#161b22',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                   <div style={{ display: 'flex', alignItems: 'center', flex: 1, paddingLeft: '4px' }}>
                     {result.logo && (
                       <div style={{ width: '32px', height: '32px', flexShrink: 0, marginRight: '10px' }}>
                         <img
                           src={result.logo}
                           alt={`${result.symbol} logo`}
                           style={{
                             width: '100%',
                             height: '100%',
                             borderRadius: '4px',
                             objectFit: 'contain',
                           }}
                         />
                       </div>
                     )}
                     <span style={{ fontWeight: 'bold', fontSize: '14px' }}>{result.symbol}</span>
                   </div>
                   <span style={{ color: '#8b949e', fontSize: '13px' }}>
                     {result.name || ''}
                   </span>
                 </div>
              ))}
            </div>
          )}
        </div>

        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={items}
            strategy={verticalListSortingStrategy}
          >
<div style={watchlistContainerStyle}>
               {items.length > 0 ? (
                 items.map((ticker, index) => (
                   <SortableItem key={ticker} ticker={ticker} rowIndex={index} />
                 ))
               ) : (
                 <p style={noResultsStyle}>No tickers in watchlist</p>
               )}
             </div>
          </SortableContext>
        </DndContext>
      </div>
    </div>
  );
}

export default WatchlistDialog;
