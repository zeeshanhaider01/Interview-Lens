# Interview Lens Browser Extension (Chrome-first)

This extension collects LinkedIn profile sections and submits them to the Interview Lens backend using `prep_id`.

Current target:
- Chrome Manifest V3

Architecture is intentionally cross-browser friendly:
- `src/lib/browser-api.js` abstracts `chrome` vs `browser` API differences.
- Shared logic is isolated from platform-specific packaging.
- Manifest includes `browser_specific_settings` for future Firefox support.

## Features in this version

- Auth via Auth0 Authorization Code + PKCE using browser identity flow.
- Capture LinkedIn sections:
  - Experience
  - Education
  - Certifications
  - Projects
  - Skills
  - Honors & Awards
- Review/edit captured text in popup before submission.
- Create `prep_id` session from extension.
- Submit profile data to backend endpoint:
  - `POST /api/prep-sessions/{prep_id}/profiles`

## Load in Chrome (developer mode)

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select the `extension/` folder.

## Required settings in popup

- Backend API URL (default: `http://localhost:8000/api`)
- Auth0 domain
- Auth0 client ID
- Auth0 audience

## Security notes

- Uses short-lived access token.
- Does not store client secret.
- Stores auth/session state in extension local storage only.
- Data submission requires authenticated token and explicit `prep_id`.

## Next version (cross-browser)

- Add Firefox build/publish pipeline.
- Add Safari packaging with Xcode wrapper.
- Add browser-specific manifest overlays if needed.
