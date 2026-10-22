-- URLovingly database schema (SQLite). Timestamps are ISO-8601 UTC strings.

CREATE TABLE IF NOT EXISTS plans (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    price_paise   INTEGER NOT NULL CHECK (price_paise >= 0),
    link_limit    INTEGER NOT NULL,
    hosting_days  INTEGER NOT NULL,
    whatsapp_generator  INTEGER NOT NULL DEFAULT 0,
    rsvp_dashboard      INTEGER NOT NULL DEFAULT 0,
    multi_day_routing   INTEGER NOT NULL DEFAULT 0,
    upi_shagun          INTEGER NOT NULL DEFAULT 0,
    custom_audio        INTEGER NOT NULL DEFAULT 0,
    sort_order    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL DEFAULT '',
    picture       TEXT NOT NULL DEFAULT '',
    google_sub    TEXT,
    created_at    TEXT NOT NULL,
    last_login_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

-- One row per celebration. The plan attached to an event controls every feature the customer sees.
CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id    TEXT NOT NULL UNIQUE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id      TEXT NOT NULL REFERENCES plans(id),
    title        TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('pending_payment', 'active')),
    is_trial     INTEGER NOT NULL DEFAULT 0,
    upi_id       TEXT NOT NULL DEFAULT '',
    upi_name     TEXT NOT NULL DEFAULT '',
    audio_file   TEXT NOT NULL DEFAULT '',
    audio_type   TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    activated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id);

CREATE TABLE IF NOT EXISTS payments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id            INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    plan_id             TEXT NOT NULL REFERENCES plans(id),
    provider            TEXT NOT NULL,
    provider_order_id   TEXT NOT NULL UNIQUE,
    provider_payment_id TEXT,
    amount_paise        INTEGER NOT NULL CHECK (amount_paise > 0),
    currency            TEXT NOT NULL DEFAULT 'INR',
    status              TEXT NOT NULL CHECK (status IN ('created', 'paid')),
    created_at          TEXT NOT NULL,
    paid_at             TEXT
);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);

CREATE TABLE IF NOT EXISTS invites (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id        TEXT NOT NULL UNIQUE,
    event_id         INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    host_email       TEXT NOT NULL,
    guest_name       TEXT NOT NULL,
    guest_phone      TEXT NOT NULL DEFAULT '',
    couple_names     TEXT NOT NULL,
    event_type       TEXT NOT NULL DEFAULT 'Wedding',
    couple_slug      TEXT NOT NULL,
    guest_slug       TEXT NOT NULL,
    template         TEXT NOT NULL,
    allowed_ceremonies TEXT NOT NULL DEFAULT '[]',
    html             TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    expires_at       TEXT NOT NULL,
    UNIQUE (couple_slug, guest_slug)
);
CREATE INDEX IF NOT EXISTS idx_invites_event ON invites(event_id);

CREATE TABLE IF NOT EXISTS rsvps (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    invite_id  INTEGER NOT NULL UNIQUE REFERENCES invites(id) ON DELETE CASCADE,
    response   TEXT NOT NULL CHECK (response IN ('yes', 'no', 'maybe')),
    guests     INTEGER NOT NULL DEFAULT 1,
    message    TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);