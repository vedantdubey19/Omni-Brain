import { useState } from 'react'
import './App.css'

const BACKEND_URL = ''

function App() {
  const [file, setFile] = useState(null)
  const [uploadedFilename, setUploadedFilename] = useState(null)
  const [jobId, setJobId] = useState(null)
  const [status, setStatus] = useState('READY')
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [isDragging, setIsDragging] = useState(false)

  const handleFileChange = (event) => {
    const selectedFile = event.target.files[0]

    if (!selectedFile) return

    if (selectedFile.type !== 'application/pdf') {
      setError('Please select a PDF file.')
      return
    }

    setFile(selectedFile)
    setUploadedFilename(null)
    setJobId(null)
    setStatus('READY')
    setError('')
  }

  const handleDrop = (event) => {
    event.preventDefault()
    setIsDragging(false)

    const droppedFile = event.dataTransfer.files[0]

    if (!droppedFile) return

    if (droppedFile.type !== 'application/pdf') {
      setError('Please select a PDF file.')
      return
    }

    setFile(droppedFile)
    setUploadedFilename(null)
    setJobId(null)
    setStatus('READY')
    setError('')
  }

  const uploadPDF = async () => {
    if (!file) {
      setError('Please choose a PDF first.')
      return
    }

    setUploading(true)
    setError('')
    setStatus('UPLOADING')

    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch(
        `${BACKEND_URL}/api/v1/upload`,
        {
          method: 'POST',
          body: formData,
        }
      )

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.status}`)
      }

      const data = await response.json()
      const newJobId = data.job_id

      if (!newJobId) {
        throw new Error(
          'Upload succeeded, but no job ID was returned.'
        )
      }

      setUploadedFilename(file.name)
      setJobId(newJobId)
      setStatus('QUEUED')

      checkProcessingStatus(newJobId)
    } catch (err) {
      setStatus('ERROR')
      setError(err.message || 'Unable to upload PDF.')
      setUploading(false)
    }
  }

  const checkProcessingStatus = async (currentJobId) => {
    const startTime = Date.now()
    const maxWaitTime = 300000

    const pollStatus = async () => {
      if (Date.now() - startTime >= maxWaitTime) {
        setStatus('TIMEOUT')
        setError(
          'PDF processing took too long. Please try again.'
        )
        setUploading(false)
        return
      }

      try {
        const response = await fetch(
          `${BACKEND_URL}/api/v1/ingest/status/${currentJobId}`
        )

        if (!response.ok) {
          throw new Error(
            `Unable to check processing status: ${response.status}`
          )
        }

        const data = await response.json()
        const currentStatus = data.status || 'UNKNOWN'

        setStatus(currentStatus)

        if (
          currentStatus === 'COMPLETED' ||
          currentStatus === 'DONE'
        ) {
          setUploading(false)
          return
        }

        if (currentStatus === 'FAILED') {
          setUploading(false)
          setError('PDF processing failed.')
          return
        }

        setTimeout(pollStatus, 2000)
      } catch (err) {
        setUploading(false)
        setStatus('ERROR')
        setError(
          err.message ||
            'Unable to check PDF status.'
        )
      }
    }

    pollStatus()
  }

  const askQuestion = async () => {
    const trimmedQuestion = question.trim()

    if (!trimmedQuestion) return

    if (!uploadedFilename) {
      setError(
        'Please upload and process a PDF first.'
      )
      return
    }

    const userMessage = {
      role: 'user',
      content: trimmedQuestion,
    }

    setMessages((previous) => [
      ...previous,
      userMessage,
    ])

    setQuestion('')
    setLoading(true)
    setError('')

    try {
      const response = await fetch(
        `${BACKEND_URL}/api/v1/query`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            question: trimmedQuestion,
            top_k: 3,
            document_id: null,
          }),
        }
      )

      if (!response.ok) {
        throw new Error(
          `Query failed: ${response.status}`
        )
      }

      const data = await response.json()

      const answer =
        data.answer ||
        'No answer was returned.'

      const retrievedChunks =
        data.retrieved_chunks || []

      const sources = retrievedChunks.map(
        (chunk) => ({
          filename:
            chunk.source || 'Unknown',
          chunkId:
            chunk.chunk_id || 'Unknown',
          page:
            chunk.page || 'Unknown',
          score:
            Number(
              chunk.score || 0
            ).toFixed(4),
          content:
            chunk.content || '',
        })
      )

      const assistantMessage = {
        role: 'assistant',
        content: answer,
        sources,
      }

      setMessages((previous) => [
        ...previous,
        assistantMessage,
      ])
    } catch (err) {
      setError(
        err.message ||
          'Unable to get an answer.'
      )
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (event) => {
    if (
      event.key === 'Enter' &&
      !event.shiftKey
    ) {
      event.preventDefault()
      askQuestion()
    }
  }

  const clearChat = () => {
    setMessages([])
    setError('')
  }

  const getStatusText = () => {
    if (status === 'UPLOADING')
      return 'Uploading...'

    if (status === 'QUEUED')
      return 'Queued...'

    if (status === 'PROCESSING')
      return 'Processing...'

    if (
      status === 'COMPLETED' ||
      status === 'DONE'
    ) {
      return 'Ready'
    }

    if (
      status === 'FAILED' ||
      status === 'ERROR'
    ) {
      return 'Error'
    }

    if (status === 'TIMEOUT')
      return 'Timeout'

    return 'Ready'
  }

  const isReady =
    status === 'COMPLETED' ||
    status === 'DONE'

  return (
    <div className="app">

      <aside className="sidebar">

        <div className="brand">
          <div className="brand-icon">
            🧠
          </div>

          <div>
            <h2>OmniBrain</h2>
            <span>
              AI Document Assistant
            </span>
          </div>
        </div>

        <div className="document-box">

          <span className="file-icon">
            📄
          </span>

          <div>
            <strong>
              {uploadedFilename ||
                'No document'}
            </strong>

            <p>
              {uploadedFilename
                ? 'Document uploaded'
                : 'Upload a PDF to begin'}
            </p>
          </div>

        </div>

        <button
          className="clear-btn"
          onClick={clearChat}
        >
          🗑 Clear Chat
        </button>

        <div className="sidebar-bottom">
          <span>OmniBrain</span>
          <small>
            Semantic Search • AI Chat
          </small>
        </div>

      </aside>

      <main className="main">

        <header className="header">

          <div>
            <p className="eyebrow">
              ✨ MULTI-AGENT DOCUMENT INTELLIGENCE
            </p>

            <h1>
              Ask your <span className="rose-gradient">documents</span> anything.
            </h1>

            <p className="subtitle">
              Multi-agent document intelligence — retrieval, reasoning and chart analysis, orchestrated for you.
            </p>
          </div>

          <div className="status">
            <span></span>
            {getStatusText()}
          </div>

        </header>

        <div className="suggestion-cards-grid">
          <button
            className="suggestion-card"
            onClick={() => {
              setQuestion('Please provide a comprehensive summary of this document.')
            }}
          >
            <span>📄 Summarize this document</span>
            <span className="arrow">→</span>
          </button>
          <button
            className="suggestion-card"
            onClick={() => {
              setQuestion('What are the key findings, metrics, and highlights?')
            }}
          >
            <span>🔍 List the key findings</span>
            <span className="arrow">→</span>
          </button>
          <button
            className="suggestion-card"
            onClick={() => {
              setQuestion('Analyze the charts and visual data in this document.')
            }}
          >
            <span>📊 Analyze the charts</span>
            <span className="arrow">→</span>
          </button>
          <button
            className="suggestion-card"
            onClick={() => {
              setQuestion('What are the primary risks and challenges mentioned?')
            }}
          >
            <span>⚠️ What are the risks mentioned?</span>
            <span className="arrow">→</span>
          </button>
        </div>

        <section
          className={`upload-card ${
            isDragging ? 'dragging' : ''
          }`}
          onDragOver={(event) => {
            event.preventDefault()
            setIsDragging(true)
          }}
          onDragLeave={() => {
            setIsDragging(false)
          }}
          onDrop={handleDrop}
        >

          <div className="upload-icon">
            ↑
          </div>

          <h2>
            {uploadedFilename
              ? 'Document uploaded'
              : isDragging
              ? 'Drop your PDF here'
              : 'Upload your document'}
          </h2>

          <p>
            {uploadedFilename
              ? uploadedFilename
              : 'Drop your PDF here or choose a file from your computer'}
          </p>

          <input
            id="pdf-upload"
            type="file"
            accept=".pdf,application/pdf"
            onChange={handleFileChange}
            hidden
          />

          <div className="upload-actions">

            <label
              htmlFor="pdf-upload"
              className="upload-btn"
            >
              📄 Choose PDF
            </label>

            {file &&
              !uploadedFilename && (
                <button
                  className="upload-btn secondary-btn"
                  onClick={uploadPDF}
                  disabled={uploading}
                >
                  {uploading
                    ? '⏳ Processing...'
                    : '🚀 Upload PDF'}
                </button>
              )}

          </div>

          {file && (
            <div className="selected-file">

              <div className="selected-file-icon">
                📑
              </div>

              <div>
                <strong>
                  {file.name}
                </strong>

                <span>
                  {(file.size / 1024 / 1024).toFixed(
                    2
                  )}{' '}
                  MB • PDF Document
                </span>
              </div>

            </div>
          )}

          <div className="processing-status">

            <span
              className={
                isReady
                  ? 'status-dot ready-dot'
                  : status === 'ERROR'
                  ? 'status-dot error-dot'
                  : 'status-dot'
              }
            ></span>

            {status === 'PROCESSING'
              ? '⚙️ Processing your document...'
              : status === 'QUEUED'
              ? '⏳ Waiting for processing...'
              : isReady
              ? '✅ Document ready for chat'
              : status === 'ERROR'
              ? '❌ Something went wrong'
              : 'PDF files only'}

          </div>

        </section>

        {error && (
          <div className="error-message">
            <span>⚠️</span>
            {error}
          </div>
        )}

        <section className="chat-card">

          <div className="chat-header">

            <div>
              <span className="chat-icon">
                💬
              </span>

              <div>
                <h2>
                  Document Chat
                </h2>

                <p>
                  Ask questions about your
                  uploaded PDF
                </p>
              </div>
            </div>

            {isReady && (
              <div className="chat-ready">
                <span></span>
                AI Ready
              </div>
            )}

          </div>

          <div className="chat-messages">

            {messages.length === 0 ? (

              <div className="empty-chat">

                <div className="empty-icon">
                  ✦
                </div>

                <h2>
                  Start a conversation
                </h2>

                <p>
                  Upload a document above,
                  then ask anything about its
                  content.
                </p>

                {!isReady && (
                  <div className="chat-hint">
                    🔒 Upload a PDF to unlock
                    document chat
                  </div>
                )}

              </div>

            ) : (

              messages.map(
                (message, index) => (

                  <div
                    key={index}
                    className={`message ${
                      message.role === 'user'
                        ? 'user-message'
                        : 'assistant-message'
                    }`}
                  >

                    <div className="message-label">
                      {message.role === 'user'
                        ? 'You'
                        : 'OmniBrain'}
                    </div>

                    <div className="message-content">
                      {message.content}
                    </div>

                    {message.role ===
                      'assistant' &&
                      message.sources &&
                      message.sources.length >
                        0 && (

                        <details className="sources">

                          <summary>
                            📚 View Sources
                          </summary>

                          {message.sources.map(
                            (
                              source,
                              sourceIndex
                            ) => (

                              <div
                                className="source-item"
                                key={sourceIndex}
                              >

                                <strong>
                                  📄{' '}
                                  {source.filename}
                                </strong>

                                <small>
                                  Chunk:{' '}
                                  {source.chunkId}
                                  {' • '}
                                  Page:{' '}
                                  {source.page}
                                  {' • '}
                                  Score:{' '}
                                  {source.score}
                                </small>

                                {source.content && (
                                  <p>
                                    {
                                      source.content
                                    }
                                  </p>
                                )}

                              </div>

                            )
                          )}

                        </details>
                      )}

                  </div>

                )
              )

            )}

            {loading && (
              <div className="message assistant-message">

                <div className="message-label">
                  OmniBrain
                </div>

                <div className="message-content typing">
                  <span></span>
                  <span></span>
                  <span></span>
                  Searching your document...
                </div>

              </div>
            )}

          </div>

          <div className="chat-input">

            <input
              type="text"
              value={question}
              onChange={(event) =>
                setQuestion(
                  event.target.value
                )
              }
              onKeyDown={handleKeyDown}
              placeholder={
                isReady
                  ? 'Ask something about your PDF...'
                  : 'Upload and process a PDF first...'
              }
              disabled={
                !isReady || loading
              }
            />

            <button
              onClick={askQuestion}
              disabled={
                !isReady ||
                loading ||
                !question.trim()
              }
            >
              ➤
            </button>

          </div>

        </section>

      </main>

    </div>
  )
}

export default App