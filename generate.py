import os
import sys
import re

def slugify(text):
    text = text.lower().replace('&', 'and')
    return re.sub(r'[\W_]+', '-', text).strip('-')

def main():
    guest_name = os.environ.get("GUEST_NAME", "").strip()
    if not guest_name:
        print("Error: GUEST_NAME environment variable is empty.")
        sys.exit(1)

    couple_names = os.environ.get("COUPLE_NAMES", "Aarav & Priya")
    rendered_html = os.environ.get("RENDERED_HTML", "").strip()

    guest_slug = slugify(guest_name)
    couple_slug = slugify(couple_names)

    # Wrap the dynamic preview template inside a complete mobile-responsive HTML wrapper page
    full_page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Wedding Invitation for {guest_name}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,600;0,700;1,400&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    body {{ font-family: 'Plus Jakarta Sans', sans-serif; background: #fcfaff; margin: 0; padding: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh; }}
    .invite-container {{ width: 100%; max-width: 420px; min-height: 100vh; background: white; box-shadow: 0 0 40px rgba(0,0,0,0.05); }}
  </style>
</head>
<body>
  <div class="invite-container">
    {rendered_html}
  </div>
</body>
</html>
"""

    output_dir = os.path.join(couple_slug, "to", guest_slug)
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, "index.html")
    with open(output_file, "w", encoding="utf-8") as out:
        out.write(full_page_html)

    print(f"Successfully generated custom HTML invite for '{guest_name}' at /{couple_slug}/to/{guest_slug}/index.html")

if __name__ == "__main__":
    main()