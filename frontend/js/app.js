// Logica applicativa JARVIS: login, dati reali delle conversazioni, ciclo
// vocale/testuale collegato al backend, delega (ADR-0003), voce.
// Guida l'interfaccia 3D di scene.js.
import { Scene3D, BRAINS } from "./scene.js";

const $ = (id) => document.getElementById(id);

const loginScreen = $("login-screen");
const chatScreen = $("chat-screen");
const loginForm = $("login-form");
const loginPassword = $("login-password");
const loginSubmit = $("login-submit");
const loginError = $("login-error");

const canvas = $("scene-canvas");
const labelLayer = $("body-labels");
const brainsEl = $("jv-brains");
const bodyCountEl = $("jv-bodycount");
const stateCodeEl = $("jv-statecode");
const sidebarEl = $("jv-sidebar");
const rowsEl = $("jv-rows");
const homeBtn = $("jv-home-btn");
const dockEl = $("jv-dock");
const transcriptEl = $("jv-transcript");
const messageForm = $("message-form");
const messageInput = $("message-input");
const micBtn = $("mic-btn");
const attachBtn = $("attach-btn");
const imageInput = $("image-input");
const imagePreview = $("image-preview");
const imagePreviewImg = $("image-preview-img");
const imagePreviewRemove = $("image-preview-remove");
const captionEl = $("jv-caption");
const subCaptionEl = $("jv-subcaption");
const panelEl = $("jv-panel");
const panelKindEl = $("jv-panel-kind");
const panelCloseBtn = $("jv-panel-close");
const panelTitleEl = $("jv-panel-title");
const panelSummaryEl = $("jv-panel-summary");
const panelWhenEl = $("jv-panel-when");
const panelMsgsEl = $("jv-panel-msgs");
const panelRelFillEl = $("jv-panel-relfill");
const panelBrainDotEl = $("jv-panel-brain-dot");
const panelBrainEl = $("jv-panel-brain");
const ttsBtn = $("tts-btn");
const googleBtn = $("google-btn");
const logoutBtn = $("logout-btn");
const libraryBtn = $("library-btn");
const libraryOverlay = $("library-overlay");
const libraryCloseBtn = $("library-close-btn");
const libraryListEl = $("library-list");
const projectsBtn = $("projects-btn");
const projectsOverlay = $("projects-overlay");
const projectsCloseBtn = $("projects-close-btn");
const projectsListEl = $("projects-list");
const projectCreateForm = $("project-create-form");
const projectNameInput = $("project-name-input");
const panelProjectSelect = $("jv-panel-project");

let scene = null;
let socket = null;
let currentConversationId = null;
let pendingImage = null;
let requestToken = 0;
let msgs = []; // trascritto visibile, max 2 — { who: 'you'|'jarvis', text }
let pendingAction = null; // action_payload dell'ultimo messaggio assistant, o null

const CAPTIONS = {
  idle: ["Standby", "tap the core or type"],
  listening: ["Listening", "the core is taking in sound"],
  processing: ["Processing", "routing to the best brain"],
  responding: ["Responding", null], // sottotitolo impostato dinamicamente col brain
};

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

