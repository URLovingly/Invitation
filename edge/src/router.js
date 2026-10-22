// URL routing: decides whether a request path is a guest invitation.

// /:couple_slug/to/:guest_slug  (optional trailing slash). Slugs are lowercase a-z, 0-9 and "-".
const INVITE_PATH = /^\/([a-z0-9-]{1,100})\/to\/([a-z0-9-]{1,100})\/?$/;

/**
 * @param {string} pathname e.g. "/aarav-and-priya/to/rahul-sharma/"
 * @returns {{coupleSlug: string, guestSlug: string} | null}
 */
export function matchInvitePath(pathname) {
  const match = INVITE_PATH.exec(pathname.toLowerCase());
  return match ? { coupleSlug: match[1], guestSlug: match[2] } : null;
}
