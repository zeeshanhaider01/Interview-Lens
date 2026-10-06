import React, { useState } from 'react'
import './hero-visual.css'

function LensLogo() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="3" fill="#0d6efd" />
      <path
        d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1l2.1-2.1M17 7l2.1-2.1"
        stroke="#0d6efd"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <circle cx="12" cy="12" r="8.5" stroke="#0d6efd" strokeWidth="1.5" opacity="0.45" />
    </svg>
  )
}

function ShieldCheck() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 2l8 4v6c0 5-3.5 9.5-8 10-4.5-.5-8-5-8-10V6l8-4z"
        stroke="#6c757d"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path
        d="M9 12l2 2 4-4"
        stroke="#6c757d"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function TrendUpIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 18h16" stroke="#c92a2a" strokeWidth="2" strokeLinecap="round" />
      <path
        d="M7 14l4-4 3 3 5-6"
        stroke="#c92a2a"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function StarIcon({ color = '#e67700' }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3l2.6 5.8 6.3.6-4.7 4.1 1.4 6.2L12 17.8 6.4 20.7l1.4-6.2L3.1 9.4l6.3-.6L12 3z"
        stroke={color}
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function TrendDownIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 6h16" stroke="#868e96" strokeWidth="2" strokeLinecap="round" />
      <path
        d="M7 10l4 4 3-3 5 6"
        stroke="#868e96"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function BarChartIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 20V10M12 20V4M18 20v-7" stroke="#0d6efd" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function CodeIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M9 8L5 12l4 4M15 8l4 4-4 4"
        stroke="#0d6efd"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

const TOPICS = [
  { title: 'System design', likelihood: 'HIGH', level: 'high', Icon: TrendUpIcon },
  { title: 'Leadership stories', likelihood: 'MEDIUM', level: 'medium', Icon: StarIcon },
  { title: 'Domain deep-dive', likelihood: 'LOWER', level: 'lower', Icon: TrendDownIcon },
]

const FOCUS_AREAS = [
  { label: 'scalability', Icon: BarChartIcon },
  { label: 'STAR stories', Icon: () => <StarIcon color="#0d6efd" /> },
  { label: 'API design', Icon: CodeIcon },
]

function ProfileCard({ label, name, role, avatarSrc, initials }) {
  const [imgFailed, setImgFailed] = useState(false)

  return (
    <div className="hero-visual__profile-card">
      <div className="hero-visual__banner">
        <span className="hero-visual__role-pill">{label}</span>
      </div>
      <div className="hero-visual__avatar-wrap">
        {!imgFailed ? (
          <img
            src={avatarSrc}
            alt={`Fictional demo profile: ${name}, ${role}`}
            className="hero-visual__avatar"
            width={80}
            height={80}
            onError={() => setImgFailed(true)}
          />
        ) : (
          <div
            className="hero-visual__avatar d-flex align-items-center justify-content-center bg-primary text-white fw-bold"
            style={{ fontSize: '1.1rem' }}
          >
            {initials}
          </div>
        )}
      </div>
      <div className="hero-visual__name">{name}</div>
      <div className="hero-visual__role">{role}</div>
    </div>
  )
}

export default function HeroVisual() {
  return (
    <div className="hero-visual">
      <div className="hero-visual__panel">
        <div className="hero-visual__header">
          <div className="hero-visual__brand">
            <LensLogo />
            <span>InterviewerLens</span>
          </div>
          <div className="hero-visual__tagline">
            <ShieldCheck />
            <span>AI-Powered Interview Intelligence</span>
          </div>
        </div>

        <div className="hero-visual__profiles">
          <ProfileCard
            label="Interviewee"
            name="Ahmed Hassan"
            role="Software Engineer"
            avatarSrc="/landing/ahmed-hassan-avatar.png"
            initials="AH"
          />
          <ProfileCard
            label="Interviewer"
            name="Omar Farooq"
            role="Engineering Manager"
            avatarSrc="/landing/omar-farooq-avatar.png"
            initials="OF"
          />
        </div>

        <div className="hero-visual__topic-map">
          <div className="hero-visual__topic-title">Your topic map</div>
          <div className="hero-visual__topic-context">
            Prep for <strong>Ahmed Hassan</strong> · Interview with <strong>Omar Farooq</strong>
          </div>
          <div className="hero-visual__topic-grid">
            <div className="hero-visual__topic-list">
              {TOPICS.map(({ title, likelihood, level, Icon }) => (
                <div key={title} className="hero-visual__topic-row">
                  <div className="hero-visual__topic-label">
                    <Icon />
                    <span>{title}</span>
                  </div>
                  <span className={`hero-visual__likelihood hero-visual__likelihood--${level}`}>
                    {likelihood}
                  </span>
                </div>
              ))}
            </div>
            <div>
              <div className="hero-visual__focus-heading">Recommended focus areas</div>
              <div className="hero-visual__focus-chips">
                {FOCUS_AREAS.map(({ label, Icon }) => (
                  <span key={label} className="hero-visual__focus-chip">
                    <Icon />
                    {label}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
