import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Form, Button, Row, Col, Spinner, Card, Alert, ListGroup, Badge, FormControl } from 'react-bootstrap'
import axios from 'axios'
import { useAuth0 } from '@auth0/auth0-react'

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

export default function ProfileForm() {
  const [form, setForm] = useState({
    interviewee: { name: '', email: '', education: '', experience: '' },
    interviewer: { name: '', education: '', experience: '' },
  })
  const [manualLoading, setManualLoading] = useState(false)
  const [manualResult, setManualResult] = useState(null)
  const [manualError, setManualError] = useState(null)

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
  }, [selectedPrepId, apiBase, getToken])

  const onChange = (e, section, field) => {
    setForm((prev) => ({
      ...prev,
      [section]: { ...prev[section], [field]: e.target.value },
    }))
  }

  const submitManual = async (e) => {
    e.preventDefault()
    setManualResult(null)
    setManualError(null)
    setManualLoading(true)
    try {
      const token = await getToken()
      const resp = await axios.post(`${apiBase}/api/predict-questions/`, form, {
        headers: { Authorization: `Bearer ${token}` },
      })
      setManualResult(resp.data)
    } catch (err) {
      setManualError(err?.response?.data?.detail || 'Something went wrong')
    } finally {
      setManualLoading(false)
    }
  }

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
    <div className="container my-4">
      <Alert variant="info" className="shadow-sm">
        <div className="fw-semibold">Interview Lens Dashboard</div>
        <div className="small">
          Choose a prep session below to view generated prep. You can also submit profiles manually at the bottom.
        </div>
      </Alert>

      <Card className="shadow-sm mb-4">
        <Card.Header className="bg-white d-flex flex-wrap align-items-center justify-content-between gap-2">
          <h4 className="mb-0 text-primary">Prep sessions</h4>
          <Button variant="outline-secondary" size="sm" onClick={() => loadSessions()} disabled={sessionsLoading}>
            Refresh list
          </Button>
        </Card.Header>
        <Card.Body>
          <Form onSubmit={createSession} className="mb-3">
            <Row className="g-2 align-items-end">
              <Col md={4}>
                <Form.Group>
                  <Form.Label className="small mb-1">Title</Form.Label>
                  <Form.Control
                    value={createTitle}
                    onChange={(e) => setCreateTitle(e.target.value)}
                    placeholder="e.g. Senior Backend Engineer"
                    maxLength={200}
                  />
                </Form.Group>
              </Col>
              <Col md={4}>
                <Form.Group>
                  <Form.Label className="small mb-1">Company</Form.Label>
                  <Form.Control
                    value={createCompanyName}
                    onChange={(e) => setCreateCompanyName(e.target.value)}
                    placeholder="e.g. Acme"
                    maxLength={200}
                  />
                </Form.Group>
              </Col>
              <Col md={4} className="d-flex gap-2">
                <Button type="submit" disabled={createLoading}>
                  {createLoading ? (
                    <>
                      <Spinner animation="border" size="sm" className="me-2" />
                      Creating…
                    </>
                  ) : (
                    'Create prep session'
                  )}
                </Button>
              </Col>
            </Row>
            {createError && <Alert variant="danger" className="mt-2 mb-0 py-2">{String(createError)}</Alert>}
          </Form>

          <FormControl
            type="search"
            placeholder="Filter by title, company, or ID…"
            className="mb-3"
            value={sessionFilter}
            onChange={(e) => setSessionFilter(e.target.value)}
          />
          {sessionsLoading && (
            <div className="text-muted py-3">
              <Spinner animation="border" size="sm" className="me-2" />
              Loading sessions…
            </div>
          )}
          {sessionsError && <Alert variant="danger">{String(sessionsError)}</Alert>}
          {!sessionsLoading && !sessions.length && !sessionsError && (
            <p className="text-secondary mb-0">
              No prep sessions yet. Create one from the browser extension or use manual submission below after you add sessions via the API.
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
                    className={s.is_latest ? 'border border-success border-2 rounded mb-1' : ''}
                  >
                    <div className="d-flex justify-content-between align-items-start gap-2 flex-wrap">
                      <div>
                        <div className="fw-semibold">{formatSessionPrimaryLabel(s)}</div>
                        <div className="small text-muted font-monospace">ID …{s.prep_id.slice(-12)}</div>
                        {s.is_latest && (
                          <Badge bg="success" className="mt-1">
                            Latest
                          </Badge>
                        )}
                      </div>
                      <Badge bg={rowStatusVariant(s.row_status)} text={s.row_status === 'generating' ? 'dark' : undefined}>
                        {rowStatusLabel(s.row_status)}
                      </Badge>
                    </div>
                  </ListGroup.Item>
                )
              })}
            </ListGroup>
          )}
        </Card.Body>
      </Card>

      {selectedPrepId && (
        <Card className="shadow-sm mb-4">
          <Card.Header className="bg-primary text-white">
            <h5 className="mb-0">Prep results</h5>
            {selectedSession && (
              <div className="small opacity-90 mt-1">{formatSessionPrimaryLabel(selectedSession)}</div>
            )}
          </Card.Header>
          <Card.Body>
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
                {sessionDetailError && <Alert variant="danger" className="py-2">{sessionDetailError}</Alert>}
                {archiveError && <Alert variant="danger" className="py-2">{archiveError}</Alert>}
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
                        <Form.Select value={editStatus} onChange={(e) => setEditStatus(e.target.value)}>
                          <option value="ACTIVE">ACTIVE</option>
                          <option value="CLOSED">CLOSED</option>
                        </Form.Select>
                      </Form.Group>
                    </Col>
                  </Row>
                  <div className="mt-3 d-flex gap-2">
                    <Button type="submit" variant="outline-primary" disabled={editLoading || !selectedPrepId}>
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
                  {editError && <Alert variant="danger" className="mt-2 mb-0 py-2">{editError}</Alert>}
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
                    <Button size="sm" variant={prepIdCopied ? 'success' : 'outline-primary'} onClick={copyPrepId}>
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
                  predictionData.prediction?.result?.html && (
                    <div className="prose" dangerouslySetInnerHTML={{ __html: predictionData.prediction.result.html }} />
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
          </Card.Body>
        </Card>
      )}

      <Card className="shadow-sm">
        <Card.Header className="bg-white">
          <h4 className="mb-0 text-primary">Manual profile submission</h4>
          <div className="small text-muted mt-1">
            Submit interviewee and interviewer text directly (does not use prep sessions above).
          </div>
        </Card.Header>
        <Card.Body>
          <Form onSubmit={submitManual}>
            <h5 className="text-secondary">Interviewee</h5>
            <Row className="g-3">
              <Col md={6}>
                <Form.Group>
                  <Form.Label>Name</Form.Label>
                  <Form.Control
                    value={form.interviewee.name}
                    onChange={(e) => onChange(e, 'interviewee', 'name')}
                    required
                  />
                </Form.Group>
              </Col>
              <Col md={6}>
                <Form.Group>
                  <Form.Label>Email</Form.Label>
                  <Form.Control
                    type="email"
                    value={form.interviewee.email}
                    onChange={(e) => onChange(e, 'interviewee', 'email')}
                    required
                  />
                </Form.Group>
              </Col>
              <Col md={6}>
                <Form.Group>
                  <Form.Label>Education</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={3}
                    value={form.interviewee.education}
                    onChange={(e) => onChange(e, 'interviewee', 'education')}
                    required
                  />
                </Form.Group>
              </Col>
              <Col md={6}>
                <Form.Group>
                  <Form.Label>Professional experience</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={3}
                    value={form.interviewee.experience}
                    onChange={(e) => onChange(e, 'interviewee', 'experience')}
                    required
                  />
                </Form.Group>
              </Col>
            </Row>

            <hr className="my-4" />

            <h5 className="text-secondary">Interviewer</h5>
            <Row className="g-3">
              <Col md={4}>
                <Form.Group>
                  <Form.Label>Name</Form.Label>
                  <Form.Control
                    value={form.interviewer.name}
                    onChange={(e) => onChange(e, 'interviewer', 'name')}
                    required
                  />
                </Form.Group>
              </Col>
              <Col md={4}>
                <Form.Group>
                  <Form.Label>Educational experience</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={3}
                    value={form.interviewer.education}
                    onChange={(e) => onChange(e, 'interviewer', 'education')}
                    required
                  />
                </Form.Group>
              </Col>
              <Col md={4}>
                <Form.Group>
                  <Form.Label>Professional experience</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={3}
                    value={form.interviewer.experience}
                    onChange={(e) => onChange(e, 'interviewer', 'experience')}
                    required
                  />
                </Form.Group>
              </Col>
            </Row>

            <div className="mt-4 d-flex align-items-center gap-3">
              <Button type="submit" variant="primary" disabled={manualLoading}>
                {manualLoading ? (
                  <>
                    <Spinner animation="border" size="sm" className="me-2" /> Processing…
                  </>
                ) : (
                  'Submit'
                )}
              </Button>
              {manualError && <span className="text-danger">{manualError}</span>}
            </div>
          </Form>
        </Card.Body>
      </Card>

      {manualResult?.html && (
        <Card className="shadow-sm mt-4">
          <Card.Header className="bg-primary text-white">
            <h5 className="mb-0">Your personalized interview plan (manual)</h5>
          </Card.Header>
          <Card.Body>
            <div className="prose" dangerouslySetInnerHTML={{ __html: manualResult.html }} />
          </Card.Body>
        </Card>
      )}
    </div>
  )
}
