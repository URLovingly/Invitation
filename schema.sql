CREATE TABLE Sessions (
    token TEXT PRIMARY KEY, 
    email TEXT NOT NULL
);

CREATE TABLE Invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    host_email TEXT NOT NULL, 
    guest_name TEXT NOT NULL, 
    template TEXT NOT NULL,
    invite_url TEXT NOT NULL, 
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);