function formatWhen(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const min = Math.round(diffMs / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr} hr${hr > 1 ? "s" : ""} ago`;
  const day = Math.round(hr / 24);
  if (day === 1) return "yesterday";
  if (day < 7) return `${day} days ago`;
  const week = Math.round(day / 7);
  return `${week} week${week > 1 ? "s" : ""} ago`;
}

// target di routing (app.chat_service) -> nome "brain" del design (scene.BRAINS)
function targetToBrain(target) {
  if (target === "claude") return "Claude";
  if (target === "chatgpt") return "ChatGPT";
  if (target === "gemini") return "Gemini";
  return "Groq"; // "local": classificato ed eventualmente risposto da Groq
}

// ---------- Conversazioni reali -> Body[] della scena ----------

function computeRelevance(conv, maxMsgCount) {
  const hoursSince = (Date.now() - new Date(conv.updated_at).getTime()) / 3600000;
  const recency = Math.exp(-hoursSince / 72); // decadimento ~72h
  const frequency = maxMsgCount > 0 ? Math.min(conv.message_count / maxMsgCount, 1) : 0;
  return Math.min(1, Math.max(0.12, 0.15 + recency * 0.6 + frequency * 0.25));
}

function conversationsToBodies(convs) {
  const maxMsgCount = Math.max(1, ...convs.map((c) => c.message_count || 0));
  return convs.map((c, i) => {
    const brain = targetToBrain(c.last_target);
    const msgCount = c.message_count || 0;
    return {
      id: c.id,
      name: c.title || "Untitled",
      kind: "chat",
      projectId: c.project_id || null,
      rel: computeRelevance(c, maxMsgCount),
      msgs: msgCount,
      when: formatWhen(c.updated_at),
      brain,
      summary: msgCount > 0 ? `${msgCount} exchange${msgCount === 1 ? "" : "s"}, last via ${brain}.` : "No messages yet.",
      order: i,
    };
  });
}

let allBodies = [];

async function refreshConversations(preserveSelection = true) {
  const { ok, body } = await api("/api/chat/conversations");
  if (!ok || !body?.data) return;
  allBodies = conversationsToBodies(body.data.conversations);
  scene.setBodies(allBodies);
  renderSidebarRows();
  bodyCountEl.textContent = String(scene.bodies.length).padStart(2, "0");

  if (preserveSelection && currentConversationId) {
    const stillExists = allBodies.some((b) => b.id === currentConversationId);
    if (stillExists) scene.select(currentConversationId);
  }
}

// ---------- Sidebar "Constellation" ----------

function renderSidebarRows() {
  rowsEl.innerHTML = "";
  if (!allBodies.length) {
    const empty = document.createElement("div");
    empty.className = "jv-sidebar-empty";
    empty.textContent = "No conversations yet — say something to start one.";
    rowsEl.appendChild(empty);
    return;
  }
  for (const b of allBodies) {
    const brainDef = BRAINS.find((x) => x.name === b.brain) || BRAINS[0];
    const row = document.createElement("div");
    row.className = "jv-row" + (currentConversationId === b.id ? " selected" : "");
    row.style.borderLeftColor = currentConversationId === b.id ? brainDef.color : "transparent";
    row.innerHTML = `<span class="jv-row-dot" style="background:${brainDef.color};opacity:${0.45 + b.rel * 0.55};box-shadow:0 0 8px 1px ${brainDef.color}55;"></span>
      <span class="jv-row-text">
        <span class="jv-row-name"></span>
        <span class="jv-row-meta">${escapeHtml((b.kind === "project" ? "Project" : "Chat") + " · " + b.when)}</span>
      </span>`;
    row.querySelector(".jv-row-name").textContent = b.name;
    row.addEventListener("click", () => selectConversation(b.id));
    row.addEventListener("mouseenter", () => scene.hoverRow(b.id));
    row.addEventListener("mouseleave", () => scene.clearHover());
    rowsEl.appendChild(row);
  }
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

// ---------- Selezione / pannello di dettaglio ----------

async function selectConversation(id) {
  currentConversationId = id;
  pendingAction = null;
  scene.select(id);
  renderSidebarRows();
  const { ok, body } = await api(`/api/chat/history?conversation_id=${id}`);
  if (ok && body?.data) {
    const all = body.data.messages;
    msgs = all.slice(-2).map((m) => ({ who: m.role === "user" ? "you" : "jarvis", text: m.content }));
    renderTranscript();
  }
}

function deselectConversation() {
  currentConversationId = null;
  pendingAction = null;
  scene.deselect();
  renderSidebarRows();
  msgs = [];
  renderTranscript();
}

homeBtn.addEventListener("click", deselectConversation);
panelCloseBtn.addEventListener("click", deselectConversation);

function renderPanel(data) {
  if (!data) {
    panelEl.hidden = true;
    return;
  }
  const brainDef = BRAINS.find((x) => x.name === data.brain) || BRAINS[0];
  panelEl.hidden = false;
  panelKindEl.textContent = data.kind === "project" ? "Project" : "Conversation";
  panelTitleEl.textContent = data.name;
  panelSummaryEl.textContent = data.summary;
  panelWhenEl.textContent = data.when;
  panelMsgsEl.textContent = String(data.msgs);
  panelRelFillEl.style.width = Math.round(data.rel * 100) + "%";
  panelRelFillEl.style.background = `linear-gradient(90deg, ${brainDef.color}, #9d7bff)`;
  panelBrainDotEl.style.background = brainDef.color;
  panelBrainDotEl.style.boxShadow = `0 0 9px 2px ${brainDef.color}66`;
  panelBrainEl.textContent = "ROUTED VIA " + data.brain.toUpperCase();
  populatePanelProjectSelect();
  panelProjectSelect.value = data.projectId || "";
}

// ---------- Status bar: chip dei modelli ----------

let activeBrainName = null;

function renderBrainChips() {
  brainsEl.innerHTML = "";
  for (const b of BRAINS) {
    const on = b.name === activeBrainName && currentMode !== "idle";
    const chip = document.createElement("div");
    chip.className = "jv-chip";
    let shapeStyle = `width:8px;height:8px;flex:0 0 auto;background:${b.color};opacity:${on ? 1 : 0.42};box-shadow:${on ? `0 0 9px 2px ${b.color}80` : "none"};`;
    if (b.name === "Groq") shapeStyle += "clip-path:polygon(50% 0,100% 100%,0 100%);";
    else if (b.name === "Gemini") shapeStyle += "transform:rotate(45deg);";
    else if (b.name === "ChatGPT") shapeStyle += "border-radius:3px;";
    else shapeStyle += "border-radius:50%;";
    chip.innerHTML = `<span class="jv-chip-shape" style="${shapeStyle}"></span><span class="jv-chip-label" style="color:${on ? "#f2f5ff" : "rgba(200,212,255,.45)"};"></span>`;
    chip.querySelector(".jv-chip-label").textContent = b.name;
    brainsEl.appendChild(chip);
  }
  const routeLine = document.createElement("span");
  routeLine.className = "jv-routeline";
  const activeDef = BRAINS.find((b) => b.name === activeBrainName);
  routeLine.textContent = currentMode === "idle" || !activeDef ? "standby / router idle" : activeDef.note;
  brainsEl.appendChild(routeLine);
}

// ---------- Stato / caption ----------

let currentMode = "idle";

function setMode(mode, subCaptionOverride) {
  currentMode = mode;
  scene.setMode(mode);
  stateCodeEl.textContent = mode.toUpperCase();
  const [caption, sub] = CAPTIONS[mode];
  captionEl.textContent = caption;
  subCaptionEl.textContent = subCaptionOverride || sub || "";
  renderBrainChips();
}

// ---------- Trascritto (ultime 2 battute) ----------

function renderTranscript() {
  transcriptEl.innerHTML = "";
  for (const m of msgs) {
    const div = document.createElement("div");
    div.className = "jv-msg " + (m.who === "you" ? "user" : "assistant");
    div.textContent = m.text;
    transcriptEl.appendChild(div);
  }
  if (pendingAction) renderActionCard(pendingAction);
}

function pushTranscript(who, text) {
  msgs = [...msgs, { who, text }].slice(-2);
  renderTranscript();
}

// ---------- Azioni sul messaggio dell'assistente (conferma invio email, delega Claude/ChatGPT) ----------

function clearPendingAction() {
  pendingAction = null;
  renderTranscript();
}

function renderActionCard(action) {
  const card = document.createElement("div");
  card.className = "jv-action";

  if (action.type === "confirm_email_send") {
    const send = document.createElement("button");
    send.type = "button";
    send.className = "jv-action-btn primary";
    send.textContent = "Invia";

    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "jv-action-btn";
    cancel.textContent = "Annulla";

    send.addEventListener("click", async () => {
      send.disabled = true;
      cancel.disabled = true;
      const { ok } = await api("/api/email/send", {
        method: "POST",
        body: JSON.stringify({ draft_id: action.draft_id }),
      });
      clearPendingAction();
      pushTranscript("jarvis", ok ? "Email inviata." : "Invio non riuscito — riprova.");
    });
    cancel.addEventListener("click", () => {
      clearPendingAction();
      pushTranscript("jarvis", "Ok, non la invio.");
    });

    card.append(send, cancel);
  } else if (action.type === "copy_and_open") {
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "jv-action-btn primary";
    copy.textContent = "Copia prompt";
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(action.prompt);
        copy.textContent = "Copiato!";
        setTimeout(() => (copy.textContent = "Copia prompt"), 1500);
      } catch (_) {
        /* clipboard non disponibile: l'utente può comunque aprire manualmente */
      }
    });

    const open = document.createElement("button");
    open.type = "button";
    open.className = "jv-action-btn";
    open.textContent = "Apri " + (action.target === "claude" ? "Claude" : "ChatGPT");
    open.addEventListener("click", () => window.open(action.url, "_blank", "noopener"));

    card.append(copy, open);
  } else if (action.type === "generated_image") {
    card.className = "jv-action jv-action-image";
    const img = document.createElement("img");
    img.className = "jv-generated-image";
    img.src = `data:image/jpeg;base64,${action.image_base64}`;
    img.alt = action.prompt || "Immagine generata";
    card.appendChild(img);
  } else {
    return;
  }

  transcriptEl.appendChild(card);
}

