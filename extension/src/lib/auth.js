import { extensionApi, storageGet, storageSet } from "./browser-api.js";
import { getSettings } from "./config.js";
import { STORAGE_KEYS } from "./constants.js";

function encodeBase64Url(bytes) {
  const base64 = btoa(String.fromCharCode(...new Uint8Array(bytes)));
  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomString(length = 64) {
  const random = new Uint8Array(length);
  crypto.getRandomValues(random);
  return encodeBase64Url(random);
}

async function sha256ToBase64Url(input) {
  const msgBytes = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", msgBytes);
  return encodeBase64Url(digest);
}

async function loginWithAuth0() {
  const settings = await getSettings();
  if (!settings.auth0Domain || !settings.auth0ClientId || !settings.auth0Audience) {
    throw new Error("Set Auth0 domain, client ID, and audience in Settings first.");
  }

  const verifier = randomString(64);
  const challenge = await sha256ToBase64Url(verifier);
  const state = randomString(32);
  const redirectUri = extensionApi.identity.getRedirectURL("auth0");

  const authUrl = new URL(`https://${settings.auth0Domain}/authorize`);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("client_id", settings.auth0ClientId);
  authUrl.searchParams.set("redirect_uri", redirectUri);
  authUrl.searchParams.set("scope", "openid profile email");
  authUrl.searchParams.set("audience", settings.auth0Audience);
  authUrl.searchParams.set("code_challenge", challenge);
  authUrl.searchParams.set("code_challenge_method", "S256");
  authUrl.searchParams.set("state", state);

  const callbackUrl = await extensionApi.identity.launchWebAuthFlow({
    url: authUrl.toString(),
    interactive: true,
  });

  if (!callbackUrl) {
    throw new Error("Authentication cancelled.");
  }

  const callback = new URL(callbackUrl);
  if (callback.searchParams.get("state") !== state) {
    throw new Error("Auth state mismatch.");
  }

  const code = callback.searchParams.get("code");
  if (!code) {
    throw new Error("Authorization code missing in callback.");
  }

  const tokenResponse = await fetch(`https://${settings.auth0Domain}/oauth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      grant_type: "authorization_code",
      client_id: settings.auth0ClientId,
      code_verifier: verifier,
      code,
      redirect_uri: redirectUri,
    }),
  });

  if (!tokenResponse.ok) {
    throw new Error("Failed to exchange authorization code.");
  }

  const tokenPayload = await tokenResponse.json();
  const authState = {
    accessToken: tokenPayload.access_token,
    expiresAt: Date.now() + (tokenPayload.expires_in ?? 3600) * 1000,
    tokenType: tokenPayload.token_type ?? "Bearer",
  };
  await storageSet({ [STORAGE_KEYS.AUTH]: authState });
  return authState;
}

async function getAuthState() {
  const state = await storageGet(STORAGE_KEYS.AUTH);
  return state[STORAGE_KEYS.AUTH] ?? null;
}

async function getValidAccessToken() {
  const authState = await getAuthState();
  if (!authState?.accessToken) {
    return null;
  }

  const expiresSoonThresholdMs = 30 * 1000;
  if ((authState.expiresAt ?? 0) <= Date.now() + expiresSoonThresholdMs) {
    return null;
  }
  return authState.accessToken;
}

async function logout() {
  await storageSet({ [STORAGE_KEYS.AUTH]: null });
}

export { getAuthState, getValidAccessToken, loginWithAuth0, logout };
