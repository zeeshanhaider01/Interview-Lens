import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Form, Button, Row, Col, Spinner, Card, Alert, ListGroup, Badge, FormControl } from 'react-bootstrap'
import axios from 'axios'
import { useAuth0 } from '@auth0/auth0-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

function formatSessionPrimaryLabel(session) {
  const parts = []
  if (session.title?.trim()) parts.push(session.title.trim())
  if (session.company_name?.trim()) {
    if (!parts.length || parts[0] !== session.company_name.trim()) {
      parts.push(session.company_name.trim())
    }
  }
  const title = parts.length ? parts.join(' · ') : 'Untitled prep'
  const d = new Date(session.created_at)
  const dateStr = d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
  const timeStr = d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  return `${title} — ${dateStr} ${timeStr}`
}

function rowStatusLabel(rowStatus) {
  switch (rowStatus) {
    case 'waiting_for_profiles':
      return 'Waiting for profiles'
    case 'generating':
      return 'Generating'
    case 'ready':
      return 'Ready'
    case 'failed':
      return 'Failed'
    default:
      return rowStatus || '—'
  }
}

function rowStatusVariant(rowStatus) {
  switch (rowStatus) {
    case 'ready':
      return 'success'
    case 'failed':
      return 'danger'
    case 'generating':
      return 'warning'
    case 'waiting_for_profiles':
      return 'secondary'
    default:
      return 'light'
  }
}