// ---------- Voce (Web Speech API) ----------

const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognizer = null;
let isListening = false;

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
    sendMessage(transcript);
  };
  recognizer.onend = () => {
    isListening = false;
    micBtn.classList.remove("listening");
    if (currentMode === "listening") setMode("idle");
  };
  recognizer.onerror = () => {
    isListening = false;
    micBtn.classList.remove("listening");
    if (currentMode === "listening") setMode("idle");
  };
}

function startVoice() {
  if (!recognizer || isListening) return;
  isListening = true;
  micBtn.classList.add("listening");
  setMode("listening");
  try {
    recognizer.start();
  } catch (_) {
    isListening = false;
    micBtn.classList.remove("listening");
    setMode("idle");
  }
}

micBtn.addEventListener("click", startVoice);

// ---------- TTS: stessa euristica di selezione voce già validata in Fase 4 ----------

let cachedVoices = [];
let chosenVoice = null;
const VOICE_QUALITY_HINTS = ["neural", "online", "natural", "google", "premium", "enhanced", "plus"];
const VOICE_LOW_QUALITY_HINTS = ["compact", "desktop", "eloquence"];

function scoreVoice(voice) {
  const name = voice.name.toLowerCase();
  let score = 0;
  if (voice.lang?.toLowerCase().startsWith("it")) score += 10;
  if (VOICE_QUALITY_HINTS.some((h) => name.includes(h))) score += 5;
  if (VOICE_LOW_QUALITY_HINTS.some((h) => name.includes(h))) score -= 5;
  if (voice.localService === false) score += 2;
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

/** Parla il testo e ritorna una Promise che si risolve a fine riproduzione
 * (o subito se la voce è disattivata/non disponibile) — usata per tenere lo
 * stato "responding" per la durata reale del parlato, non un timer fisso. */
function speak(text) {
  return new Promise((resolve) => {
    if (!ttsEnabled || !("speechSynthesis" in window)) {
      resolve();
      return;
    }
    try {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "it-IT";
      utterance.rate = 1.02;
      if (chosenVoice) utterance.voice = chosenVoice;
      utterance.onend = resolve;
      utterance.onerror = resolve;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    } catch (_) {
      resolve();
    }
  });
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

function connectSocket() {
  if (socket) return;
  socket = io({ withCredentials: true });
  socket.on("typing", () => {}); // lo stato "processing/responding" è già pilotato da sendMessage
  socket.on("error", () => {
    setMode("idle");
  });
}

function disconnectSocket() {
  if (socket) {
    socket.disconnect();
    socket = null;
  }
}

// ---------- Invio messaggi (testo o voce) ----------

async function sendMessage(text) {
  text = (text || "").trim();
  if (!text && !pendingImage) return;

  const myToken = ++requestToken;
  pendingAction = null;
  pushTranscript("you", text || "[image]");
  activeBrainName = null; // il router non ha ancora deciso: nessun chip acceso
  setMode("processing");

  const payload = { text, image: pendingImage || undefined, conversation_id: currentConversationId };
  messageInput.value = "";
  pendingImage = null;
  imagePreview.hidden = true;
  imageInput.value = "";

  const { ok, body } = await api("/api/chat/message", { method: "POST", body: JSON.stringify(payload) });
  if (myToken !== requestToken) return; // superato da un invio più recente

  if (!ok || !body?.data) {
    pushTranscript("jarvis", "Something went wrong — try again.");
    setMode("idle");
    return;
  }

  currentConversationId = body.data.conversation_id;
  const msg = body.data.message;
  const brain = targetToBrain(msg.target);
  activeBrainName = brain;
  pendingAction = body.data.action || null;
  pushTranscript("jarvis", msg.content);
  setMode("responding", brain + " is answering");

  await refreshConversations();
  await speak(msg.content);

  if (myToken === requestToken) setMode("idle");
}

messageForm.addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage(messageInput.value);
});

