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
  return promisifyChrome((...args) => extensionApi.storage.local.get(...args), keys);
}

async function storageSet(values) {
  if (isFirefoxStyleApi) {
    return extensionApi.storage.local.set(values);
  }
  return promisifyChrome((...args) => extensionApi.storage.local.set(...args), values);
}

async function queryTabs(queryInfo) {
  if (isFirefoxStyleApi) {
    return extensionApi.tabs.query(queryInfo);
  }
  return promisifyChrome((...args) => extensionApi.tabs.query(...args), queryInfo);
}

async function sendMessageToTab(tabId, message) {
  if (isFirefoxStyleApi) {
    return extensionApi.tabs.sendMessage(tabId, message);
  }
  return promisifyChrome((...args) => extensionApi.tabs.sendMessage(...args), tabId, message);
}

async function runtimeSendMessage(message) {
  if (isFirefoxStyleApi) {
    return extensionApi.runtime.sendMessage(message);
  }
  return promisifyChrome((...args) => extensionApi.runtime.sendMessage(...args), message);
}

export {
  extensionApi,
  queryTabs,
  runtimeSendMessage,
  sendMessageToTab,
  storageGet,
  storageSet,
};
