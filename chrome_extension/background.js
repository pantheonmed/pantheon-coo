chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'coo-selection',
    title: 'Ask COO about selected text',
    contexts: ['selection'],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'coo-selection' && info.selectionText) {
    chrome.storage.local.set({ coo_pending_command: info.selectionText });
    chrome.action.openPopup?.();
  }
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'COO_TASK_DONE') {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icon.png',
      title: 'COO',
      message: 'Task done ✅',
    });
  }
  sendResponse({ ok: true });
  return true;
});
