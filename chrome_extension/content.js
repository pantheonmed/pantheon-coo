chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'GET_PAGE_TEXT') {
    const text = document.body ? document.body.innerText : '';
    sendResponse({ text: text.slice(0, 12000) });
  }
  return true;
});
