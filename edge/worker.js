/**
 * URLovingly invitations: single-file Cloudflare Worker (Dynamic URL Hydration).
 *
 *   GET /:couple_slug/to/:guest_slug
 *     -> find the guest in D1
 *     -> not found: clean 404 page
 *     -> found: fill the HTML template's {{PLACEHOLDERS}} and return 200
 *
 * HOW TO USE IN THE CLOUDFLARE DASHBOARD
 *   1. Workers & Pages > Create > Worker, then "Edit code" and paste this whole file.
 *   2. Settings > Bindings > Add > D1 database. Variable name must be exactly: DB
 *   3. Create the two tables in the D1 console using edge/migrations/0001_create_invitations.sql.
 *   4. Deploy, then open /<couple_slug>/to/<guest_slug>.
 *
 * To add a design: add another entry to TEMPLATES and set guests.template_id to its key.
 * Keep TEMPLATES.base identical to edge/public/templates/base.html (a test checks this).
 */

// ---------------------------------------------------------------------------
// Templates (keys are guests.template_id; 'base' is the fallback)
// ---------------------------------------------------------------------------
const DEFAULT_TEMPLATE_ID = 'base';

const TEMPLATES = {
  base: `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex">
  <title>{{GUEST_NAME}}, you are invited | {{COUPLE_NAMES}}</title>
  <meta name="description" content="A personal invitation for {{GUEST_NAME}} from {{COUPLE_NAMES}}.">
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,600;0,700;1,400&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script>
    tailwind.config = {
      theme: { extend: {
        fontFamily: { serif: ['"Cormorant Garamond"', 'Georgia', 'serif'], sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'] },
        colors: { brand: { navy: '#151438', pink: '#F42F6C', purple: '#6C2BD9' } }
      } }
    };
  </script>
  <style>
    .brand-gradient { background: linear-gradient(160deg, #FF5E8E 0%, #F42F6C 40%, #6C2BD9 100%); }
    @keyframes rise { from { opacity: 0; transform: translateY(18px); } to { opacity: 1; transform: none; } }
    @keyframes drift { 0%, 100% { transform: translateY(0) rotate(-6deg); } 50% { transform: translateY(-14px) rotate(6deg); } }
    .rise { animation: rise .8s cubic-bezier(.2, .75, .25, 1) both; }
    .d1 { animation-delay: .15s; } .d2 { animation-delay: .35s; } .d3 { animation-delay: .55s; } .d4 { animation-delay: .75s; }
    .heart { position: absolute; color: rgba(255, 255, 255, .35); animation: drift 6s ease-in-out infinite; }
    @media (prefers-reduced-motion: reduce) { .rise, .heart { animation: none; } }
  </style>
</head>
<body class="bg-[#fcfaff] font-sans text-brand-navy antialiased">
  <main class="mx-auto min-h-screen w-full max-w-md bg-white shadow-xl shadow-purple-900/5">

    <!-- Hero -->
    <header class="brand-gradient relative overflow-hidden px-6 pb-20 pt-14 text-center text-white">
      <span class="heart left-6 top-8 text-2xl" aria-hidden="true">&#10084;</span>
      <span class="heart right-8 top-20 text-lg" style="animation-delay: 1.5s" aria-hidden="true">&#10084;</span>
      <span class="heart bottom-10 left-12 text-xl" style="animation-delay: 3s" aria-hidden="true">&#10084;</span>

      <p class="rise text-[11px] font-semibold uppercase tracking-[.3em] text-white/85">You are warmly invited</p>
      <h1 class="rise d1 mt-5 font-serif text-5xl font-bold leading-[1.05] sm:text-6xl">{{COUPLE_NAMES}}</h1>
      <p class="rise d2 mt-5 text-sm text-white/90">invite you to celebrate with them</p>
    </header>

    <!-- Guest card overlaps the hero -->
    <section class="relative -mt-12 px-5" aria-label="Invitation for the guest">
      <div class="rise d2 rounded-3xl border border-pink-100 bg-white px-6 py-7 text-center shadow-xl shadow-pink-500/10">
        <p class="text-[11px] font-bold uppercase tracking-[.25em] text-brand-pink">A special invitation for</p>
        <p class="mt-2 break-words font-serif text-3xl font-bold text-brand-navy">{{GUEST_NAME}}</p>
      </div>
    </section>

    <!-- Personal note -->
    <section class="px-5 pt-6" aria-label="A personal note">
      <figure class="rise d3 rounded-3xl bg-pink-50/70 px-6 py-6 text-center">
        <span class="block font-serif text-4xl leading-none text-brand-pink" aria-hidden="true">&ldquo;</span>
        <blockquote class="-mt-1 whitespace-pre-line break-words font-serif text-xl italic leading-relaxed text-brand-navy">{{CUSTOM_NOTE}}</blockquote>
      </figure>
    </section>

    <!-- When and where -->
    <section class="px-5 py-6" aria-label="Event details">
      <div class="rise d4 divide-y divide-purple-100 overflow-hidden rounded-3xl border border-purple-100">
        <div class="flex items-start gap-4 px-5 py-4">
          <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-purple-50 text-lg" aria-hidden="true">&#128197;</span>
          <div class="min-w-0">
            <p class="text-[11px] font-bold uppercase tracking-widest text-brand-purple">When</p>
            <p class="mt-0.5 break-words text-sm font-semibold">{{EVENT_DATE}}</p>
          </div>
        </div>
        <div class="flex items-start gap-4 px-5 py-4">
          <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-purple-50 text-lg" aria-hidden="true">&#128205;</span>
          <div class="min-w-0">
            <p class="text-[11px] font-bold uppercase tracking-widest text-brand-purple">Where</p>
            <p class="mt-0.5 break-words text-sm font-semibold">{{VENUE}}</p>
          </div>
        </div>
      </div>
    </section>

    <footer class="px-6 pb-12 pt-2 text-center">
      <p class="font-serif text-lg italic text-brand-navy/80">With love, {{COUPLE_NAMES}}</p>
      <p class="mt-6 text-[10px] uppercase tracking-widest text-slate-400">Made with URLovingly</p>
    </footer>
  </main>
</body>
</html>`,
};

