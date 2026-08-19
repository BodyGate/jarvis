# ADR-0002: Autenticazione applicativa con password singola + sessione Flask

## Stato
Accettato — 2026-08-20

## Contesto
Il documento di progetto originale non definisce un meccanismo di login per l'app
JARVIS in sé: descrive solo l'OAuth 2.0 Google, che serve esclusivamente ad
autorizzare l'accesso a Gmail/Calendar, non a proteggere l'accesso all'app. Lo
schema dati usa `user_id TEXT DEFAULT 'default'`, confermando un design single-user
senza account multipli.

Le direttive di sviluppo impongono però, come requisito non negoziabile, che
"nessun endpoint [sia] accessibile senza sessione valida, anche in fase di
sviluppo", da implementare dentro la Fase 2 (Backend Core), non rimandata.
Questo è un gap del documento originale che va colmato con una decisione esplicita.

## Decisione
Autenticazione con **password singola** (definita dall'utente in variabile
d'ambiente, memorizzata come hash — non in chiaro) più **cookie di sessione
firmato da Flask** (`Flask` `session`, `SECRET_KEY` da variabile d'ambiente).
Ogni endpoint API (eccetto `/api/health` e le route di login) richiede una
sessione valida; il WebSocket verifica la sessione alla connessione.

Alternative valutate e scartate in questa fase:
- **Supabase Auth (email+password)**: più solido e pronto per multi-utente futuro,
  ma introduce complessità di setup (gestione utenti, conferma email, ecc.) non
  giustificata per un assistente a singolo utente.
- **Login con Google OAuth riusato come identità app**: eviterebbe un secondo
  meccanismo di auth, ma legherebbe l'accesso all'intera app alla disponibilità e
  configurazione dell'OAuth Google, complicando debug e sviluppo locale.

## Motivazione
- Coerente con lo scope single-user del documento originale (`user_id = 'default'`).
- Setup minimo, zero costi aggiuntivi, nessuna dipendenza da servizi esterni per il
  solo login dell'app.
- Riduce la superficie d'attacco: anche prima di collegare Google/Gmail/Calendar,
  l'app non è mai raggiungibile senza autenticarsi.
- Non preclude una migrazione futura a Supabase Auth se il progetto scala a
  multi-tenancy (scenario "più utenti (famiglia)" già previsto nella roadmap di
  scaling del documento originale, sezione 16.2).

## Conseguenze
- Un solo segreto (`APP_PASSWORD_HASH`) da ruotare manualmente in caso di
  compromissione; non c'è un flusso di recupero password (non necessario per un
  singolo utente che controlla le variabili d'ambiente del deploy).
- La sessione Flask deve avere `Secure`, `HttpOnly`, `SameSite=Strict` e timeout
  esplicito per rispettare RNF-005 (sicurezza) e la mitigazione "accesso fisico al
  dispositivo" del modello di minaccia (sezione 11.1 del documento).
- Se in futuro serve multi-utente, questa decisione va rivista verso Supabase Auth.
