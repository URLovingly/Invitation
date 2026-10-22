"""The AI-facing skill file must keep pace with the code (see AGENTS.md)."""
import os
import re

from server.config import BASE_DIR

SKILL_PATH = os.path.join(BASE_DIR, ".github", "skills", "urlovingly-workspace", "SKILL.md")
UNTRACKED = {".git", ".gitignore", "data", "__pycache__", ".pytest_cache", "node_modules", ".wrangler"}


def skill_text():
    with open(SKILL_PATH, encoding="utf-8") as handle:
        return handle.read()


def files_under(*parts, suffixes):
    root = os.path.join(BASE_DIR, *parts)
    for name in sorted(os.listdir(root)):
        if name.endswith(suffixes):
            yield "/".join(parts + (name,))


def test_skill_file_has_frontmatter_and_update_rule():
    text = skill_text()
    assert text.startswith("---\nname: urlovingly-workspace\ndescription:")
    assert "Update this file in the same change" in text


def test_ai_instruction_files_point_to_the_skill():
    for relative in ("AGENTS.md", os.path.join(".github", "copilot-instructions.md")):
        with open(os.path.join(BASE_DIR, relative), encoding="utf-8") as handle:
            assert "urlovingly-workspace/SKILL.md" in handle.read(), relative


def test_every_top_level_entry_is_documented():
    text = skill_text()
    for name in os.listdir(BASE_DIR):
        if name not in UNTRACKED:
            assert name in text, f"{name} is not described in SKILL.md"


def test_every_server_module_is_documented():
    text = skill_text()
    for path in files_under("server", suffixes=(".py",)):
        assert path in text, f"{path} is not described in SKILL.md"


def test_every_edge_file_is_documented():
    text = skill_text()
    paths = [
        *files_under("edge", "src", suffixes=(".js",)),
        *files_under("edge", "test", suffixes=(".js",)),
        *files_under("edge", "migrations", suffixes=(".sql",)),
        *files_under("edge", "public", "templates", suffixes=(".html",)),
        *files_under("edge", suffixes=(".toml", ".json", ".sql", ".js")),
    ]
    for path in paths:
        assert path in text, f"{path} is not described in SKILL.md"


def test_single_file_worker_embeds_the_base_template():
    def read(*parts):
        with open(os.path.join(BASE_DIR, *parts), encoding="utf-8") as handle:
            return handle.read()

    assert read("edge", "public", "templates", "base.html").strip() in read("edge", "worker.js")


def test_every_test_module_is_documented():
    text = skill_text()
    for name in os.listdir(os.path.join(BASE_DIR, "tests")):
        if name.startswith("test_") and name.endswith(".py"):
            assert name in text, f"{name} is not described in SKILL.md"


def test_every_environment_variable_is_documented():
    with open(os.path.join(BASE_DIR, "server", "config.py"), encoding="utf-8") as handle:
        variables = re.findall(r'env\("([A-Z_]+)"', handle.read())
    assert variables
    text = skill_text()
    for variable in variables:
        assert variable in text, f"{variable} is not described in SKILL.md"


def test_every_api_route_is_documented(app):
    normalise = lambda value: re.sub(r"<[^>]+>", "<>", value)
    text = normalise(skill_text())
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/"):
            assert normalise(rule.rule) in text, f"{rule.rule} is not described in SKILL.md"
