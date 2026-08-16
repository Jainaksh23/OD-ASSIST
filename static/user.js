const API_BASE = window.location.origin;
let token = sessionStorage.getItem("userToken");

// DOM Elements
const loginContainer = document.getElementById("login-screen");
const chatContainer = document.getElementById("chat-app");
const loginForm = document.getElementById("login-form");
const logoutBtn = document.getElementById("logout-btn");
const chatBox = document.getElementById("messages");
const chatForm = document.getElementById("chat-form");
const queryInput = document.getElementById("query-input");
const themeToggle = document.getElementById("theme-toggle");

// Init
if (token) {
    showChat();
}

// Login
loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;
    const errDiv = document.getElementById("login-error");
    
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
        }
    } catch (e) {
        errDiv.textContent = "Connection error";
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

// Chat Submissions
chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = queryInput.value.trim();
    if (!text) return;
    
    // Add user message
    appendMessage(text, "user");
    queryInput.value = "";
    
    // Add typing indicator
    const typingId = "typing-" + Date.now();
    const typingEl = document.createElement("div");
    typingEl.id = typingId;
    typingEl.className = "typing-indicator";
    typingEl.textContent = "OD Assist is thinking...";
    chatBox.appendChild(typingEl);
    scrollToBottom();
    
    try {
        const res = await fetch(`${API_BASE}/chat/query`, {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ query: text })
        });
        
        document.getElementById(typingId).remove();
        
        if (res.ok) {
            const data = await res.json();
            appendAssistantMessage(data);
        } else if (res.status === 401) {
            logoutBtn.click();
        } else {
            appendMessage("Sorry, an error occurred while processing your query.", "assistant");
        }
    } catch (e) {
        document.getElementById(typingId).remove();
        appendMessage("Network error. Please try again later.", "assistant");
    }
});

function appendMessage(text, role) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${role}-msg`;
    msgDiv.innerHTML = `<div class="bubble">${escapeHTML(text)}</div>`;
    chatBox.appendChild(msgDiv);
    scrollToBottom();
}

function appendAssistantMessage(data) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `message assistant-msg`;
    
    let html = `<div class="bubble">`;
    
    if (data.confidence === "low") {
        html += `<div class="confidence-disclaimer">⚠️ Disclaimer: I am not entirely confident about this answer based on the provided sources.</div>`;
    }
    
    html += `${formatAnswer(data.answer)}`;
    html += `</div>`;
    
    // Sources Accordion
    if (data.sources && data.sources.length > 0) {
        let sourcesHtml = data.sources.map(s => `<li>[${s.id}] ${escapeHTML(s.title)}</li>`).join("");
        
        html += `
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
        html += `
        <div class="feedback-box" id="feedback-${data.query_id}">
            <button class="feedback-btn" onclick="submitFeedback(${data.query_id}, 'up', this)">👍</button>
            <button class="feedback-btn" onclick="submitFeedback(${data.query_id}, 'down', this)">👎</button>
        </div>
        `;
    }
    
    msgDiv.innerHTML = html;
    chatBox.appendChild(msgDiv);
    scrollToBottom();
}

window.submitFeedback = async function(queryId, feedback, btnElem) {
    try {
        const res = await fetch(`${API_BASE}/chat/feedback`, {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ query_id: queryId, feedback })
        });
        if (res.ok) {
            // highlight btn
            const box = document.getElementById(`feedback-${queryId}`);
            box.querySelectorAll('.feedback-btn').forEach(b => b.classList.remove('active'));
            btnElem.classList.add('active');
        }
    } catch (e) {
        console.error("Feedback error", e);
    }
}

// Dark mode toggle
themeToggle.addEventListener("click", () => {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    if (isDark) {
        document.documentElement.removeAttribute("data-theme");
        themeToggle.textContent = "🌙";
    } else {
        document.documentElement.setAttribute("data-theme", "dark");
        themeToggle.textContent = "☀️";
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
    // Basic formatting: newlines to <br>, simple markdown bold **text** to <strong>
    let formatted = escapeHTML(text);
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    formatted = formatted.replace(/\n/g, '<br>');
    return formatted;
}
