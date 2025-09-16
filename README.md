
# InterviewerLens

Smart interview prep: enter interviewee + interviewer profiles, get predicted questions.
- **Frontend:** React (Vite), Bootstrap, Auth0 React SDK
- **Backend:** Django REST, Auth0 JWT, OpenAI API

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
