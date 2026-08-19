# ADR-0001: Frontend in vanilla HTML/CSS/JS invece di Next.js/TypeScript/Tailwind

## Stato
Accettato — 2026-08-20

## Contesto
Le direttive di sviluppo del progetto indicano come stack frontend "Next.js +
TypeScript + Tailwind". Il documento di progetto originale (v2.0, sezione 6.2 e
decisione D13 del Decision Log) specifica invece esplicitamente HTML5/CSS3/JavaScript
vanilla, senza framework, motivato da "semplicità, zero bundle": zero dipendenze,
zero build step, coerente con i wireframe e la palette colori già definiti nella
sezione 10 del documento.

I due riferimenti sono in conflitto diretto e non possono coesistere. È stata posta
la domanda esplicitamente all'utente.

## Decisione
Si segue il documento di progetto originale: frontend PWA in HTML/CSS/JavaScript
vanilla, senza framework né build step.

## Motivazione
- JARVIS è un'app PWA single-user (assistente personale), non un prodotto con team
  frontend dedicato: la superficie UI è piccola (chat, bolle messaggio, action card,
  input) e non giustifica la complessità di un framework component-based.
- Il documento originale ha già fissato wireframe, palette (`--bg-primary`, `--accent`,
  ecc.) e struttura DOM assumendo vanilla JS — riscriverli in Next.js richiederebbe
  lavoro aggiuntivo non richiesto dal requisito.
- Zero build step riduce la superficie di configurazione (nessun bundler, nessun
  tsconfig, nessun deploy step aggiuntivo su Koyeb) mantenendo il vincolo di
  costo/complessità zero del progetto.
- Il vincolo di type safety (requisito non negoziabile #5) si applica comunque lato
  backend (type hints Python); lato frontend si compensa con JSDoc dove la logica
  non è ovvia.

## Conseguenze
- Più codice DOM manuale rispetto a un framework component-based (coerente con D13
  del documento originale, che accetta questo trade-off).
- Nessuna astrazione a componenti riutilizzabili: le action card, le bolle messaggio
  ecc. sono funzioni JS che generano markup, non componenti.
- Se in futuro il progetto scalasse a un team frontend o a una UI significativamente
  più complessa, questa decisione andrebbe rivista.
