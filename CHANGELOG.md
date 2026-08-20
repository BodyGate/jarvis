# Changelog

Tutte le milestone rilevanti del progetto JARVIS sono tracciate qui, in ordine
cronologico inverso (più recente in cima).

## [Unreleased] — Cancellazione conversazioni via chat (richiesta dall'utente)

L'utente ha segnalato che, chiedendo a JARVIS di eliminare vecchie
conversazioni di test, l'assistente rispondeva di non poterlo fare. Aggiunta
la capacità di eliminare la conversazione attiva su richiesta in linguaggio
naturale, più un endpoint REST equivalente per il frontend.

### Added
- `backend/app/router.py`: nuovo specialist `conversation_delete` riconosciuto
  dal classificatore Groq
- `backend/app/chat_service.py`: `_handle_conversation_delete()` — se non
  c'è una conversazione attiva selezionata chiede all'utente di sceglierne
  una, altrimenti conferma ed elimina la conversazione (in `process_message`,
  solo dopo aver salvato la risposta di conferma, per non rompere l'insert
  del messaggio assistant; i messaggi vengono rimossi in cascata dallo schema
  del DB — `ON DELETE CASCADE`, Fase 1)
- `backend/app/chat_routes.py`: `DELETE /api/chat/conversations/<id>`,
  scoping per utente, 404 per id inesistenti o non-UUID (senza questo
  controllo un id malformato causava un 500 da Postgres invece di un 404,
  scoperto durante la verifica manuale contro il DB reale)
- 5 nuovi test (`test_router.py`, `test_chat_service.py`,
  `test_chat_routes.py`), 150/150 passanti nel modulo `backend/tests`

## [Unreleased] — Memoria a lungo termine (RF-013)

Su richiesta dell'utente ("implementiamo subito memoria a lungo termine"),
JARVIS ora estrae e ricorda fatti rilevanti sull'utente (preferenze,
contatti, abitudini, lavoro) tra conversazioni diverse, e li usa per
personalizzare sia le risposte locali sia le richieste delegate a
Claude/ChatGPT.

### Added
- `backend/app/memory.py`: `extract_facts()` (Groq, prompt conservativo che
  riceve i fatti già noti per evitare duplicati; non solleva mai eccezioni —
  in caso di errore restituisce `[]` così l'estrazione non può mai rompere
  il flusso della chat), `save_facts()`, `get_known_facts()`
  (tabella `user_facts`)
- `backend/app/chat_service.py`: ogni messaggio utente viene analizzato per
  nuovi fatti; i fatti noti vengono iniettati sia in `local_chat.py` (risposte
  generiche) sia nel prompt copiato per Claude/ChatGPT
- 13 nuovi test (`test_memory.py`, `test_local_chat.py`,
  `test_chat_service.py`)

## [Unreleased] — Fix: risposta locale generica (specialist "other")

