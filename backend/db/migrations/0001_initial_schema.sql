-- Migration 0001: schema iniziale JARVIS
-- Fonte: documento di progetto v2.0, sezione 7.1 (Schema Relazionale).
-- Target: Supabase PostgreSQL.
--
-- Deviazioni rispetto al documento originale, giustificate in docs/adr/0004:
--   1. Row Level Security abilitata su tutte le tabelle SENZA policy permissive
--      (deny-by-default per i ruoli `anon`/`authenticated` esposti da PostgREST).
--      Il backend Flask è l'unico client e usa la service_role key, che bypassa
--      RLS by design in Supabase: questo impedisce che le tabelle siano leggibili
--      direttamente via API REST auto-generata di Supabase con la chiave anon.
--   2. Trigger `set_updated_at` su `conversations` e `google_tokens` per
--      mantenere coerente la colonna `updated_at` ad ogni UPDATE (il documento
--      definisce la colonna ma non un meccanismo che la aggiorni).
--   3. Statement idempotenti (IF NOT EXISTS / CREATE OR REPLACE) per permettere
--      di rieseguire lo script in sicurezza.
--
-- Esecuzione: incolla nel SQL Editor di Supabase, oppure
--   psql "$DATABASE_URL" -f backend/db/migrations/0001_initial_schema.sql
-- Non ancora eseguito contro un progetto Supabase reale: in attesa di
-- credenziali e conferma esplicita (Fase 1).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Funzione di supporto per aggiornare updated_at automaticamente.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Tabella: conversations
-- Raggruppa i thread di chat
-- ============================================================================
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL DEFAULT 'default',
    title TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE TRIGGER trg_conversations_updated_at
BEFORE UPDATE ON conversations
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Tabella: messages
-- Ogni messaggio della chat
-- ============================================================================
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    intent TEXT,              -- intento classificato dal router
    target TEXT,               -- 'local', 'chatgpt', 'claude', 'gemini'
    source TEXT,                -- chi ha generato la risposta
    action_type TEXT,           -- 'speak', 'open_external', 'draft_email'
    action_payload JSONB,      -- dati azione (URL, prompt, bozza)
    has_image BOOLEAN DEFAULT FALSE,
    image_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id, created_at);

ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Tabella: google_tokens
-- Credenziali OAuth Google (criptate AES-256-GCM lato applicazione prima
-- dell'INSERT — vedi ADR-0002 e requisito non negoziabile #4: nessun segreto
-- in chiaro. Le colonne sono TEXT perché contengono il testo cifrato, non i
-- token in chiaro).
-- ============================================================================
CREATE TABLE IF NOT EXISTS google_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL DEFAULT 'default',
    provider TEXT NOT NULL DEFAULT 'google',
    access_token TEXT NOT NULL,   -- criptato AES-256-GCM
    refresh_token TEXT NOT NULL,  -- criptato AES-256-GCM
    expires_at TIMESTAMPTZ,
    scopes TEXT[],                 -- ['gmail.readonly', 'calendar']
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE TRIGGER trg_google_tokens_updated_at
BEFORE UPDATE ON google_tokens
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE google_tokens ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Tabella: user_facts
-- Memoria a lungo termine su preferenze e fatti dell'utente (RF-013)
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL DEFAULT 'default',
    category TEXT,             -- 'preference', 'contact', 'habit', 'work'
    fact TEXT NOT NULL,        -- "Odia il caffè", "Marco è il capo"
    confidence FLOAT DEFAULT 1.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    -- ON DELETE SET NULL (non la CASCADE di default): un fatto di memoria a
    -- lungo termine deve sopravvivere alla cancellazione della conversazione
    -- da cui è stato estratto — perde solo il riferimento alla fonte. Senza
    -- questo, cancellare una conversazione con fatti associati falliva con
    -- un 500 (violazione FK su messages, bug in produzione).
    source_message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_facts_category
    ON user_facts(user_id, category);

-- Corregge il vincolo per i database creati prima di questa modifica
-- (CREATE TABLE IF NOT EXISTS non lo applicherebbe retroattivamente).
ALTER TABLE user_facts DROP CONSTRAINT IF EXISTS user_facts_source_message_id_fkey;
ALTER TABLE user_facts ADD CONSTRAINT user_facts_source_message_id_fkey
    FOREIGN KEY (source_message_id) REFERENCES messages(id) ON DELETE SET NULL;

ALTER TABLE user_facts ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Tabella: email_cache
-- Cache metadati email per risposta rapida (RF-005, RF-006)
-- ============================================================================
CREATE TABLE IF NOT EXISTS email_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL DEFAULT 'default',
    gmail_message_id TEXT NOT NULL UNIQUE,
    thread_id TEXT,
    from_address TEXT,
    from_name TEXT,
    subject TEXT,
    snippet TEXT,
    body_preview TEXT,
    received_at TIMESTAMPTZ,
    is_read BOOLEAN DEFAULT FALSE,
    labels TEXT[],
    cached_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_email_cache_received
    ON email_cache(user_id, received_at DESC);

ALTER TABLE email_cache ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Tabella: calendar_cache
-- Cache eventi calendario (RF-009, RF-010)
-- ============================================================================
CREATE TABLE IF NOT EXISTS calendar_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL DEFAULT 'default',
    google_event_id TEXT NOT NULL UNIQUE,
    summary TEXT,
    description TEXT,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    location TEXT,
    attendees JSONB,
    status TEXT,
    cached_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_calendar_cache_start
    ON calendar_cache(user_id, start_time);

ALTER TABLE calendar_cache ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Tabella: device_agents
-- Dispositivi locali collegabili (agente companion sul PC/telefono) a cui
-- JARVIS può inviare comandi da una whitelist fissa lato server e lato
-- agente (mai comandi arbitrari) — richiesta esplicita dell'utente: "voglio
-- che si colleghi al dispositivo dove è installato per poterlo gestire".
-- token_hash è l'hash del token per-dispositivo (werkzeug
-- generate_password_hash, stesso meccanismo di APP_PASSWORD_HASH): il
-- token in chiaro viene mostrato una sola volta alla registrazione e non è
-- mai persistito.
-- ============================================================================
CREATE TABLE IF NOT EXISTS device_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_device_agents_user
    ON device_agents(user_id);

ALTER TABLE device_agents ENABLE ROW LEVEL SECURITY;
