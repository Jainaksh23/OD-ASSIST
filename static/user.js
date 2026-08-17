const API_BASE = window.location.origin;
let token = sessionStorage.getItem("userToken");

// DOM Elements
const loginContainer = document.getElementById("login-screen");
const chatContainer = document.getElementById("chat-app");
const loginForm = document.getElementById("login-form");
const logoutBtn = document.getElementById("logout-btn");
const chatBox = document.getElementById("messages");
const emptyState = document.getElementById("empty-state");
const chatForm = document.getElementById("chat-form");
const queryInput = document.getElementById("query-input");
const sendBtn = document.getElementById("send-btn");
const themeToggle = document.getElementById("theme-toggle");

// Init
if (token) {
    showChat();
}

// Restore saved theme preference
if (localStorage.getItem("odTheme") === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
    themeToggle.textContent = "☀️";
}

// Login
loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;
    const errDiv = document.getElementById("login-error");
    errDiv.classList.add("hidden");

    try {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });

        if (res.ok) {
            const data = await res.json();
            token = data.access_token;
            sessionStorage.setItem("userToken", token);
            showChat();
        } else {
            errDiv.textContent = "Invalid credentials";
            errDiv.classList.remove("hidden");
        }
    } catch (e) {
        errDiv.textContent = "Connection error";
        errDiv.classList.remove("hidden");
    }
});

logoutBtn.addEventListener("click", () => {
    sessionStorage.removeItem("userToken");
    token = null;
    loginContainer.classList.remove("hidden");
    chatContainer.classList.add("hidden");
});

function showChat() {
    loginContainer.classList.add("hidden");
    chatContainer.classList.remove("hidden");
    queryInput.focus();
}

function authHeaders() {
    return {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json"
    };
}

function scrollToBottom() {
    chatBox.scrollTop = chatBox.scrollHeight;
}

function hideEmptyState() {
    if (emptyState && !emptyState.classList.contains("hidden")) {
        emptyState.classList.add("hidden");
    }
}

// Suggested prompt chips
document.querySelectorAll(".suggestion-chip").forEach(chip => {
    chip.addEventListener("click", () => {
        const q = chip.getAttribute("data-q");
        queryInput.value = q;
        chatForm.requestSubmit();
    });
});

// Auto-resize textarea
queryInput.addEventListener("input", () => {
    queryInput.style.height = "auto";
    queryInput.style.height = Math.min(queryInput.scrollHeight, 120) + "px";
});

// Enter to send, Shift+Enter for newline
queryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        chatForm.requestSubmit();
    }
});

// Chat Submissions
chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = queryInput.value.trim();
    if (!text) return;

    hideEmptyState();

    // Add user message
    appendMessage(text, "user");
    queryInput.value = "";
    queryInput.style.height = "auto";
    sendBtn.disabled = true;

    // Add typing indicator
    const typingId = "typing-" + Date.now();
    const typingEl = document.createElement("div");
    typingEl.id = typingId;
    typingEl.className = "typing-indicator";
    typingEl.innerHTML = "<span></span><span></span><span></span>";
    chatBox.appendChild(typingEl);
    scrollToBottom();

    try {
        const res = await fetch(`${API_BASE}/chat/query`, {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ query: text })
        });

        const typingElem = document.getElementById(typingId);
        if (typingElem) typingElem.remove();

        if (res.ok) {
            const data = await res.json();
            appendAssistantMessage(data);
        } else if (res.status === 401) {
            logoutBtn.click();
        } else {
            appendMessage("Sorry, an error occurred while processing your query.", "assistant");
        }
    } catch (e) {
        const typingElem = document.getElementById(typingId);
        if (typingElem) typingElem.remove();
        appendMessage("Network error. Please try again later.", "assistant");
    } finally {
        sendBtn.disabled = false;
        queryInput.focus();
    }
});

function avatarHTML(role) {
    if (role === "user") return `<div class="msg-avatar">You</div>`;
    return `<div class="msg-avatar">⚡</div>`;
}

function appendMessage(text, role) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${role}-msg`;
    msgDiv.innerHTML = `${avatarHTML(role)}<div class="bubble">${escapeHTML(text)}</div>`;
    chatBox.appendChild(msgDiv);
    scrollToBottom();
}

function appendAssistantMessage(data) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `message assistant-msg`;

    let bubble = `<div class="bubble">`;

    if (data.confidence === "low") {
        bubble += `<div class="confidence-disclaimer">⚠️ I am not entirely confident about this answer based on the provided sources.</div>`;
    }

    bubble += `${formatAnswer(data.answer)}`;

    // Sources Accordion
    if (data.sources && data.sources.length > 0) {
        let sourcesHtml = data.sources.map(s => `<li>[${s.id}] ${escapeHTML(s.title)}</li>`).join("");

        bubble += `
        <div class="sources-accordion">
            <div class="accordion-header" onclick="this.nextElementSibling.classList.toggle('open')">
                <span>View Sources (${data.sources.length})</span>
                <span>▼</span>
            </div>
            <div class="accordion-content">
                <ul>${sourcesHtml}</ul>
            </div>
        </div>
        `;
    }

    // Feedback buttons
    if (data.query_id) {
        bubble += `
        <div class="feedback-box" id="feedback-${data.query_id}">
            <button class="feedback-btn" onclick="submitFeedback(${data.query_id}, 'up', this)">👍</button>
            <button class="feedback-btn" onclick="submitFeedback(${data.query_id}, 'down', this)">👎</button>
        </div>
        `;
    }

    bubble += `</div>`;

    msgDiv.innerHTML = `${avatarHTML("assistant")}${bubble}`;
    chatBox.appendChild(msgDiv);
    scrollToBottom();
}

window.submitFeedback = async function (queryId, feedback, btnElem) {
    try {
        const res = await fetch(`${API_BASE}/chat/feedback`, {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ query_id: queryId, feedback })
        });
        if (res.ok) {
            const box = document.getElementById(`feedback-${queryId}`);
            box.querySelectorAll('.feedback-btn').forEach(b => b.classList.remove('active'));
            btnElem.classList.add('active');
        }
    } catch (e) {
        console.error("Feedback error", e);
    }
}

// Dark mode toggle (persisted)
themeToggle.addEventListener("click", () => {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    if (isDark) {
        document.documentElement.removeAttribute("data-theme");
        themeToggle.textContent = "🌙";
        localStorage.setItem("odTheme", "light");
    } else {
        document.documentElement.setAttribute("data-theme", "dark");
        themeToggle.textContent = "☀️";
        localStorage.setItem("odTheme", "dark");
    }
});

function escapeHTML(str) {
    return str.replace(/[&<>'"]/g,
        tag => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            "'": '&#39;',
            '"': '&quot;'
        }[tag])
    );
}

function formatAnswer(text) {
    let formatted = escapeHTML(text);
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    formatted = formatted.replace(/\n/g, '<br>');
    return formatted;
}