Bug segnalato dall'utente: chiedendo a JARVIS di presentarsi, il router
classificava correttamente la richiesta come locale, ma non c'era nessuna
risposta reale dietro lo specialist "other" — solo un segnaposto
("Ho classificato la richiesta come locale, ma non ho un modo specifico per
gestirla ancora."). Il documento di progetto (sezione 6.1) prevede Groq
anche per generare le risposte locali, non solo per il routing — non era
ancora implementato.

### Added
- `backend/app/local_chat.py`: genera una risposta reale via Groq (persona
  JARVIS, contesto conversazione incluso) per richieste locali generiche
  (chiacchiere, "presentati", domande di conoscenza generale) che non
  rientrano in meteo/ricerca/ora/email/calendario
- 5 nuovi test (`test_local_chat.py`), 128/128 passanti nel modulo
  `backend/tests`

## [Unreleased] — Frontend 3D "deep space HUD" (sostituisce l'interfaccia glass/2D)

Ricostruzione completa del frontend a partire da un handoff di design
(`design_handoff_jarvis_interface/`, non versionato nel repo): un nucleo 3D
deformante via shader GLSL custom rappresenta lo stato dell'assistente, le
conversazioni orbitano attorno come corpi luminosi, la camera vola nello
spazio 3D quando se ne seleziona una.

### Added
- `frontend/js/scene.js`: motore three.js. Shader GLSL (rumore simplex,
  campo di deformazione `deform()`, nebulosa fbm ridged), tabella `STATES`
  (idle/listening/processing/responding) con smorzamento esponenziale,
  meccanica di orbita, volo camera, algoritmo anti-sovrapposizione delle
  etichette — trasferiti pressoché identici dal file di design, come
  richiesto dal suo handoff
- `frontend/index.html`/`css/styles.css` riscritti secondo i design token
  del documento di handoff (colori, tipografia Sora/JetBrains Mono, raggi,
  ombre, blur, tempi) — status bar, sidebar "Constellation", dock chat,
  pannello di dettaglio
- Dati reali al posto dei placeholder del prototipo: conversazioni da
  `GET /api/chat/conversations` (esteso con `message_count` e
  `last_target`, sezione 9.1) mappate al modello `Body` del design;
  `rel` (rilevanza) calcolata da recenza (decadimento ~72h) + frequenza
  (conteggio messaggi), non hardcoded
- Ciclo vocale/testuale collegato a eventi reali invece di `setTimeout`:
  `listening` dura quanto l'ascolto STT reale, `processing` finisce
  all'arrivo della risposta dal backend, `responding` dura quanto la
  sintesi vocale reale (Promise su `utterance.onend`)
- Quarto chip "ChatGPT" nella status bar (non presente nel design
  originale, che ne prevedeva 3): il nostro router delega anche a ChatGPT
  oltre che a Claude (ADR-0003), non solo ai tre brain del prototipo
- `three.js` r160 (build minificata, 656KB) vendorizzato in
  `frontend/js/vendor/`, stesso principio già applicato a Socket.IO
  (ADR-0001, niente CDN a runtime)

### Note
- Nessun concetto di "progetto" nello schema dati attuale: tutti i corpi
  sono "Chat" — il design distingueva chat/project, funzionalità non
  ancora esistente lato backend
- I riepiloghi nel pannello di dettaglio sono generati deterministicamente
  da dati reali (conteggio scambi, ultimo brain), non da un modello — il
  design assumeva un sommario testuale generato, non presente nel backend
- L'interfaccia conserva testo inglese per la "cromatura" HUD (status bar,
  didascalie, etichette mono) come da fedeltà "definitiva" richiesta dal
  documento di handoff; la schermata di login resta in italiano, non
  coperta dal design

## [Unreleased] — Fase 4: Frontend PWA

### Added
- PWA completa in `frontend/`: login, chat via WebSocket (con fallback REST
  se il socket non è connesso), action card per la delega Claude/ChatGPT
  (ADR-0003), upload immagini, input vocale e sintesi vocale (Web Speech
  API), pulsante per collegare Google, nuova conversazione, logout
- Tema "deep space HUD": fondale a nebulosa/stelle in CSS puro, pannelli in
  vetro sfocato, bagliori sull'accento cyan della palette di progetto
  (sezione 10.4), animazioni di ingresso messaggi, indicatore "sta
  scrivendo" animato — nessun asset esterno oltre le icone generate
  localmente
- Service worker (`frontend/sw.js`, RNF-008/RF-014): cache dell'app shell
  con strategia network-first (mai cache-first: servirebbe HTML/JS vecchi
  dopo ogni deploy finché la cache non scade)
- Icone PWA generate via script Python/Pillow (nessun asset esterno
  scaricato), manifest already pronto dalla Fase 0
- Libreria client Socket.IO vendorizzata in `frontend/js/vendor/` invece di
  caricata da CDN a runtime — coerente con lo spirito "vanilla, zero
  dipendenze esterne" di ADR-0001
- Backend serve ora anche il frontend statico dallo stesso servizio Render
  (`app/__init__.py`, `static_folder` puntato a `frontend/`) invece di un
  secondo host separato, evitando CORS e un deploy in più per un progetto
  single-user
- `/auth/callback` ora reindirizza a `/?google=connected` (o `google=error`)
  invece di restituire JSON grezzo, per una UX sensata dopo il consenso
  Google

