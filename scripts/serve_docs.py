#!/usr/bin/env python3
"""로컬에서 markdown 문서를 예쁘게 렌더링해서 브라우저로 보기.

usage: python scripts/serve_docs.py [port]
열면: http://localhost:8765
"""
import http.server
import socketserver
import sys
from pathlib import Path

try:
    import markdown
except ImportError:
    print("Installing markdown package…")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "markdown", "pymdown-extensions"], check=True)
    import markdown


BASE_DIR = Path(__file__).resolve().parent.parent / "docs" / "superpowers"
DOC_DIRS = {
    "specs": BASE_DIR / "specs",
    "plans": BASE_DIR / "plans",
}
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765

CSS = """
<style>
:root {
  --bg: #0d1117;
  --fg: #e6edf3;
  --muted: #8b949e;
  --accent: #58a6ff;
  --accent-2: #f78166;
  --border: #30363d;
  --code-bg: #161b22;
  --success: #3fb950;
  --warning: #d29922;
  --danger: #f85149;
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
  background: var(--bg); color: var(--fg);
  margin: 0; padding: 0; line-height: 1.7;
}
.container { max-width: 980px; margin: 0 auto; padding: 40px 32px 100px; }
.nav {
  position: sticky; top: 0; background: rgba(13,17,23,0.95);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border); padding: 14px 32px;
  z-index: 100; font-size: 14px;
}
.nav a { color: var(--accent); text-decoration: none; margin-right: 18px; }
.nav a:hover { text-decoration: underline; }
.nav .brand { color: var(--fg); font-weight: 700; margin-right: 24px; }
h1 { font-size: 36px; margin-top: 0; border-bottom: 2px solid var(--border); padding-bottom: 18px; }
h2 { font-size: 26px; margin-top: 48px; color: var(--accent); }
h3 { font-size: 20px; color: var(--accent-2); margin-top: 36px; }
h4 { font-size: 16px; color: var(--fg); }
blockquote {
  border-left: 4px solid var(--accent);
  background: rgba(88,166,255,0.08);
  padding: 12px 20px; margin: 20px 0;
  color: var(--muted);
}
code {
  background: var(--code-bg); color: var(--accent-2);
  padding: 2px 6px; border-radius: 4px;
  font-size: 0.92em;
  font-family: "JetBrains Mono", "SF Mono", Menlo, monospace;
}
pre {
  background: var(--code-bg); border: 1px solid var(--border);
  border-radius: 8px; padding: 16px 20px; overflow-x: auto;
  font-family: "JetBrains Mono", "SF Mono", Menlo, monospace;
  line-height: 1.55;
  font-size: 13px;
}
pre code { background: transparent; color: var(--fg); padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 18px 0; font-size: 14px; }
th, td { border: 1px solid var(--border); padding: 10px 14px; text-align: left; vertical-align: top; }
th { background: var(--code-bg); color: var(--accent); font-weight: 600; }
tr:nth-child(even) { background: rgba(255,255,255,0.02); }
a { color: var(--accent); }
a:hover { color: var(--accent-2); }
ul, ol { padding-left: 24px; }
li { margin: 4px 0; }
hr { border: 0; border-top: 1px solid var(--border); margin: 40px 0; }
strong { color: #fff; }
.doc-list {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px; margin-top: 30px;
}
.doc-card {
  border: 1px solid var(--border); border-radius: 12px;
  padding: 20px; transition: all 0.2s;
  background: var(--code-bg);
}
.doc-card:hover { border-color: var(--accent); transform: translateY(-2px); }
.doc-card a { display: block; color: var(--fg); text-decoration: none; font-weight: 600; font-size: 16px; margin-bottom: 6px; }
.doc-card .desc { color: var(--muted); font-size: 13px; }
.badge {
  display: inline-block; padding: 2px 8px; border-radius: 10px;
  font-size: 11px; font-weight: 600; margin-left: 8px;
}
.badge-overview { background: rgba(63,185,80,0.2); color: var(--success); }
.badge-design { background: rgba(88,166,255,0.2); color: var(--accent); }
.badge-plan { background: rgba(247,129,102,0.2); color: var(--accent-2); }
.readme-box {
  background: var(--code-bg); border: 1px solid var(--border);
  border-radius: 12px; padding: 24px; margin: 20px 0;
}
.readme-box h1 { font-size: 22px; margin-top: 0; border: none; padding: 0; }
.readme-box h2 { font-size: 18px; margin-top: 20px; }
.readme-box h3 { font-size: 16px; }
</style>
"""


