import React, { useState } from 'react'
import { Form, Button, Row, Col, Spinner, Card } from 'react-bootstrap'
import axios from 'axios'
import { useAuth0 } from '@auth0/auth0-react'

export default function ProfileForm() {
  const [form, setForm] = useState({
    interviewee: { name: '', email: '', education: '', experience: '' },
    interviewer: { name: '', education: '', experience: '' },
  })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null) // { html: string }
  const [error, setError] = useState(null)
  const { getAccessTokenSilently } = useAuth0()

  const onChange = (e, section, field) => {
    setForm(prev => ({
      ...prev,
      [section]: { ...prev[section], [field]: e.target.value }
    }))
  }

  const submit = async (e) => {
    e.preventDefault()
    setResult(null)
    setError(null)
    setLoading(true)
    try {
      const token = await getAccessTokenSilently({
        authorizationParams: {
          audience: import.meta.env.VITE_AUTH0_AUDIENCE,
          scope: 'openid profile email' // refresh handled by SDK if configured
        }
      })

      const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '')
      console.log('API base at runtime:', API_BASE)

      const resp = await axios.post(
        `${API_BASE}/api/predict-questions/`,
        form,
        { headers: { Authorization: `Bearer ${token}` } }
      )

      // New shape: { html: "<article>...</article>" }
      setResult(resp.data)
    } catch (err) {
      console.error('Axios error:', err)
      console.log('Backend response data:', err?.response?.data)
      console.log('Backend status code:', err?.response?.status)
      setError(err?.response?.data?.detail || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container my-4">
      <Card className="shadow-sm">
        <Card.Header className="bg-white">
          <h4 className="mb-0 text-primary">Enter Profiles</h4>
        </Card.Header>
        <Card.Body>
          <Form onSubmit={submit}>
            <h5 className="text-secondary">Interviewee</h5>
            <Row className="g-3">
              <Col md={6}>
                <Form.Group>
                  <Form.Label>Name</Form.Label>
                  <Form.Control
                    value={form.interviewee.name}
                    onChange={(e)=>onChange(e,'interviewee','name')}
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
                    onChange={(e)=>onChange(e,'interviewee','email')}
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
                    onChange={(e)=>onChange(e,'interviewee','education')}
                    required
                  />
                </Form.Group>
              </Col>
              <Col md={6}>
                <Form.Group>
                  <Form.Label>Professional Experience</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={3}
                    value={form.interviewee.experience}
                    onChange={(e)=>onChange(e,'interviewee','experience')}
                    required
                  />
                </Form.Group>
              </Col>
            </Row>

            <hr className="my-4"/>

            <h5 className="text-secondary">Interviewer</h5>
            <Row className="g-3">
              <Col md={4}>
                <Form.Group>
                  <Form.Label>Name</Form.Label>
                  <Form.Control
                    value={form.interviewer.name}
                    onChange={(e)=>onChange(e,'interviewer','name')}
                    required
                  />
                </Form.Group>
              </Col>
              <Col md={4}>
                <Form.Group>
                  <Form.Label>Educational Experience</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={3}
                    value={form.interviewer.education}
                    onChange={(e)=>onChange(e,'interviewer','education')}
                    required
                  />
                </Form.Group>
              </Col>
              <Col md={4}>
                <Form.Group>
                  <Form.Label>Professional Experience</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={3}
                    value={form.interviewer.experience}
                    onChange={(e)=>onChange(e,'interviewer','experience')}
                    required
                  />
                </Form.Group>
              </Col>
            </Row>

            <div className="mt-4 d-flex align-items-center gap-3">
              <Button type="submit" variant="primary" disabled={loading}>
                {loading ? <><Spinner animation="border" size="sm" className="me-2"/> Processing...</> : 'Submit'}
              </Button>
              {error && <span className="text-danger">{error}</span>}
            </div>
          </Form>
        </Card.Body>
      </Card>

      {result?.html && (
        <Card className="shadow-sm mt-4">
          <Card.Header className="bg-primary text-white">
            <h5 className="mb-0">Your Personalized Interview Plan</h5>
          </Card.Header>
          <Card.Body>
            {/* Render sanitized HTML from server */}
            <div
              className="prose"
              dangerouslySetInnerHTML={{ __html: result.html }}
            />
          </Card.Body>
        </Card>
      )}
    </div>
  )
}



// import React, { useState } from 'react'
// import { Form, Button, Row, Col, Spinner, Card } from 'react-bootstrap'
// import axios from 'axios'
// import { useAuth0 } from '@auth0/auth0-react'

// export default function ProfileForm() {
//   const [form, setForm] = useState({
//     interviewee: { name: '', email: '', education: '', experience: '' },
//     interviewer: { name: '', education: '', experience: '' },
//   })
//   const [loading, setLoading] = useState(false)
//   const [result, setResult] = useState(null)
//   const [error, setError] = useState(null)
//   const { getAccessTokenSilently } = useAuth0()

//   const onChange = (e, section, field) => {
//     setForm(prev => ({
//       ...prev,
//       [section]: { ...prev[section], [field]: e.target.value }
//     }))
//   }

