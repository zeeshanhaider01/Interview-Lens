import { queryTabs, runtimeSendMessage, sendMessageToTab, storageGet, storageSet } from "../lib/browser-api.js";
import { getSettings, saveSettings, DEFAULT_SETTINGS, SETTINGS_UI_ENABLED } from "../lib/config.js";
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
let popupDraftSaveQueue = Promise.resolve();
let currentResolvedSettings = { ...DEFAULT_SETTINGS };
const POPUP_LOCAL_DRAFT_KEY = "popup_draft_local_backup";

const INTERVIEWEE_PROFILE_CHOICES = {
  REUSE_SAVED: "reuse_saved",
  UPLOAD_NEW: "upload_new",
};

const INTERVIEWEE_UPLOAD_SCOPES = {
  SESSION_ONLY: "session_only",
  SAVE_AS_DEFAULT: "save_as_default",
};

function readSettingsFromUi() {
  if (!SETTINGS_UI_ENABLED || !ui.apiBaseUrl) {
    return { ...currentResolvedSettings };
  }
  return {
    apiBaseUrl: ui.apiBaseUrl.value,
    dashboardUrl: ui.dashboardUrl.value,
    auth0Domain: ui.auth0Domain.value,
    auth0ClientId: ui.auth0ClientId.value,
    auth0Audience: ui.auth0Audience.value,
    clearPrepIdOnLogout: ui.clearPrepIdOnLogout.checked,
  };
}

function buildPopupDraft() {
  return {
    settings: readSettingsFromUi(),
    prepId: ui.prepIdInput.value.trim(),
    role: ui.roleSelect.value,
    intervieweeChoice: getIntervieweeChoice(),
    uploadScope: getIntervieweeUploadScope(),
    sections: readEditedSections(),
    updatedAt: Date.now(),
  };
}

const SETTINGS_TEXT_KEYS = ["apiBaseUrl", "dashboardUrl", "auth0Domain", "auth0ClientId", "auth0Audience"];

function firstNonEmptyText(...candidates) {
  for (const c of candidates) {
    if (c != null && String(c).trim() !== "") {
      return String(c);
    }
  }
  return "";
}

function mergeSettingsFromDraftSources(a, b) {
  const out = {};
  for (const k of SETTINGS_TEXT_KEYS) {
    out[k] = firstNonEmptyText(a?.[k], b?.[k]);
  }
  out.clearPrepIdOnLogout = Boolean(a?.clearPrepIdOnLogout ?? b?.clearPrepIdOnLogout);
  return out;
}

/**
 * `localStorage` and `chrome.storage` can be briefly out of sync. Merge per-field from both, then
 * fill UI using non-empty + saved settings fallbacks (empty string is valid for `??` but is wrong
 * for display when the other source has the value).
 */
function mergePopupDraftRecords(local, remote) {
  if (!local && !remote) {
    return null;
  }
  if (!local) {
    return remote;
  }
  if (!remote) {
    return local;
  }
  return {
    ...remote,
    ...local,
    settings: mergeSettingsFromDraftSources(local.settings, remote.settings),
    prepId: firstNonEmptyText(local.prepId, remote.prepId),
  };
}

function isLikelyTeardownEmptySettings(settings) {
  if (!settings) {
    return true;
  }
  return SETTINGS_TEXT_KEYS.every((k) => !String(settings[k] ?? "").trim());
}

function hadNonEmptyTextSettings(stored) {
  const s = stored?.settings;
  if (!s) {
    return false;
  }
  return SETTINGS_TEXT_KEYS.some((k) => String(s[k] ?? "").trim() !== "");
}

/**
 * When the popup is closing, Chrome may run save handlers after inputs are cleared.
 * If the new snapshot has all empty text settings but a previous save had data, keep the previous
 * so we do not clobber a good draft.
 */
function applyTeardownSafeMerge(fresh) {
  const previous = readLocalPopupDraft();
  if (!previous || !hadNonEmptyTextSettings(previous) || !isLikelyTeardownEmptySettings(fresh.settings)) {
    return fresh;
  }
  return {
    ...fresh,
    settings: { ...previous.settings },
  };
}

