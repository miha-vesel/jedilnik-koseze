import subprocess
import json
import re
import os
import urllib.request
import tarfile
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

    week_label = ""
    for line in lines:
        m = re.search(r'\d{2}\.\s*\d{2}\.\s*\d{4}\s*[-–]\s*\d{2}\.\s*\d{2}\.\s*\d{4}', line)
        if m:
            week_label = line.replace("JEDILNIK","").replace("(","").replace(")","").strip()
            break

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

    if not result["malica"]:
        class TableParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.tables = []
                self.current_table = []
                self.current_row = []
                self.current_cell = []
                self.in_cell = False
            def handle_starttag(self, tag, attrs):
                if tag == "table": self.current_table = []
                elif tag == "tr": self.current_row = []
                elif tag in ("td","th"): self.in_cell = True; self.current_cell = []
            def handle_endtag(self, tag):
                if tag == "table": self.tables.append(self.current_table)
                elif tag == "tr" and self.current_row: self.current_table.append(self.current_row)
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


def setup_fonts():
    font_dir = "/tmp/fonts"
    os.makedirs(font_dir, exist_ok=True)
    regular = os.path.join(font_dir, "DejaVuSans.ttf")
    bold = os.path.join(font_dir, "DejaVuSans-Bold.ttf")

    if not os.path.exists(regular):
        print("Downloading fonts...")
        tar_path = "/tmp/dejavu.tar.bz2"
        urllib.request.urlretrieve(
            "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.tar.bz2",
            tar_path
        )
        with tarfile.open(tar_path, "r:bz2") as tar:
            for member in tar.getmembers():
                if member.name.endswith("DejaVuSans.ttf") or member.name.endswith("DejaVuSans-Bold.ttf"):
                    member.name = os.path.basename(member.name)
                    tar.extract(member, font_dir)
        print("Fonts ready.")
    return regular, bold


def generate_pdf(data, output_path="jedilnik.pdf"):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    regular, bold = setup_fonts()
    pdfmetrics.registerFont(TTFont('Regular', regular))
    pdfmetrics.registerFont(TTFont('Bold', bold))

    GREEN_DARK = colors.HexColor("#1a472a")
    GREEN_MID  = colors.HexColor("#2d6a4f")
    GREEN_PALE = colors.HexColor("#d8f3dc")
    GRAY_LIGHT = colors.HexColor("#f5f5f0")

    def strip_allergens(text):
        return re.sub(r'\s*\([0-9,\s]+\)\s*$', '', text).replace('*', '').strip()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
    )
    styles = getSampleStyleSheet()

    title_style   = ParagraphStyle('T', parent=styles['Normal'], fontSize=18, textColor=GREEN_DARK, fontName='Bold', spaceAfter=4)
    subtitle_style = ParagraphStyle('S', parent=styles['Normal'], fontSize=11, textColor=colors.HexColor("#555555"), fontName='Regular', spaceAfter=16)
    cell_style    = ParagraphStyle('C', parent=styles['Normal'], fontSize=9, fontName='Regular', leading=13)
    header_style  = ParagraphStyle('H', parent=styles['Normal'], fontSize=10, fontName='Bold', textColor=colors.white, alignment=TA_CENTER)
    day_style     = ParagraphStyle('D', parent=styles['Normal'], fontSize=10, fontName='Bold', textColor=GREEN_DARK, alignment=TA_CENTER)
    footer_style  = ParagraphStyle('F', parent=styles['Normal'], fontSize=8, textColor=colors.gray, fontName='Regular')

    story = []
    story.append(Paragraph("Tedenski jedilnik · OŠ Koseze", title_style))
    story.append(Paragraph(f"Teden: {data.get('weekLabel', '')}", subtitle_style))

    header_row = [
        Paragraph("DAN", header_style),
        Paragraph("MALICA", header_style),
        Paragraph("KOSILO", header_style),
        Paragraph("POPOLDANSKA MALICA", header_style),
    ]
    table_data = [header_row]
    for day in DAYS:
        table_data.append([
            Paragraph(day, day_style),
            Paragraph(strip_allergens(data["malica"].get(day, "—")), cell_style),
            Paragraph(strip_allergens(data["kosilo"].get(day, "—")), cell_style),
            Paragraph(strip_allergens(data["popoldne"].get(day, "—")), cell_style),
        ])

    page_w = landscape(A4)[0] - 3*cm
    col_w = [3.5*cm] + [(page_w - 3.5*cm)/3]*3
    table = Table(table_data, colWidths=col_w, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), GREEN_DARK),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,0), 10), ('BOTTOMPADDING', (0,0), (-1,0), 10),
        ('LINEBELOW', (0,0), (-1,0), 1.5, GREEN_MID),
        ('BACKGROUND', (0,1), (0,-1), GREEN_PALE),
        ('ALIGN', (0,1), (0,-1), 'CENTER'),
        *[('BACKGROUND', (1,i), (-1,i), GRAY_LIGHT if i%2==0 else colors.white) for i in range(1,6)],
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
        ('TOPPADDING', (0,1), (-1,-1), 10), ('BOTTOMPADDING', (0,1), (-1,-1), 10),
        ('LEFTPADDING', (0,0), (-1,-1), 10), ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("* Alergeni so razvidni iz celotnega jedilnika na spletni strani šole: www.oskoseze.si", footer_style))
    doc.build(story)
    print(f"PDF generated: {output_path}")


if __name__ == "__main__":
    html = fetch_html()
    data = parse(html)

    with open("jedilnik.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("JSON OK:", data.get("weekLabel", "?"))

    generate_pdf(data, "jedilnik.pdf")
    print("Done.")
