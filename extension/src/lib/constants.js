const SECTION_KEYS = [
  "experience",
  "education",
  "certifications",
  "projects",
  "skills",
  "honors_awards",
];

const PROFILE_ROLES = {
  INTERVIEWEE: "INTERVIEWEE",
  INTERVIEWER: "INTERVIEWER",
};

const CAPTURE_VIEW_MODES = {
  DEFAULT_PROFILE: "default_profile",
  PREP_SESSION: "prep_session",
};

const CAPTURE_BADGE_KINDS = {
  DEFAULT_PROFILE: "DEFAULT_PROFILE",
};

const STORAGE_KEYS = {
  AUTH: "auth_state",
  LAST_AUTH_RESULT: "last_auth_result",
  SETTINGS: "collector_settings",
  LAST_CAPTURE: "last_capture",
  ACTIVE_PREP_ID: "active_prep_id",
  POPUP_DRAFT: "popup_draft",
  POPUP_ACCESSIBILITY_PREFS: "popup_accessibility_prefs",
};

export { CAPTURE_BADGE_KINDS, CAPTURE_VIEW_MODES, PROFILE_ROLES, SECTION_KEYS, STORAGE_KEYS };