// ---------- Scena: click sul nucleo / su un corpo ----------

function onSceneReady() {
  scene.onNucleusClick = () => startVoice();
  scene.onSelectionChange = (data) => renderPanel(data);
}

// ---------- Login / bootstrap ----------

function showLogin() {
  chatScreen.hidden = true;
  loginScreen.hidden = false;
  loginPassword.value = "";
  loginPassword.focus();
}

async function showChat() {
  loginScreen.hidden = true;
  chatScreen.hidden = false;

  if (!scene) {
    scene = new Scene3D(canvas, labelLayer, {});
    onSceneReady();
    await scene.init();
  }

  connectSocket();
  setMode("idle");
  renderBrainChips();
  await refreshConversations(false);
  await refreshProjects();
  registerServiceWorker();
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
    await showChat();
  } else {
    const messages = {
      invalid_password: "Password errata.",
      app_password_not_configured: "L'app non è ancora configurata (manca APP_PASSWORD_HASH).",
    };
    loginError.textContent = messages[body?.error] || "Accesso non riuscito. Riprova.";
    loginError.hidden = false;
  }
});

logoutBtn.addEventListener("click", async () => {
  await api("/api/session/logout", { method: "POST" });
  disconnectSocket();
  showLogin();
});

// ---------- Libreria (fatti di memoria a lungo termine, RF-013) ----------