//   const submit = async (e) => {
//     e.preventDefault()
//     setResult(null)
//     setError(null)
//     setLoading(true)
//     try {
//       const token = await getAccessTokenSilently({
//         authorizationParams: {
//           audience: import.meta.env.VITE_AUTH0_AUDIENCE,
//           scope: 'openid profile email'
//         }
//       })

//       // Use the deployed backend base URL from Vercel envs
//       const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '')
//       console.log('API base at runtime:', API_BASE)

//       const resp = await axios.post(
//         `${API_BASE}/api/predict-questions/`,
//         form,
//         { headers: { Authorization: `Bearer ${token}` } }
//       )
//       setResult(resp.data)
//     } catch (err) {
//       console.error('Axios error:', err)
//       console.log('Backend response data:', err?.response?.data)
//       console.log('Backend status code:', err?.response?.status)
//       setError(err?.response?.data?.detail || 'Something went wrong')
//     } finally {
//       setLoading(false)
//     }
//   }

//   return (
//     <div className="container my-4">
//       <Card className="shadow-sm">
//         <Card.Header className="bg-white">
//           <h4 className="mb-0 text-primary">Enter Profiles</h4>
//         </Card.Header>
//         <Card.Body>
//           <Form onSubmit={submit}>
//             <h5 className="text-secondary">Interviewee</h5>
//             <Row className="g-3">
//               <Col md={6}>
//                 <Form.Group>
//                   <Form.Label>Name</Form.Label>
//                   <Form.Control
//                     value={form.interviewee.name}
//                     onChange={(e)=>onChange(e,'interviewee','name')}
//                     required
//                   />
//                 </Form.Group>
//               </Col>
//               <Col md={6}>
//                 <Form.Group>
//                   <Form.Label>Email</Form.Label>
//                   <Form.Control
//                     type="email"
//                     value={form.interviewee.email}
//                     onChange={(e)=>onChange(e,'interviewee','email')}
//                     required
//                   />
//                 </Form.Group>
//               </Col>
//               <Col md={6}>
//                 <Form.Group>
//                   <Form.Label>Education</Form.Label>
//                   <Form.Control
//                     as="textarea"
//                     rows={3}
//                     value={form.interviewee.education}
//                     onChange={(e)=>onChange(e,'interviewee','education')}
//                     required
//                   />
//                 </Form.Group>
//               </Col>
//               <Col md={6}>
//                 <Form.Group>
//                   <Form.Label>Professional Experience</Form.Label>
//                   <Form.Control
//                     as="textarea"
//                     rows={3}
//                     value={form.interviewee.experience}
//                     onChange={(e)=>onChange(e,'interviewee','experience')}
//                     required
//                   />
//                 </Form.Group>
//               </Col>
//             </Row>

//             <hr className="my-4"/>

//             <h5 className="text-secondary">Interviewer</h5>
//             <Row className="g-3">
//               <Col md={4}>
//                 <Form.Group>
//                   <Form.Label>Name</Form.Label>
//                   <Form.Control
//                     value={form.interviewer.name}
//                     onChange={(e)=>onChange(e,'interviewer','name')}
//                     required
//                   />
//                 </Form.Group>
//               </Col>
//               <Col md={4}>
//                 <Form.Group>
//                   <Form.Label>Educational Experience</Form.Label>
//                   <Form.Control
//                     as="textarea"
//                     rows={3}
//                     value={form.interviewer.education}
//                     onChange={(e)=>onChange(e,'interviewer','education')}
//                     required
//                   />
//                 </Form.Group>
//               </Col>
//               <Col md={4}>
//                 <Form.Group>
//                   <Form.Label>Professional Experience</Form.Label>
//                   <Form.Control
//                     as="textarea"
//                     rows={3}
//                     value={form.interviewer.experience}
//                     onChange={(e)=>onChange(e,'interviewer','experience')}
//                     required
//                   />
//                 </Form.Group>
//               </Col>
//             </Row>

//             <div className="mt-4 d-flex align-items-center gap-3">
//               <Button type="submit" variant="primary" disabled={loading}>
//                 {loading ? <><Spinner animation="border" size="sm" className="me-2"/> Processing...</> : 'Submit'}
//               </Button>
//               {error && <span className="text-danger">{error}</span>}
//             </div>
//           </Form>
//         </Card.Body>
//       </Card>

//       {result && (
//         <Card className="shadow-sm mt-4">
//           <Card.Header className="bg-primary text-white">
//             <h5 className="mb-0">Predicted Questions</h5>
//           </Card.Header>
//           <Card.Body>
//             <ol className="ps-3">
//               {result.questions?.map((q, i)=>(<li key={i} className="mb-2">{q}</li>))}
//             </ol>
//             {result.tips?.length>0 && (
//               <>
//                 <h6 className="text-primary">Prep Tips</h6>
//                 <ul className="ps-3">
//                   {result.tips.map((t, i)=>(<li key={i}>{t}</li>))}
//                 </ul>
//               </>
//             )}
//           </Card.Body>
//         </Card>
//       )}
//     </div>
//   )
// }
