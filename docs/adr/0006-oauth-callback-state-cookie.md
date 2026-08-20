# ADR-0006: Cookie di stato dedicato per `/auth/callback` invece della sessione app

## Stato
Accettato — 2026-08-20

## Contesto
ADR-0002 impone che ogni endpoint API richieda una sessione JARVIS valida,
eccetto `/api/health` e le route di login. Il flusso OAuth Google (RF-005→
RF-010) introduce però `GET /auth/callback`: Google reindirizza il browser
dell'utente a questo endpoint dopo il consenso, come **navigazione
cross-site di primo livello** (il referrer è `accounts.google.com`).

Il cookie di sessione JARVIS ha `SameSite=Strict` (ADR-0002, requisito di
sicurezza). Per specifica, un cookie `Strict` **non viene inviato** su una
navigazione cross-site come questa — è esattamente il caso d'uso per cui
`SameSite=Strict` esiste. Il risultato pratico: se `/auth/callback` richiede
`session.get("authenticated")` come tutti gli altri endpoint, il redirect di
Google arriverebbe sempre senza sessione valida, rompendo il flusso OAuth
per design.

## Decisione
`/auth/callback` non usa la sessione app per l'autenticazione. Al posto:
1. `GET /auth/google` (questo endpoint sì richiede la sessione app normale,
   essendo raggiunto da un click/redirect same-site dalla UI di JARVIS)
   genera lo `state` OAuth e lo salva in un cookie dedicato `oauth_state`
   (`HttpOnly`, `Secure` in produzione, `SameSite=Lax`, scadenza 10 minuti).
   `SameSite=Lax` — a differenza di `Strict` — viene inviato su navigazioni
   cross-site di primo livello via GET, quindi sopravvive al redirect di
   Google.
2. `GET /auth/callback` confronta lo `state` nella query string con quello
   nel cookie `oauth_state` (confronto a tempo costante), poi lo elimina.
   Se non corrispondono (o il cookie manca/è scaduto), la richiesta viene
   rifiutata. Solo dopo la verifica si procede allo scambio del codice.

Dato che JARVIS è single-user (`user_id = 'default'` ovunque, ADR-0002), non
c'è ambiguità su "di chi" siano i token salvati: l'unico rischio reale non è
confondere utenti diversi, ma un CSRF che porti l'app a salvare le
credenziali Google di un attaccante. Il cookie `oauth_state` con confronto
a tempo costante mitiga esattamente questo.

## Motivazione
- `SameSite=Lax` sul solo cookie di stato OAuth (durata 10 minuti, nessun
  dato sensibile al suo interno oltre a un valore casuale) non indebolisce
  la protezione `Strict` del cookie di sessione principale, che resta
  invariata su tutti gli altri endpoint.
- Alternative scartate: cambiare il cookie di sessione principale a `Lax`
  (indebolirebbe la protezione CSRF su *tutta* l'app per un solo endpoint);
  usare un parametro `state` senza validazione lato server (nessuna
  protezione CSRF reale).

## Conseguenze
- `/auth/callback` va aggiunto alla whitelist di endpoint pubblici in
  `app/__init__.py`, con un commento che rimanda a questo ADR — un lettore
  futuro non deve leggerlo come "endpoint dimenticato per errore".
- Se in futuro JARVIS diventa multi-utente, questa decisione va rivista:
  servirà legare esplicitamente i token salvati all'utente che ha avviato
  il flusso, non solo validare lo `state`.