function formatFactCategory(category) {
  const labels = { preference: "Preferenza", contact: "Contatto", habit: "Abitudine", work: "Lavoro" };
  return labels[category] || category || "";
}

function renderLibraryList(facts) {
  libraryListEl.innerHTML = "";
  if (!facts.length) {
    const empty = document.createElement("div");
    empty.className = "jv-library-empty";
    empty.textContent = "Non ricordo ancora niente di te — parliamo un po'.";
    libraryListEl.appendChild(empty);
    return;
  }
  for (const f of facts) {
    const item = document.createElement("div");
    item.className = "jv-library-item";
    item.innerHTML = `<div class="jv-library-item-body">
        <div class="jv-library-item-fact"></div>
        <div class="jv-library-item-meta"></div>
      </div>
      <button type="button" class="jv-library-item-delete" title="Dimentica">&times;</button>`;
    item.querySelector(".jv-library-item-fact").textContent = f.fact;
    item.querySelector(".jv-library-item-meta").textContent =
      formatFactCategory(f.category) + " · " + formatWhen(f.created_at);
    item.querySelector(".jv-library-item-delete").addEventListener("click", async () => {
      const { ok } = await api(`/api/library/facts/${f.id}`, { method: "DELETE" });
      if (ok) item.remove();
      if (ok && !libraryListEl.children.length) renderLibraryList([]);
    });
    libraryListEl.appendChild(item);
  }
}

async function openLibrary() {
  libraryOverlay.hidden = false;
  const { ok, body } = await api("/api/library/facts");
  renderLibraryList(ok && body?.data ? body.data.facts : []);
}

