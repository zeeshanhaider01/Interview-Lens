
import React from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import LandingPage from './landing/LandingPage.jsx'

export default function Protected({ children }) {
  const { isAuthenticated, isLoading } = useAuth0()

  if (isLoading) return <div className="text-center p-5">Loading...</div>
  if (!isAuthenticated) return <LandingPage />
  return children
}
