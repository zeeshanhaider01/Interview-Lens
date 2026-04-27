import {
  createPrepSession,
  getIntervieweeBaselineProfile,
  getPrepSessionDetail,
  submitPrepProfile,
  upsertIntervieweeBaselineProfile,
} from "../lib/api-client.js";
import { getAuthState, loginWithAuth0, logout } from "../lib/auth.js";
import { storageSet } from "../lib/browser-api.js";
import { STORAGE_KEYS } from "../lib/constants.js";

async function clearUserSessionData() {
  await storageSet({
    [STORAGE_KEYS.AUTH]: null,
    [STORAGE_KEYS.ACTIVE_PREP_ID]: null,
    [STORAGE_KEYS.LAST_CAPTURE]: null,
    [STORAGE_KEYS.POPUP_DRAFT]: null,
  });
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const run = async () => {
    switch (message?.type) {
      case "AUTH_LOGIN": {
        try {
          const authState = await loginWithAuth0();
          await storageSet({
            [STORAGE_KEYS.LAST_AUTH_RESULT]: {
              status: "success",
              message: "Authentication successful.",
              updatedAt: Date.now(),
            },
          });
          return authState;
        } catch (error) {
          const message = error?.message || "Authentication failed.";
          await storageSet({
            [STORAGE_KEYS.LAST_AUTH_RESULT]: {
              status: "error",
              message,
              updatedAt: Date.now(),
            },
          });
          throw error;
        }
      }
      case "AUTH_LOGOUT":
        await logout();
        await clearUserSessionData();
        await storageSet({
          [STORAGE_KEYS.LAST_AUTH_RESULT]: {
            status: "info",
            message: "Logged out.",
            updatedAt: Date.now(),
          },
        });
        return { ok: true };
      case "AUTH_STATE":
        return getAuthState();
      case "CREATE_PREP_SESSION":
        return createPrepSession(message.payload);
      case "SUBMIT_PROFILE":
        return submitPrepProfile(message.prepId, message.payload);
      case "GET_PREP_SESSION_DETAIL":
        return getPrepSessionDetail(message.prepId);
      case "GET_INTERVIEWEE_BASELINE_PROFILE":
        return getIntervieweeBaselineProfile();
      case "UPSERT_INTERVIEWEE_BASELINE_PROFILE":
        return upsertIntervieweeBaselineProfile(message.payload);
      case "GET_ACTIVE_PREP_ID": {
        const state = await storageGet(STORAGE_KEYS.ACTIVE_PREP_ID);
        return { prepId: state[STORAGE_KEYS.ACTIVE_PREP_ID] ?? "" };
      }
      case "SET_ACTIVE_PREP_ID": {
        const prepId = String(message.prepId ?? "").trim();
        await storageSet({ [STORAGE_KEYS.ACTIVE_PREP_ID]: prepId || null });
        return { prepId };
      }
      case "CLEAR_ACTIVE_PREP_ID":
        await storageSet({ [STORAGE_KEYS.ACTIVE_PREP_ID]: null });
        return { ok: true };
      case "SAVE_LAST_CAPTURE":
        await storageSet({ [STORAGE_KEYS.LAST_CAPTURE]: message.payload });
        return { ok: true };
      default:
        throw new Error("Unsupported message type.");
    }
  };

  run()
    .then((data) => sendResponse({ ok: true, data }))
    .catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});
