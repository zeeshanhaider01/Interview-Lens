import { queryTabs, runtimeSendMessage, sendMessageToTab, storageGet } from "../lib/browser-api.js";
import { getSettings, saveSettings } from "../lib/config.js";
import { PROFILE_ROLES, SECTION_KEYS, STORAGE_KEYS } from "../lib/constants.js";
import { normalizeCapture } from "../lib/normalizer.js";

const ui = {
  apiBaseUrl: document.getElementById("apiBaseUrl"),
  dashboardUrl: document.getElementById("dashboardUrl"),
  auth0Domain: document.getElementById("auth0Domain"),
  auth0ClientId: document.getElementById("auth0ClientId"),
  auth0Audience: document.getElementById("auth0Audience"),
  clearPrepIdOnLogout: document.getElementById("clearPrepIdOnLogout"),
  saveSettingsButton: document.getElementById("saveSettingsButton"),
  loginButton: document.getElementById("loginButton"),
  logoutButton: document.getElementById("logoutButton"),
  authStatus: document.getElementById("authStatus"),
  prepIdInput: document.getElementById("prepIdInput"),
  clearPrepSessionButton: document.getElementById("clearPrepSessionButton"),
  activePrepBadge: document.getElementById("activePrepBadge"),
  activePrepBadgeValue: document.getElementById("activePrepBadgeValue"),
  roleSelect: document.getElementById("roleSelect"),
  intervieweeDecisionSection: document.getElementById("intervieweeDecisionSection"),
  intervieweeDecisionHint: document.getElementById("intervieweeDecisionHint"),
  intervieweeChoiceReuse: document.getElementById("intervieweeChoiceReuse"),
  intervieweeChoiceUpload: document.getElementById("intervieweeChoiceUpload"),
  intervieweeUploadScopeSection: document.getElementById("intervieweeUploadScopeSection"),
  uploadScopeSessionOnly: document.getElementById("uploadScopeSessionOnly"),
  uploadScopeDefault: document.getElementById("uploadScopeDefault"),
  createPrepSessionButton: document.getElementById("createPrepSessionButton"),
  captureButton: document.getElementById("captureButton"),
  submitButton: document.getElementById("submitButton"),
  dashboardCtaSection: document.getElementById("dashboardCtaSection"),
  openDashboardButton: document.getElementById("openDashboardButton"),
  statusMessage: document.getElementById("statusMessage"),
  fields: {
    experience: document.getElementById("experienceField"),
    education: document.getElementById("educationField"),
    certifications: document.getElementById("certificationsField"),
    projects: document.getElementById("projectsField"),
    skills: document.getElementById("skillsField"),
    honors_awards: document.getElementById("honorsAwardsField"),
  },
};

let latestDashboardUrl = "";
let isAuthenticated = false;
let hasDefaultIntervieweeProfile = false;

const INTERVIEWEE_PROFILE_CHOICES = {
  REUSE_SAVED: "reuse_saved",
  UPLOAD_NEW: "upload_new",
};

const INTERVIEWEE_UPLOAD_SCOPES = {
  SESSION_ONLY: "session_only",
  SAVE_AS_DEFAULT: "save_as_default",
};

function setStatus(message, isError = false) {
  ui.statusMessage.textContent = message;
  ui.statusMessage.style.color = isError ? "#fca5a5" : "#a7f3d0";
}

function setDashboardCtaUrl(url) {
  latestDashboardUrl = (url ?? "").trim();
  ui.dashboardCtaSection.classList.toggle("hidden", !latestDashboardUrl);
}

function setActivePrepBadge(prepId) {
  const value = String(prepId ?? "").trim();
  ui.activePrepBadge.classList.toggle("hidden", !value);
  ui.activePrepBadgeValue.textContent = value;
}

function setAuthUiState(authState) {
  isAuthenticated = Boolean(authState?.accessToken);
  ui.authStatus.textContent = isAuthenticated
    ? "Auth status: authenticated"
    : "Auth status: not authenticated";
  ui.loginButton.disabled = isAuthenticated;
  ui.logoutButton.disabled = !isAuthenticated;
  ui.createPrepSessionButton.disabled = !isAuthenticated;
  ui.submitButton.disabled = !isAuthenticated;
}

function getIntervieweeChoice() {
  return ui.intervieweeChoiceUpload.checked
    ? INTERVIEWEE_PROFILE_CHOICES.UPLOAD_NEW
    : INTERVIEWEE_PROFILE_CHOICES.REUSE_SAVED;
}

