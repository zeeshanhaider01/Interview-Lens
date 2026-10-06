import React from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Button, Col, Container, Row } from 'react-bootstrap'
import HeroVisual from './HeroVisual.jsx'

const STEPS = [
  {
    title: 'Create a prep session',
    body: 'Sign in and add your target role and company on the web dashboard.',
  },
  {
    title: 'Capture both profiles',
    body: 'Use the Chrome extension on LinkedIn to submit your profile and your interviewer’s.',
  },
  {
    title: 'Get your topic map',
    body: 'Generate prioritized focus areas with likelihood scores, review pointers, and session prep priorities.',
  },
]

const DIFFERENTIATORS = [
  {
    title: 'Built around your interviewer',
    body: 'We analyze both LinkedIn profiles — yours and theirs — not just a job description.',
  },
  {
    title: 'See what matters most',
    body: 'Topics ranked HIGH, MEDIUM, or LOWER so you prep the areas most likely to come up first.',
  },
  {
    title: 'More than topic names',
    body: 'Each topic shows why it matters and a few things to revisit, plus overall prep priorities for the session.',
  },
]

export default function LandingPage() {
  const { loginWithRedirect } = useAuth0()
  const extensionOpenUrl = (import.meta.env.VITE_EXTENSION_OPEN_URL || '').trim()

  return (
    <div style={{ background: 'linear-gradient(180deg, #f8fbff 0%, #ffffff 45%)' }}>
      <Container className="py-5 py-lg-6">
        <Row className="align-items-center g-4 g-lg-5">
          <Col lg={6}>
            <h1 className="display-5 fw-bold mb-3">
              <span className="text-primary">Walk in knowing</span>{' '}
              <span className="text-dark">what your interviewer is likely to focus on</span>
            </h1>

            <p className="lead text-secondary mb-4" style={{ fontSize: '1.05rem' }}>
              InterviewerLens uses our Chrome extension to capture both LinkedIn profiles—yours and
              theirs—then builds a prioritized <strong>topic map</strong> with likelihood scores
              (HIGH / MEDIUM / LOWER) and review pointers for each topic. Add your target role and company for
              sharper results.
            </p>

            <div className="d-flex flex-wrap gap-2 mb-3">
              <Button size="lg" onClick={() => loginWithRedirect()}>
                Start free prep session
              </Button>
              {extensionOpenUrl ? (
                <Button
                  size="lg"
                  variant="outline-primary"
                  href={extensionOpenUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Install Chrome extension
                </Button>
              ) : (
                <Button size="lg" variant="outline-primary" href="#how-it-works">
                  See how it works
                </Button>
              )}
            </div>

            <p className="small text-muted mb-0">
              Predictions are AI-generated topic guidance, not guaranteed interview questions.
            </p>
          </Col>

          <Col lg={6}>
            <HeroVisual />
          </Col>
        </Row>
      </Container>

      <Container id="how-it-works" className="pb-5">
        <h2 className="h4 text-primary fw-bold mb-4">How it works</h2>
        <Row className="g-3">
          {STEPS.map((step, index) => (
            <Col md={4} key={step.title}>
              <div className="h-100 border rounded-3 bg-white p-3 shadow-sm">
                <div
                  className="rounded-circle bg-primary text-white d-flex align-items-center justify-content-center fw-semibold mb-3"
                  style={{ width: 32, height: 32, fontSize: '0.9rem' }}
                >
                  {index + 1}
                </div>
                <h3 className="h6 fw-semibold mb-2">{step.title}</h3>
                <p className="small text-secondary mb-0">{step.body}</p>
              </div>
            </Col>
          ))}
        </Row>
      </Container>

      <Container className="pb-5">
        <h2 className="h4 text-primary fw-bold mb-4">Prep smarter, not longer</h2>
        <Row className="g-3">
          {DIFFERENTIATORS.map((item) => (
            <Col md={4} key={item.title}>
              <div className="h-100 border rounded-3 bg-white p-3 shadow-sm">
                <h3 className="h6 fw-semibold mb-2">{item.title}</h3>
                <p className="small text-secondary mb-0">{item.body}</p>
              </div>
            </Col>
          ))}
        </Row>
      </Container>

      <Container className="pb-5 text-center">
        <h2 className="h4 fw-bold mb-3">Ready to prep smarter?</h2>
        <Button size="lg" onClick={() => loginWithRedirect()}>
          Sign up to get started
        </Button>
        <p className="small text-muted mt-3 mb-0">
          Predictions are AI-generated topic guidance, not guaranteed interview questions.
        </p>
      </Container>
    </div>
  )
}
