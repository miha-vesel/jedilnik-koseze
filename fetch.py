import urllib.request
import json
import re
from html.parser import HTMLParser

URL = "https://www.oskoseze.si/sl/jedilnik/"
DAYS = ["Ponedeljek", "Torek", "Sreda", "Četrtek", "Petek"]

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip = False
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav"):
            self.skip = True
    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav"):
            self.skip = False
        if tag in ("td","th","tr","li","p","div","h2","h3","br"):
            self.text.append("\n")
    def handle_data(self, data):
        if not self.skip:
            self.text.append(data)
    def get_text(self):
        return "".join(self.text)

def fetch_html():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "sl-SI,sl;q=0.9",
        "Referer": "https://www.oskoseze.si/sl/",
    }
    req = urllib.request.Request(URL, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")

def parse(html):
    parser = TextExtractor()
    parser.feed(html)
    text = parser.get_text()

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Week label
    week_label = ""
    for line in lines:
        m = re.search(r'\d{2}\.\s*\d{2}\.\s*\d{4}\s*[-–]\s*\d{2}\.\s*\d{2}\.\s*\d{4}', line)
        if m:
            week_label = line.replace("JEDILNIK","").replace("(","").replace(")","").strip()
            break

    # Find table starts by | DAN | header rows
    table_starts = []
    for i, line in enumerate(lines):
        if re.search(r'\|\s*DAN\s*\|', line, re.I):
            table_starts.append(i)

    keys = ["malica", "kosilo", "popoldne"]
    result = {"malica": {}, "kosilo": {}, "popoldne": {}, "weekLabel": week_label}

    for ti, start in enumerate(table_starts[:3]):
        end = table_starts[ti+1] if ti+1 < len(table_starts) else start + 20
        for line in lines[start:end]:
            clean = line.lstrip("|").strip()
            for day in DAYS:
                if clean.startswith(day):
                    meal = clean[len(day):].lstrip(" |:-").split("|")[0].strip()
                    if meal and len(meal) > 3:
                        result[keys[ti]][day] = meal
                    break

    return result

if __name__ == "__main__":
    html = fetch_html()
    data = parse(html)
    with open("jedilnik.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("OK:", data.get("weekLabel", "?"))
    for k in ["malica", "kosilo", "popoldne"]:
        print(f"\n{k.upper()}:")
        for d, m in data[k].items():
            print(f"  {d}: {m}")
