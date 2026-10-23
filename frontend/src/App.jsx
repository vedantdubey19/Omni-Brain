import React, { useState, useEffect, useRef } from 'react';
import './App.css';

// Automatically detect backend URL
const getBackendUrl = () => {
  if (import.meta.env.VITE_BACKEND_URL) {
    return import.meta.env.VITE_BACKEND_URL.replace(/\/$/, '');
  }
  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1') {
      return 'http://localhost:8000';
    }
  }
  return 'https://omnibrain-backend-fw8h.onrender.com';
};

const BACKEND_URL = getBackendUrl();

export default function App() {
  const [backendStatus, setBackendStatus] = useState('checking'); // 'healthy' | 'offline' | 'checking'
  const [activeTab, setActiveTab] = useState('pdf'); // 'pdf' | 'csv' | 'image'
  const [file, setFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatusText, setUploadStatusText] = useState('');
  
  // Track currently active uploaded file
  const [currentDoc, setCurrentDoc] = useState(null); // { name, type, detail }

  // Chat conversation
  const [messages, setMessages] = useState([]);
  const [queryInput, setQueryInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [expandedDetails, setExpandedDetails] = useState({});

  const chatBottomRef = useRef(null);
  const fileInputRef = useRef(null);

  // Check Backend Health on Mount
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/health`, { signal: AbortSignal.timeout(6000) });
        if (res.ok) {
          setBackendStatus('healthy');
        } else {
          setBackendStatus('offline');
        }
      } catch (err) {
        console.warn('Health check warning:', err);
        setBackendStatus('offline');
      }
    };
    checkHealth();
  }, []);

  // Auto-scroll chat to bottom
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Handle Drag & Drop / File Selection
  const handleFileChange = (selectedFile) => {
    if (!selectedFile) return;
    setFile(selectedFile);

    const ext = selectedFile.name.split('.').pop().toLowerCase();
    if (['png', 'jpg', 'jpeg', 'webp'].includes(ext)) {
      setActiveTab('image');
      const reader = new FileReader();
      reader.onload = (e) => setImagePreview(e.target.result);
      reader.readAsDataURL(selectedFile);
    } else if (ext === 'csv') {
      setActiveTab('csv');
      setImagePreview(null);
    } else {
      setActiveTab('pdf');
      setImagePreview(null);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileChange(e.dataTransfer.files[0]);
    }
  };

  // Upload Document Pipeline
  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    setUploadProgress(15);
    setUploadStatusText('Uploading file to OmniBrain Gateway...');

    const ext = file.name.split('.').pop().toLowerCase();

    try {
      const formData = new FormData();
      formData.append('file', file);

      // 1. PDF Upload -> Poll Status
      if (ext === 'pdf') {
        const res = await fetch(`${BACKEND_URL}/api/v1/upload`, {
          method: 'POST',
          body: formData,
        });

        if (!res.ok) throw new Error(`Upload failed with HTTP ${res.status}`);
        const data = await res.json();
        const jobId = data.job_id;

        setUploadProgress(40);
        setUploadStatusText('Queued for OCR & vector indexing...');

        // Poll job status
        let completed = false;
        const maxPoll = 40;
        for (let i = 0; i < maxPoll; i++) {
          await new Promise((r) => setTimeout(r, 1500));
          const statusRes = await fetch(`${BACKEND_URL}/api/v1/ingest/status/${jobId}`);
          if (statusRes.ok) {
            const statusData = await statusRes.json();
            if (statusData.status === 'PROCESSING') {
              setUploadProgress(70);
              setUploadStatusText(statusData.message || 'Extracting text and chunking points...');
            } else if (statusData.status === 'COMPLETED') {
              setUploadProgress(100);
              setUploadStatusText('Document indexed successfully into vector database!');
              setCurrentDoc({ name: file.name, type: 'pdf', detail: 'Ready for SearchAgent RAG queries' });
              completed = true;
              break;
            } else if (statusData.status === 'FAILED') {
              throw new Error(statusData.error_detail || 'PDF parsing failed.');
            }
          }
        }

        if (!completed) {
          setCurrentDoc({ name: file.name, type: 'pdf', detail: 'Background processing ongoing' });
        }
      } 
      // 2. CSV Upload -> Direct Table Load
      else if (ext === 'csv') {
        const res = await fetch(`${BACKEND_URL}/api/v1/sql/load-csv`, {
          method: 'POST',
          body: formData,
        });

        if (!res.ok) throw new Error(`CSV load failed with HTTP ${res.status}`);
        const data = await res.json();
        setUploadProgress(100);
        setUploadStatusText(`Loaded ${data.rows_loaded || 0} rows into analytical SQLite database!`);
        setCurrentDoc({
          name: file.name,
          type: 'csv',
          detail: `Structured table (${data.rows_loaded || 0} rows, columns: ${(data.columns || []).slice(0, 4).join(', ')}...)`
        });
      } 
      // 3. Image Upload -> Vision Registration
      else {
        const res = await fetch(`${BACKEND_URL}/api/v1/vision/upload-image`, {
          method: 'POST',
          body: formData,
        });

        if (!res.ok) throw new Error(`Image registration failed with HTTP ${res.status}`);
        setUploadProgress(100);
        setUploadStatusText('Visual artifact registered for VisionAgent multimodal analysis!');
        setCurrentDoc({ name: file.name, type: 'image', detail: 'Registered for Multimodal Chart Reasoning' });
      }

      setFile(null);
    } catch (err) {
      alert(`Upload Notice: ${err.message}`);
      setUploadStatusText(`Error: ${err.message}`);
    } finally {
      setTimeout(() => setUploading(false), 2000);
    }
  };

  // Submit Query to LangGraph Multi-Agent Orchestrator
  const submitQuery = async (queryText) => {
    const trimmed = (queryText || queryInput).trim();
    if (!trimmed || loading) return;

    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: trimmed,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setMessages((prev) => [...prev, userMessage]);
    setQueryInput('');
    setLoading(true);

    try {
      const payload = {
        question: trimmed,
        document_id: currentDoc ? currentDoc.name : null,
      };

      const res = await fetch(`${BACKEND_URL}/api/v1/agent/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error(`Agent query failed with HTTP ${res.status}`);
      }

      const data = await res.json();

      const assistantMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: data.final_answer || 'No response returned from agent pipeline.',
        agent: data.selected_agent || (currentDoc?.type === 'csv' ? 'sql_agent' : currentDoc?.type === 'image' ? 'vision_agent' : 'search_agent'),
        metadata: data.metadata || {},
        sources: data.retrieved_chunks || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      const errorMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: `⚠️ Unable to complete request: ${err.message}. Please check that the backend gateway is reachable.`,
        agent: 'error',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitQuery();
    }
  };

  // Toggle detail accordions for citations/SQL queries
  const toggleAccordion = (id) => {
    setExpandedDetails((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // Safe formatting for assistant markdown text
  const formatText = (text) => {
    if (!text) return '';
    
    // Split lines for formatting
    const lines = text.split('\n');
    return lines.map((line, idx) => {
      // Bold syntax
      let formatted = line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      // Inline code syntax
      formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');

      // Unordered list
      if (line.trim().startsWith('* ') || line.trim().startsWith('- ')) {
        const itemContent = formatted.replace(/^[\s]*[\*\-]\s+/, '');
        return (
          <li key={idx} dangerouslySetInnerHTML={{ __html: itemContent }} />
        );
      }

      // Headers
      if (line.startsWith('### ')) {
        return <h4 key={idx} dangerouslySetInnerHTML={{ __html: formatted.replace('### ', '') }} />;
      }
      if (line.startsWith('## ')) {
        return <h3 key={idx} dangerouslySetInnerHTML={{ __html: formatted.replace('## ', '') }} />;
      }

      if (!line.trim()) {
        return <div key={idx} className="line-break" />;
      }

      return (
        <p key={idx} dangerouslySetInnerHTML={{ __html: formatted }} />
      );
    });
  };

  return (
    <div className="app-container">
      {/* Top Navigation Bar */}
      <header className="top-nav">
        <div className="nav-brand">
          <div className="brand-badge">
            <span className="spark-icon">✨</span>
          </div>
          <div className="brand-text">
            <span className="brand-title">OmniBrain</span>
            <span className="brand-tag">Multi-Modal Intelligence</span>
          </div>
        </div>

        <div className="nav-actions">
          <div className={`status-pill ${backendStatus}`}>
            <span className="status-dot"></span>
            {backendStatus === 'healthy' ? 'Gateway Live' : backendStatus === 'checking' ? 'Connecting...' : 'Gateway Offline'}
          </div>
          {messages.length > 0 && (
            <button className="clear-btn" onClick={() => setMessages([])} title="Start new session">
              Clear Chat
            </button>
          )}
        </div>
      </header>

      {/* Main Content Area */}
      <main className="main-content">
        {/* Hero Section */}
        <section className="hero-section">
          <div className="hero-pill">
            <span className="sparkle">✦</span> LangGraph Agent Orchestrator
          </div>
          <h1 className="hero-title">Research, Financials & Vision Intelligence</h1>
          <p className="hero-subtitle">
            Upload corporate PDFs, historical financial CSV tables, or charts.
            LangGraph dynamically orchestrates each query across Search, SQL, and Vision agents.
          </p>
        </section>

        {/* Multi-File Ingestion Card */}
        <section className="upload-card">
          <div className="card-header">
            <span className="card-title">Document & Data Ingestion</span>
            {currentDoc && (
              <span className="active-doc-badge">
                Active: <strong>{currentDoc.name}</strong> ({currentDoc.type.toUpperCase()})
              </span>
            )}
          </div>

          <div
            className={`dropzone ${file ? 'has-file' : ''}`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: 'none' }}
              accept=".pdf,.csv,.png,.jpg,.jpeg,.webp"
              onChange={(e) => handleFileChange(e.target.files?.[0])}
            />

            {!file ? (
              <div className="dropzone-content">
                <div className="upload-icon-circle">📂</div>
                <div className="dropzone-text">
                  <strong>Click to upload</strong> or drag and drop files here
                </div>
                <div className="dropzone-subtext">
                  Supports PDF documents, CSV financial tables, and PNG/JPG charts (up to 25MB)
                </div>
              </div>
            ) : (
              <div className="file-selected-view">
                <div className="file-info-row">
                  <span className="file-icon">
                    {activeTab === 'pdf' ? '📄' : activeTab === 'csv' ? '📊' : '🖼️'}
                  </span>
                  <div className="file-details">
                    <span className="file-name">{file.name}</span>
                    <span className="file-size">{(file.size / 1024).toFixed(1)} KB</span>
                  </div>
                </div>

                {imagePreview && (
                  <div className="image-preview-box">
                    <img src={imagePreview} alt="Preview" />
                  </div>
                )}
              </div>
            )}
          </div>

          {file && (
            <div className="upload-action-row">
              <button
                className="upload-submit-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  handleUpload();
                }}
                disabled={uploading}
              >
                {uploading ? 'Processing...' : `Ingest & Register ${file.name.split('.').pop().toUpperCase()}`}
              </button>
            </div>
          )}

          {uploading && (
            <div className="progress-container">
              <div className="progress-bar-bg">
                <div className="progress-bar-fill" style={{ width: `${uploadProgress}%` }}></div>
              </div>
              <span className="progress-status-text">{uploadStatusText}</span>
            </div>
          )}
        </section>

        {/* 2x2 Suggestion Cards */}
        {messages.length === 0 && (
          <section className="suggestions-grid">
            <button
              className="suggestion-card"
              onClick={() => submitQuery('Please provide a comprehensive executive summary of this document.')}
            >
              <div className="card-icon">📄</div>
              <div className="card-body">
                <strong>Summarize this document</strong>
                <span>Extract core overview, takeaways, and strategic themes</span>
              </div>
              <span className="card-arrow">→</span>
            </button>

            <button
              className="suggestion-card"
              onClick={() => submitQuery('Please analyze the chart, identify all data points, trends, and key highlights.')}
            >
              <div className="card-icon">📊</div>
              <div className="card-body">
                <strong>Analyze the charts</strong>
                <span>Inspect visual trends, quarterly peaks, and anomalies</span>
              </div>
              <span className="card-arrow">→</span>
            </button>

            <button
              className="suggestion-card"
              onClick={() => submitQuery('What are the key findings, metrics, and highlights in this document?')}
            >
              <div className="card-icon">🔍</div>
              <div className="card-body">
                <strong>List the key findings</strong>
                <span>Retrieve revenue numbers, margins, and operational metrics</span>
              </div>
              <span className="card-arrow">→</span>
            </button>

            <button
              className="suggestion-card"
              onClick={() => submitQuery('What are the primary risks, challenges, and concerns mentioned?')}
            >
              <div className="card-icon">⚠️</div>
              <div className="card-body">
                <strong>What are the risks mentioned?</strong>
                <span>Pinpoint supply chain, legal, or macroeconomic risk factors</span>
              </div>
              <span className="card-arrow">→</span>
            </button>
          </section>
        )}

        {/* Chat Feed */}
        <section className="chat-thread">
          {messages.map((msg) => (
            <div key={msg.id} className={`chat-message ${msg.role}`}>
              {msg.role === 'user' ? (
                <div className="user-bubble">
                  <div className="message-text">{msg.content}</div>
                  <span className="msg-time">{msg.timestamp}</span>
                </div>
              ) : (
                <div className="assistant-card">
                  <div className="assistant-header">
                    <div className="agent-badge-wrapper">
                      {msg.agent === 'search_agent' && (
                        <span className="agent-badge search">🔍 SearchAgent (Qdrant RAG)</span>
                      )}
                      {msg.agent === 'sql_agent' && (
                        <span className="agent-badge sql">📊 SQLAgent (SQLite Engine)</span>
                      )}
                      {msg.agent === 'vision_agent' && (
                        <span className="agent-badge vision">👁️ VisionAgent (Multimodal Vision)</span>
                      )}
                      {msg.agent === 'error' && (
                        <span className="agent-badge error">⚠️ Notice</span>
                      )}
                    </div>
                    <span className="msg-time">{msg.timestamp}</span>
                  </div>

                  <div className="message-body">{formatText(msg.content)}</div>

                  {/* Collapsible Metadata Drawer (SQL or Citations) */}
                  {(msg.metadata?.sql_query || (msg.sources && msg.sources.length > 0)) && (
                    <div className="metadata-drawer">
                      <button
                        className="drawer-toggle-btn"
                        onClick={() => toggleAccordion(msg.id)}
                      >
                        {expandedDetails[msg.id] ? '▲ Hide Grounding Details' : '▼ View Verification & Citations'}
                      </button>

                      {expandedDetails[msg.id] && (
                        <div className="drawer-content">
                          {msg.metadata?.sql_query && (
                            <div className="sql-code-block">
                              <span className="code-label">Executed Read-Only SQL Query:</span>
                              <code>{msg.metadata.sql_query}</code>
                            </div>
                          )}

                          {msg.sources && msg.sources.length > 0 && (
                            <div className="sources-list">
                              <span className="sources-label">Retrieved Vector Chunks:</span>
                              {msg.sources.map((src, i) => (
                                <div key={i} className="source-item">
                                  <div className="source-header">
                                    <span className="source-name">📄 {src.source || currentDoc?.name || 'Document'}</span>
                                    {src.page && <span className="source-page">Page {src.page}</span>}
                                    {src.score && (
                                      <span className="source-score">Confidence: {(src.score * 100).toFixed(1)}%</span>
                                    )}
                                  </div>
                                  <p className="source-snippet">"{src.content}"</p>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="chat-message assistant">
              <div className="assistant-card loading-state">
                <div className="pulsing-dots">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
                <span className="loading-text">Orchestrating agent reasoning via LangGraph...</span>
              </div>
            </div>
          )}

          <div ref={chatBottomRef} />
        </section>
      </main>

      {/* Floating Bottom Input Bar */}
      <footer className="input-bar-container">
        <div className="input-pill">
          <input
            type="text"
            className="query-input"
            placeholder="Ask OmniBrain anything about your document, financials, or charts..."
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
          />
          <button
            className="send-button"
            onClick={() => submitQuery()}
            disabled={!queryInput.trim() || loading}
            aria-label="Send query"
          >
            {loading ? (
              <span className="button-spinner"></span>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            )}
          </button>
        </div>
      </footer>
    </div>
  );
}
