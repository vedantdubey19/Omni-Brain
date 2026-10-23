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
  const [currentView, setCurrentView] = useState('app'); // 'app' | '404' | 'privacy' | 'terms'
  const [backendStatus, setBackendStatus] = useState('checking'); // 'healthy' | 'offline' | 'checking'
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  
  // File upload state
  const [file, setFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatusText, setUploadStatusText] = useState('');
  const [currentDoc, setCurrentDoc] = useState(null); // { name, type, detail }

  // Chat conversation
  const [messages, setMessages] = useState([]);
  const [queryInput, setQueryInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [expandedDetails, setExpandedDetails] = useState({});
  const [copiedId, setCopiedId] = useState(null);

  // Toast notifications (Success and Error messages)
  const [toasts, setToasts] = useState([]);

  const chatBottomRef = useRef(null);
  const fileInputRef = useRef(null);

  // Dynamic Page Title
  useEffect(() => {
    if (currentView === '404') {
      document.title = '404 - Page Not Found | OmniBrain';
    } else if (currentDoc) {
      document.title = `OmniBrain | ${currentDoc.name}`;
    } else {
      document.title = 'OmniBrain | Multi-Modal Research, Financials & Vision Intelligence';
    }
  }, [currentView, currentDoc]);

  // Toast Notification Helper
  const showToast = (message, type = 'info') => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  };

  // Check Backend Health on Mount
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/health`, { signal: AbortSignal.timeout(5000) });
        if (res.ok) {
          setBackendStatus('healthy');
        } else {
          setBackendStatus('offline');
        }
      } catch (err) {
        setBackendStatus('offline');
      }
    };
    checkHealth();
  }, []);

  // Auto-scroll chat to bottom
  useEffect(() => {
    if (currentView === 'app') {
      chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loading, currentView]);

  // Handle Drag & Drop / File Selection
  const handleFileChange = (selectedFile) => {
    if (!selectedFile) return;

    const allowed = ['pdf', 'csv', 'png', 'jpg', 'jpeg', 'webp'];
    const ext = selectedFile.name.split('.').pop().toLowerCase();
    
    if (!allowed.includes(ext)) {
      showToast(`Invalid file type '.${ext}'. Supported formats: PDF, CSV, PNG, JPG, WEBP.`, 'error');
      return;
    }

    setFile(selectedFile);

    if (['png', 'jpg', 'jpeg', 'webp'].includes(ext)) {
      const reader = new FileReader();
      reader.onload = (e) => setImagePreview(e.target.result);
      reader.readAsDataURL(selectedFile);
    } else {
      setImagePreview(null);
    }

    showToast(`File selected: ${selectedFile.name} (${(selectedFile.size / 1024).toFixed(1)} KB)`, 'info');
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileChange(e.dataTransfer.files[0]);
    }
  };

  const removeSelectedFile = (e) => {
    e.stopPropagation();
    setFile(null);
    setImagePreview(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    showToast('File selection cleared.', 'info');
  };

  // Upload Document Pipeline
  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    setUploadProgress(15);
    setUploadStatusText('Uploading to OmniBrain Gateway...');

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

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || `Upload failed with status HTTP ${res.status}`);
        }
        
        const data = await res.json();
        const jobId = data.job_id;

        setUploadProgress(40);
        setUploadStatusText('Extracting text and chunking dense vectors...');

        // Poll job status
        let completed = false;
        const maxPoll = 45;
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
              showToast(`🎉 '${file.name}' is fully processed and ready for queries!`, 'success');
              completed = true;
              break;
            } else if (statusData.status === 'FAILED') {
              throw new Error(statusData.error_detail || 'PDF parsing failed.');
            }
          }
        }

        if (!completed) {
          setCurrentDoc({ name: file.name, type: 'pdf', detail: 'Processing in background' });
          showToast('Processing continues in the background.', 'info');
        }
      } 
      // 2. CSV Upload -> Direct Table Load
      else if (ext === 'csv') {
        const res = await fetch(`${BACKEND_URL}/api/v1/sql/load-csv`, {
          method: 'POST',
          body: formData,
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || `CSV load failed with HTTP ${res.status}`);
        }
        
        const data = await res.json();
        setUploadProgress(100);
        setUploadStatusText(`Loaded ${data.rows_loaded || 0} rows into SQLite!`);
        setCurrentDoc({
          name: file.name,
          type: 'csv',
          detail: `Structured table (${data.rows_loaded || 0} rows, columns: ${(data.columns || []).slice(0, 4).join(', ')}...)`
        });
        showToast(`🎉 '${file.name}' loaded into table 'company_financials' (${data.rows_loaded || 0} rows)!`, 'success');
      } 
      // 3. Image Upload -> Vision Registration
      else {
        const res = await fetch(`${BACKEND_URL}/api/v1/vision/upload-image`, {
          method: 'POST',
          body: formData,
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || `Image registration failed with HTTP ${res.status}`);
        }
        
        setUploadProgress(100);
        setUploadStatusText('Visual artifact registered for VisionAgent analysis!');
        setCurrentDoc({ name: file.name, type: 'image', detail: 'Registered for Multimodal Chart Reasoning' });
        showToast(`🎉 Image '${file.name}' registered for VisionAgent multimodal analysis!`, 'success');
      }

      setFile(null);
      setImagePreview(null);
    } catch (err) {
      showToast(`Upload Error: ${err.message}`, 'error');
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
        throw new Error(`Gateway returned HTTP ${res.status}`);
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
        content: `⚠️ Unable to complete request: ${err.message}. Please verify the backend gateway connection.`,
        agent: 'error',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setMessages((prev) => [...prev, errorMessage]);
      showToast(`Query Failed: ${err.message}`, 'error');
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

  // Copy assistant response
  const copyToClipboard = (text, msgId) => {
    navigator.clipboard.writeText(text);
    setCopiedId(msgId);
    showToast('Message copied to clipboard!', 'success');
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Toggle detail accordions for citations/SQL queries
  const toggleAccordion = (id) => {
    setExpandedDetails((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // Reset to Top / Home view
  const handleLogoClick = () => {
    setCurrentView('app');
    setMobileMenuOpen(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Clear chat conversation
  const handleClearChat = () => {
    setMessages([]);
    showToast('Conversation cleared.', 'info');
  };

  // Safe formatting for assistant markdown text
  const formatText = (text) => {
    if (!text) return '';
    const lines = text.split('\n');
    return lines.map((line, idx) => {
      let formatted = line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');

      if (line.trim().startsWith('* ') || line.trim().startsWith('- ')) {
        const itemContent = formatted.replace(/^[\s]*[\*\-]\s+/, '');
        return (
          <li key={idx} dangerouslySetInnerHTML={{ __html: itemContent }} />
        );
      }

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
      {/* Toast Notification Container */}
      <div className="toast-container">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast-card ${toast.type}`}>
            <span className="toast-icon">
              {toast.type === 'success' ? '✓' : toast.type === 'error' ? '✕' : 'ℹ'}
            </span>
            <span className="toast-text">{toast.message}</span>
            <button
              className="toast-close"
              onClick={() => setToasts((prev) => prev.filter((t) => t.id !== toast.id))}
              aria-label="Close notification"
            >
              ×
            </button>
          </div>
        ))}
      </div>

      {/* Top Navigation Bar */}
      <header className="top-nav">
        {/* Clickable Logo */}
        <div className="nav-brand" onClick={handleLogoClick} title="Return to Dashboard">
          <div className="brand-badge">
            <span className="spark-icon">✨</span>
          </div>
          <div className="brand-text">
            <span className="brand-title">OmniBrain</span>
            <span className="brand-tag">Multi-Modal Intelligence</span>
          </div>
        </div>

        {/* Desktop Navigation Links */}
        <div className="nav-desktop-links">
          <button className="nav-link-btn" onClick={() => setCurrentView('app')}>
            Dashboard
          </button>
          <a
            href={`${BACKEND_URL}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            className="nav-link-btn"
          >
            OpenAPI Docs ↗
          </a>
          <a
            href="https://github.com/vedantdubey19/Omni-Brain"
            target="_blank"
            rel="noopener noreferrer"
            className="nav-link-btn"
          >
            GitHub ↗
          </a>
        </div>

        {/* Actions & Status */}
        <div className="nav-actions">
          <div className={`status-pill ${backendStatus}`} title={`Backend: ${BACKEND_URL}`}>
            <span className="status-dot"></span>
            <span className="status-label">
              {backendStatus === 'healthy' ? 'Gateway Live' : backendStatus === 'checking' ? 'Connecting...' : 'Offline'}
            </span>
          </div>

          {messages.length > 0 && (
            <button className="clear-btn desktop-only" onClick={handleClearChat} title="Clear conversation">
              Clear Chat
            </button>
          )}

          {/* Mobile Hamburger Button */}
          <button
            className={`hamburger-btn ${mobileMenuOpen ? 'is-active' : ''}`}
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Toggle mobile menu"
          >
            <span></span>
            <span></span>
            <span></span>
          </button>
        </div>
      </header>

      {/* Mobile Navigation Drawer Overlay */}
      {mobileMenuOpen && (
        <div className="mobile-drawer-backdrop" onClick={() => setMobileMenuOpen(false)}>
          <div className="mobile-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-header">
              <span className="drawer-brand">OmniBrain Menu</span>
              <button className="drawer-close-btn" onClick={() => setMobileMenuOpen(false)}>✕</button>
            </div>

            <nav className="drawer-nav">
              <button
                className="drawer-nav-item"
                onClick={() => {
                  setCurrentView('app');
                  setMobileMenuOpen(false);
                }}
              >
                📊 Dashboard
              </button>
              <a
                href={`${BACKEND_URL}/docs`}
                target="_blank"
                rel="noopener noreferrer"
                className="drawer-nav-item"
                onClick={() => setMobileMenuOpen(false)}
              >
                📚 OpenAPI Gateway Docs ↗
              </a>
              <a
                href="https://github.com/vedantdubey19/Omni-Brain"
                target="_blank"
                rel="noopener noreferrer"
                className="drawer-nav-item"
                onClick={() => setMobileMenuOpen(false)}
              >
                🐙 GitHub Repository ↗
              </a>
              
              <div className="drawer-divider"></div>
              <span className="drawer-section-title">Support & Contact</span>
              
              {/* Clickable Phone Number */}
              <a href="tel:+18005550199" className="drawer-contact-item">
                📞 +1 (800) 555-0199
              </a>
              {/* Clickable Email */}
              <a href="mailto:support@omnibrain.ai" className="drawer-contact-item">
                ✉️ support@omnibrain.ai
              </a>

              <div className="drawer-divider"></div>

              {messages.length > 0 && (
                <button
                  className="drawer-clear-btn"
                  onClick={() => {
                    handleClearChat();
                    setMobileMenuOpen(false);
                  }}
                >
                  🧹 Clear Conversation
                </button>
              )}
            </nav>
          </div>
        </div>
      )}

      {/* Main Content Area */}
      {currentView === 'app' && (
        <main className="main-content">
          {/* Hero Section */}
          <section className="hero-section">
            <div className="hero-pill">
              <span className="sparkle">✦</span> LangGraph Agent Orchestrator
            </div>
            <h1 className="hero-title">Research, Financials & Vision Intelligence</h1>
            <p className="hero-subtitle">
              Upload corporate PDFs, structured historical financial CSVs, or embedded charts.
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
                      {file.name.endsWith('.csv') ? '📊' : file.name.endsWith('.pdf') ? '📄' : '🖼️'}
                    </span>
                    <div className="file-details">
                      <span className="file-name">{file.name}</span>
                      <span className="file-size">{(file.size / 1024).toFixed(1)} KB</span>
                    </div>
                    <button
                      className="remove-file-btn"
                      onClick={removeSelectedFile}
                      title="Deselect file"
                      aria-label="Remove file"
                    >
                      ✕
                    </button>
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
                  {uploading ? 'Processing File...' : `Ingest & Register ${file.name.split('.').pop().toUpperCase()}`}
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
                      <div className="assistant-actions">
                        <button
                          className="copy-btn"
                          onClick={() => copyToClipboard(msg.content, msg.id)}
                          title="Copy answer"
                        >
                          {copiedId === msg.id ? '✓ Copied' : '📋 Copy'}
                        </button>
                        <span className="msg-time">{msg.timestamp}</span>
                      </div>
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
      )}

      {/* Custom 404 View */}
      {currentView === '404' && (
        <main className="main-content not-found-view">
          <div className="not-found-card">
            <span className="not-found-badge">404</span>
            <h1 className="not-found-title">Page Not Found</h1>
            <p className="not-found-desc">
              The multi-modal intelligence pathway you requested does not exist or has moved.
            </p>
            <button className="return-btn" onClick={() => setCurrentView('app')}>
              ← Back to Main Dashboard
            </button>
          </div>
        </main>
      )}

      {/* Modal Dialog: Privacy Policy */}
      {currentView === 'privacy' && (
        <div className="modal-backdrop" onClick={() => setCurrentView('app')}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Privacy Policy</h2>
              <button className="modal-close-btn" onClick={() => setCurrentView('app')}>✕</button>
            </div>
            <div className="modal-body">
              <p><strong>Effective Date:</strong> January 1, {new Date().getFullYear()}</p>
              <br />
              <p>OmniBrain Technologies Inc. ("OmniBrain", "we", "our") is committed to protecting your privacy. This policy explains how we handle your documents and queries:</p>
              <br />
              <p><strong>1. Document Ingestion Safety:</strong> Uploaded PDF, CSV, and image documents are stored strictly within ephemeral session containers and are never shared or used to train public foundation models.</p>
              <br />
              <p><strong>2. Encryption:</strong> All data transmitted between your browser and our API gateway is protected by 256-bit TLS/SSL encryption.</p>
              <br />
              <p><strong>3. Data Retention:</strong> You can purge your session history at any time using the "Clear Chat" button.</p>
            </div>
            <div className="modal-footer">
              <button className="modal-primary-btn" onClick={() => setCurrentView('app')}>I Understand</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Dialog: Terms of Service */}
      {currentView === 'terms' && (
        <div className="modal-backdrop" onClick={() => setCurrentView('app')}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Terms of Service</h2>
              <button className="modal-close-btn" onClick={() => setCurrentView('app')}>✕</button>
            </div>
            <div className="modal-body">
              <p><strong>Last Updated:</strong> October {new Date().getFullYear()}</p>
              <br />
              <p>By accessing or using OmniBrain, you agree to be bound by these Terms of Service:</p>
              <br />
              <p><strong>1. Permitted Use:</strong> OmniBrain provides an AI agent orchestration framework for multi-modal document search, structured Text-to-SQL analytics, and visual reasoning.</p>
              <br />
              <p><strong>2. Enterprise Guardrails:</strong> Users must not attempt prompt injection, jailbreaking, or unauthorized data extraction.</p>
              <br />
              <p><strong>3. Disclaimer:</strong> Generated AI responses are grounded via Self-RAG and retrieval citations, but critical decisions should be verified against source documentation.</p>
            </div>
            <div className="modal-footer">
              <button className="modal-primary-btn" onClick={() => setCurrentView('app')}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Bottom Input Bar (when on app view) */}
      {currentView === 'app' && (
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
      )}

      {/* Comprehensive Production Footer */}
      <footer className="site-footer">
        <div className="footer-content">
          <div className="footer-col brand-col">
            <div className="footer-brand" onClick={handleLogoClick}>
              <span className="brand-badge-small">✨</span>
              <span className="footer-brand-title">OmniBrain</span>
            </div>
            <p className="footer-tagline">
              Autonomous LangGraph multi-modal orchestrator for enterprise research and complex document reasoning.
            </p>
          </div>

          <div className="footer-col">
            <span className="footer-heading">Platform</span>
            <button className="footer-link-btn" onClick={() => setCurrentView('app')}>SearchAgent (RAG)</button>
            <button className="footer-link-btn" onClick={() => setCurrentView('app')}>SQLAgent (SQLite)</button>
            <button className="footer-link-btn" onClick={() => setCurrentView('app')}>VisionAgent (Multimodal)</button>
          </div>

          <div className="footer-col">
            <span className="footer-heading">Resources</span>
            <a href={`${BACKEND_URL}/docs`} target="_blank" rel="noopener noreferrer" className="footer-link-btn">
              API Documentation ↗
            </a>
            <a href="https://github.com/vedantdubey19/Omni-Brain" target="_blank" rel="noopener noreferrer" className="footer-link-btn">
              GitHub Repository ↗
            </a>
            <button className="footer-link-btn" onClick={() => setCurrentView('404')}>
              Status Page
            </button>
          </div>

          <div className="footer-col">
            <span className="footer-heading">Direct Contact</span>
            {/* Clickable Phone Number */}
            <a href="tel:+18005550199" className="footer-contact-link">
              📞 +1 (800) 555-0199
            </a>
            {/* Clickable Email */}
            <a href="mailto:support@omnibrain.ai" className="footer-contact-link">
              ✉️ support@omnibrain.ai
            </a>
            <span className="footer-meta">San Francisco, CA • Open 24/7</span>
          </div>
        </div>

        <div className="footer-bottom-bar">
          <span className="copyright-text">
            © {new Date().getFullYear()} OmniBrain Technologies Inc. All rights reserved.
          </span>
          <div className="footer-legal-links">
            <button className="legal-btn" onClick={() => setCurrentView('privacy')}>Privacy Policy</button>
            <span className="divider">•</span>
            <button className="legal-btn" onClick={() => setCurrentView('terms')}>Terms of Service</button>
          </div>
        </div>
      </footer>
    </div>
  );
}
