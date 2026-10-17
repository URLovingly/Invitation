import os
import sys
import re
from jinja2 import Environment, FileSystemLoader

def slugify(text):
    return re.sub(r'[\W_]+', '-', text.lower()).strip('-')

guest_name = os.environ.get("GUEST_NAME")
template_name = os.environ.get("TEMPLATE", "classic")

if not guest_name:
    sys.exit("Error: No guest name provided.")

slug = slugify(guest_name)
env = Environment(loader=FileSystemLoader("templates"))
template = env.get_template(f"{template_name}/index.html")

html_out = template.render(guest_name=guest_name)

# Save to the repository root in a /to/ folder
output_dir = os.path.join("to", slug)
os.makedirs(output_dir, exist_ok=True)

with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as out:
    out.write(html_out)

print(f"Created invite at /to/{slug}/")