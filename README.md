
# InterviewerLens

Smart interview prep: enter interviewee + interviewer profiles, get predicted questions.
- **Frontend:** React (Vite), Bootstrap, Auth0 React SDK
- **Backend:** Django REST, Auth0 JWT, OpenAI API
- **Extension:** Chrome MV3 collector (`extension/`) for LinkedIn profile ingestion

## Run locally

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in Auth0 + OpenAI keys
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### Frontend
```bash
cd frontend
cp .env.example .env  # set your Auth0 domain, client id, audience
npm install
npm run dev
```

Open http://localhost:5173, log in, and submit the form.

### Browser extension (Chrome developer mode)
```bash
# Load unpacked extension from:
extension/
```

Key backend endpoints for extension:
- `POST /api/prep-sessions/`
- `POST /api/prep-sessions/{prep_id}/profiles`

## Staging and production setup (Render)

This project now supports:
- SQLite by default for local development
- Postgres when `DATABASE_URL` is present (staging/production)

Recommended rollout path:
1. Develop locally (`backend/.env` from `backend/.env.example`)
2. Deploy branch to a staging environment on Render
3. Verify core flows on staging
4. Promote the same commit to production

Render services to run:
- Web service (Django API)
- Worker service (Celery)
- Managed Redis
- Managed Postgres

Notes:
- `render.yaml` includes web + worker + redis + postgres blueprint entries.
- For staging, create a separate Render Blueprint environment or clone services with `-staging` names.
