import os
import sys
import re
from jinja2 import Environment, FileSystemLoader

def slugify(text):
    text = text.lower().replace('&', 'and')
    return re.sub(r'[\W_]+', '-', text).strip('-')

def main():
    guest_name = os.environ.get("GUEST_NAME", "").strip()
    if not guest_name:
        print("Error: GUEST_NAME environment variable is empty.")
        sys.exit(1)

    template_name = os.environ.get("TEMPLATE", "urlovingly").strip()
    couple_names = os.environ.get("COUPLE_NAMES", "Aarav & Priya")
    wedding_date = os.environ.get("WEDDING_DATE", "December 18, 2026")
    wedding_time = os.environ.get("WEDDING_TIME", "5:30 PM Onwards")
    venue = os.environ.get("VENUE", "The Grand Ballroom, Taj Lands End, Mumbai")
    map_url = os.environ.get("MAP_URL", "https://maps.google.com")
    rsvp_phone = os.environ.get("RSVP_PHONE", "919876543210")
    table_no = os.environ.get("TABLE_NO", "VIP Lounge")
    custom_note = os.environ.get("CUSTOM_NOTE", "We can't wait to celebrate our special day with you!")

    slug = slugify(guest_name)
    env = Environment(loader=FileSystemLoader("templates"))
    
    try:
        template = env.get_template(f"{template_name}/index.html")
    except Exception:
        template = env.get_template("urlovingly/index.html")

    html_out = template.render(
        guest_name=guest_name,
        couple_names=couple_names,
        wedding_date=wedding_date,
        wedding_time=wedding_time,
        venue=venue,
        map_url=map_url,
        rsvp_phone=rsvp_phone,
        table_no=table_no,
        custom_note=custom_note
    )

    output_dir = os.path.join("to", slug)
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, "index.html")
    with open(output_file, "w", encoding="utf-8") as out:
        out.write(html_out)

    print(f"Successfully generated URLovingly invite for '{guest_name}' at /to/{slug}/index.html")

if __name__ == "__main__":
    main()