### Fixed
- L'attributo HTML `hidden` veniva silenziosamente ignorato su più elementi
  (`.screen`, `.typing-indicator`, `.image-preview`) perché ogni regola
  d'autore che imposta `display` batte lo user-agent stylesheet a parità di
  specificità — il bug non era visibile ad occhio perché lo scroll
  automatico al focus dell'input nascondeva la schermata di login
  sovrapposta per coincidenza. Fix strutturale: `[hidden] { display: none
  !important; }` una volta per tutte, invece di patch per singola classe

### Note
- Qualità della sintesi vocale non verificabile da questo ambiente: il
  browser di test sandboxed espone zero voci di sistema (fallback
  robotico). Il codice sceglie automaticamente la voce italiana migliore
  disponibile sul dispositivo reale dell'utente (euristica su nome/motore),
  con pulsante per disattivarla — da verificare su iOS Safari ed Edge/Windows
- Verificato in locale (login, invio messaggi via WebSocket, action card,
  routing verso Claude, responsive 320px→desktop); non ancora ridistribuito
  su Render

## [Unreleased] — Fase 3: verifica end-to-end su account Google reale

### Fixed
- `create_event` (Calendar API) rifiutava con 400 Bad Request date/ore
  senza fuso orario esplicito. Ora assume UTC quando l'offset non è già
  presente nella stringa — verificato creando e cancellando un evento
  reale sul calendario dell'utente

### Verified
- Flusso OAuth completo eseguito dall'utente su Google reale (dopo aver
  aggiunto il proprio account come "test user" nella schermata di consenso,
  necessario perché l'app Google Cloud è in modalità Testing — normale e
  sufficiente per un uso personale, non serve la verifica completa di
  Google)
- Lettura email reali, lettura calendario e creazione/cancellazione evento
  reale, tutti verificati in produzione con l'account Google effettivo
  dell'utente

## [Unreleased] — Fase 3: Integrazioni (completata)

### Added
- Meteo (RF-012): `backend/app/weather.py` via OpenWeatherMap, con bias
  `,IT` per disambiguare città omonime (`q=Roma` senza qualificatore
  risolveva a Rome, NY, non Roma, Italia — verificato e corretto) e fallback
  automatico se la città non esiste in Italia (per città estere tipo
  "Parigi"). Nuovo endpoint `GET /api/weather?city=`
- OAuth Google (RF-005→RF-010, flusso 8.2): `backend/app/google_oauth.py`
  (authlib), `backend/app/token_crypto.py` (AES-256-GCM per i token, sezione
  11.3), `backend/app/google_tokens_repo.py` (persistenza cifrata +
  refresh automatico). Endpoint `GET /auth/google`, `GET /auth/callback`,
  `GET /auth/status`, `POST /auth/revoke`
- ADR-0006: `/auth/callback` non richiede la sessione app (cookie
  `SameSite=Strict` bloccato sul redirect cross-site da Google) — protetto
  invece da un cookie di stato dedicato `SameSite=Lax` con confronto a
  tempo costante
- Gmail (RF-005→RF-008): `backend/app/gmail.py` (lettura, ricerca,
  creazione bozze con threading corretto su reply, invio). Endpoint
  `GET /api/email/list`, `GET /api/email/search`, `GET /api/email/<id>`,
  `POST /api/email/draft`, `POST /api/email/send`
- Calendar (RF-009, RF-010): `backend/app/calendar_service.py` (lettura,
  creazione, cancellazione eventi). Endpoint `GET /api/calendar/events`,
  `POST /api/calendar/event`, `DELETE /api/calendar/event/<id>`
- Router: estratti nuovi campi per gli specialist "calendar_read"
  (`date_range`: today/tomorrow/week) e "calendar_create" (`event_title`,
  `event_date`, `event_time`) — la data corrente viene iniettata nel prompt
  di sistema ad ogni chiamata, altrimenti il modello non può risolvere
  riferimenti relativi come "domani" o "venerdì"
- 69 nuovi test (weather, token_crypto, google_oauth, google_tokens_repo,
  google_auth_routes, gmail, calendar_service, email_routes,
  calendar_routes) — 120/120 passanti nel modulo `backend/tests`

