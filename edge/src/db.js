// Data access: the only module that talks to D1.

const FIND_INVITATION = `
  SELECT g.guest_name, g.custom_note, g.template_id,
         c.couple_names, c.event_date, c.venue
  FROM guests g
  JOIN couples c ON c.couple_slug = g.couple_slug
  WHERE g.couple_slug = ?1 AND g.guest_slug = ?2
  LIMIT 1`;

/**
 * Look up one guest together with the shared couple details.
 * Values are bound as parameters, never concatenated into SQL.
 *
 * @param {D1Database} db
 * @returns {Promise<object | null>} the row, or null when no guest matches
 */
export async function findInvitation(db, coupleSlug, guestSlug) {
  const row = await db.prepare(FIND_INVITATION).bind(coupleSlug, guestSlug).first();
  return row ?? null;
}