function formatRelativeTime(isoString) {
  if (!isoString) return null
  const diff = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} minute${mins !== 1 ? 's' : ''} ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} hour${hours !== 1 ? 's' : ''} ago`
  const days = Math.floor(hours / 24)
  return `${days} day${days !== 1 ? 's' : ''} ago`
}

/**
 * Extracts the final Markdown string from a prediction result object.
 * Handles two failure modes that can occur when the AI model misbehaves:
 *   1. The model prepends prose before the JSON → result.markdown is correct (backend fixed).
 *   2. The model double-wraps: result.markdown is itself a JSON string like
 *      '{"markdown": "# 🎯..."}' instead of the raw Markdown.
 * The second case can exist in already-cached DB records, so we unwrap it here too.
 */
function extractMarkdown(result) {
  const raw = result?.markdown || result?.html || ''
  if (typeof raw === 'string' && raw.trimStart().startsWith('{')) {
    try {
      const inner = JSON.parse(raw)
      if (inner?.markdown) return inner.markdown
      if (inner?.html) return inner.html
    } catch (_) {}
  }
  return raw
}

function likelihoodBadgeVariant(likelihood) {
  if (likelihood === 'HIGH') return 'danger'
  if (likelihood === 'MEDIUM') return 'warning'
  return 'secondary'
}

function TopicList({ topics }) {
  if (!topics?.length) return null
  return (
    <div className="mb-4">
      <h6 className="text-primary mb-3">Interview topics</h6>
      <div className="d-flex flex-column gap-2">
        {topics.map((topic) => (
          <Card key={topic.id || topic.topic_key} className="border-0 shadow-sm">
            <Card.Body className="py-3">
              <div className="d-flex justify-content-between align-items-start gap-2">
                <div className="fw-semibold">
                  {topic.emoji ? `${topic.emoji} ` : ''}
                  {topic.title}
                </div>
                <Badge bg={likelihoodBadgeVariant(topic.likelihood)} className="flex-shrink-0">
                  {topic.likelihood}
                </Badge>
              </div>
              {topic.why && <div className="small text-muted mt-2">{topic.why}</div>}
              {topic.study_anchors?.length > 0 && (
                <div className="small mt-2">
                  <span className="text-muted">Study: </span>
                  {topic.study_anchors.join(' · ')}
                </div>
              )}
            </Card.Body>
          </Card>
        ))}
      </div>
    </div>
  )
}

function RefreshIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" fill="currentColor" viewBox="0 0 16 16">
      <path fillRule="evenodd" d="M8 3a5 5 0 1 0 4.546 2.914.5.5 0 0 1 .908-.417A6 6 0 1 1 8 2v1z" />
      <path d="M8 4.466V.534a.25.25 0 0 1 .41-.192l2.36 1.966c.12.1.12.284 0 .384L8.41 4.658A.25.25 0 0 1 8 4.466z" />
    </svg>
  )
}

export default function ProfileForm() {
  const [sessions, setSessions] = useState([])
  const [sessionsLoading, setSessionsLoading] = useState(true)
  const [sessionsError, setSessionsError] = useState(null)
  const [sessionFilter, setSessionFilter] = useState('')
  const [selectedPrepId, setSelectedPrepId] = useState('')
  const [createTitle, setCreateTitle] = useState('')
  const [createCompanyName, setCreateCompanyName] = useState('')
  const [createLoading, setCreateLoading] = useState(false)
  const [createError, setCreateError] = useState(null)

  const [sessionDetail, setSessionDetail] = useState(null)
  const [sessionDetailLoading, setSessionDetailLoading] = useState(false)
  const [sessionDetailError, setSessionDetailError] = useState(null)

  const [editTitle, setEditTitle] = useState('')
  const [editCompanyName, setEditCompanyName] = useState('')
  const [editStatus, setEditStatus] = useState('ACTIVE')
  const [editLoading, setEditLoading] = useState(false)
  const [editError, setEditError] = useState(null)

  const [archiveLoading, setArchiveLoading] = useState(false)
  const [archiveError, setArchiveError] = useState(null)

  const [predictionData, setPredictionData] = useState(null)
  const [predictionLoading, setPredictionLoading] = useState(false)
  const [predictionPollRefreshing, setPredictionPollRefreshing] = useState(false)
  const [predictionError, setPredictionError] = useState(null)
  const [predictionRefreshKey, setPredictionRefreshKey] = useState(0)

  const [intervieweeDecision, setIntervieweeDecision] = useState('reuse_saved')
  const [intervieweeUploadScope, setIntervieweeUploadScope] = useState('session_only')
  const [prepIdCopied, setPrepIdCopied] = useState(false)

  const { getAccessTokenSilently } = useAuth0()

  const apiBase = useMemo(
    () => (import.meta.env.VITE_API_BASE || '').replace(/\/+$/, ''),
    []
  )
  const extensionOpenUrl = useMemo(
    () => (import.meta.env.VITE_EXTENSION_OPEN_URL || '').trim(),
    []
  )

  const getToken = useCallback(async () => {
    return getAccessTokenSilently({
      authorizationParams: {
        audience: import.meta.env.VITE_AUTH0_AUDIENCE,
        scope: 'openid profile email',
      },
    })
  }, [getAccessTokenSilently])

  const apiErrorMessage = useCallback((err, fallback) => {
    const detail = err?.response?.data?.detail
    if (Array.isArray(detail)) return detail.join(', ')
    if (typeof detail === 'string') return detail
    if (detail && typeof detail === 'object') return JSON.stringify(detail)
    return err?.message || fallback
  }, [])

  const filteredSessions = useMemo(() => {
    const q = sessionFilter.trim().toLowerCase()
    if (!q) return sessions
    return sessions.filter((s) => {
      const blob = `${s.prep_id} ${s.title || ''} ${s.company_name || ''}`.toLowerCase()
      return blob.includes(q)
    })
  }, [sessions, sessionFilter])

  const loadSessions = useCallback(async () => {
    setSessionsLoading(true)
    setSessionsError(null)
    try {
      const token = await getToken()
      const resp = await axios.get(`${apiBase}/api/prep-sessions/`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      setSessions(resp.data?.results || [])
    } catch (err) {
      setSessionsError(err?.response?.data?.detail || err.message || 'Failed to load prep sessions')
      setSessions([])
    } finally {
      setSessionsLoading(false)
    }
  }, [apiBase, getToken])

  useEffect(() => {
    loadSessions()
  }, [loadSessions])

  useEffect(() => {
    if (sessionsLoading) return
    if (!sessions.length) {
      setSelectedPrepId('')
      return
    }
    if (selectedPrepId && sessions.some((s) => s.prep_id === selectedPrepId)) {
      return
    }
    const fromUrl = new URLSearchParams(window.location.search).get('prep_id')
    if (fromUrl && sessions.some((s) => s.prep_id === fromUrl)) {
      setSelectedPrepId(fromUrl)
      return
    }
    const first = sessions[0].prep_id
    setSelectedPrepId(first)
    window.history.replaceState({}, '', `?prep_id=${encodeURIComponent(first)}`)
  }, [sessions, sessionsLoading, selectedPrepId])

  const selectSession = useCallback((prepId) => {
    setSelectedPrepId(prepId)
    window.history.replaceState({}, '', `?prep_id=${encodeURIComponent(prepId)}`)
  }, [])

  const loadSessionDetail = useCallback(
    async (prepId) => {
      if (!prepId) return
      setSessionDetailLoading(true)
      setSessionDetailError(null)
      try {
        const token = await getToken()
        const resp = await axios.get(`${apiBase}/api/prep-sessions/${encodeURIComponent(prepId)}/`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        const detail = resp.data
        setSessionDetail(detail)
        setEditTitle(detail?.title || '')
        setEditCompanyName(detail?.company_name || '')
        setEditStatus(detail?.status || 'ACTIVE')
      } catch (err) {
        setSessionDetailError(apiErrorMessage(err, 'Failed to load session details'))
        setSessionDetail(null)
      } finally {
        setSessionDetailLoading(false)
      }
    },
    [apiBase, getToken, apiErrorMessage]
  )

  useEffect(() => {
    if (!selectedPrepId) {
      setSessionDetail(null)
      setSessionDetailError(null)
      return
    }
    loadSessionDetail(selectedPrepId)
  }, [selectedPrepId, loadSessionDetail])

  useEffect(() => {
    if (!selectedPrepId) {
      setPredictionData(null)
      setPredictionError(null)
      return
    }

    let cancelled = false
    let pollTimer

    async function fetchPrediction(isFirst) {
      try {
        if (isFirst) {
          setPredictionLoading(true)
        } else {
          setPredictionPollRefreshing(true)
        }
        setPredictionError(null)
        const token = await getToken()
        const resp = await axios.get(
          `${apiBase}/api/prep-sessions/${encodeURIComponent(selectedPrepId)}/prediction`,
          { headers: { Authorization: `Bearer ${token}` } }
        )
        if (cancelled) return
        setPredictionData(resp.data)
        const st = resp.data?.prediction?.status
        if (st === 'RUNNING' || st === 'NOT_STARTED') {
          pollTimer = setTimeout(() => fetchPrediction(false), 3000)
        }
      } catch (err) {
        if (!cancelled) {
          setPredictionError(err?.response?.data?.detail || err.message || 'Failed to load prediction')
          setPredictionData(null)
        }
      } finally {
        if (!cancelled) {
          setPredictionLoading(false)
          setPredictionPollRefreshing(false)
        }
      }
    }

    fetchPrediction(true)
    return () => {
      cancelled = true
      if (pollTimer) clearTimeout(pollTimer)
    }
  // predictionRefreshKey in deps allows manual re-trigger: incrementing it
  // causes the cleanup to cancel any pending poll and starts a fresh fetch.
  }, [selectedPrepId, apiBase, getToken, predictionRefreshKey])

  const manualRefreshPrediction = useCallback(() => {
    setPredictionRefreshKey((k) => k + 1)
  }, [])

  // People names sourced from profile_submissions returned by the session detail API
  const intervieweeSubmission = sessionDetail?.profile_submissions?.find((s) => s.role === 'INTERVIEWEE')
  const interviewerSubmission = sessionDetail?.profile_submissions?.find((s) => s.role === 'INTERVIEWER')
  const intervieweeName = intervieweeSubmission?.profile_name || ''
  const interviewerName = interviewerSubmission?.profile_name || ''
  const lastUpdatedAt = predictionData?.prediction?.last_success_at || null

  const isPredictionBusy = predictionLoading || predictionPollRefreshing
  const refreshButtonLabel = isPredictionBusy
    ? 'Updating…'
    : predictionData?.prediction?.status === 'FAILED'
      ? '↻ Retry'
      : predictionData?.prediction?.status === 'COMPLETED'
        ? '↻ Refresh Results'
        : 'Fetch Results'

  const selectedSession = sessionDetail || sessions.find((s) => s.prep_id === selectedPrepId)
  const hasDefaultIntervieweeProfile = Boolean(sessionDetail?.has_default_interviewee_profile)

  useEffect(() => {
    if (!hasDefaultIntervieweeProfile) {
      setIntervieweeDecision('upload_new')
    }
  }, [hasDefaultIntervieweeProfile])

  const copyPrepId = useCallback(async () => {
    if (!selectedPrepId) return
    try {
      await navigator.clipboard.writeText(selectedPrepId)
      setPrepIdCopied(true)
      window.setTimeout(() => setPrepIdCopied(false), 1400)
    } catch (_err) {
      setPrepIdCopied(false)
    }
  }, [selectedPrepId])

  const createSession = async (e) => {
    e.preventDefault()
    setCreateLoading(true)
    setCreateError(null)
    try {
      const token = await getToken()
      const payload = {
        title: createTitle.trim(),
        company_name: createCompanyName.trim(),
      }
      const resp = await axios.post(`${apiBase}/api/prep-sessions/`, payload, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const newPrepId = resp?.data?.prep_id
      setCreateTitle('')
      setCreateCompanyName('')
      await loadSessions()
      if (newPrepId) {
        selectSession(newPrepId)
      }
    } catch (err) {
      setCreateError(apiErrorMessage(err, 'Failed to create prep session'))
    } finally {
      setCreateLoading(false)
    }
  }

  const updateSession = async (e) => {
    e.preventDefault()
    if (!selectedPrepId) return
    setEditLoading(true)
    setEditError(null)
    try {
      const token = await getToken()
      await axios.patch(
        `${apiBase}/api/prep-sessions/${encodeURIComponent(selectedPrepId)}/`,
        {
          title: editTitle,
          company_name: editCompanyName,
          status: editStatus,
        },
        { headers: { Authorization: `Bearer ${token}` } }
      )
      await Promise.all([loadSessions(), loadSessionDetail(selectedPrepId)])
    } catch (err) {
      setEditError(apiErrorMessage(err, 'Failed to update prep session'))
    } finally {
      setEditLoading(false)
    }
  }

  const archiveSession = async () => {
    if (!selectedPrepId || archiveLoading) return
    const confirmed = window.confirm('Archive this prep session? You can still view it, but it will be closed.')
    if (!confirmed) return

    setArchiveLoading(true)
    setArchiveError(null)
    try {
      const token = await getToken()
      await axios.delete(`${apiBase}/api/prep-sessions/${encodeURIComponent(selectedPrepId)}/`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      await Promise.all([loadSessions(), loadSessionDetail(selectedPrepId)])
    } catch (err) {
      setArchiveError(apiErrorMessage(err, 'Failed to archive prep session'))
    } finally {
      setArchiveLoading(false)
    }
  }


  return (
    <div className="container-fluid px-3 px-lg-4 my-4">
      <Alert variant="info" className="shadow-sm">
        <div className="fw-semibold">Interview Lens Dashboard</div>
        <div className="small">
          Choose a prep session on the left to view generated prep.
        </div>
      </Alert>

      {/* ── Two-panel workspace ── */}
      <div
        className="d-flex border rounded shadow-sm overflow-hidden mb-4"
        style={{ height: 'calc(100vh - 160px)' }}
      >
        {/* ── LEFT PANEL: Session list ── */}
        <div
          style={{
            width: '360px',
            minWidth: '240px',
            flexShrink: 0,
            borderRight: '1px solid #dee2e6',
            overflowY: 'auto',
            background: '#f8f9fa',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Panel header */}
          <div className="d-flex align-items-center justify-content-between px-3 py-2 border-bottom bg-white" style={{ flexShrink: 0 }}>
            <h6 className="mb-0 text-primary fw-bold text-uppercase" style={{ letterSpacing: '0.04em', fontSize: '0.78rem' }}>
              Prep Sessions
            </h6>
            <Button
              variant="outline-primary"
              size="sm"
              onClick={() => loadSessions()}
              disabled={sessionsLoading}
              className="d-flex align-items-center gap-1 py-1"
            >
              {sessionsLoading ? <Spinner animation="border" size="sm" /> : <RefreshIcon />}
              <span style={{ fontSize: '0.78rem' }}>Refresh</span>
            </Button>
          </div>

          {/* Create form */}
          <div className="px-3 pt-3 pb-2 border-bottom bg-white" style={{ flexShrink: 0 }}>
            <Form onSubmit={createSession}>
              <Row className="g-2">
                <Col xs={12}>
                  <Form.Control
                    size="sm"
                    value={createTitle}
                    onChange={(e) => setCreateTitle(e.target.value)}
                    placeholder="e.g. Senior Backend Engineer"
                    maxLength={200}
                  />
                </Col>
                <Col xs={12}>
                  <Form.Control
                    size="sm"
                    value={createCompanyName}
                    onChange={(e) => setCreateCompanyName(e.target.value)}
                    placeholder="e.g. Acme"
                    maxLength={200}
                  />
                </Col>
                <Col xs={12}>
                  <Button type="submit" size="sm" className="w-100" disabled={createLoading}>
                    {createLoading ? (
                      <>
                        <Spinner animation="border" size="sm" className="me-1" />
                        Creating…
                      </>
                    ) : (
                      '+ Create prep session'
                    )}
                  </Button>
                </Col>
              </Row>
              {createError && (
                <Alert variant="danger" className="mt-2 mb-0 py-1 small">
                  {String(createError)}
                </Alert>
              )}
            </Form>
          </div>

          {/* Filter */}
          <div className="px-3 pt-2 pb-1" style={{ flexShrink: 0 }}>
            <FormControl
              type="search"
              size="sm"
              placeholder="Filter by title, company, or ID…"
              value={sessionFilter}
              onChange={(e) => setSessionFilter(e.target.value)}
            />
          </div>

          {/* Session list */}
          <div className="px-2 py-1" style={{ overflowY: 'auto', flex: 1 }}>
            {sessionsLoading && (
              <div className="text-muted py-3 px-2 small">
                <Spinner animation="border" size="sm" className="me-2" />
                Loading sessions…
              </div>
            )}
            {sessionsError && (
              <Alert variant="danger" className="mx-2 mt-2 small py-2">
                {String(sessionsError)}
              </Alert>
            )}
            {!sessionsLoading && !sessions.length && !sessionsError && (
              <p className="text-secondary mb-0 px-2 py-3 small">
                No prep sessions yet. Create one above or use the browser extension.
              </p>
            )}
            {!sessionsLoading && filteredSessions.length > 0 && (
              <ListGroup variant="flush">
                {filteredSessions.map((s) => {
                  const active = s.prep_id === selectedPrepId
                  return (
                    <ListGroup.Item
                      key={s.prep_id}
                      action
                      active={active}
                      onClick={() => selectSession(s.prep_id)}
                      className={`rounded mb-1 ${s.is_latest && !active ? 'border border-success border-2' : ''}`}
                    >
                      <div className="d-flex justify-content-between align-items-start gap-2 flex-wrap">
                        <div style={{ minWidth: 0 }}>
                          <div className="fw-semibold text-truncate" style={{ fontSize: '0.82rem' }}>
                            {formatSessionPrimaryLabel(s)}
                          </div>
                          <div className="text-muted font-monospace" style={{ fontSize: '0.7rem' }}>
                            ID …{s.prep_id.slice(-12)}
                          </div>
                          {s.is_latest && (
                            <Badge bg="success" className="mt-1" style={{ fontSize: '0.65rem' }}>
                              Latest
                            </Badge>
                          )}
                        </div>
                        <Badge
                          bg={rowStatusVariant(s.row_status)}
                          text={s.row_status === 'generating' ? 'dark' : undefined}
                          style={{ fontSize: '0.65rem', whiteSpace: 'normal', textAlign: 'right' }}
                        >
                          {rowStatusLabel(s.row_status)}
                        </Badge>
                      </div>
                    </ListGroup.Item>
                  )
                })}
              </ListGroup>
            )}
          </div>
        </div>

        {/* ── RIGHT PANEL: Prep Results ── */}
        <div style={{ flex: 1, minWidth: 0, overflowY: 'auto', background: '#fff' }}>
          {!selectedPrepId ? (
            <div className="d-flex align-items-center justify-content-center h-100 text-muted">
              <div className="text-center p-4">
                <div className="mb-3" style={{ fontSize: '2.5rem' }}>📋</div>
                <div className="fw-semibold">No session selected</div>
                <div className="small mt-1">Select a session from the left to view prep results.</div>
              </div>
            </div>
          ) : (
            <div className="p-3">
              {/* Right panel header */}
              <div className="d-flex justify-content-between align-items-start mb-3 pb-3 border-bottom">
                <div style={{ minWidth: 0 }}>
                  <h5 className="mb-0 text-primary text-truncate">
                    {selectedSession ? formatSessionPrimaryLabel(selectedSession) : '…'}
                  </h5>
                  {(intervieweeName || interviewerName) && (
                    <div className="small text-muted mt-1">
                      <span className="me-1">👤</span>
                      {intervieweeName || '—'}&nbsp;→&nbsp;{interviewerName || '—'}
                    </div>
                  )}
                  {lastUpdatedAt && (
                    <div className="small text-muted mt-1">
                      Last updated: {formatRelativeTime(lastUpdatedAt)}
                    </div>
                  )}
                </div>
                <Button
                  size="sm"
                  variant="outline-secondary"
                  disabled={isPredictionBusy}
                  onClick={manualRefreshPrediction}
                  className="d-flex align-items-center gap-1 ms-2 flex-shrink-0"
                >
                  {isPredictionBusy ? (
                    <Spinner animation="border" size="sm" />
                  ) : (
                    <RefreshIcon />
                  )}
                  <span style={{ fontSize: '0.78rem' }}>{refreshButtonLabel}</span>
                </Button>
              </div>

              {/* Session settings */}
              <Card className="mb-3">
                <Card.Body>
                  <div className="d-flex justify-content-between align-items-center mb-2">
                    <h6 className="mb-0">Session settings</h6>
                    {sessionDetail?.status && (
                      <Badge bg={sessionDetail.status === 'CLOSED' ? 'secondary' : 'success'}>
                        {sessionDetail.status}
                      </Badge>
                    )}
                  </div>
                  {sessionDetailLoading && (
                    <div className="small text-muted mb-2">
                      <Spinner animation="border" size="sm" className="me-2" />
                      Loading session details…
                    </div>
                  )}
                  {sessionDetailError && (
                    <Alert variant="danger" className="py-2">
                      {sessionDetailError}
                    </Alert>
                  )}
                  {archiveError && (
                    <Alert variant="danger" className="py-2">
                      {archiveError}
                    </Alert>
                  )}
                  <Form onSubmit={updateSession}>
                    <Row className="g-2">
                      <Col md={4}>
                        <Form.Group>
                          <Form.Label className="small mb-1">Title</Form.Label>
                          <Form.Control
                            value={editTitle}
                            onChange={(e) => setEditTitle(e.target.value)}
                            maxLength={200}
                          />
                        </Form.Group>
                      </Col>
                      <Col md={4}>
                        <Form.Group>
                          <Form.Label className="small mb-1">Company</Form.Label>
                          <Form.Control
                            value={editCompanyName}
                            onChange={(e) => setEditCompanyName(e.target.value)}
                            maxLength={200}
                          />
                        </Form.Group>
                      </Col>
                      <Col md={4}>
                        <Form.Group>
                          <Form.Label className="small mb-1">Status</Form.Label>
                          <Form.Select
                            value={editStatus}
                            onChange={(e) => setEditStatus(e.target.value)}
                          >
                            <option value="ACTIVE">ACTIVE</option>
                            <option value="CLOSED">CLOSED</option>
                          </Form.Select>
                        </Form.Group>
                      </Col>
                    </Row>
                    <div className="mt-3 d-flex gap-2">
                      <Button
                        type="submit"
                        variant="outline-primary"
                        disabled={editLoading || !selectedPrepId}
                      >
                        {editLoading ? 'Saving…' : 'Save session'}
                      </Button>
                      <Button
                        type="button"
                        variant="outline-danger"
                        disabled={archiveLoading || !selectedPrepId}
                        onClick={archiveSession}
                      >
                        {archiveLoading ? 'Archiving…' : 'Archive session'}
                      </Button>
                    </div>
                    {editError && (
                      <Alert variant="danger" className="mt-2 mb-0 py-2">
                        {editError}
                      </Alert>
                    )}
                  </Form>
                  <hr />
                  <div className="small">
                    <div className="fw-semibold mb-1">Interviewee profile decision for this session</div>
                    {hasDefaultIntervieweeProfile ? (
                      <>
                        <Form.Check
                          type="radio"
                          id="decisionReuse"
                          name="intervieweeDecision"
                          label="Use saved profile"
                          checked={intervieweeDecision === 'reuse_saved'}
                          onChange={() => setIntervieweeDecision('reuse_saved')}
                        />
                        <Form.Check
                          type="radio"
                          id="decisionUpload"
                          name="intervieweeDecision"
                          label="Upload new profile"
                          checked={intervieweeDecision === 'upload_new'}
                          onChange={() => setIntervieweeDecision('upload_new')}
                        />
                      </>
                    ) : (
                      <Alert variant="secondary" className="py-2 mb-2">
                        No default interviewee profile found yet. Upload a new interviewee profile from the extension.
                      </Alert>
                    )}
                    {intervieweeDecision === 'upload_new' && (
                      <div className="ms-3 mt-2">
                        <Form.Check
                          type="radio"
                          id="scopeSessionOnly"
                          name="intervieweeUploadScope"
                          label="Use only for this session"
                          checked={intervieweeUploadScope === 'session_only'}
                          onChange={() => setIntervieweeUploadScope('session_only')}
                        />
                        <Form.Check
                          type="radio"
                          id="scopeSaveDefault"
                          name="intervieweeUploadScope"
                          label="Save as default profile"
                          checked={intervieweeUploadScope === 'save_as_default'}
                          onChange={() => setIntervieweeUploadScope('save_as_default')}
                        />
                      </div>
                    )}
                  </div>
                  <hr />
                  <div className="small">
                    <div className="fw-semibold mb-2">Use browser extension for profile upload</div>
                    <div className="d-flex align-items-center gap-2 mb-2 flex-wrap">
                      <Form.Control value={selectedPrepId} readOnly className="font-monospace" />
                      <Button
                        size="sm"
                        variant={prepIdCopied ? 'success' : 'outline-primary'}
                        onClick={copyPrepId}
                      >
                        {prepIdCopied ? 'Copied' : 'Copy prep_id'}
                      </Button>
                      {extensionOpenUrl && (
                        <Button
                          size="sm"
                          variant="outline-secondary"
                          onClick={() => window.open(extensionOpenUrl, '_blank', 'noopener,noreferrer')}
                        >
                          Open extension
                        </Button>
                      )}
                    </div>
                    <ol className="mb-2 ps-3">
                      <li>Open the Interview Lens extension popup.</li>
                      <li>Paste the copied prep_id.</li>
                      <li>Select role and choose reuse/upload option.</li>
                      <li>Capture LinkedIn data and submit.</li>
                    </ol>
                    {extensionOpenUrl && (
                      <div className="text-muted">
                        If the extension does not open directly, click browser Extensions icon and choose Interview Lens.
                      </div>
                    )}
                  </div>
                </Card.Body>
              </Card>

              {/* Prediction results */}
              {predictionLoading && (
                <div className="text-muted">
                  <Spinner animation="border" size="sm" className="me-2" />
                  Loading…
                </div>
              )}
              {predictionError && <Alert variant="danger">{predictionError}</Alert>}
              {predictionPollRefreshing && !predictionLoading && (
                <div className="small text-muted mb-2">Updating…</div>
              )}
              {predictionData && !predictionLoading && (
                <>
                  {predictionData.pipeline_status === 'WAITING_FOR_COUNTERPART_PROFILE' && (
                    <Alert variant="secondary" className="mb-0">
                      {predictionData?.has_interviewee_profile && !predictionData?.has_interviewer_profile
                        ? 'Interviewee profile is ready. Submit interviewer profile from the extension.'
                        : !predictionData?.has_interviewee_profile && predictionData?.has_interviewer_profile
                          ? 'Interviewer profile is ready. Submit interviewee profile from the extension.'
                          : 'Waiting for both interviewee and interviewer profiles for this session. Submit the missing profile from the extension.'}
                    </Alert>
                  )}
                                    {predictionData.pipeline_status === 'READY_FOR_TOPIC_GENERATION' &&
                    predictionData.prediction?.status === 'COMPLETED' &&
                    (predictionData.prediction?.result?.topics?.length > 0 ||
                      predictionData.prediction?.result?.markdown ||
                      predictionData.prediction?.result?.html) && (
                      <div className="mt-2">
                        <TopicList topics={predictionData.prediction.result.topics} />
                        {(() => {
                          const md = extractMarkdown(predictionData.prediction.result)
                          if (!md) {
                            if (predictionData.prediction.result.html) {
                              return (
                                <div
                                  className="prose max-w-none"
                                  dangerouslySetInnerHTML={{
                                    __html: predictionData.prediction.result.html,
                                  }}
                                />
                              )
                            }
                            return null
                          }
                          return (
                            <div className="prose max-w-none">
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>{md}</ReactMarkdown>
                            </div>
                          )
                        })()}
                      </div>
                    )}
                  {predictionData.pipeline_status === 'READY_FOR_TOPIC_GENERATION' &&
                    (predictionData.prediction?.status === 'RUNNING' ||
                      predictionData.prediction?.status === 'NOT_STARTED') && (
                      <Alert variant="warning" className="mb-0">
                        Generating your interview prep… This page will update automatically.
                      </Alert>
                    )}
                  {predictionData.pipeline_status === 'READY_FOR_TOPIC_GENERATION' &&
                    predictionData.prediction?.status === 'FAILED' && (
                      <Alert variant="danger" className="mb-0">
                        {predictionData.prediction?.error || 'Generation failed. Try again later.'}
                      </Alert>
                    )}
                </>
              )}
            </div>
          )}
        </div>
      </div>

    </div>
  )
}
