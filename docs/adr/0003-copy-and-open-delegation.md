# ADR-0003: Delega a Claude/ChatGPT con pattern "copia e apri" invece del deep link `?q=`

## Stato
Accettato — 2026-08-20

## Contesto
Il documento di progetto originale (sezioni 8.5 e 9, decisione D4 del Decision Log)
descrive la delega a Claude/ChatGPT tramite deep link con parametro URL, es.
`https://claude.ai/new?q=[prompt URL-encoded]`, aperto dal client dopo che l'utente
clicca "Apri Claude".

Le direttive di sviluppo impongono invece esplicitamente di **non** usare questo
meccanismo: "Delega a Claude/ChatGPT via pattern 'copia e apri', MAI tramite
parametro URL `?q=` o simili (verificato non affidabile)". Questo è un requisito
non negoziabile, non una preferenza: il documento originale va corretto, non seguito
alla lettera.

## Decisione
Il flusso di delega diventa:
1. Al tap dell'utente su "Apri Claude" / "Apri ChatGPT", il client JS copia il
   prompt completo negli appunti (`navigator.clipboard.writeText`) **dentro il
   gesto di tap** (requisito per i permessi clipboard su iOS Safari — una chiamata
   asincrona fuori dal gesto utente viene bloccata).
2. Subito dopo, apre una nuova scheda verso l'URL semplice e senza parametri
   (`https://claude.ai/new`, `https://chatgpt.com/`).
3. L'utente incolla manualmente il prompt nella chat già aperta.

L'`action_payload` salvato su `messages` (schema esistente, campo JSONB) contiene
comunque `type: "copy_and_open"`, `target`, `url` (senza query string) e `prompt`
in chiaro, così la action card può essere ri-renderizzata e il prompt ricopiato
anche da cronologia.

## Motivazione
- Il parametro `?q=` su claude.ai/chatgpt.com non è un'API pubblica documentata e
  supportata: il comportamento non è garantito e può cambiare o essere rimosso senza
  preavviso, rompendo silenziosamente la funzionalità di delega (requisito RF-003 e
  obiettivo O8, entrambi critici per il progetto).
- Il pattern "copia e apri" dipende solo dalla Clipboard API, uno standard web
  stabile e supportato da Safari iOS.

## Conseguenze
- Un passaggio manuale in più per l'utente (incollare) rispetto al deep link
  ideale — accettato come trade-off esplicito per l'affidabilità.
- Se in futuro Anthropic/OpenAI pubblicano un meccanismo di prefill ufficiale e
  documentato, questa decisione va rivista.
- Il documento di progetto originale (sezione 8.5, 9, D4) resta come riferimento
  storico ma non descrive più il comportamento implementato: qualsiasi lettura
  futura del documento va incrociata con questo ADR.