function closeLibrary() {
  libraryOverlay.hidden = true;
}

libraryBtn.addEventListener("click", openLibrary);
libraryCloseBtn.addEventListener("click", closeLibrary);
libraryOverlay.addEventListener("click", (e) => {
  if (e.target === libraryOverlay) closeLibrary();
});

// ---------- Progetti (raggruppare conversazioni correlate) ----------

let cachedProjects = [];

function renderProjectsList(projects) {
  projectsListEl.innerHTML = "";
  if (!projects.length) {
    const empty = document.createElement("div");
    empty.className = "jv-library-empty";
    empty.textContent = "Nessun progetto ancora — creane uno qui sopra.";
    projectsListEl.appendChild(empty);
    return;
  }
  for (const p of projects) {
    const item = document.createElement("div");
    item.className = "jv-library-item";
    item.innerHTML = `<div class="jv-library-item-body">
        <div class="jv-project-item-name"></div>
        <div class="jv-library-item-meta"></div>
      </div>
      <button type="button" class="jv-library-item-delete" title="Elimina progetto">&times;</button>`;
    item.querySelector(".jv-project-item-name").textContent = p.name;
    const count = p.conversation_count || 0;
    item.querySelector(".jv-library-item-meta").textContent =
      `${count} conversazion${count === 1 ? "e" : "i"}`;
    item.querySelector(".jv-library-item-delete").addEventListener("click", async () => {
      const { ok } = await api(`/api/projects/${p.id}`, { method: "DELETE" });
      if (ok) {
        item.remove();
        await refreshProjects();
        if (!projectsListEl.children.length) renderProjectsList([]);
      }
    });
    projectsListEl.appendChild(item);
  }
}

async function refreshProjects() {
  const { ok, body } = await api("/api/projects");
  cachedProjects = ok && body?.data ? body.data.projects : [];
  populatePanelProjectSelect();
  return cachedProjects;
}

function populatePanelProjectSelect() {
  const current = panelProjectSelect.value;
  panelProjectSelect.innerHTML = '<option value="">Nessuno</option>';
  for (const p of cachedProjects) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = p.name;
    panelProjectSelect.appendChild(opt);
  }
  panelProjectSelect.value = current;
}

async function openProjects() {
  projectsOverlay.hidden = false;
  const projects = await refreshProjects();
  renderProjectsList(projects);
}

function closeProjects() {
  projectsOverlay.hidden = true;
}

projectsBtn.addEventListener("click", openProjects);
projectsCloseBtn.addEventListener("click", closeProjects);
projectsOverlay.addEventListener("click", (e) => {
  if (e.target === projectsOverlay) closeProjects();
});

projectCreateForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = projectNameInput.value.trim();
  if (!name) return;
  const { ok } = await api("/api/projects", { method: "POST", body: JSON.stringify({ name }) });
  if (ok) {
    projectNameInput.value = "";
    renderProjectsList(await refreshProjects());
  }
});

panelProjectSelect.addEventListener("change", async () => {
  if (!currentConversationId) return;
  const projectId = panelProjectSelect.value || null;
  const { ok } = await api(`/api/chat/conversations/${currentConversationId}/project`, {
    method: "PUT",
    body: JSON.stringify({ project_id: projectId }),
  });
  if (ok) await refreshConversations();
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
    pushTranscript("jarvis", "Google collegato con successo. Ora posso leggere email e calendario.");
  } else if (status === "error") {
    const detail = params.get("google_error") || "errore sconosciuto";
    pushTranscript("jarvis", `Collegamento a Google non riuscito (${detail}).`);
  }
  window.history.replaceState({}, "", window.location.pathname);
}

// ---------- Service worker ----------

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("/sw.js").catch(() => {
    /* offline caching non disponibile: la chat resta comunque funzionante online */
  });
}

async function bootstrap() {
  initSpeechRecognition();
  const { ok, body } = await api("/api/session/status");
  if (ok && body?.data?.authenticated) {
    await showChat();
    await refreshGoogleStatus();
    handleGoogleCallbackFeedback();
  } else {
    showLogin();
  }
}

bootstrap();
