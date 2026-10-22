-- Sample data for local testing:  npm run db:seed:local
INSERT OR REPLACE INTO couples (couple_slug, couple_names, event_date, venue)
VALUES ('aarav-and-priya', 'Aarav & Priya', 'December 25, 2026', 'The Grand Ballroom, Taj Lands End, Mumbai');

INSERT OR REPLACE INTO guests (couple_slug, guest_slug, guest_name, custom_note, template_id)
VALUES
  ('aarav-and-priya', 'rahul-sharma-and-family', 'Rahul Sharma & Family',
   'You have been part of every chapter of our story. Please bless us with your presence.', 'base'),
  ('aarav-and-priya', 'meera', 'Meera', NULL, 'base');
