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
    const contentType = response.headers.get("content-type") || "";
    if (response.status === 404 && contentType.includes("text/html")) {
      throw new Error(
        `API route not found (404): ${path}. The server at ${baseUrl} may not have the latest backend deployed yet.`
      );
    }
    if (contentType.includes("application/json")) {
      try {
        const body = JSON.parse(raw);
        const detail = body?.detail;
        if (typeof detail === "string" && detail.trim()) {
          throw new Error(detail);
        }
      } catch (error) {
        if (!(error instanceof SyntaxError)) {
          throw error;
        }
      }
    }
    throw new Error(raw?.trim() || `Request failed with ${response.status}`);
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

async function getPrepSessionRoleProfile(prepId, role) {
  if (!prepId?.trim()) {
    throw new Error("prep_id is required.");
  }
  const roleValue = String(role ?? "").trim().toUpperCase();
  if (!roleValue) {
    throw new Error("role is required.");
  }
  return authorizedFetch(
    `/prep-sessions/${encodeURIComponent(prepId.trim())}/profiles/${encodeURIComponent(roleValue)}`,
    { method: "GET" }
  );
}

async function generatePrepSession(prepId) {
  if (!prepId?.trim()) {
    throw new Error("prep_id is required.");
  }
  return authorizedFetch(`/prep-sessions/${encodeURIComponent(prepId.trim())}/generate`, {
    method: "POST",
    body: JSON.stringify({}),
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
  generatePrepSession,
  getIntervieweeBaselineProfile,
  getPrepSessionDetail,
  getPrepSessionRoleProfile,
  submitPrepProfile,
  upsertIntervieweeBaselineProfile,
};
