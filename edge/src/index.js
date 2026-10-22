// Cloudflare Worker entry point: Dynamic URL Hydration.
//
//   GET /:couple_slug/to/:guest_slug
//     -> look the guest up in D1
//     -> not found: clean 404 page
//     -> found: fetch the HTML template, fill the {{PLACEHOLDERS}}, return 200
//
// Bindings (see wrangler.toml): DB = D1 database, ASSETS = static template files.

import { findInvitation } from './db.js';
import { buildValues, hydrate } from './render.js';
import {
  invitationResponse,
  methodNotAllowedResponse,
  notFoundResponse,
  serverErrorResponse,
} from './responses.js';
import { matchInvitePath } from './router.js';
import { loadTemplate } from './template.js';

export async function handleRequest(request, env) {
  if (request.method !== 'GET' && request.method !== 'HEAD') return methodNotAllowedResponse();

  const route = matchInvitePath(new URL(request.url).pathname);
  if (!route) return notFoundResponse();

  const invitation = await findInvitation(env.DB, route.coupleSlug, route.guestSlug);
  if (!invitation) return notFoundResponse();

  const template = await loadTemplate(env, request.url, invitation.template_id);
  if (template === null) {
    console.error(`Template "${invitation.template_id}" and the base template are both missing`);
    return serverErrorResponse();
  }

  return invitationResponse(hydrate(template, buildValues(invitation)));
}

export default {
  async fetch(request, env) {
    try {
      return await handleRequest(request, env);
    } catch (error) {
      console.error('Unhandled error while rendering invitation', error);
      return serverErrorResponse();
    }
  },
};