// ---------------------------------------------------------------------------
// Routing
// ---------------------------------------------------------------------------
// /:couple_slug/to/:guest_slug (optional trailing slash); slugs are a-z, 0-9 and "-".
const INVITE_PATH = /^\/([a-z0-9-]{1,100})\/to\/([a-z0-9-]{1,100})\/?$/;

function matchInvitePath(pathname) {
  const match = INVITE_PATH.exec(pathname.toLowerCase());
  return match ? { coupleSlug: match[1], guestSlug: match[2] } : null;
}

// ---------------------------------------------------------------------------
// Database (D1 binding: DB)
// ---------------------------------------------------------------------------
const FIND_INVITATION = `
  SELECT g.guest_name, g.custom_note, g.template_id,
         c.couple_names, c.event_date, c.venue
  FROM guests g
  JOIN couples c ON c.couple_slug = g.couple_slug
  WHERE g.couple_slug = ?1 AND g.guest_slug = ?2
  LIMIT 1`;

async function findInvitation(db, coupleSlug, guestSlug) {
  const row = await db.prepare(FIND_INVITATION).bind(coupleSlug, guestSlug).first();
  return row ?? null;
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------
const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => HTML_ESCAPES[char]);
}

function buildValues(invitation) {
  return {
    GUEST_NAME: invitation.guest_name,
    COUPLE_NAMES: invitation.couple_names,
    CUSTOM_NOTE: invitation.custom_note?.trim() || "We can't wait to celebrate this special day with you!",
    EVENT_DATE: invitation.event_date?.trim() || 'Details to follow',
    VENUE: invitation.venue?.trim() || 'Venue to be announced',
  };
}

// One pass, values escaped: a value containing "{{...}}" is never expanded again.
function hydrate(template, values) {
  return template.replace(/\{\{\s*([A-Z_]+)\s*\}\}/g, (_match, key) =>
    Object.hasOwn(values, key) ? escapeHtml(values[key]) : '',
  );
}

function pickTemplate(templateId) {
  return Object.hasOwn(TEMPLATES, templateId) ? TEMPLATES[templateId] : TEMPLATES[DEFAULT_TEMPLATE_ID];
}

// ---------------------------------------------------------------------------
// Responses
// ---------------------------------------------------------------------------
const BASE_HEADERS = {
  'Content-Type': 'text/html; charset=utf-8',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
};

function respond(body, status, cacheControl, extraHeaders = {}) {
  return new Response(body, { status, headers: { ...BASE_HEADERS, 'Cache-Control': cacheControl, ...extraHeaders } });
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

const notFound = () => respond(NOT_FOUND_PAGE, 404, 'public, max-age=30');
const methodNotAllowed = () =>
  respond('Method Not Allowed', 405, 'no-store', { Allow: 'GET, HEAD', 'Content-Type': 'text/plain; charset=utf-8' });
const serverError = () =>
  respond('Something went wrong. Please try again shortly.', 500, 'no-store', { 'Content-Type': 'text/plain; charset=utf-8' });

// ---------------------------------------------------------------------------
// Worker entry point
// ---------------------------------------------------------------------------
async function handleRequest(request, env) {
  if (request.method !== 'GET' && request.method !== 'HEAD') return methodNotAllowed();

  const route = matchInvitePath(new URL(request.url).pathname);
  if (!route) return notFound();

  const invitation = await findInvitation(env.DB, route.coupleSlug, route.guestSlug);
  if (!invitation) return notFound();

  const html = hydrate(pickTemplate(invitation.template_id), buildValues(invitation));
  return respond(html, 200, 'public, max-age=60, stale-while-revalidate=300');
}

export default {
  async fetch(request, env) {
    try {
      return await handleRequest(request, env);
    } catch (error) {
      console.error('Unhandled error while rendering invitation', error);
      return serverError();
    }
  },
};
