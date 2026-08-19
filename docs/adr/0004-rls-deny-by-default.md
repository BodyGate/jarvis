# ADR-0004: Row Level Security deny-by-default invece di policy basate su user_id

## Stato
Accettato — 2026-08-20

## Contesto
Il documento di progetto (sezione 11.3) richiede "RLS Supabase: Ogni query
filtrata per `user_id`", assumendo implicitamente policy Postgres del tipo
`USING (user_id = auth.uid())`. Quel pattern presuppone che i client si
autentichino direttamente con Supabase Auth e che `auth.uid()` sia popolato dal
JWT della richiesta.

Con ADR-0002 abbiamo scelto un'autenticazione applicativa (password singola +
sessione Flask), non Supabase Auth. Il backend Flask è l'unico client che parla
con Supabase, usando la **service_role key**, che per design di Supabase bypassa
sempre RLS — quindi una policy `user_id = auth.uid()` non avrebbe alcun effetto
sulle query del backend (che restano comunque filtrate per `user_id` a livello
applicativo, nel codice Python) e darebbe una falsa sensazione di protezione a
livello database.

## Decisione
RLS abilitata su tutte le tabelle, **senza policy permissive** per i ruoli
`anon` e `authenticated` (quelli usati dall'API REST auto-generata di Supabase
via PostgREST con la chiave `anon`/pubblica). L'isolamento per `user_id` resta
responsabilità del codice applicativo (ogni query del backend filtra
esplicitamente per `user_id`), non del database.

## Motivazione
- Il rischio reale in questa architettura non è "un utente legge i dati di un
  altro utente" (siamo single-user, `user_id = 'default'` ovunque), ma "qualcuno
  con la chiave `anon` di Supabase legge le tabelle direttamente via REST API",
  bypassando completamente il backend Flask e la sua autenticazione. RLS
  deny-by-default chiude esattamente questo buco.
- Aggiungere una policy `user_id = auth.uid()` che il service_role bypassa
  comunque sarebbe sicurezza-teatro: darebbe l'impressione di protezione senza
  fornirla, contraddicendo lo standard "Platinum" del progetto.

## Conseguenze
- Se in futuro il frontend dovesse parlare direttamente con Supabase (bypassando
  Flask) con la chiave `anon`, questa decisione andrebbe rivista introducendo
  policy reali basate su Supabase Auth.
- Va usata sempre la `service_role` key lato backend (mai la `anon` key), e la
  `service_role` key non deve mai essere esposta al frontend — è equivalente a
  un segreto di root sul database.