function readLocalPopupDraft() {
  try {
    const raw = globalThis.localStorage?.getItem(POPUP_LOCAL_DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_error) {
    return null;
  }
}

function writeLocalPopupDraft(draft) {
  try {
    globalThis.localStorage?.setItem(POPUP_LOCAL_DRAFT_KEY, JSON.stringify(draft));
  } catch (_error) {
    // Ignore storage write failures (quota/privacy modes).
  }
}

async function persistPopupDraft() {
  const draft = applyTeardownSafeMerge(buildPopupDraft());
  // Synchronous backup to survive very fast popup-close events.
  writeLocalPopupDraft(draft);
  popupDraftSaveQueue = popupDraftSaveQueue
    .catch(() => {
      // Keep queue alive even if a previous write failed.
    })
    .then(() =>
      storageSet({
        [STORAGE_KEYS.POPUP_DRAFT]: draft,
      })
    );
  return popupDraftSaveQueue;
}

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
  // Apply local draft synchronously first so the user never sees an empty flash
  // when async storage/runtime calls are still in flight.
  const localDraft = readLocalPopupDraft();
  const localSettings = localDraft?.settings ?? {};
  if (SETTINGS_UI_ENABLED && ui.apiBaseUrl) {
    ui.apiBaseUrl.value = firstNonEmptyText(localSettings.apiBaseUrl);
    ui.dashboardUrl.value = firstNonEmptyText(localSettings.dashboardUrl);
    ui.auth0Domain.value = firstNonEmptyText(localSettings.auth0Domain);
    ui.auth0ClientId.value = firstNonEmptyText(localSettings.auth0ClientId);
    ui.auth0Audience.value = firstNonEmptyText(localSettings.auth0Audience);
    ui.clearPrepIdOnLogout.checked = Boolean(localSettings.clearPrepIdOnLogout);
  }

  const settings = await getSettings();
  const draftState = await storageGet(STORAGE_KEYS.POPUP_DRAFT);
  const draft = mergePopupDraftRecords(
    localDraft,
    draftState[STORAGE_KEYS.POPUP_DRAFT] ?? null
  );
  const draftSettings = mergeSettingsFromDraftSources(draft?.settings, {});
  const resolvedSettings = {
    apiBaseUrl:
      firstNonEmptyText(draftSettings.apiBaseUrl, settings.apiBaseUrl) || DEFAULT_SETTINGS.apiBaseUrl,
    dashboardUrl:
      firstNonEmptyText(draftSettings.dashboardUrl, settings.dashboardUrl) || DEFAULT_SETTINGS.dashboardUrl,
    auth0Domain: firstNonEmptyText(draftSettings.auth0Domain, settings.auth0Domain),
    auth0ClientId: firstNonEmptyText(draftSettings.auth0ClientId, settings.auth0ClientId),
    auth0Audience: firstNonEmptyText(draftSettings.auth0Audience, settings.auth0Audience),
  };
  currentResolvedSettings = {
    ...resolvedSettings,
    clearPrepIdOnLogout: Boolean(draftSettings.clearPrepIdOnLogout ?? settings.clearPrepIdOnLogout),
  };
  if (SETTINGS_UI_ENABLED && ui.apiBaseUrl) {
    ui.apiBaseUrl.value = resolvedSettings.apiBaseUrl;
    ui.dashboardUrl.value = resolvedSettings.dashboardUrl;
    ui.auth0Domain.value = resolvedSettings.auth0Domain;
    ui.auth0ClientId.value = resolvedSettings.auth0ClientId;
    ui.auth0Audience.value = resolvedSettings.auth0Audience;
    ui.clearPrepIdOnLogout.checked = currentResolvedSettings.clearPrepIdOnLogout;
  }

  const authState = await withRuntimeMessage({ type: "AUTH_STATE" });
  setAuthUiState(authState);

  const activeState = await withRuntimeMessage({ type: "GET_ACTIVE_PREP_ID" });
  const activePrepId = String(activeState?.prepId ?? "").trim();
  const draftPrepId = String(draft?.prepId ?? "").trim();
  if (activePrepId) {
    ui.prepIdInput.value = activePrepId;
    setDashboardCtaUrl(buildDashboardUrl(ui.dashboardUrl.value, activePrepId));
  }
  setActivePrepBadge(activePrepId);
  if (!activePrepId && draftPrepId) {
    ui.prepIdInput.value = draftPrepId;
    setDashboardCtaUrl(buildDashboardUrl(ui.dashboardUrl.value, draftPrepId));
    setActivePrepBadge(draftPrepId);
  }

  const store = await storageGet(STORAGE_KEYS.LAST_CAPTURE);
  const cached = store[STORAGE_KEYS.LAST_CAPTURE];
  if (!activePrepId && cached?.prepId) {
    ui.prepIdInput.value = cached.prepId;
    await persistActivePrepId(cached.prepId);
    setDashboardCtaUrl(buildDashboardUrl(settings.dashboardUrl, cached.prepId));
    setActivePrepBadge(cached.prepId);
  }
  if (draft?.role && Object.values(PROFILE_ROLES).includes(draft.role)) {
    ui.roleSelect.value = draft.role;
  } else if (cached?.role && Object.values(PROFILE_ROLES).includes(cached.role)) {
    ui.roleSelect.value = cached.role;
  }
  if (draft?.intervieweeChoice === INTERVIEWEE_PROFILE_CHOICES.UPLOAD_NEW) {
    ui.intervieweeChoiceUpload.checked = true;
    ui.intervieweeChoiceReuse.checked = false;
  }
  if (draft?.uploadScope === INTERVIEWEE_UPLOAD_SCOPES.SAVE_AS_DEFAULT) {
    ui.uploadScopeDefault.checked = true;
    ui.uploadScopeSessionOnly.checked = false;
  }
  writeSections(draft?.sections ?? cached?.payload?.extracted_sections ?? {});
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

if (ui.saveSettingsButton) {
  ui.saveSettingsButton.addEventListener("click", async () => {
    try {
      await saveSettings(readSettingsFromUi());
      await persistPopupDraft();
      setStatus("Settings saved.");
    } catch (error) {
      setStatus(error.message, true);
    }
  });
}

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
    if (readSettingsFromUi().clearPrepIdOnLogout) {
      ui.prepIdInput.value = "";
      setDashboardCtaUrl("");
      setActivePrepBadge("");
      await persistPopupDraft();
      setStatus("Logged out. Active prep_id cleared.");
      return;
    }
    await persistPopupDraft();
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
    await persistPopupDraft();
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
    await persistPopupDraft();
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
    await persistPopupDraft();
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
  persistPopupDraft().catch(() => {
    // Best-effort draft persistence.
  });
});

