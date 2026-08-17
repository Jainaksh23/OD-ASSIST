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
const scrollBottomBtn = document.getElementById("scroll-bottom-btn");

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

// Rotating Tips
const tips = [
    "Tip: You can ask follow-up questions too",
    "Tip: I cite my sources for every answer",
    "Tip: Switch to dark mode from the header",
    "Tip: Use Shift+Enter for a new line"
];
let tipIndex = 0;
const rotatingTipsEl = document.getElementById("rotating-tips");
if (rotatingTipsEl) {
    const tipDiv = document.createElement("div");
    tipDiv.className = "tip-text active";
    tipDiv.textContent = tips[0];
    rotatingTipsEl.appendChild(tipDiv);
    
    setInterval(() => {
        tipDiv.classList.remove("active");
        setTimeout(() => {
            tipIndex = (tipIndex + 1) % tips.length;
            tipDiv.textContent = tips[tipIndex];
            tipDiv.classList.add("active");
        }, 500); 
    }, 4500);
}

// Scroll to bottom logic
if (scrollBottomBtn) {
    chatBox.addEventListener("scroll", () => {
        if (chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight > 150) {
            scrollBottomBtn.classList.remove("hidden");
        } else {
            scrollBottomBtn.classList.add("hidden");
        }
    });
    scrollBottomBtn.addEventListener("click", () => {
        scrollToBottom();
    });
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

function getTimestamp() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function appendMessage(text, role) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${role}-msg`;
    msgDiv.innerHTML = `${avatarHTML(role)}<div class="bubble">${escapeHTML(text)}<span class="msg-timestamp">${getTimestamp()}</span></div>`;
    chatBox.appendChild(msgDiv);
    scrollToBottom();
}

function generateFollowUps(text) {
    const lowerText = text.toLowerCase();
    const chips = [];
    if (lowerText.includes("fee")) chips.push("How is the fee calculated?", "Can I pay fees online?");
    else if (lowerText.includes("admission")) chips.push("What are the admission requirements?", "Admission form link");
    else if (lowerText.includes("transport")) chips.push("Transport fee details", "Bus route tracking");
    else if (lowerText.includes("payroll")) chips.push("When is payroll processed?", "View my payslip");
    else if (lowerText.includes("student")) chips.push("Student attendance policy", "How to view student marks");
    
    if (chips.length === 0) chips.push("Tell me more about this", "What else should I know?");
    return chips.slice(0, 2);
}

function typeWriter(element, htmlContent, onComplete) {
    let i = 0;
    let isTag = false;
    let text = "";
    function type() {
        if (i < htmlContent.length) {
            text += htmlContent.charAt(i);
            element.innerHTML = text;
            if (htmlContent.charAt(i) === '<') isTag = true;
            if (htmlContent.charAt(i) === '>') isTag = false;
            i++;
            if (isTag) {
                type();
            } else {
                setTimeout(type, 15); // Fast typewriter
            }
            scrollToBottom();
        } else {
            if(onComplete) onComplete();
        }
    }
    type();
}

function appendAssistantMessage(data) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `message assistant-msg`;
    msgDiv.innerHTML = `${avatarHTML("assistant")}<div class="bubble" id="temp-bubble-${data.query_id}"></div>`;
    chatBox.appendChild(msgDiv);
    
    const bubbleEl = msgDiv.querySelector('.bubble');
    const formattedHtml = formatAnswer(data.answer);
    
    typeWriter(bubbleEl, formattedHtml, () => {
        let extras = "";
        
        // Confidence dot
        let confClass = "high";
        if (data.confidence === "low") confClass = "low";
        else if (data.confidence === "medium") confClass = "medium";
        
        extras += `<span class="msg-timestamp">${getTimestamp()} <span class="confidence-dot ${confClass}" title="Confidence: ${data.confidence}"></span></span>`;
        
        // Sources Accordion
        if (data.sources && data.sources.length > 0) {
            let sourcesHtml = data.sources.map(s => `<li>[${s.id}] ${escapeHTML(s.title)}</li>`).join("");
            extras += `
            <div class="sources-accordion">
                <div class="accordion-header" onclick="this.nextElementSibling.classList.toggle('open')">
                    <span>View Sources (${data.sources.length})</span>
                    <span>▼</span>
                </div>
                <div class="accordion-content">
                    <ul>${sourcesHtml}</ul>
                </div>
            </div>`;
        }

        // Smart Follow-up Chips
        const followUps = generateFollowUps(data.answer);
        if (followUps.length > 0) {
            const chipsHtml = followUps.map(f => `<button onclick="document.getElementById('query-input').value='${f}'; document.getElementById('chat-form').requestSubmit();">${f}</button>`).join("");
            extras += `<div class="follow-up-chips">${chipsHtml}</div>`;
        }

        // Feedback buttons
        if (data.query_id) {
            extras += `
            <div class="feedback-box" id="feedback-${data.query_id}">
                <button class="feedback-btn" onclick="submitFeedback(${data.query_id}, 'up', this)">👍</button>
                <button class="feedback-btn" onclick="submitFeedback(${data.query_id}, 'down', this)">👎</button>
            </div>`;
        }
        
        bubbleEl.innerHTML += extras;
        scrollToBottom();
    });
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
            box.querySelectorAll('.feedback-btn').forEach(b => {
                b.classList.remove('active');
                b.classList.remove('confetti');
            });
            btnElem.classList.add('active');
            if (feedback === 'up') {
                btnElem.classList.add('confetti');
                setTimeout(() => btnElem.classList.remove('confetti'), 700);
            }
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