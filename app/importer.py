"""Turn files / URLs into plain text for the knowledge base.

Failure is explicit: if nothing usable is extracted we raise ImportFailure
instead of storing a title or login page as if it were content.
"""
import io
import re
import urllib.request
import zipfile
from html.parser import HTMLParser

MIN_CHARS = 200
UA = "Mozilla/5.0 (HKUST-Freshmen-Assistant demo; read-only)"
MANUAL_HOSTS = {
    "mp.weixin.qq.com": "微信文章无法自动抓取。请把正文复制/另存为 .md、.txt 或 PDF，放进 data/inbox/（文件名可写成 General__标题.md）",
    "docs.qq.com": "腾讯文档需要登录。请导出为 PDF/DOCX，放进 data/inbox/",
    "ebookshelf.hkust.edu.hk": "翻页电子书无法直接提取。请导出 PDF，放进 data/inbox/",
}


class ImportFailure(Exception):
    pass


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "nav", "header", "footer", "noscript", "svg", "form", "aside"}
    BLOCK = {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "table"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip_depth, self.title, self._in_title = [], 0, "", False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" | ")
        if tag in ("h1", "h2", "h3"):
            self.parts.append("\n## ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip_depth and data.strip():
            self.parts.append(data.strip() + " ")


_BOILERPLATE = re.compile(
    r"^(skip to main content|sections?|left column|right column|text area|container|home|menu|"
    r"search|back to top|share|print|top)$", re.I)


def html_to_text(html):
    p = _TextExtractor()
    p.feed(html)
    text = "".join(p.parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    lines = [ln for ln in text.splitlines() if not _BOILERPLATE.match(ln.strip().strip("#").strip())]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return p.title.strip(), text.strip()


def docx_to_text(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    xml = z.read("word/document.xml").decode("utf-8", "ignore")
    out = []
    for para in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        t = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", para))
        if t.strip():
            out.append(t.strip())
    return "\n\n".join(out)


class NeedsOCR(ImportFailure):
    """PDF opens fine but the pages are pictures; only headers/footers have real text."""


_PAGE_NOISE = re.compile(
    r"(page\s*\d+\s*of\s*\d+|https?://\S+|\d{4}/\d{1,2}/\d{1,2},?\s*\d{1,2}:\d{2}|\.pdf\b|^\s*\d+\s*$)", re.I)


def pdf_to_text(data):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportFailure("缺少 pypdf，请先运行: pip install pypdf")
    reader = PdfReader(io.BytesIO(data))
    pages, real_pages = [], 0
    for i, pg in enumerate(reader.pages, 1):
        t = (pg.extract_text() or "").strip()
        if t:
            pages.append(f"[Page {i}]\n{t}")
            # a page counts as real content only if something is left after stripping
            # print-to-PDF headers/footers (date, file name, "Page 3 of 85", URL)
            rest = "\n".join(ln for ln in t.splitlines() if not _PAGE_NOISE.search(ln))
            if len(rest.strip()) >= 40:
                real_pages += 1
    n = len(reader.pages)
    if n and real_pages / n < 0.3:
        raise NeedsOCR(f"这个 PDF 共 {n} 页，但只有 {real_pages} 页含真实文字（其余是图片，只有页眉页脚）。"
                       "请先运行: python3 manage.py ocr <文件>")
    return "\n\n".join(pages)


def bytes_to_text(filename, data):
    name = filename.lower()
    if name.endswith((".md", ".txt", ".csv", ".markdown")):
        return data.decode("utf-8", "ignore")
    if name.endswith(".docx"):
        return docx_to_text(data)
    if name.endswith(".pdf"):
        return pdf_to_text(data)
    if name.endswith((".html", ".htm")):
        return html_to_text(data.decode("utf-8", "ignore"))[1]
    raise ImportFailure(f"暂不支持的文件类型: {filename}")


def parse_front_matter(text):
    """Optional header lines: 'key: value' until the first blank line / '---'."""
    meta, lines = {}, text.splitlines()
    i = 0
    keys = {"title", "category", "source", "source_url", "publisher", "source_type",
            "effective_date", "retrieved_at"}
    if lines and lines[0].strip() == "---":
        i = 1
    while i < len(lines):
        m = re.match(r"^\s*([A-Za-z_]+)\s*[:：]\s*(.*)$", lines[i])
        if m and m.group(1).lower() in keys:
            k = m.group(1).lower()
            meta["source_url" if k == "source" else k] = m.group(2).strip()
            i += 1
        else:
            break
    if i < len(lines) and lines[i].strip() == "---":
        i += 1
    return meta, "\n".join(lines[i:]).strip()


def fetch_url(url):
    """Returns (title, text, content_type). Raises ImportFailure on any problem."""
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    for h, msg in MANUAL_HOSTS.items():
        if host.endswith(h):
            raise ImportFailure(f"需人工导出：{msg}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            ctype = r.headers.get("Content-Type", "").lower()
            data = r.read(25_000_000)
    except Exception as e:
        raise ImportFailure(f"无法访问链接: {e}")
    if "pdf" in ctype or url.lower().split("?")[0].endswith(".pdf"):
        title, text = url.rsplit("/", 1)[-1], pdf_to_text(data)
    else:
        title, text = html_to_text(data.decode("utf-8", "ignore"))
    if len(text) < MIN_CHARS:
        raise ImportFailure(f"提取到的正文过短({len(text)}字)，可能是登录页或动态页面，请人工导出")
    return title or url, text, ctype


def extract_urls(text):
    urls = re.findall(r"https?://[^\s<>\"'）)]+", text.replace("&amp;", "&"))
    return list(dict.fromkeys(u.rstrip(".,;") for u in urls))
