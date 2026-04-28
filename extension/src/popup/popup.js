import {
  extensionApi,
  queryTabs,
  runtimeSendMessage,
  sendMessageToTab,
  storageGet,
  storageSet,
} from "../lib/browser-api.js";
import { getSettings } from "../lib/config.js";
import { PROFILE_ROLES, SECTION_KEYS, STORAGE_KEYS } from "../lib/constants.js";
import { normalizeCapture } from "../lib/normalizer.js";

const ui = {
  loginButton: document.getElementById("loginButton"),
  logoutButton: document.getElementById("logoutButton"),
  authProgress: document.getElementById("authProgress"),
  authProgressLabel: document.getElementById("authProgressLabel"),
  authStatus: document.getElementById("authStatus"),
  loggedOutGuidanceSection: document.getElementById("loggedOutGuidanceSection"),
  openSignupButton: document.getElementById("openSignupButton"),
  viewModeSelect: document.getElementById("viewModeSelect"),
  fontScaleSelect: document.getElementById("fontScaleSelect"),
  openLargeViewButton: document.getElementById("openLargeViewButton"),
  prepSessionSection: document.getElementById("prepSessionSection"),
  captureProfileSection: document.getElementById("captureProfileSection"),
  reviewEditSection: document.getElementById("reviewEditSection"),
  submitSection: document.getElementById("submitSection"),
  prepIdInput: document.getElementById("prepIdInput"),
  addPrepSessionButton: document.getElementById("addPrepSessionButton"),
  clearPrepSessionButton: document.getElementById("clearPrepSessionButton"),
  prepValidationProgress: document.getElementById("prepValidationProgress"),
  prepValidationLabel: document.getElementById("prepValidationLabel"),
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
  captureProgress: document.getElementById("captureProgress"),
  captureProgressLabel: document.getElementById("captureProgressLabel"),
  captureSummary: document.getElementById("captureSummary"),
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
let currentSettings = {};
let isAuthFlowPending = false;
let isPrepValidationPending = false;
let activePrepId = "";
const POPUP_LOCAL_DRAFT_KEY = "popup_draft_local_backup";
const DEFAULT_ACCESSIBILITY_PREFS = {
  viewMode: "compact",
  fontScale: "100",
};

const INTERVIEWEE_PROFILE_CHOICES = {
  REUSE_SAVED: "reuse_saved",
  UPLOAD_NEW: "upload_new",
};

const INTERVIEWEE_UPLOAD_SCOPES = {
  SESSION_ONLY: "session_only",
  SAVE_AS_DEFAULT: "save_as_default",
};
const STATUS_COLORS = {
  SUCCESS: "#008000",
  ERROR: "#b91c1c",
};

function setCaptureProgress(isVisible, label = "Capturing...") {
  ui.captureProgress.classList.toggle("hidden", !isVisible);
  ui.captureProgressLabel.textContent = label;
}

function setCaptureSummary(message = "") {
  const summary = String(message ?? "").trim();
  ui.captureSummary.textContent = summary;
  ui.captureSummary.classList.toggle("hidden", !summary);
}

function applyAccessibilityPrefs(prefs) {
  const viewMode = ["compact", "comfortable", "large"].includes(prefs?.viewMode)
    ? prefs.viewMode
    : DEFAULT_ACCESSIBILITY_PREFS.viewMode;
  const fontScale = ["100", "115", "130"].includes(String(prefs?.fontScale))
    ? String(prefs.fontScale)
    : DEFAULT_ACCESSIBILITY_PREFS.fontScale;

  document.body.classList.remove("view-compact", "view-comfortable", "view-large");
  document.body.classList.add(`view-${viewMode}`);
  document.documentElement.style.setProperty("--scale-factor", String(Number(fontScale) / 100));
  ui.viewModeSelect.value = viewMode;
  ui.fontScaleSelect.value = fontScale;
}

async function persistAccessibilityPrefs() {
  const prefs = {
    viewMode: ui.viewModeSelect.value,
    fontScale: ui.fontScaleSelect.value,
  };
  applyAccessibilityPrefs(prefs);
  await storageSet({ [STORAGE_KEYS.POPUP_ACCESSIBILITY_PREFS]: prefs });
}

function autoResizeTextarea(textarea) {
  if (!textarea) {
    return;
  }
  textarea.style.height = "auto";
  const maxHeight = document.body.classList.contains("view-large") ? 340 : 260;
  textarea.style.height = `${Math.min(textarea.scrollHeight + 2, maxHeight)}px`;
}

function autoResizeAllTextareas() {
  for (const field of Object.values(ui.fields)) {
    autoResizeTextarea(field);
  }
}

function summarizeCapture(normalizedCapture) {
  const counts = normalizedCapture?.confidence_flags?.section_counts ?? {};
  const totalCount = Object.values(counts).reduce((sum, count) => sum + Number(count || 0), 0);
  const quality = totalCount >= 12 ? "high" : totalCount >= 4 ? "medium" : "low";
  const orderedCounts = SECTION_KEYS.map((key) => `${key}: ${counts[key] ?? 0}`).join(", ");
  if (quality === "low") {
    return `Partial capture (${orderedCounts}). Please review and manually add missing details.`;
  }
  return `Capture quality ${quality}. Section counts: ${orderedCounts}.`;
}

function buildPopupDraft() {
  return {
    prepId: ui.prepIdInput.value.trim(),
    role: ui.roleSelect.value,
    intervieweeChoice: getIntervieweeChoice(),
    uploadScope: getIntervieweeUploadScope(),
    sections: readEditedSections(),
    updatedAt: Date.now(),
  };
}

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
    prepId: String(local.prepId ?? remote.prepId ?? "").trim(),
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

function clearLocalPopupDraft() {
  try {
    globalThis.localStorage?.removeItem(POPUP_LOCAL_DRAFT_KEY);
  } catch (_error) {
    // Ignore storage removal failures.
  }
}

async function persistPopupDraft() {
  const draft = buildPopupDraft();
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
  ui.statusMessage.style.color = isError ? STATUS_COLORS.ERROR : STATUS_COLORS.SUCCESS;
}

function setAuthProgress(isVisible, label = "Authenticating...") {
  ui.authProgress.classList.toggle("hidden", !isVisible);
  ui.authProgressLabel.textContent = label;
}

function applyActionAvailability() {
  ui.loginButton.disabled = isAuthFlowPending || isAuthenticated;
  ui.logoutButton.disabled = isAuthFlowPending || !isAuthenticated;
  ui.createPrepSessionButton.disabled = isAuthFlowPending || !isAuthenticated;
  ui.submitButton.disabled = isAuthFlowPending || !isAuthenticated;
  ui.captureButton.disabled = isAuthFlowPending;
  updatePrepActionButtonsVisibility();
}

function buildSignupUrl(baseUrl) {
  const cleanBaseUrl = (baseUrl ?? "").trim().replace(/\/+$/, "");
  if (!cleanBaseUrl) {
    return "";
  }
  return `${cleanBaseUrl}/signup`;
}

function renderAuthStateUi() {
  const showWorkflow = isAuthenticated;
  ui.loggedOutGuidanceSection.classList.toggle("hidden", showWorkflow);
  ui.prepSessionSection.classList.toggle("hidden", !showWorkflow);
  ui.captureProfileSection.classList.toggle("hidden", !showWorkflow);
  ui.reviewEditSection.classList.toggle("hidden", !showWorkflow);
  ui.submitSection.classList.toggle("hidden", !showWorkflow);
  ui.dashboardCtaSection.classList.toggle("hidden", !showWorkflow || !latestDashboardUrl);
}

function readErrorMessage(error, fallbackMessage = "Something went wrong.") {
  return error?.message || fallbackMessage;
}

function setDashboardCtaUrl(url) {
  latestDashboardUrl = (url ?? "").trim();
  renderAuthStateUi();
}

function setActivePrepBadge(prepId) {
  const value = String(prepId ?? "").trim();
  activePrepId = value;
  ui.activePrepBadge.classList.toggle("hidden", !value);
  ui.activePrepBadgeValue.textContent = value;
  updatePrepActionButtonsVisibility();
}

function setPrepValidationProgress(isVisible, label = "Validating preparation ID...") {
  ui.prepValidationProgress.classList.toggle("hidden", !isVisible);
  ui.prepValidationLabel.textContent = label;
}

function updatePrepActionButtonsVisibility() {
  const inputValue = ui.prepIdInput.value.trim();
  const shouldShowAdd = !inputValue || inputValue !== activePrepId;
  const shouldShowClear = !shouldShowAdd;

  ui.addPrepSessionButton.classList.toggle("hidden", !shouldShowAdd);
  ui.clearPrepSessionButton.classList.toggle("hidden", !shouldShowClear);
  ui.addPrepSessionButton.disabled =
    isAuthFlowPending || !isAuthenticated || isPrepValidationPending || !inputValue;
  ui.clearPrepSessionButton.disabled = isAuthFlowPending || isPrepValidationPending || !isAuthenticated;
}

function setAuthUiState(authState) {
  isAuthenticated = Boolean(authState?.accessToken);
  ui.authStatus.textContent = isAuthenticated
    ? "Auth status: authenticated"
    : "Auth status: not authenticated";
  applyActionAvailability();
  renderAuthStateUi();
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
  autoResizeAllTextareas();
}

function resetPopupFormAfterLogout() {
  ui.prepIdInput.value = "";
  setDashboardCtaUrl("");
  setActivePrepBadge("");
  ui.roleSelect.value = PROFILE_ROLES.INTERVIEWEE;
  ui.intervieweeChoiceReuse.checked = true;
  ui.intervieweeChoiceUpload.checked = false;
  ui.uploadScopeSessionOnly.checked = true;
  ui.uploadScopeDefault.checked = false;
  writeSections({});
  clearLocalPopupDraft();
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
  const localDraft = readLocalPopupDraft();
  const settings = await getSettings();
  currentSettings = { ...settings };
  const draftState = await storageGet([
    STORAGE_KEYS.POPUP_DRAFT,
    STORAGE_KEYS.LAST_AUTH_RESULT,
    STORAGE_KEYS.POPUP_ACCESSIBILITY_PREFS,
  ]);
  const draft = mergePopupDraftRecords(
    localDraft,
    draftState[STORAGE_KEYS.POPUP_DRAFT] ?? null
  );
  const lastAuthResult = draftState[STORAGE_KEYS.LAST_AUTH_RESULT] ?? null;
  applyAccessibilityPrefs(
    draftState[STORAGE_KEYS.POPUP_ACCESSIBILITY_PREFS] ?? DEFAULT_ACCESSIBILITY_PREFS
  );
  if (lastAuthResult?.message) {
    setStatus(lastAuthResult.message, lastAuthResult.status === "error");
  }

  const authState = await withRuntimeMessage({ type: "AUTH_STATE" });
  setAuthUiState(authState);

  const activeState = await withRuntimeMessage({ type: "GET_ACTIVE_PREP_ID" });
  const activePrepId = String(activeState?.prepId ?? "").trim();
  const draftPrepId = String(draft?.prepId ?? "").trim();
  if (activePrepId) {
    ui.prepIdInput.value = activePrepId;
    setDashboardCtaUrl(buildDashboardUrl(settings.dashboardUrl, activePrepId));
  }
  setActivePrepBadge(activePrepId);
  if (!activePrepId && draftPrepId) {
    ui.prepIdInput.value = draftPrepId;
    setDashboardCtaUrl(buildDashboardUrl(settings.dashboardUrl, draftPrepId));
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

ui.loginButton.addEventListener("click", async () => {
  if (isAuthFlowPending) {
    return;
  }
  isAuthFlowPending = true;
  applyActionAvailability();
  setAuthProgress(true, "Opening secure login...");
  try {
    setStatus("Opening login window...");
    const authState = await withRuntimeMessage({ type: "AUTH_LOGIN" });
    setAuthUiState(authState);
    setAuthProgress(true, "Fetching latest data...");
    await refreshIntervieweeDecisionState();
    setStatus("Authentication successful.");
  } catch (error) {
    setStatus(readErrorMessage(error, "Authentication failed."), true);
  } finally {
    isAuthFlowPending = false;
    setAuthProgress(false);
    applyActionAvailability();
  }
});

ui.logoutButton.addEventListener("click", async () => {
  try {
    await withRuntimeMessage({ type: "AUTH_LOGOUT" });
    setAuthUiState(null);
    hasDefaultIntervieweeProfile = false;
    resetPopupFormAfterLogout();
    updateIntervieweeDecisionUi();
    setStatus("Logged out. Cleared active session and captured profile data.");
  } catch (error) {
    setStatus(readErrorMessage(error), true);
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
    setDashboardCtaUrl(buildDashboardUrl(currentSettings.dashboardUrl, data.prep_id));
    setActivePrepBadge(data.prep_id);
    await refreshIntervieweeDecisionState();
    setStatus("New prep session created.");
  } catch (error) {
    setStatus(readErrorMessage(error), true);
  }
});

ui.addPrepSessionButton.addEventListener("click", async () => {
  const prepId = ui.prepIdInput.value.trim();
  if (!prepId) {
    setStatus("Preparation ID is required before validation.", true);
    return;
  }
  if (prepId === activePrepId) {
    setStatus("Preparation ID is already active.");
    return;
  }
  try {
    isPrepValidationPending = true;
    updatePrepActionButtonsVisibility();
    setPrepValidationProgress(true, "Validating preparation ID...");
    await withRuntimeMessage({ type: "GET_PREP_SESSION_DETAIL", prepId });
    await persistActivePrepId(prepId);
    setDashboardCtaUrl(buildDashboardUrl(currentSettings.dashboardUrl, prepId));
    setActivePrepBadge(prepId);
    await persistPopupDraft();
    await refreshIntervieweeDecisionState();
    setStatus("Preparation ID validated and added successfully.");
  } catch (error) {
    setStatus(
      readErrorMessage(
        error,
        "Preparation ID is invalid. Please add a valid ID or create a new prep_id."
      ),
      true
    );
  } finally {
    isPrepValidationPending = false;
    setPrepValidationProgress(false);
    updatePrepActionButtonsVisibility();
  }
});

ui.prepIdInput.addEventListener("change", async () => {
  try {
    await persistPopupDraft();
    updatePrepActionButtonsVisibility();
  } catch (error) {
    setStatus(readErrorMessage(error), true);
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
    setStatus(readErrorMessage(error), true);
  }
});

ui.captureButton.addEventListener("click", async () => {
  const progressSteps = [
    "Starting capture...",
    "Loading LinkedIn profile content...",
    "Expanding visible sections...",
    "Extracting section data...",
  ];
  let progressIndex = 0;
  setCaptureSummary("");
  setCaptureProgress(true, progressSteps[progressIndex]);
  const progressTimer = setInterval(() => {
    progressIndex = Math.min(progressIndex + 1, progressSteps.length - 1);
    setCaptureProgress(true, progressSteps[progressIndex]);
  }, 600);
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
    setCaptureSummary(summarizeCapture(normalized));
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
    setStatus(readErrorMessage(error), true);
    setCaptureSummary("");
  } finally {
    clearInterval(progressTimer);
    setCaptureProgress(false);
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
        setDashboardCtaUrl(buildDashboardUrl(currentSettings.dashboardUrl, prepId));
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
      (data.dashboard_url ?? "").trim() || buildDashboardUrl(currentSettings.dashboardUrl, prepId);
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
  ui.prepIdInput,
  ...Object.values(ui.fields),
]
  .filter(Boolean)
  .forEach((element) => {
  const saveDraft = () => {
    persistPopupDraft().catch(() => {
      // Best-effort draft persistence.
    });
    if (element === ui.prepIdInput) {
      updatePrepActionButtonsVisibility();
    } else {
      autoResizeTextarea(element);
    }
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

ui.openSignupButton.addEventListener("click", () => {
  const signupUrl = buildSignupUrl(currentSettings.dashboardUrl);
  if (!signupUrl) {
    setStatus("Signup URL is not configured.", true);
    return;
  }
  window.open(signupUrl, "_blank", "noopener,noreferrer");
});

ui.viewModeSelect.addEventListener("change", () => {
  persistAccessibilityPrefs().catch(() => {
    // Best-effort preference persistence.
  });
  autoResizeAllTextareas();
});

ui.fontScaleSelect.addEventListener("change", () => {
  persistAccessibilityPrefs().catch(() => {
    // Best-effort preference persistence.
  });
});

ui.openLargeViewButton.addEventListener("click", () => {
  const largeViewUrl = extensionApi?.runtime?.getURL?.("src/popup/popup.html");
  if (!largeViewUrl) {
    setStatus("Unable to open large view in this browser.", true);
    return;
  }
  window.open(largeViewUrl, "_blank", "noopener,noreferrer");
});

renderAuthStateUi();
updatePrepActionButtonsVisibility();
loadInitialState().catch((error) => {
  setStatus(readErrorMessage(error), true);
});
