
import React from 'react'
import { Navbar, Container, Nav, Dropdown, Image, Button } from 'react-bootstrap'
import { useAuth0 } from '@auth0/auth0-react'
import logo from '../assets/logo.svg'

export default function Header() {
  const { isAuthenticated, user, loginWithRedirect, logout } = useAuth0()

  return (
    <Navbar bg="primary" data-bs-theme="dark" expand="lg" className="shadow-sm">
      <Container>
        <Navbar.Brand href="#" className="d-flex align-items-center gap-2">
          <img src={logo} alt="InterviewerLens" height={32} />
        </Navbar.Brand>
        <Nav className="ms-auto">
          {!isAuthenticated ? (
            <Button variant="light" onClick={() => loginWithRedirect()}>
              Sign up / Log in
            </Button>
          ) : (
            <Dropdown align="end">
              <Dropdown.Toggle variant="light" id="user-menu" className="d-flex align-items-center gap-2">
                <Image
                  src={user?.picture || 'https://ui-avatars.com/api/?name=U'}
                  roundedCircle
                  width={28}
                  height={28}
                />
                <span className="d-none d-sm-inline">{user?.name || 'Account'}</span>
              </Dropdown.Toggle>
              <Dropdown.Menu>
                <Dropdown.Item onClick={() => logout({ logoutParams: { returnTo: window.location.origin }})}>
                  Logout
                </Dropdown.Item>
              </Dropdown.Menu>
            </Dropdown>
          )}
        </Nav>
      </Container>
    </Navbar>
  )
}
