-- Cloudflare D1 schema for Dynamic URL Hydration.
-- Apply with:  npx wrangler d1 migrations apply urlovingly-invites --remote
-- (use --local for the wrangler dev database)

-- One row per celebration. Shared details live here so they are stored once.
CREATE TABLE IF NOT EXISTS couples (
    couple_slug  TEXT PRIMARY KEY
                 CHECK (length(couple_slug) BETWEEN 1 AND 100 AND couple_slug NOT GLOB '*[^a-z0-9-]*'),
    couple_names TEXT NOT NULL,
    event_date   TEXT,
    venue        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per guest or family. (couple_slug, guest_slug) is the public URL key:
--   /<couple_slug>/to/<guest_slug>
CREATE TABLE IF NOT EXISTS guests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_slug TEXT NOT NULL REFERENCES couples(couple_slug) ON DELETE CASCADE,
    guest_slug  TEXT NOT NULL
                CHECK (length(guest_slug) BETWEEN 1 AND 100 AND guest_slug NOT GLOB '*[^a-z0-9-]*'),
    guest_name  TEXT NOT NULL,
    custom_note TEXT,
    template_id TEXT NOT NULL DEFAULT 'base'
                CHECK (length(template_id) BETWEEN 1 AND 60 AND template_id NOT GLOB '*[^a-z0-9-]*'),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (couple_slug, guest_slug)
);