### Note
- Il flusso OAuth end-to-end (consenso reale su Google) richiede
  un'interazione umana nel browser che non posso simulare da qui — sarà
  verificato con l'utente contro l'istanza di produzione, l'unica con il
  redirect URI registrato su Google Cloud Console
- Gli intervalli "oggi"/"domani"/"settimana" per il calendario sono
  calcolati sull'ora del server (UTC su Render), non sul fuso orario reale
  dell'utente — lo schema del progetto non prevede un fuso orario utente
  configurabile

## [Unreleased] — Fase 3: Integrazioni (parziale — ricerca e visione)

### Added
- `backend/app/search.py`: ricerca web (RF-003, specialist "search") via
  `ddgs`, con `SearchError` esposto invece di far crashare la richiesta
- `backend/app/vision.py`: analisi immagini (RF-011, flusso 8.4) via Gemini
- `backend/app/router.py`: il router ora restituisce anche `specialist`
  quando `target == "local"` (weather/search/time/email_read/email_search/
  calendar_read/calendar_create/other) — necessario per smistare
  effettivamente le richieste locali invece del segnaposto generico della
  Fase 2
- `backend/app/chat_service.py`: dispatch reale per gli specialisti "search"
  e "time"; "weather" ed email/calendar restano segnaposto espliciti
  (mancano `OPENWEATHER_API_KEY` e le credenziali OAuth Google)
- 14 nuovi test (`test_search.py`, `test_vision.py`, aggiornamenti a
  `test_router.py`/`test_chat_service.py`) — 39/39 passanti

### Fixed
- Il documento di progetto (sezione 6.3) indicava la libreria
  `duckduckgo-search`; restituiva solo `RatelimitException` ad ogni
  chiamata. Sostituita con `ddgs`, l'erede attivamente mantenuto dello
  stesso progetto — vedi commento in `requirements.txt`
