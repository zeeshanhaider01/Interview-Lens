
import React from 'react'
import { useAuth0 } from '@auth0/auth0-react'

export default function Protected({ children }) {
  const { isAuthenticated, isLoading, loginWithRedirect } = useAuth0()

  if (isLoading) return <div className="text-center p-5">Loading...</div>
  if (!isAuthenticated) {
    return (
      <div className="container py-5">
        <h2 className="text-primary fw-bold">Get interview-ready with InterviewerLens</h2>
        <p className="text-secondary">
          Smart predictions of what your specific interviewer is likely to ask—based on both your profile and theirs.
          Save time, focus your prep, and walk in confident.
        </p>
        <button className="btn btn-primary" onClick={() => loginWithRedirect()}>
          Sign up to get started
        </button>
      </div>
    )
  }
  return children
}
