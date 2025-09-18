
import React from 'react'
import { Auth0Provider } from '@auth0/auth0-react'
import Header from '../components/Header.jsx'
import Protected from '../components/Protected.jsx'
import ProfileForm from '../components/ProfileForm.jsx'

const domain = import.meta.env.VITE_AUTH0_DOMAIN
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID
const audience = import.meta.env.VITE_AUTH0_AUDIENCE

export default function App() {
  return (
    <Auth0Provider
      domain={domain}
      clientId={clientId}
      authorizationParams={{
        redirect_uri: window.location.origin,
        audience: audience,
        scope: "openid profile email offline_access"
      }}
      cacheLocation="localstorage"
      useRefreshTokens={true}
    >
      <Header />
      <Protected>
        <ProfileForm />
      </Protected>
    </Auth0Provider>
  )
}
