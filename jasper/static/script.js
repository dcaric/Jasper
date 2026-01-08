const chatWindow = document.getElementById('chat-window');
const chatForm = document.getElementById('chat-form');
const userInput = document.getElementById('user-input');

// Helper to escape HTML and prevent injection/layout breaks
function escapeHTML(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function appendMessage(role, content, data = null) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', role);

    // Parse Markdown if marked library is available, otherwise use raw text
    let parsedContent = content;
    if (typeof marked !== 'undefined') {
        parsedContent = marked.parse(content);
    }

    let html = `<div class="bubble">${parsedContent}`;

    if (data && data.length > 0) {
        data.forEach(item => {
            let actionLink = '';

            // Check if it's a file result
            if (item.path && !item.sender) {
                // Escape backslashes carefully for the function call
                const safePath = String(item.path).replace(/\\/g, '\\\\');
                let btnLabel = "Open File";
                const itemKind = String(item.kind || "").toLowerCase();
                if (itemKind === 'folder' || itemKind === 'directory') {
                    btnLabel = "Open Folder";
                }
                actionLink = `<button onclick="openFileItem('${safePath}')" class="gmail-link" style="background-color: #34a853; border:none; cursor:pointer; color:white;">${btnLabel}</button>`;

                html += `
                    <div class="file-card">
                        <div class="file-name">${item.name}</div>
                        <div class="file-path">${item.path}</div>
                        <div class="summary" style="font-size: 0.85em; color: #666; margin: 8px 0; border-left: 3px solid #eee; padding-left: 8px;">
                            ${escapeHTML(item.content || item.summary || 'No snippet available.')}
                        </div>
                        <div class="file-meta">
                            <span>Kind: ${item.kind}</span>
                            <span>Date: ${item.date || item.received || 'Recent'}</span>
                        </div>
                        <div style="margin-top:5px;">
                            ${actionLink}
                        </div>
                    </div>
                `;
            } else if (item.sender) {
                // Email result
                const provider = item.provider || 'GMAIL';
                if (provider === 'GMAIL') {
                    const gmailUrl = `https://mail.google.com/mail/u/0/#search/rfc822msgid:${encodeURIComponent(item.message_id)}`;
                    actionLink = `<a href="${gmailUrl}" target="_blank" class="gmail-link">View in Gmail</a>`;
                } else {
                    actionLink = `<button onclick="openOutlookItem('${item.message_id}')" class="gmail-link" style="background-color: #0078d4; border:none; cursor:pointer; color:white;">Open in Outlook</button>`;
                }

                html += `
                    <div class="email-card">
                        <div class="sender">From: ${item.sender}</div>
                        <div class="subject">${item.subject}</div>
                        <div class="summary">
                            ${(item.content || item.summary || 'No content snippet available.')}
                        </div>
                        <div class="date">${item.received || 'Recently indexed'}</div>
                        ${actionLink}
                    </div>
                `;
            }
        });
    }

    html += `</div>`;
    messageDiv.innerHTML = html;
    chatWindow.appendChild(messageDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function showTyping() {
    const typingDiv = document.createElement('div');
    typingDiv.id = 'typing-indicator';
    typingDiv.classList.add('message', 'assistant');
    typingDiv.innerHTML = `
        <div class="bubble">
            <div class="typing">
                <span></span><span></span><span></span>
            </div>
        </div>
    `;
    chatWindow.appendChild(typingDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function removeTyping() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) indicator.remove();
}

chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = userInput.value.trim();
    if (!query) return;

    appendMessage('user', query);
    userInput.value = '';

    showTyping();

    try {
        const response = await fetch('/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        });

        const result = await response.json();
        removeTyping();

        if (result.type === 'results') {
            appendMessage('assistant', result.content, result.data);
        } else {
            appendMessage('assistant', result.content);
        }
    } catch (error) {
        removeTyping();
        appendMessage('assistant', 'Error connecting to backend: ' + error.message);
    }
});

// Restart Service Logic
const restartBtn = document.getElementById('restart-btn');
const restartOverlay = document.getElementById('restart-overlay');

if (restartBtn) {
    restartBtn.addEventListener('click', async () => {
        if (!confirm("Are you sure you want to restart Jasper? This will clear memory and refresh the backend.")) return;

        restartOverlay.classList.add('active');

        try {
            // Trigger restart
            fetch('/restart', { method: 'POST' }).catch(() => { });

            // Wait 3 seconds then start polling
            setTimeout(pollForServer, 3000);

        } catch (e) {
            console.error("Restart failed", e);
            restartOverlay.classList.remove('active');
        }
    });
}

async function pollForServer() {
    try {
        const resp = await fetch('/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: 'PING' }) // Simple check
        });

        if (resp.ok) {
            // Backend is up!
            window.location.reload();
        } else {
            setTimeout(pollForServer, 2000);
        }
    } catch (e) {
        // Still down
        setTimeout(pollForServer, 2000);
    }
}

async function openOutlookItem(entryId) {
    try {
        await fetch('/open', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: entryId, provider: 'OUTLOOK' })
        });
    } catch (e) {
        console.error("Failed to open outlook item", e);
    }
}

async function openFileItem(path) {
    try {
        await fetch('/open', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: path, provider: 'FILES' })
        });
    } catch (e) {
        console.error("Failed to open file", e);
    }
}

// Index Status Polling
async function pollIndexStatus() {
    try {
        const resp = await fetch('/index-status');
        if (resp.ok) {
            const data = await resp.json();
            const meta = document.getElementById('index-meta');
            const pctText = document.getElementById('index-pct');
            const bar = document.getElementById('index-bar');

            if (data.status !== "Idle" || data.percent < 100) {
                meta.style.display = "flex";
                pctText.innerText = data.percent + "%";
                bar.style.width = data.percent + "%";

                // If it's active, poll more frequently (every 5s)
                setTimeout(pollIndexStatus, 5000);
            } else {
                // Idle, hide or show 100% then hide
                pctText.innerText = "100%";
                bar.style.width = "100%";
                setTimeout(() => {
                    meta.style.display = "none";
                }, 10000);

                // Poll less frequently (every 30s)
                setTimeout(pollIndexStatus, 30000);
            }
        }
    } catch (e) {
        console.warn("Status poll failed", e);
        setTimeout(pollIndexStatus, 30000);
    }
}

// Start polling on load
pollIndexStatus();
