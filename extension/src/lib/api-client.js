import { getSettings } from "./config.js";
import { getValidAccessToken } from "./auth.js";

async function authorizedFetch(path, options = {}) {
  const settings = await getSettings();
  const token = await getValidAccessToken();
  if (!token) {
    throw new Error("Not authenticated. Login required.");
  }

  const baseUrl = settings.apiBaseUrl.replace(/\/+$/, "");
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options.headers ?? {}),
    },
  });

  if (!response.ok) {
    const raw = await response.text();
    throw new Error(raw || `Request failed with ${response.status}`);
  }

  return response.json();
}

async function createPrepSession(payload) {
  return authorizedFetch("/prep-sessions/", {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  });
}

async function submitPrepProfile(prepId, payload) {
  if (!prepId?.trim()) {
    throw new Error("prep_id is required.");
  }
  return authorizedFetch(`/prep-sessions/${encodeURIComponent(prepId.trim())}/profiles`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

async function getPrepSessionDetail(prepId) {
  if (!prepId?.trim()) {
    throw new Error("prep_id is required.");
  }
  return authorizedFetch(`/prep-sessions/${encodeURIComponent(prepId.trim())}/`, {
    method: "GET",
  });
}

async function getIntervieweeBaselineProfile() {
  return authorizedFetch("/profile-baseline/interviewee", {
    method: "GET",
  });
}

async function upsertIntervieweeBaselineProfile(payload) {
  return authorizedFetch("/profile-baseline/interviewee", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export {
  createPrepSession,
  getIntervieweeBaselineProfile,
  getPrepSessionDetail,
  submitPrepProfile,
  upsertIntervieweeBaselineProfile,
};