function getIntervieweeUploadScope() {
  return ui.uploadScopeDefault.checked
    ? INTERVIEWEE_UPLOAD_SCOPES.SAVE_AS_DEFAULT
    : INTERVIEWEE_UPLOAD_SCOPES.SESSION_ONLY;
}

function updateIntervieweeDecisionUi() {
  const isInterviewee = ui.roleSelect.value === PROFILE_ROLES.INTERVIEWEE;
  ui.intervieweeDecisionSection.classList.toggle("hidden", !isInterviewee);
  const choice = getIntervieweeChoice();
  ui.intervieweeUploadScopeSection.classList.toggle(
    "hidden",
    !isInterviewee || choice !== INTERVIEWEE_PROFILE_CHOICES.UPLOAD_NEW
  );
  if (!isInterviewee) {
    return;
  }
  ui.intervieweeChoiceReuse.disabled = !hasDefaultIntervieweeProfile;
  if (!hasDefaultIntervieweeProfile && choice === INTERVIEWEE_PROFILE_CHOICES.REUSE_SAVED) {
    ui.intervieweeChoiceUpload.checked = true;
    ui.intervieweeChoiceReuse.checked = false;
  }
  ui.intervieweeDecisionHint.textContent = hasDefaultIntervieweeProfile
    ? "Reuse your saved interviewee profile or upload a new one for this prep session."
    : "No saved default interviewee profile found. Upload a new profile first.";
}

function buildDashboardUrl(baseUrl, prepId) {
  const cleanBaseUrl = (baseUrl ?? "").trim().replace(/\/+$/, "");
  if (!cleanBaseUrl) {
    return "";
  }
  if (!prepId) {
    return cleanBaseUrl;
  }
  const encodedPrepId = encodeURIComponent(prepId.trim());
  return `${cleanBaseUrl}/?prep_id=${encodedPrepId}`;
}

function readEditedSections() {
  const sections = {};
  for (const key of SECTION_KEYS) {
    sections[key] = ui.fields[key].value
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
  }
  return sections;
}

function writeSections(sections = {}) {
  for (const key of SECTION_KEYS) {
    ui.fields[key].value = (sections[key] ?? []).join("\n");
  }
}

async function withRuntimeMessage(message) {
  const response = await runtimeSendMessage(message);
  if (!response?.ok) {
    throw new Error(response?.error || "Unknown extension runtime error.");
  }
  return response.data;
}

async function persistActivePrepId(prepId) {
  const value = String(prepId ?? "").trim();
  await withRuntimeMessage({ type: "SET_ACTIVE_PREP_ID", prepId: value });
  return value;
}

async function refreshIntervieweeDecisionState() {
  if (!isAuthenticated) {
    hasDefaultIntervieweeProfile = false;
    updateIntervieweeDecisionUi();
    return;
  }
  try {
    const baseline = await withRuntimeMessage({ type: "GET_INTERVIEWEE_BASELINE_PROFILE" });
    hasDefaultIntervieweeProfile = Boolean(baseline?.exists);
  } catch (_error) {
    hasDefaultIntervieweeProfile = false;
  }

  const prepId = ui.prepIdInput.value.trim();
  if (prepId) {
    try {
      const detail = await withRuntimeMessage({ type: "GET_PREP_SESSION_DETAIL", prepId });
      if (detail?.has_default_interviewee_profile) {
        hasDefaultIntervieweeProfile = true;
      }
    } catch (_error) {
      // Keep baseline capability from profile endpoint even when session lookup fails.
    }
  }
  updateIntervieweeDecisionUi();
}

