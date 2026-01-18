#!/usr/bin/env python3
"""Generate static site from RST files using git history."""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

try:
    import tomllib as toml
except Exception:
    import tomli as toml  # type: ignore

try:
    from docutils.core import publish_parts
except Exception:
    publish_parts = None

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except Exception:
    Environment = None


def load_config(path):
    with open(path, "rb") as f:
        cfg = toml.load(f)
    return cfg


def find_rst_files(content_dir):
    rst_files = []
    for root, _, files in os.walk(content_dir):
        for fn in files:
            if fn.lower().endswith(".rst"):
                rst_files.append(os.path.join(root, fn))
    return sorted(rst_files)


def git_log_commits(path):
    # path should be repo-relative; use subprocess git log
    rel = os.path.relpath(path, os.getcwd())
    res = subprocess.run(["git", "log", "--pretty=format:%H|%cI|%an|%s", "--", rel], capture_output=True, text=True)
    if res.returncode != 0:
        return []
    lines = [l for l in res.stdout.splitlines() if l.strip()]
    commits = []
    for line in lines:
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        sha, date, author, message = parts
        commits.append({"sha": sha, "date": date, "author": author, "message": message})
    return commits


def first_commit_date(commits):
    if not commits:
        return datetime.now(timezone.utc).isoformat()
    # git log lists newest first -> earliest is last
    return commits[-1]["date"]


def render_rst(rst_text):
    if publish_parts is None:
        raise RuntimeError("docutils not installed")
    parts = publish_parts(source=rst_text, writer_name="html5")
    return parts.get("html_body", "")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def copy_static(static_dir, out_dir):
    src = os.path.abspath(static_dir)
    dst = os.path.join(out_dir, os.path.basename(static_dir))
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

def copy_media(media_dir, out_dir):
    src = os.path.abspath(media_dir)
    dst = os.path.join(out_dir, os.path.basename(media_dir))
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--output", default=None)
    parser.add_argument("--skip-render", action="store_true", help="Skip docutils/Jinja rendering (dry run of git parts)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    content_dir = cfg.get("content_dir", "content")
    static_dir = cfg.get("static_dir", "static")
    media_dir = cfg.get("media_dir", "media")
    out_dir = args.output or cfg.get("output_dir", "site")
    repo_url = cfg.get("repo_url", "")
    branch = cfg.get("branch", "main")
    site_title = cfg.get("site_title", "Site")
    domain = cfg.get("domain")

    rst_files = find_rst_files(content_dir)

    pages = []
    for path in rst_files:
        commits = git_log_commits(path)
        first_date = first_commit_date(commits)
        rel = os.path.relpath(path, os.getcwd())
        slug = os.path.splitext(os.path.basename(path))[0]
        out_filename = f"{slug}.html"
        page = {
            "path": path,
            "rel": rel,
            "slug": slug,
            "out_filename": out_filename,
            "commits": commits,
            "first_commit_date": first_date,
            "title": slug,
            "url": f"/{out_filename}",
        }
        pages.append(page)

    # Sort by first commit date descending (newest first)
    pages.sort(key=lambda p: p["first_commit_date"], reverse=True)

    if args.dry_run:
        print("Dry run: discovered pages:")
        for p in pages:
            print(p["rel"], "first_commit_date=", p["first_commit_date"], "commits=", len(p["commits"]))
        return 0

    if args.skip_render:
        print("Skip-render mode: verifying git discovery and listing pages")
        for p in pages:
            print(p["rel"], "->", p["out_filename"], "commits=", len(p["commits"]))
        return 0

    # Full render requires Jinja2 and docutils
    if publish_parts is None or Environment is None:
        print("Missing dependencies: please install docutils and Jinja2.\nExample: python -m pip install docutils Jinja2 tomli\nOr use your environment manager (pixi).")
        return 2

    env = Environment(
        loader=FileSystemLoader(os.path.join(os.getcwd(), "templates")),
        autoescape=select_autoescape(["html", "xml"]),
    )
    base = env.get_template("base.html")
    page_tpl = env.get_template("page.html")
    index_tpl = env.get_template("index.html")

    ensure_dir(out_dir)
    copy_static(static_dir, out_dir)

    # Write CNAME for GitHub Pages if domain provided
    if domain:
        cname_path = os.path.join(out_dir, "CNAME")
        with open(cname_path, "w", encoding="utf-8") as f:
            f.write(domain.strip() + "\n")
        print("Wrote CNAME ->", cname_path)
    try:
        copy_media(media_dir, out_dir)
    except FileNotFoundError:
        pass  # media dir is optional

    def commit_url(sha):
        if not repo_url:
            return "#"
        url = repo_url.rstrip(".git").rstrip("/")
        return f"{url}/commit/{sha}"

    def commits_for_path_url(relpath):
        if not repo_url:
            return "#"
        url = repo_url.rstrip(".git").rstrip("/")
        return f"{url}/commits/{branch}/{relpath}"

    # Render pages
    for p in pages:
        with open(p["path"], "r", encoding="utf-8") as f:
            rst_text = f.read()
        body = render_rst(rst_text)
        rendered = page_tpl.render(
            title=p["title"],
            site_title=site_title,
            static_dir=static_dir,
            body=body,
            commits=p["commits"],
            commit_url=commit_url,
            commits_for_path_url=commits_for_path_url(p["rel"]),
        )
        out_path = os.path.join(out_dir, p["out_filename"])
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(rendered)
        print("Wrote", out_path)

    pages = sorted(pages, key=lambda p: p["first_commit_date"], reverse=True)

    # Render index
    index_html = index_tpl.render(pages=pages, site_title=site_title, static_dir=static_dir)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)
    print("Wrote index for", len(pages), "pages")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
