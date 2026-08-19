# JARVIS

Assistente personale AI multi-cervello. Un router (Groq/Llama 3.3 70B) classifica
l'intento dell'utente e smista a: risposta locale rapida, Gemini (visione), o delega
a Claude/ChatGPT via browser per coding/reasoning profondo.

Architettura: **GOLD (Cloud-Native)** — vedi `docs/JARVIS_Progetto_Completo_v2.pdf`
per il documento di progetto completo (requisiti, schema dati, API, wireframe).

## Stack

- **Backend**: Python 3.11+ / Flask 3.x / Flask-SocketIO / SQLAlchemy 2.x / Supabase (PostgreSQL)
- **Frontend**: PWA — HTML5 / CSS3 / JavaScript vanilla, zero framework (ADR-0001)
- **Hosting**: Koyeb (backend), Supabase (database)
- **AI**: Groq (router + risposte), Gemini 1.5 Flash (visione + fallback)
- **Costo aggiuntivo**: 0€/mese (solo tier gratuiti + abbonamenti già attivi)

## Struttura repository

```
backend/    Flask app, config, test
frontend/   PWA statica (HTML/CSS/JS, manifest, service worker)
docs/adr/   Architecture Decision Records
```

## Setup locale

1. `cd backend && cp .env.example .env` e compila le variabili (vedi commenti nel file)
2. `pip install -r backend/requirements.txt`
3. `pytest backend/tests`

Le fasi di implementazione, i requisiti e lo schema dati completo sono nel documento
di progetto allegato. Le decisioni non ovvie sono tracciate in `docs/adr/`.