def render_md(content: str, title: str) -> str:
    md = markdown.Markdown(extensions=[
        "fenced_code", "tables", "toc", "pymdownx.tilde", "pymdownx.emoji",
    ])
    body = md.convert(content)
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title>
{CSS}
</head>
<body>
<div class="nav">
  <span class="brand">📚 HYDRA Docs</span>
  <a href="/">← 문서 목록</a>
</div>
<div class="container">
{body}
</div>
</body></html>"""


def _section_cards(section: str, dir_path: Path) -> str:
    cards = []
    for f in sorted(dir_path.glob("*.md"), reverse=True):
        name = f.stem
        badge = ""
        if "overview" in name:
            badge = '<span class="badge badge-overview">한눈에</span>'
        elif section == "plans":
            badge = '<span class="badge badge-plan">계획</span>'
        else:
            badge = '<span class="badge badge-design">상세</span>'
        first_line = ""
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("> "):
                        first_line = line[2:].strip()[:120]
                        break
                    if line.startswith("**") and ":" in line:
                        first_line = line.strip()[:120]
                        break
        except Exception:
            pass
        cards.append(f"""
<div class="doc-card">
  <a href="/{section}/{f.name}">{name}{badge}</a>
  <div class="desc">{first_line}</div>
</div>
""")
    return "".join(cards)


def index_page() -> str:
    readme_html = ""
    readme_path = BASE_DIR / "README.md"
    if readme_path.exists():
        md = markdown.Markdown(extensions=["fenced_code", "tables"])
        readme_html = f'<div class="readme-box">{md.convert(readme_path.read_text(encoding="utf-8"))}</div>'

    specs_cards = _section_cards("specs", DOC_DIRS["specs"])
    plans_cards = _section_cards("plans", DOC_DIRS["plans"])

    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8"/>
<title>HYDRA Docs</title>
{CSS}
</head><body>
<div class="nav">
  <span class="brand">📚 HYDRA Docs</span>
  <a href="/">Home</a>
  <a href="#specs">Specs</a>
  <a href="#plans">Plans</a>
</div>
<div class="container">
<h1>HYDRA 설계 문서</h1>
<p style="color:var(--muted)">프로젝트 설계/구현 계획 문서 모음. README 는 아래, 개별 문서는 카드 클릭.</p>
{readme_html}
<h2 id="specs">🏛️ Specs — 설계 문서</h2>
<p style="color:var(--muted);font-size:14px">"왜 이렇게 짜는지"</p>
<div class="doc-list">{specs_cards}</div>
<h2 id="plans">🔨 Plans — 구현 계획</h2>
<p style="color:var(--muted);font-size:14px">"실제 task 단위로 어떻게 짜는지"</p>
<div class="doc-list">{plans_cards}</div>
</div></body></html>"""


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.strip("/").split("?")[0]
        if path == "" or path == "index.html":
            html = index_page()
        elif path.endswith(".md"):
            # specs/xxx.md 또는 plans/xxx.md 형태
            parts = path.split("/", 1)
            if len(parts) == 2 and parts[0] in DOC_DIRS:
                f = DOC_DIRS[parts[0]] / parts[1]
            else:
                # 구 경로 호환: /xxx.md → specs/xxx.md
                f = DOC_DIRS["specs"] / path
            if not f.exists():
                self.send_error(404); return
            content = f.read_text(encoding="utf-8")
            title = f.stem
            html = render_md(content, title)
        else:
            return super().do_GET()

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, fmt, *args):
        pass  # quiet


if __name__ == "__main__":
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"\n  📚 HYDRA Docs  →  http://localhost:{PORT}\n")
        httpd.serve_forever()
