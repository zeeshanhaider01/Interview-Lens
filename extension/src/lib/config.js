import { STORAGE_KEYS } from "./constants.js";
import { storageGet, storageSet } from "./browser-api.js";

const DEFAULT_SETTINGS = {
  apiBaseUrl: "http://localhost:8000/api",
  dashboardUrl: "http://localhost:5173",
  auth0Domain: "",
  auth0ClientId: "",
  auth0Audience: "",
  clearPrepIdOnLogout: false,
};

async function getSettings() {
  const state = await storageGet(STORAGE_KEYS.SETTINGS);
  return { ...DEFAULT_SETTINGS, ...(state[STORAGE_KEYS.SETTINGS] ?? {}) };
}

async function saveSettings(settings) {
  const safeSettings = {
    apiBaseUrl: (settings.apiBaseUrl ?? DEFAULT_SETTINGS.apiBaseUrl).trim(),
    dashboardUrl: (settings.dashboardUrl ?? DEFAULT_SETTINGS.dashboardUrl).trim(),
    auth0Domain: (settings.auth0Domain ?? "").trim(),
    auth0ClientId: (settings.auth0ClientId ?? "").trim(),
    auth0Audience: (settings.auth0Audience ?? "").trim(),
    clearPrepIdOnLogout: Boolean(settings.clearPrepIdOnLogout),
  };
  await storageSet({ [STORAGE_KEYS.SETTINGS]: safeSettings });
  return safeSettings;
}

export { getSettings, saveSettings, DEFAULT_SETTINGS };
