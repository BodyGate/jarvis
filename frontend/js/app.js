// Logica applicativa JARVIS: login, chat via WebSocket, azioni di delega
// (ADR-0003), upload immagini, voce (Web Speech API), collegamento Google.
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const loginScreen = $("login-screen");
  const chatScreen = $("chat-screen");
  const loginForm = $("login-form");
  const loginPassword = $("login-password");
  const loginSubmit = $("login-submit");
  const loginError = $("login-error");

  const messagesEl = $("messages");
  const typingIndicator = $("typing-indicator");
  const messageForm = $("message-form");
  const messageInput = $("message-input");
  const sendBtn = $("send-btn");
  const attachBtn = $("attach-btn");
  const imageInput = $("image-input");
  const imagePreview = $("image-preview");
  const imagePreviewImg = $("image-preview-img");
  const imagePreviewRemove = $("image-preview-remove");
  const micBtn = $("mic-btn");
  const newChatBtn = $("new-chat-btn");
  const logoutBtn = $("logout-btn");
  const googleBtn = $("google-btn");
  const connectionDot = $("connection-dot");
  const connectionLabel = $("connection-label");
  const actionCardTemplate = $("action-card-template");

  let socket = null;
  let currentConversationId = null;
  let pendingImage = null; // data URL in attesa di invio

  // ---------- Utility ----------

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    let body = null;
    try {
      body = await response.json();
    } catch (_) {
      /* risposta senza corpo JSON */
    }
    return { ok: response.ok, status: response.status, body };
  }

  function autoResizeTextarea() {
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + "px";
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function formatTime(iso) {
    try {
      return new Date(iso).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
    } catch (_) {
      return "";
    }
  }

  // ---------- Rendering messaggi ----------

  function clearMessages() {
    messagesEl.innerHTML = "";
  }

  function showEmptyState() {
    clearMessages();
    const wrap = document.createElement("div");
    wrap.className = "empty-state";
    wrap.innerHTML = `
      <img src="icons/icon-192.png" alt="" class="brand-mark" />
      <p>Ciao! Scrivimi qualcosa, oppure allega una foto o usa la voce.</p>
    `;
    messagesEl.appendChild(wrap);
  }

  function renderActionCard(container, action) {
    const node = actionCardTemplate.content.cloneNode(true);
    const label = node.querySelector(".action-card-label");
    const openBtn = node.querySelector(".action-open-btn");
    const copyBtn = node.querySelector(".action-copy-btn");

    const targetName = action.target === "claude" ? "Claude" : "ChatGPT";
    label.textContent = `Richiede ${targetName}`;
    openBtn.textContent = `Apri ${targetName}`;

    const doCopyAndOpen = () => {
      // ADR-0003: copia dentro il gesto di tap, poi apre subito la scheda —
      // entrambe le chiamate restano sincrone nello stesso handler.
      navigator.clipboard.writeText(action.prompt).catch(() => {});
      window.open(action.url, "_blank", "noopener");
    };

    openBtn.addEventListener("click", doCopyAndOpen);
    copyBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(action.prompt).catch(() => {});
      copyBtn.textContent = "Copiato ✓";
      copyBtn.classList.add("copied");
      setTimeout(() => {
        copyBtn.textContent = "Copia prompt";
        copyBtn.classList.remove("copied");
      }, 1600);
    });

    container.appendChild(node);
  }

  function appendMessage(msg) {
    if (messagesEl.querySelector(".empty-state")) clearMessages();

    const row = document.createElement("div");
    row.className = `msg-row ${msg.role === "user" ? "user" : "assistant"}`;

    const bubble = document.createElement("div");
    bubble.className = "bubble";

    if (msg.image_url) {
      const img = document.createElement("img");
      img.src = msg.image_url;
      img.className = "attached";
      img.alt = "Immagine allegata";
      bubble.appendChild(img);
    }

    const text = document.createElement("div");
    text.textContent = msg.content;
    bubble.appendChild(text);

    if (msg.action) {
      renderActionCard(bubble, msg.action);
    }

    const meta = document.createElement("div");
    meta.className = "msg-meta";
    meta.textContent = formatTime(msg.created_at || new Date().toISOString());
    bubble.appendChild(meta);

    row.appendChild(bubble);
    messagesEl.appendChild(row);
    scrollToBottom();

    if (msg.role === "assistant" && msg.content) {
      speak(msg.content);
    }
  }

  function setTyping(isTyping) {
    typingIndicator.hidden = !isTyping;
    if (isTyping) scrollToBottom();
  }

  // ---------- Voce (Web Speech API) ----------

  const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognizer = null;
  let isRecording = false;

  function initSpeechRecognition() {
    if (!SpeechRecognitionImpl) {
      micBtn.style.display = "none";
      return;
    }
    recognizer = new SpeechRecognitionImpl();
    recognizer.lang = "it-IT";
    recognizer.interimResults = false;
    recognizer.maxAlternatives = 1;

    recognizer.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      messageInput.value = (messageInput.value ? messageInput.value + " " : "") + transcript;
      autoResizeTextarea();
      messageInput.focus();
    };
    recognizer.onend = () => {
      isRecording = false;
      micBtn.classList.remove("recording");
    };
    recognizer.onerror = () => {
      isRecording = false;
      micBtn.classList.remove("recording");
    };
  }

  micBtn.addEventListener("click", () => {
    if (!recognizer) return;
    if (isRecording) {
      recognizer.stop();
      return;
    }
    isRecording = true;
    micBtn.classList.add("recording");
    try {
      recognizer.start();
    } catch (_) {
      isRecording = false;
      micBtn.classList.remove("recording");
    }
  });

  // La Web Speech API espone qualunque voce installata nel sistema operativo,
  // ma sceglie di default quella più "compatta"/robotica se non specificata
  // esplicitamente. Qui si cerca la miglior voce italiana disponibile,
  // preferendo i motori neurali/cloud (molto più naturali) a quelli offline
  // di base — la disponibilità varia per dispositivo (iPhone/Safari ha
  // tipicamente voci migliori di Chrome su Windows).
  let cachedVoices = [];
  let chosenVoice = null;

  const VOICE_QUALITY_HINTS = [
    "neural", "online", "natural", "google", "premium", "enhanced", "plus",
  ];
  const VOICE_LOW_QUALITY_HINTS = ["compact", "desktop", "eloquence"];

  function scoreVoice(voice) {
    const name = voice.name.toLowerCase();
    let score = 0;
    if (voice.lang?.toLowerCase().startsWith("it")) score += 10;
    if (VOICE_QUALITY_HINTS.some((hint) => name.includes(hint))) score += 5;
    if (VOICE_LOW_QUALITY_HINTS.some((hint) => name.includes(hint))) score -= 5;
    if (voice.localService === false) score += 2; // voci cloud, di solito più naturali
    return score;
  }

  function pickBestVoice() {
    if (!cachedVoices.length) return null;
    const savedName = localStorage.getItem("jarvis_tts_voice");
    if (savedName) {
      const saved = cachedVoices.find((v) => v.name === savedName);
      if (saved) return saved;
    }
    return [...cachedVoices].sort((a, b) => scoreVoice(b) - scoreVoice(a))[0] || null;
  }

  function loadVoices() {
    cachedVoices = window.speechSynthesis.getVoices();
    if (cachedVoices.length) chosenVoice = pickBestVoice();
  }

  if ("speechSynthesis" in window) {
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;
  }

  let ttsEnabled = localStorage.getItem("jarvis_tts_muted") !== "true";
  const ttsBtn = $("tts-btn");

  function updateTtsButton() {
    ttsBtn.classList.toggle("active", ttsEnabled);
    ttsBtn.title = ttsEnabled ? "Disattiva voce risposte" : "Attiva voce risposte";
  }
  updateTtsButton();

  ttsBtn.addEventListener("click", () => {
    ttsEnabled = !ttsEnabled;
    localStorage.setItem("jarvis_tts_muted", (!ttsEnabled).toString());
    updateTtsButton();
    if (!ttsEnabled) window.speechSynthesis?.cancel();
  });

  function speak(text) {
    if (!ttsEnabled || !("speechSynthesis" in window)) return;
    try {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "it-IT";
      utterance.rate = 1.02;
      if (chosenVoice) utterance.voice = chosenVoice;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    } catch (_) {
      /* TTS non disponibile: degradazione silenziosa, non blocca la chat */
    }
  }

  // ---------- Upload immagine ----------

  attachBtn.addEventListener("click", () => imageInput.click());

  imageInput.addEventListener("change", () => {
    const file = imageInput.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      pendingImage = reader.result;
      imagePreviewImg.src = pendingImage;
      imagePreview.hidden = false;
    };
    reader.readAsDataURL(file);
  });

  imagePreviewRemove.addEventListener("click", () => {
    pendingImage = null;
    imageInput.value = "";
    imagePreview.hidden = true;
  });

  // ---------- Connessione WebSocket ----------

  function setConnectionStatus(state) {
    connectionDot.classList.remove("online", "error");
    if (state === "online") {
      connectionDot.classList.add("online");
      connectionLabel.textContent = "Online";
    } else if (state === "error") {
      connectionDot.classList.add("error");
      connectionLabel.textContent = "Disconnesso";
    } else {
      connectionLabel.textContent = "Connessione...";
    }
  }

  function connectSocket() {
    if (socket) return;
    socket = io({ withCredentials: true });

    socket.on("connect", () => setConnectionStatus("online"));
    socket.on("disconnect", () => setConnectionStatus("error"));
    socket.on("connect_error", () => setConnectionStatus("error"));

    socket.on("typing", (data) => setTyping(data.status === "start"));

    socket.on("message", (msg) => {
      setTyping(false);
      currentConversationId = msg.conversation_id || currentConversationId;
      appendMessage(msg);
    });

    socket.on("error", (data) => {
      setTyping(false);
      appendMessage({
        role: "assistant",
        content: `Si è verificato un problema: ${data.error || "errore sconosciuto"}.`,
        created_at: new Date().toISOString(),
      });
    });
  }

  function disconnectSocket() {
    if (socket) {
      socket.disconnect();
      socket = null;
    }
  }

  // ---------- Invio messaggi ----------

  messageInput.addEventListener("input", autoResizeTextarea);
  messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      messageForm.requestSubmit();
    }
  });

  messageForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = messageInput.value.trim();
    if (!text && !pendingImage) return;

    appendMessage({
      role: "user",
      content: text,
      image_url: pendingImage || null,
      created_at: new Date().toISOString(),
    });

    const payload = {
      text,
      image: pendingImage || undefined,
      conversation_id: currentConversationId,
    };

    messageInput.value = "";
    autoResizeTextarea();
    pendingImage = null;
    imagePreview.hidden = true;
    imageInput.value = "";
    setTyping(true);

    if (socket && socket.connected) {
      socket.emit("send_message", payload);
    } else {
      // Fallback REST se il WebSocket non è disponibile.
      api("/api/chat/message", { method: "POST", body: JSON.stringify(payload) }).then(
        ({ ok, body }) => {
          setTyping(false);
          if (ok && body?.data) {
            currentConversationId = body.data.conversation_id;
            appendMessage({ ...body.data.message, action: body.data.action });
          } else {
            appendMessage({
              role: "assistant",
              content: "Non sono riuscito a inviare il messaggio. Riprova.",
              created_at: new Date().toISOString(),
            });
          }
        }
      );
    }
  });

  // ---------- Nuova conversazione / logout ----------

  newChatBtn.addEventListener("click", () => {
    currentConversationId = null;
    showEmptyState();
  });

  logoutBtn.addEventListener("click", async () => {
    await api("/api/session/logout", { method: "POST" });
    disconnectSocket();
    showLogin();
  });

  // ---------- Google ----------

  async function refreshGoogleStatus() {
    const { ok, body } = await api("/auth/status");
    if (ok && body?.data?.connected) {
      googleBtn.classList.add("active");
      googleBtn.title = "Google collegato";
    } else {
      googleBtn.classList.remove("active");
      googleBtn.title = "Collega Google";
    }
  }

  googleBtn.addEventListener("click", () => {
    window.location.href = "/auth/google";
  });

  function handleGoogleCallbackFeedback() {
    const params = new URLSearchParams(window.location.search);
    const status = params.get("google");
    if (!status) return;

    if (status === "connected") {
      appendMessage({
        role: "assistant",
        content: "Google collegato con successo. Ora posso leggere email e calendario.",
        created_at: new Date().toISOString(),
      });
    } else if (status === "error") {
      const detail = params.get("google_error") || "errore sconosciuto";
      appendMessage({
        role: "assistant",
        content: `Collegamento a Google non riuscito (${detail}).`,
        created_at: new Date().toISOString(),
      });
    }
    window.history.replaceState({}, "", window.location.pathname);
  }

  // ---------- Login / bootstrap ----------

  function showLogin() {
    chatScreen.hidden = true;
    loginScreen.hidden = false;
    loginPassword.value = "";
    loginPassword.focus();
  }

  function showChat() {
    loginScreen.hidden = true;
    chatScreen.hidden = false;
    showEmptyState();
    connectSocket();
    refreshGoogleStatus();
    handleGoogleCallbackFeedback();
    messageInput.focus();
  }

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    loginError.hidden = true;
    loginSubmit.disabled = true;
    loginSubmit.querySelector(".btn-spinner").hidden = false;

    const { ok, body } = await api("/api/session/login", {
      method: "POST",
      body: JSON.stringify({ password: loginPassword.value }),
    });

    loginSubmit.disabled = false;
    loginSubmit.querySelector(".btn-spinner").hidden = true;

    if (ok && body?.success) {
      showChat();
    } else {
      const messages = {
        invalid_password: "Password errata.",
        app_password_not_configured: "L'app non è ancora configurata (manca APP_PASSWORD_HASH).",
      };
      loginError.textContent = messages[body?.error] || "Accesso non riuscito. Riprova.";
      loginError.hidden = false;
    }
  });

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* offline caching non disponibile: la chat resta comunque funzionante online */
    });
  }

  async function bootstrap() {
    initSpeechRecognition();
    registerServiceWorker();
    const { ok, body } = await api("/api/session/status");
    if (ok && body?.data?.authenticated) {
      showChat();
    } else {
      showLogin();
    }
  }

  bootstrap();
})();
