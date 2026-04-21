const extensionApi = globalThis.browser ?? globalThis.chrome;
const isFirefoxStyleApi = Boolean(globalThis.browser);

function promisifyChrome(method, ...args) {
  return new Promise((resolve, reject) => {
    method(...args, (result) => {
      const maybeError = globalThis.chrome?.runtime?.lastError;
      if (maybeError) {
        reject(new Error(maybeError.message));
        return;
      }
      resolve(result);
    });
  });
}

async function storageGet(keys) {
  if (isFirefoxStyleApi) {
    return extensionApi.storage.local.get(keys);
  }
  return promisifyChrome(extensionApi.storage.local.get, keys);
}

async function storageSet(values) {
  if (isFirefoxStyleApi) {
    return extensionApi.storage.local.set(values);
  }
  return promisifyChrome(extensionApi.storage.local.set, values);
}

async function queryTabs(queryInfo) {
  if (isFirefoxStyleApi) {
    return extensionApi.tabs.query(queryInfo);
  }
  return promisifyChrome(extensionApi.tabs.query, queryInfo);
}

async function sendMessageToTab(tabId, message) {
  if (isFirefoxStyleApi) {
    return extensionApi.tabs.sendMessage(tabId, message);
  }
  return promisifyChrome(extensionApi.tabs.sendMessage, tabId, message);
}

async function runtimeSendMessage(message) {
  if (isFirefoxStyleApi) {
    return extensionApi.runtime.sendMessage(message);
  }
  return promisifyChrome(extensionApi.runtime.sendMessage, message);
}

export {
  extensionApi,
  queryTabs,
  runtimeSendMessage,
  sendMessageToTab,
  storageGet,
  storageSet,
};