ui.intervieweeChoiceReuse.addEventListener("change", () => {
  updateIntervieweeDecisionUi();
  persistPopupDraft().catch(() => {
    // Best-effort draft persistence.
  });
});

ui.intervieweeChoiceUpload.addEventListener("change", () => {
  updateIntervieweeDecisionUi();
  persistPopupDraft().catch(() => {
    // Best-effort draft persistence.
  });
});

ui.uploadScopeSessionOnly.addEventListener("change", () => {
  persistPopupDraft().catch(() => {
    // Best-effort draft persistence.
  });
});
ui.uploadScopeDefault.addEventListener("change", () => {
  persistPopupDraft().catch(() => {
    // Best-effort draft persistence.
  });
});

[
  ui.apiBaseUrl,
  ui.dashboardUrl,
  ui.auth0Domain,
  ui.auth0ClientId,
  ui.auth0Audience,
  ui.clearPrepIdOnLogout,
  ui.prepIdInput,
  ...Object.values(ui.fields),
]
  .filter(Boolean)
  .forEach((element) => {
  const saveDraft = () => {
    persistPopupDraft().catch(() => {
      // Best-effort draft persistence.
    });
  };
  element.addEventListener("input", saveDraft);
  element.addEventListener("change", saveDraft);
  element.addEventListener("paste", () => {
    // Pasted text is applied after the event loop tick.
    setTimeout(saveDraft, 0);
  });
  // Do not use "blur" here: on popup close, blur can fire with inputs already empty and overwrite
  // the good draft. input/change/paste is enough for normal editing.
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
