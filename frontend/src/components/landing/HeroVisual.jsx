import React from 'react'
import { Badge, Card } from 'react-bootstrap'

function ProfileCard({ name, role, initials, variant }) {
  return (
    <Card className="border shadow-sm flex-fill" style={{ minWidth: 0 }}>
      <Card.Body className="py-2 px-2 text-center">
        <div
          className={`rounded-circle mx-auto mb-2 d-flex align-items-center justify-content-center text-white fw-semibold ${variant}`}
          style={{ width: 40, height: 40, fontSize: '0.85rem' }}
        >
          {initials}
        </div>
        <div className="fw-semibold small text-truncate">{name}</div>
        <div className="text-muted" style={{ fontSize: '0.7rem' }}>
          {role}
        </div>
      </Card.Body>
    </Card>
  )
}

function TopicRow({ title, likelihood, variant }) {
  return (
    <div className="d-flex justify-content-between align-items-center gap-2 py-2 border-bottom">
      <span className="small fw-semibold">{title}</span>
      <Badge bg={variant} className="flex-shrink-0" style={{ fontSize: '0.65rem' }}>
        {likelihood}
      </Badge>
    </div>
  )
}

export default function HeroVisual() {
  return (
    <div className="position-relative">
      <Card className="border-0 shadow-sm" style={{ background: 'linear-gradient(180deg, #f8fbff 0%, #ffffff 100%)' }}>
        <Card.Body className="p-3 p-md-4">
          <div
            className="rounded-top border bg-white px-2 py-1 d-flex align-items-center gap-1 mb-3"
            style={{ fontSize: '0.7rem' }}
          >
            <span className="rounded-circle bg-danger" style={{ width: 8, height: 8 }} />
            <span className="rounded-circle bg-warning" style={{ width: 8, height: 8 }} />
            <span className="rounded-circle bg-success" style={{ width: 8, height: 8 }} />
            <span className="text-muted ms-1">LinkedIn · Profile capture</span>
          </div>

          <div className="d-flex gap-2 mb-3">
            <ProfileCard
              name="Ahmad Hassan"
              role="Software Engineer"
              initials="AH"
              variant="bg-primary"
            />
            <ProfileCard
              name="Omar Farooq"
              role="Engineering Manager"
              initials="OF"
              variant="bg-info text-dark"
            />
          </div>

          <div className="text-center text-muted mb-2" style={{ fontSize: '0.75rem' }}>
            <span className="d-inline-block border rounded-pill px-2 py-1 bg-white">
              Chrome extension · Capture both profiles
            </span>
          </div>

          <div className="text-center text-primary mb-2" style={{ fontSize: '1.25rem' }}>
            ↓
          </div>

          <Card className="border-primary border-opacity-25 shadow-sm">
            <Card.Body className="py-3 px-3">
              <div className="fw-semibold text-primary mb-2">Your topic map</div>
              <TopicRow title="System design" likelihood="HIGH" variant="danger" />
              <TopicRow title="Leadership stories" likelihood="MEDIUM" variant="warning" />
              <TopicRow title="Domain deep-dive" likelihood="LOWER" variant="secondary" />
              <div className="d-flex flex-wrap gap-1 mt-3">
                {['scalability', 'STAR stories', 'API design'].map((anchor) => (
                  <Badge key={anchor} bg="light" text="dark" className="border fw-normal">
                    {anchor}
                  </Badge>
                ))}
              </div>
            </Card.Body>
          </Card>
        </Card.Body>
      </Card>
    </div>
  )
}