async function loadInitialState() {
  const settings = await getSettings();
  ui.apiBaseUrl.value = settings.apiBaseUrl;
  ui.dashboardUrl.value = settings.dashboardUrl;
  ui.auth0Domain.value = settings.auth0Domain;
  ui.auth0ClientId.value = settings.auth0ClientId;
  ui.auth0Audience.value = settings.auth0Audience;
  ui.clearPrepIdOnLogout.checked = Boolean(settings.clearPrepIdOnLogout);

  const authState = await withRuntimeMessage({ type: "AUTH_STATE" });
  setAuthUiState(authState);

  const activeState = await withRuntimeMessage({ type: "GET_ACTIVE_PREP_ID" });
  const activePrepId = String(activeState?.prepId ?? "").trim();
  if (activePrepId) {
    ui.prepIdInput.value = activePrepId;
    setDashboardCtaUrl(buildDashboardUrl(settings.dashboardUrl, activePrepId));
  }
  setActivePrepBadge(activePrepId);

  const store = await storageGet(STORAGE_KEYS.LAST_CAPTURE);
  const cached = store[STORAGE_KEYS.LAST_CAPTURE];
  if (!activePrepId && cached?.prepId) {
    ui.prepIdInput.value = cached.prepId;
    await persistActivePrepId(cached.prepId);
    setDashboardCtaUrl(buildDashboardUrl(settings.dashboardUrl, cached.prepId));
    setActivePrepBadge(cached.prepId);
  }
  if (cached?.role && Object.values(PROFILE_ROLES).includes(cached.role)) {
    ui.roleSelect.value = cached.role;
  }
  writeSections(cached?.payload?.extracted_sections ?? {});
  await refreshIntervieweeDecisionState();
}

async function getCurrentLinkedInTab() {
  const tabs = await queryTabs({ active: true, currentWindow: true });
  const active = tabs?.[0];
  if (!active?.id || !active.url?.includes("linkedin.com")) {
    throw new Error("Open a LinkedIn profile tab and keep it active.");
  }
  return active;
}

