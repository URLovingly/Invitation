// Response builders. Every page is HTML, so common headers live in one place.

const BASE_HEADERS = {
  'Content-Type': 'text/html; charset=utf-8',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
};

function html(body, status, cacheControl, extraHeaders = {}) {
  return new Response(body, {
    status,
    headers: { ...BASE_HEADERS, 'Cache-Control': cacheControl, ...extraHeaders },
  });
}

/** 200 OK with the hydrated invitation. Short browser cache so edits show up quickly. */
export function invitationResponse(markup) {
  return html(markup, 200, 'public, max-age=60, stale-while-revalidate=300');
}

const NOT_FOUND_PAGE = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>Invitation not found</title>
  <style>
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 1.5rem;
           background: #fcfaff; color: #151438; font-family: system-ui, sans-serif; text-align: center; }
    main { max-width: 22rem; }
    h1 { font: 700 2rem Georgia, serif; margin: 0 0 .5rem; }
    p { margin: 0; line-height: 1.6; color: #475569; }
    .mark { font-size: 2.5rem; color: #F42F6C; }
  </style>
</head>
<body>
  <main>
    <div class="mark" aria-hidden="true">&#10084;</div>
    <h1>Invitation not found</h1>
    <p>We could not find an invitation at this link. Please check the link you received, or ask your host to send it again.</p>
  </main>
</body>
</html>`;

/** Clean 404 page for unknown guests and for every non-invitation path. */
export function notFoundResponse() {
  return html(NOT_FOUND_PAGE, 404, 'public, max-age=30');
}

export function methodNotAllowedResponse() {
  return html('Method Not Allowed', 405, 'no-store', { Allow: 'GET, HEAD', 'Content-Type': 'text/plain; charset=utf-8' });
}

export function serverErrorResponse() {
  return html('Something went wrong. Please try again shortly.', 500, 'no-store', { 'Content-Type': 'text/plain; charset=utf-8' });
}
