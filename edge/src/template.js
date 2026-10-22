// Loads HTML templates from the static-asset bucket bound as env.ASSETS.

export const DEFAULT_TEMPLATE_ID = 'base';
const TEMPLATE_ID = /^[a-z0-9-]{1,60}$/;

async function fetchTemplate(env, requestUrl, templateId) {
  const assetUrl = new URL(`/templates/${templateId}.html`, requestUrl);
  const response = await env.ASSETS.fetch(new Request(assetUrl));
  return response.ok ? response.text() : null;
}

/**
 * Returns the template markup for `templateId`, falling back to the base template
 * when the id is malformed or the file does not exist. Returns null only if the
 * base template itself is missing (a deployment error).
 */
export async function loadTemplate(env, requestUrl, templateId) {
  const id = TEMPLATE_ID.test(templateId ?? '') ? templateId : DEFAULT_TEMPLATE_ID;
  const template = await fetchTemplate(env, requestUrl, id);
  if (template !== null || id === DEFAULT_TEMPLATE_ID) return template;
  return fetchTemplate(env, requestUrl, DEFAULT_TEMPLATE_ID);
}