ui.saveSettingsButton.addEventListener("click", async () => {
  try {
    await saveSettings({
      apiBaseUrl: ui.apiBaseUrl.value,
      dashboardUrl: ui.dashboardUrl.value,
      auth0Domain: ui.auth0Domain.value,
      auth0ClientId: ui.auth0ClientId.value,
      auth0Audience: ui.auth0Audience.value,
      clearPrepIdOnLogout: ui.clearPrepIdOnLogout.checked,
    });
    setStatus("Settings saved.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

ui.loginButton.addEventListener("click", async () => {
  try {
    const authState = await withRuntimeMessage({ type: "AUTH_LOGIN" });
    setAuthUiState(authState);
    await refreshIntervieweeDecisionState();
    setStatus("Authentication successful.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

ui.logoutButton.addEventListener("click", async () => {
  try {
    await withRuntimeMessage({ type: "AUTH_LOGOUT" });
    setAuthUiState(null);
    hasDefaultIntervieweeProfile = false;
    updateIntervieweeDecisionUi();
    if (ui.clearPrepIdOnLogout.checked) {
      ui.prepIdInput.value = "";
      setDashboardCtaUrl("");
      setActivePrepBadge("");
      setStatus("Logged out. Active prep_id cleared.");
      return;
    }
    setStatus("Logged out. Login required before creating/submitting.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

ui.createPrepSessionButton.addEventListener("click", async () => {
  try {
    const data = await withRuntimeMessage({
      type: "CREATE_PREP_SESSION",
      payload: { title: "Created from extension" },
    });
    ui.prepIdInput.value = data.prep_id;
    await persistActivePrepId(data.prep_id);
    setDashboardCtaUrl(buildDashboardUrl(ui.dashboardUrl.value, data.prep_id));
    setActivePrepBadge(data.prep_id);
    await refreshIntervieweeDecisionState();
    setStatus("New prep session created.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

ui.prepIdInput.addEventListener("change", async () => {
  try {
    const prepId = await persistActivePrepId(ui.prepIdInput.value);
    setDashboardCtaUrl(buildDashboardUrl(ui.dashboardUrl.value, prepId));
    setActivePrepBadge(prepId);
    await refreshIntervieweeDecisionState();
  } catch (error) {
    setStatus(error.message, true);
  }
});

ui.clearPrepSessionButton.addEventListener("click", async () => {
  try {
    await withRuntimeMessage({ type: "CLEAR_ACTIVE_PREP_ID" });
    ui.prepIdInput.value = "";
    setDashboardCtaUrl("");
    setActivePrepBadge("");
    await refreshIntervieweeDecisionState();
    setStatus("Active prep_id cleared.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

ui.captureButton.addEventListener("click", async () => {
  try {
    if (
      ui.roleSelect.value === PROFILE_ROLES.INTERVIEWEE &&
      getIntervieweeChoice() === INTERVIEWEE_PROFILE_CHOICES.REUSE_SAVED
    ) {
      throw new Error("Reuse mode does not require capture. Switch to upload mode to capture a new interviewee profile.");
    }
    const prepId = ui.prepIdInput.value.trim();
    if (prepId) {
      await persistActivePrepId(prepId);
      setActivePrepBadge(prepId);
    }
    const activeTab = await getCurrentLinkedInTab();
    const response = await sendMessageToTab(activeTab.id, { type: "SCRAPE_PROFILE" });
    if (!response?.ok) {
      throw new Error(response?.error ?? "Failed to parse LinkedIn page.");
    }
    const normalized = normalizeCapture(response.data);
    writeSections(normalized.extracted_sections);
    await withRuntimeMessage({
      type: "SAVE_LAST_CAPTURE",
      payload: {
        prepId: ui.prepIdInput.value.trim(),
        role: ui.roleSelect.value,
        payload: normalized,
      },
    });
    setStatus("Profile captured. Review and edit before submit.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

ui.submitButton.addEventListener("click", async () => {
  try {
    if (!isAuthenticated) {
      throw new Error("Login required before submit.");
    }
    const prepId = ui.prepIdInput.value.trim();
    const role = ui.roleSelect.value;
    if (!prepId) {
      throw new Error("prep_id is required before submit.");
    }
    await persistActivePrepId(prepId);
    setActivePrepBadge(prepId);
    if (!Object.values(PROFILE_ROLES).includes(role)) {
      throw new Error("Select a valid profile role.");
    }

    let uploadScope = INTERVIEWEE_UPLOAD_SCOPES.SESSION_ONLY;
    if (role === PROFILE_ROLES.INTERVIEWEE) {
      const choice = getIntervieweeChoice();
      if (choice === INTERVIEWEE_PROFILE_CHOICES.REUSE_SAVED) {
        if (!hasDefaultIntervieweeProfile) {
          throw new Error("No default interviewee profile found. Upload a new interviewee profile first.");
        }
        setDashboardCtaUrl(buildDashboardUrl(ui.dashboardUrl.value, prepId));
        setStatus(
          "Using saved default interviewee profile. Submit interviewer profile to continue this prep session."
        );
        return;
      }
      uploadScope = getIntervieweeUploadScope();
    }

    const activeTab = await getCurrentLinkedInTab();
    const payload = {
      role,
      source: "LINKEDIN",
      source_url: activeTab.url,
      extracted_sections: readEditedSections(),
      confidence_flags: {
        edited_by_user: true,
      },
      metadata: {
        submitted_from: "chrome_extension",
      },
    };

    if (role === PROFILE_ROLES.INTERVIEWEE) {
      if (uploadScope === INTERVIEWEE_UPLOAD_SCOPES.SAVE_AS_DEFAULT) {
        await withRuntimeMessage({
          type: "UPSERT_INTERVIEWEE_BASELINE_PROFILE",
          payload: {
            source: "LINKEDIN",
            source_url: activeTab.url,
            extracted_sections: payload.extracted_sections,
            confidence_flags: payload.confidence_flags,
            metadata: {
              ...payload.metadata,
              scope: INTERVIEWEE_UPLOAD_SCOPES.SAVE_AS_DEFAULT,
            },
          },
        });
      }
    }

    const data = await withRuntimeMessage({
      type: "SUBMIT_PROFILE",
      prepId,
      payload,
    });
    const dashboardUrl =
      (data.dashboard_url ?? "").trim() || buildDashboardUrl(ui.dashboardUrl.value, prepId);
    setDashboardCtaUrl(dashboardUrl);
    setStatus(
      role === PROFILE_ROLES.INTERVIEWEE && uploadScope === INTERVIEWEE_UPLOAD_SCOPES.SAVE_AS_DEFAULT
        ? "Interviewee profile submitted and saved as default."
        : data.user_message || `Submitted successfully. Current status: ${data.pipeline_status}`
    );
    await refreshIntervieweeDecisionState();
  } catch (error) {
    setDashboardCtaUrl("");
    setStatus(error.message, true);
  }
});

ui.roleSelect.addEventListener("change", () => {
  updateIntervieweeDecisionUi();
});

ui.intervieweeChoiceReuse.addEventListener("change", () => {
  updateIntervieweeDecisionUi();
});

ui.intervieweeChoiceUpload.addEventListener("change", () => {
  updateIntervieweeDecisionUi();
});

ui.openDashboardButton.addEventListener("click", () => {
  if (!latestDashboardUrl) {
    setStatus("Dashboard URL is not configured.", true);
    return;
  }
  window.open(latestDashboardUrl, "_blank", "noopener,noreferrer");
});

loadInitialState().catch((error) => {
  setStatus(error.message, true);
});
