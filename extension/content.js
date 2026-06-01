console.log("ASLytics content script loaded");

let running = false;

chrome.runtime.onMessage.addListener((message) => {
    if (message.action === "START_ASL") {
        running = true;
        console.log("ASL STARTED");
        startCaptions();
    }

    if (message.action === "STOP_ASL") {
        running = false;
        console.log("ASL STOPPED");
    }
});

function startCaptions() {
    const interval = setInterval(async () => {
        if (!running) {
            clearInterval(interval);
            return;
        }

        const captions = document.querySelectorAll(".ytp-caption-segment");

        if (captions.length > 0) {
            const text = Array.from(captions)
                .map(c => c.innerText)
                .join(" ");

            console.log("Caption:", text);

            // send to backend
            try {
                const res = await fetch("http://127.0.0.1:5000/process", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ caption: text })
                });

                const data = await res.json();

                console.log("ASL:", data.asl_translation);

            } catch (err) {
                console.error(err);
            }
        }
    }, 1000);
}
