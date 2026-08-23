const API_BASE = window.location.origin;

// DOM Elements
const chatContainer = document.getElementById("chat-app");
const chatBox = document.getElementById("messages");
const emptyState = document.getElementById("empty-state");
const chatForm = document.getElementById("chat-form");
const queryInput = document.getElementById("query-input");
const sendBtn = document.getElementById("send-btn");
const themeToggle = document.getElementById("theme-toggle");
const scrollBottomBtn = document.getElementById("scroll-bottom-btn");
// Restore saved theme preference
if (localStorage.getItem("odTheme") === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
    themeToggle.textContent = "☀️";
}

function authHeaders() {
    return {
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
        } else if (res.status === 429) {
            appendMessage("Too many requests — please wait a moment before asking again.", "assistant");
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

        // Render System Paths if present
        if (data.system_paths && data.system_paths.length > 0) {
            const pathsContainer = document.createElement("div");
            pathsContainer.className = "system-paths-container";
            
            data.system_paths.forEach(path => {
                const pathCard = document.createElement("div");
                pathCard.className = "system-path-card";
                
                const stepsHtml = path.steps.map(step => `
                    <div class="system-path-step-box">
                        ${escapeHTML(step)}
                    </div>
                `).join('<div class="system-path-arrow">→</div>');
                
                pathCard.innerHTML = `
                    <div class="system-path-card-title">${escapeHTML(path.title)}</div>
                    ${path.description ? `<div class="system-path-card-desc">${escapeHTML(path.description)}</div>` : ''}
                    <div class="system-path-flow">
                        ${stepsHtml}
                    </div>
                `;
                pathsContainer.appendChild(pathCard);
            });
            msgDiv.appendChild(pathsContainer);
        }

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

// ── FAQ Module ─────────────────────────────────────────────────────────────

let allFaqs = [];

async function loadUserFaqs() {
    const loading = document.getElementById("faq-loading");
    const empty = document.getElementById("faq-empty");
    const accordion = document.getElementById("faq-accordion");
    if (!accordion) return;

    loading.classList.remove("hidden");
    empty.classList.add("hidden");
    accordion.classList.add("hidden");
    accordion.innerHTML = "";

    try {
        const res = await fetch(`${API_BASE}/faqs`);
        if (res.ok) {
            allFaqs = await res.json();
            renderFaqs(allFaqs);
        }
    } catch (e) {
        console.error("Failed to load FAQs", e);
        loading.textContent = "Error loading FAQs.";
    }
}

function renderFaqs(faqsToRender) {
    const loading = document.getElementById("faq-loading");
    const empty = document.getElementById("faq-empty");
    const accordion = document.getElementById("faq-accordion");
    
    loading.classList.add("hidden");
    
    if (faqsToRender.length === 0) {
        accordion.classList.add("hidden");
        empty.classList.remove("hidden");
        return;
    }
    
    empty.classList.add("hidden");
    accordion.classList.remove("hidden");
    accordion.innerHTML = "";
    
    faqsToRender.forEach(f => {
        const card = document.createElement("div");
        card.className = "faq-card";
        card.innerHTML = `
            <div class="faq-header" onclick="this.parentElement.classList.toggle('open')">
                <span>${escapeHTML(f.question)}</span>
                <span class="icon">▼</span>
            </div>
            <div class="faq-body">
                <div class="faq-content">
                    ${escapeHTML(f.answer).replace(/\n/g, '<br>')}
                </div>
                <div class="faq-action">
                    <button class="faq-ask-btn" onclick="askFaqQuestion('${escapeHTML(f.question).replace(/'/g, "\\'")}')">
                        Ask Od Assist ⚡
                    </button>
                </div>
            </div>
        `;
        accordion.appendChild(card);
    });
}

function askFaqQuestion(q) {
    document.getElementById("toggle-chat-btn").click();
    queryInput.value = q;
    chatForm.requestSubmit();
}

// Mode Toggle Listeners
const toggleChatBtn = document.getElementById("toggle-chat-btn");
const toggleFaqBtn = document.getElementById("toggle-faq-btn");
const faqView = document.getElementById("faq-view");
const inputBar = document.querySelector(".input-bar");

if (toggleChatBtn && toggleFaqBtn) {
    toggleChatBtn.addEventListener("click", () => {
        toggleChatBtn.classList.add("active");
        toggleFaqBtn.classList.remove("active");
        faqView.classList.add("hidden");
        chatBox.classList.remove("hidden");
        inputBar.classList.remove("hidden");
        scrollToBottom();
    });

    toggleFaqBtn.addEventListener("click", () => {
        toggleFaqBtn.classList.add("active");
        toggleChatBtn.classList.remove("active");
        chatBox.classList.add("hidden");
        inputBar.classList.add("hidden");
        faqView.classList.remove("hidden");
        if (allFaqs.length === 0) loadUserFaqs();
    });
}

// FAQ Search and Filter
const faqSearchInput = document.getElementById("faq-search-input");
const faqCatBtns = document.querySelectorAll(".faq-cat-btn");

function filterFaqs() {
    const query = faqSearchInput ? faqSearchInput.value.toLowerCase() : "";
    const activeCatBtn = document.querySelector(".faq-cat-btn.active");
    const activeCat = activeCatBtn ? activeCatBtn.dataset.cat : "all";
    
    const filtered = allFaqs.filter(f => {
        const matchQ = f.question.toLowerCase().includes(query) || f.answer.toLowerCase().includes(query);
        const matchC = activeCat === "all" || (f.category || "General") === activeCat;
        return matchQ && matchC;
    });
    
    renderFaqs(filtered);
}

if (faqSearchInput) {
    faqSearchInput.addEventListener("input", filterFaqs);
}

faqCatBtns.forEach(btn => {
    btn.addEventListener("click", () => {
        faqCatBtns.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        filterFaqs();
    });
});