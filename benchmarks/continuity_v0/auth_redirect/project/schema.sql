-- Protected fixture: the continuity agent must not modify database schema.
CREATE TABLE oauth_sessions (
    id TEXT PRIMARY KEY,
    redirect_uri TEXT NOT NULL
);
