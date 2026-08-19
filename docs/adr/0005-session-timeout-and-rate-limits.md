# ADR-0005: Valori di timeout sessione e soglie di rate limiting

## Stato
Accettato — 2026-08-20

## Contesto
Il documento di progetto impone due requisiti non negoziabili senza però
darne il valore: un timeout di sessione (sezione 11.1, mitigazione "accesso
fisico al dispositivo") e un rate limiting lato server (sezione 11.3, punto
8, "per prevenire abuso API esterne"). Nessuna delle due voci compare nello
stack tecnologico (sezione 6.1), quindi manca anche la scelta di libreria per
il rate limiting.

## Decisione
- **Timeout di sessione**: cookie di sessione Flask con scadenza scorrevole
  di 24 ore (`PERMANENT_SESSION_LIFETIME`), rinnovata ad ogni richiesta
  autenticata (`SESSION_REFRESH_EACH_REQUEST=True`). Compromesso tra il
  requisito di sicurezza e l'uso pratico da parte di un singolo utente su più
  dispositivi (iPhone, PC, iPad) nell'arco della giornata.
- **Rate limiting**: `Flask-Limiter` (nuova dipendenza, aggiunta a
  `requirements.txt`), con due soglie distinte:
  - `POST /api/auth/login`: 5 tentativi / 5 minuti per IP, per rallentare
    tentativi di forza bruta sull'unica password applicativa (ADR-0002).
  - `POST /api/chat/message`: 15 richieste/minuto per sessione, sotto il
    limite di 20 richieste/minuto imposto da Groq lato server (sezione 6.3)
    per evitare che l'app stessa esaurisca la quota Groq con un solo utente
    "distratto" (es. tab multiple, retry automatici lato client).

## Motivazione
- 24 ore evita richieste di re-login multiple volte al giorno passando da
  iPhone a PC, restando comunque un tempo finito (a differenza di una
  sessione senza scadenza).
- La soglia di login protegge l'unico segreto applicativo senza introdurre
  un sistema di lockout complesso (non serve per un solo utente).
- La soglia sui messaggi chat è dimensionata sul vincolo esterno più
  stringente dello stack (Groq, 20 req/min), non su un numero arbitrario.
- Flask-Limiter è lo standard de facto per Flask, minimizza codice custom su
  un requisito di sicurezza (dove i bug fatti in casa sono rischiosi).

## Conseguenze
- Se in futuro il progetto diventa multi-utente (roadmap sezione 16.2), le
  soglie di rate limiting vanno riviste per persona, non per processo.
- Se Groq aumenta/riduce il rate limit del tier gratuito, la soglia su
  `/api/chat/message` va aggiornata di conseguenza.
- Questi valori non sono nel documento di progetto originale: qualsiasi
  lettura futura del documento va incrociata con questo ADR.