- `ddgs` dichiara di richiedere `httpx>=0.28.1`, incompatibile con
  `supabase-py 2.5.1` (`httpx<0.28`). Il pin `httpx==0.27.2` sembrava
  funzionare in locale ma falliva su Render: un `pip install -r
  requirements.txt` in un venv pulito è più severo del `pip install`
  incrementale usato per testarlo qui (`ResolutionImpossible`, verificato
  riproducendo l'errore in un venv pulito). Risolto aggiornando
  `supabase` a `2.31.0`, che non fissa più `httpx<0.28` — nessun pin
  aggiuntivo necessario, verificato con test suite completa e connessione
  Supabase reale sia nel venv pulito che nell'ambiente di sviluppo
- Gemini 1.5 Flash (sezione 6.3) non esiste più; anche `gemini-2.5-flash`
  (elencato dall'API) risulta "no longer available to new users" — l'errore
  404 stesso indicava `gemini-3.6-flash` come sostituto
- `gemini-3.6-flash` di default "pensa" prima di rispondere (~18s per
  un'immagine banale nei test), incompatibile con il requisito non
  negoziabile di 5s max sui servizi esterni. Impostato
  `thinkingConfig.thinkingBudget: 128` (il valore 0, che disabiliterebbe il
  reasoning, viene rifiutato con HTTP 400 da questo modello) — latenza
  scesa a ~1s, verificato manualmente

### Note
- Meteo (RF-012) e Gmail/Calendar (RF-005→RF-010) restano da collegare:
  servono `OPENWEATHER_API_KEY` e `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`
  (quest'ultimo per l'intero flusso OAuth, non ancora implementato)
- **Rischio noto sulla ricerca**: `ddgs` non ha un'API ufficiale, ruota fra
  più motori (DuckDuckGo, Mojeek, Bing, ...) e da Render è stato osservato
  restituire risultati completamente estranei alla query una volta su tre
  tentativi (query su "Python 3.14" → risultati sul dizionario della parola
  "origin"), oltre a timeout occasionali — riproducibile solo dall'IP di
  Render, non dalla rete locale. Non è un bug nel nostro codice: è
  l'affidabilità reale del provider di ricerca non ufficiale scelto dal
  documento originale. Se diventa un problema in uso reale, valutare un'API
  di ricerca a pagamento con free tier (es. Brave Search API) come
  alternativa più solida.

### Deployed
- Fase 3 (ricerca + visione) ridistribuita su Render e verificata: /health,
  login, specialist "time" e "search" funzionanti in produzione

## [Unreleased] — Deploy: Render

### Added
- Repository pubblicato (privato) su [github.com/BodyGate/jarvis](https://github.com/BodyGate/jarvis)
  — necessario per il deploy via Blueprint di Render
- `render.yaml`: Blueprint del servizio `jarvis-backend` (piano free,
  `rootDir: backend`, Python 3.12.7)
- Deploy live su `https://jarvis-backend-wx9x.onrender.com`, verificato
  end-to-end (health, login, chat con routing verso Claude) contro Supabase
  e Groq reali

### Fixed
- `gunicorn` senza `--bind 0.0.0.0:$PORT` ascoltava sulla porta di default,
  irraggiungibile dal proxy di Render (le richieste restavano appese senza
  risposta, TLS incluso)
- Le variabili d'ambiente segrete (`SECRET_KEY`, `SUPABASE_KEY`, ecc.),
  inserite più volte dalla dashboard Render, non risultavano mai salvate sul
  servizio (verificato interrogando `GET /v1/services/{id}/env-vars` via API
  Render: erano presenti solo le 3 variabili con valore fisso in
  `render.yaml`). Impostate con successo scrivendo direttamente via API
  (`PUT /v1/services/{id}/env-vars`) — causa della dashboard non identificata

### Note
- `GOOGLE_REDIRECT_URI` di produzione impostato su
  `https://jarvis-backend-wx9x.onrender.com/auth/callback` (Fase 3, quando
  configureremo `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`)
- Piano free Render: l'istanza va in sleep dopo inattività (richieste
  successive più lente finché non si risveglia) — comportamento atteso,
  RNF-001 lo tollera già

## [Unreleased] — Fase 2: Backend Core

### Added
- App factory Flask (`backend/app/__init__.py`): sessione con cookie
  `Secure/HttpOnly/SameSite=Strict`, timeout scorrevole 24h (ADR-0005), CORS,
  guardia globale `before_request` che nega l'accesso a qualsiasi `/api/*`
  senza sessione valida, oltre alla whitelist (`/api/health`,
  `/api/session/login`, `/api/session/status`)
- Autenticazione applicativa (`backend/app/auth.py`, ADR-0002): endpoint
  `POST /api/session/login`, `POST /api/session/logout`,
  `GET /api/session/status`; rate limit 5 tentativi/5min sul login
  (ADR-0005) contro il brute force sull'unica password
- Router di intenti (`backend/app/router.py`, RF-003): classificazione via
  Groq, con fallback a `target: local` se Groq non risponde o non è
  configurato
- Logica di dominio chat (`backend/app/chat_service.py`): crea/riusa
  conversazioni, salva messaggi, applica il pattern "copia e apri"
  (ADR-0003) per i target `claude`/`chatgpt`
- Endpoint REST chat (`backend/app/chat_routes.py`): `POST /api/chat/message`
  (rate limit 15/min, ADR-0005), `GET /api/chat/history`,
  `POST /api/chat/clear`, `GET /api/chat/conversations`
- WebSocket (`backend/app/sockets.py`, Flask-SocketIO): `connect` verifica la
  sessione, `join_conversation`, `send_message`/`message`/`typing`;
  `action_triggered` riconosciuto ma non eseguito (l'esecuzione delle azioni
  richiede le integrazioni della Fase 3)
- `backend/run.py`: entrypoint per lo sviluppo locale
- ADR-0005: valori di timeout sessione e soglie di rate limiting (non
  specificati nel documento di progetto originale)
- 20 nuovi test (`backend/tests/test_auth.py`, `test_router.py`,
  `test_chat_service.py`), tutti passanti (24/24 nel modulo `backend/tests`)

### Fixed
- Il documento di progetto (sezione 6.3) prevedeva Llama 3.3 70B su Groq, ma
  il modello è stato rimosso dal catalogo Groq nel frattempo. Sostituito con
  `openai/gpt-oss-20b` (verificato disponibile via `GET /openai/v1/models` il
  2026-08-20) — vedi commento in `backend/app/router.py`

### Verified
- Flusso end-to-end testato manualmente contro Supabase e Groq reali: login
  (password corretta/errata), classificazione intento (meteo → local, coding
  → claude, email → local), persistenza conversazioni/messaggi, delega
  "copia e apri" con prompt di contesto, logout con invalidazione lato
  client, accesso negato senza sessione
- Dati di test ripuliti da Supabase al termine della verifica manuale

### Note
- Deploy su Koyeb rimandato: non abbiamo ancora le credenziali dell'account
  Koyeb. L'app è verificata solo in locale (`python backend/run.py`)
- L'esecuzione reale degli specialisti locali (meteo, ricerca, email,
  calendario) non è collegata: il router classifica correttamente ma
  `target: local` produce per ora un messaggio segnaposto esplicito, non un
  risultato inventato — arriva con le integrazioni della Fase 3
- Il logout è valido solo lato client (sessione stateless firmata, non c'è
  una revoca lato server): un cookie di sessione copiato prima del logout
  resta valido fino alla scadenza naturale (24h). Rischio basso per un'app
  single-user, ma va tenuto presente

## [Unreleased] — Fase 1: Database (eseguito su Supabase)

### Added
- `backend/db/migrations/0001_initial_schema.sql`: schema completo (6 tabelle,
  indici, trigger `updated_at`) da documento di progetto sezione 7.1, con RLS
  deny-by-default su ogni tabella
- `backend/db/README.md`: istruzioni di esecuzione e checklist di verifica
- ADR-0004: RLS deny-by-default invece di policy `user_id = auth.uid()`
  (incompatibile con l'auth applicativa scelta in ADR-0002)
- `backend/.env` popolato con le credenziali del progetto Supabase reale
  (non committato, presente in `.gitignore`)

### Verified
- Migrazione eseguita con successo contro il progetto Supabase reale
  (2026-08-20), via connessione diretta Python/psycopg2 (nessun `psql`
  disponibile nell'ambiente)
- Checklist Fase 1 completata: 6 tabelle create, RLS attiva su tutte,
  connessione testata con `supabase-py` e service_role key

### Note
- L'host di connessione diretta `db.<ref>.supabase.co` è IPv6-only e non
  risolvibile da reti solo-IPv4; usata la connection string del pooler
  (`aws-0-eu-central-1.pooler.supabase.com`, user `postgres.<ref>`) — vedi
  `backend/db/README.md` per i dettagli
- `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` e `OPENWEATHER_API_KEY` restano
  da fornire per le fasi successive (OAuth Gmail/Calendar, meteo)

## [Unreleased] — Fase 0: Preparazione ambiente

### Added
- Struttura repository iniziale: `backend/`, `frontend/`, `docs/adr/`
- `.gitignore` con esclusione di `.env` e segreti
- Scheletro backend Flask: `app/config.py` (caricamento tipizzato delle variabili
  d'ambiente) con test unitario associato
- Scheletro frontend PWA: `index.html` (shell, non ancora la chat UI),
  `manifest.json`, palette colori (dark mode) da documento di progetto sezione 10.4
  — l'interfaccia chat completa (bolle messaggio, Socket.IO, Web Speech API,
  action card) è scope di Fase 4
- `.env.example` con tutte le variabili richieste dalle integrazioni previste
  (Groq, Gemini, OpenWeatherMap, Google OAuth, Supabase, sessione app)
- ADR-0001: frontend vanilla JS invece di Next.js/TypeScript/Tailwind
- ADR-0002: autenticazione applicativa con password singola + sessione Flask
- ADR-0003: delega a Claude/ChatGPT tramite pattern "copia e apri" invece del
  deep link `?q=` previsto dal documento originale (requisito non negoziabile)

### Note
- Fase 0 richiede anche la creazione manuale di account (Koyeb, Supabase, Groq,
  Google Cloud Console) e l'ottenimento delle relative API key — attività che
  l'utente deve completare nel browser; non eseguibili da questo ambiente.
- Fase 1 (schema DB su Supabase) non è stata eseguita: in attesa di credenziali
  reali e di conferma esplicita, come da direttive di sviluppo (impatto su dati
  reali).
