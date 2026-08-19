# Database — migrazioni

Script SQL per lo schema Supabase PostgreSQL di JARVIS, applicati in ordine
numerico. Vedi `docs/adr/0004-rls-deny-by-default.md` per la scelta sulla Row
Level Security.

## Come eseguire

Opzione A — Supabase SQL Editor (consigliata la prima volta):
1. Apri il progetto Supabase → SQL Editor
2. Incolla il contenuto di `migrations/0001_initial_schema.sql`
3. Esegui

Opzione B — `psql`, con `DATABASE_URL` da `.env`:
```
psql "$DATABASE_URL" -f backend/db/migrations/0001_initial_schema.sql
```

Gli statement sono idempotenti (`IF NOT EXISTS` / `CREATE OR REPLACE`): rieseguire
lo script su uno schema già applicato non genera errori né duplica oggetti.

## Verifica post-esecuzione (checklist Fase 1)

- [x] Le 6 tabelle esistono: `conversations`, `messages`, `google_tokens`,
      `user_facts`, `email_cache`, `calendar_cache`
- [x] RLS risulta abilitata su tutte e 6 (Supabase → Table Editor → icona
      scudo, oppure `SELECT relname, relrowsecurity FROM pg_class WHERE
      relnamespace = 'public'::regnamespace;`)
- [x] Connessione testata da Python con `SUPABASE_URL` + `SUPABASE_KEY`
      (service_role key, non `anon`) da `.env`

## Stato

Eseguito con successo contro il progetto Supabase reale (2026-08-20). Nota
di connessione: l'host diretto `db.<ref>.supabase.co` è IPv6-only e non
raggiungibile da reti solo-IPv4 — usare la connection string del **pooler**
(Project Settings → Database → Connect → Session/Transaction pooler),
formato `postgres.<ref>@aws-0-<regione>.pooler.supabase.com`, con user
`postgres.<ref>` (non solo `postgres`).
