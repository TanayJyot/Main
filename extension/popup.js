document.getElementById("startBtn").addEventListener("click", async () => {
    document.getElementById("status").innerText = "Status: Running";

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    chrome.tabs.sendMessage(tab.id, {
        action: "START_ASL"
    });
});

document.getElementById("stopBtn").addEventListener("click", async () => {
    document.getElementById("status").innerText = "Status: Stopped";

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    chrome.tabs.sendMessage(tab.id, {
        action: "STOP_ASL"
    });
});
