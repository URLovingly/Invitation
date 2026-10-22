// Pure helpers: no network, no globals, so they are easy to unit test.

const DEFAULT_NOTE = "We can't wait to celebrate this special day with you!";
const DEFAULT_DATE = 'Details to follow';
const DEFAULT_VENUE = 'Venue to be announced';

const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

/** Escape text for safe use in HTML content and quoted attributes. */
export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => HTML_ESCAPES[char]);
}

/** Map a D1 row to the placeholder values used by the templates. */
export function buildValues(invitation) {
  return {
    GUEST_NAME: invitation.guest_name,
    COUPLE_NAMES: invitation.couple_names,
    CUSTOM_NOTE: invitation.custom_note?.trim() || DEFAULT_NOTE,
    EVENT_DATE: invitation.event_date?.trim() || DEFAULT_DATE,
    VENUE: invitation.venue?.trim() || DEFAULT_VENUE,
  };
}

const PLACEHOLDER = /\{\{\s*([A-Z_]+)\s*\}\}/g;

/**
 * Replace every {{PLACEHOLDER}} in one pass.
 * Values are HTML-escaped, and because the pass is single, a value that itself
 * contains "{{...}}" is never expanded again. Unknown placeholders become empty.
 */
export function hydrate(template, values) {
  return template.replace(PLACEHOLDER, (_match, key) =>
    Object.hasOwn(values, key) ? escapeHtml(values[key]) : '',
  );
}
