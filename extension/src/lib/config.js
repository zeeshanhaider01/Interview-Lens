import { STORAGE_KEYS } from "./constants.js";
import { storageGet, storageSet } from "./browser-api.js";
import { STAGING_CONFIG } from "./config.staging.js";

const SETTINGS_UI_ENABLED = false;

const DEFAULT_SETTINGS = {
  ...STAGING_CONFIG,
};

async function getSettings() {
  if (!SETTINGS_UI_ENABLED) {
    return { ...DEFAULT_SETTINGS };
  }
  const state = await storageGet(STORAGE_KEYS.SETTINGS);
  return { ...DEFAULT_SETTINGS, ...(state[STORAGE_KEYS.SETTINGS] ?? {}) };
}

async function saveSettings(settings) {
  if (!SETTINGS_UI_ENABLED) {
    return { ...DEFAULT_SETTINGS };
  }
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

export { getSettings, saveSettings, DEFAULT_SETTINGS, SETTINGS_UI_ENABLED };
