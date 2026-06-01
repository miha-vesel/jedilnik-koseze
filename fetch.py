import subprocess
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
    result = subprocess.run([
        "curl", "-sL",
        "-A", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H", "Accept-Language: sl-SI,sl;q=0.9,en;q=0.8",
        "-H", "Referer: https://www.oskoseze.si/sl/",
        "--max-time", "20",
        URL
    ], capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"curl failed: {result.stderr}")
    return result.stdout

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

    # Fallback: HTML tables
    if not result["malica"]:
        from html.parser import HTMLParser as HP
        class TableParser(HP):
            def __init__(self):
                super().__init__()
                self.tables = []
                self.current_table = []
                self.current_row = []
                self.current_cell = []
                self.in_cell = False
                self.depth = 0
            def handle_starttag(self, tag, attrs):
                if tag == "table": self.current_table = []; self.depth += 1
                elif tag == "tr": self.current_row = []
                elif tag in ("td","th"): self.in_cell = True; self.current_cell = []
            def handle_endtag(self, tag):
                if tag == "table":
                    self.tables.append(self.current_table)
                    self.depth -= 1
                elif tag == "tr" and self.current_row:
                    self.current_table.append(self.current_row)
                elif tag in ("td","th"):
                    self.current_row.append(" ".join(self.current_cell).strip())
                    self.in_cell = False
            def handle_data(self, data):
                if self.in_cell: self.current_cell.append(data.strip())

        tp = TableParser()
        tp.feed(html)
        for ti, table in enumerate(tp.tables[:3]):
            for row in table[1:]:
                if len(row) >= 2 and row[0] in DAYS:
                    result[keys[ti]][row[0]] = row[1]

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
