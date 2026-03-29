"""
ÜAK Doçentlik Atıf Belgesi PDF Oluşturucu
Şablon: atıf şablonu.docx yapısına uygun
"""
import os
import fitz  # PyMuPDF
from fpdf import FPDF
from PIL import Image
import io
import tempfile


# ── Renkler (şablondan alınan mavi tonlar) ─────────────────────
COLOR_TITLE = (46, 83, 149)    # #2E5395 - başlık mavisi
COLOR_H1    = (68, 113, 196)   # #4471C4 - h1 mavisi
COLOR_BLACK = (0, 0, 0)
COLOR_GRAY  = (100, 100, 100)
COLOR_LIGHT = (220, 230, 242)  # açık mavi arka plan

# ── Sayfa boyutu: A4 ───────────────────────────────────────────
W, H   = 210, 297
MARGIN = 20


class AtifPDF(FPDF):
    def __init__(self):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=MARGIN)
        self._load_fonts()

    def _load_fonts(self):
        """Use built-in fonts; add DejaVu for Turkish if available."""
        # fpdf2 built-in core fonts don't support Turkish chars well.
        # We'll embed a Unicode font. fpdf2 ships with DejaVu.
        font_dir = os.path.join(os.path.dirname(__file__), 'fonts')
        arial = os.path.join(font_dir, 'Arial.ttf')
        arial_b = os.path.join(font_dir, 'Arial-Bold.ttf')
        if os.path.exists(arial):
            self.add_font('Arial', '', arial)
            self.add_font('Arial', 'B', arial_b if os.path.exists(arial_b) else arial)
            self._font = 'Arial'
        else:
            self._font = 'Helvetica'

    def _set(self, size=11, bold=False, color=COLOR_BLACK):
        style = 'B' if bold else ''
        self.set_font(self._font, style, size)
        self.set_text_color(*color)

    def header(self):
        pass  # özel header yok

    def footer(self):
        self.set_y(-12)
        self._set(8, color=COLOR_GRAY)
        self.cell(0, 5, f'Sayfa {self.page_no()}', align='C')


def _extract_page_image(pdf_path: str, page_no: int) -> bytes:
    """Extract a PDF page as JPEG bytes."""
    doc = fitz.open(pdf_path)
    pg = doc.load_page(page_no)
    mat = fitz.Matrix(2.0, 2.0)  # 2x scale for quality
    pix = pg.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes('jpeg')
    doc.close()
    return img_bytes


def _image_bytes_to_temp(data: bytes, suffix='.jpg') -> str:
    """Write image bytes to a temp file and return path."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.close()
    return tmp.name


def _fit_image(pdf: AtifPDF, img_path: str, label: str):
    """Add labelled image fitting full content width."""
    content_w = W - 2 * MARGIN
    content_h = H - 2 * MARGIN - 30

    # Get image dimensions
    with Image.open(img_path) as im:
        iw, ih = im.size

    ratio = iw / ih if ih else 1
    disp_w = content_w
    disp_h = disp_w / ratio
    if disp_h > content_h:
        disp_h = content_h
        disp_w = disp_h * ratio

    # Label above image
    pdf._set(11, bold=True, color=COLOR_H1)
    pdf.cell(0, 7, label, ln=True)
    pdf.ln(1)

    # Border box
    x = MARGIN + (content_w - disp_w) / 2
    pdf.set_draw_color(*COLOR_LIGHT)
    pdf.set_line_width(0.3)
    pdf.rect(x - 1, pdf.get_y() - 1, disp_w + 2, disp_h + 2)

    pdf.image(img_path, x=x, y=pdf.get_y(), w=disp_w, h=disp_h)
    pdf.ln(disp_h + 4)


def generate_citation_pdf(data: dict, output_path: str, upload_folder: str):
    """
    data = {
        "eser_adi": str,
        "yok_id": str,
        "atiflar": [
            {
                "sira": int,
                "künye": str,
                "indeks": str,           # optional
                "pages": {
                    "unvan": {"file_id": ..., "page": int} | {"image_path": str},
                    "baslik": {...},
                    "atif_sayfasi": {...},
                    "kaynakca": {...}
                }
            },
            ...
        ]
    }
    """
    pdf = AtifPDF()
    temps = []

    # ══════════════════════════════════════════════
    # SAYFA 1 – Kapak / Özet
    # ══════════════════════════════════════════════
    pdf.add_page()

    # Başlık - eser adı (altı çizili, arka plan yok)
    style = 'BU' if True else 'B'  # Bold + Underline
    pdf.set_font(pdf._font, 'BU', 15)
    pdf.set_text_color(*COLOR_TITLE)
    eser_adi = data.get('eser_adi', '')
    yok_id   = data.get('yok_id', '')
    title_text = f"Eser Adı: {eser_adi}"
    if yok_id:
        title_text += f" (Eser YÖK İd:{yok_id})"
    pdf.multi_cell(0, 9, title_text)
    pdf.ln(4)

    # "Atıflar" başlığı
    pdf._set(13, bold=True, color=COLOR_H1)
    pdf.cell(0, 8, 'Atıflar', ln=True)
    pdf.ln(2)

    # Atıflar listesi
    atiflar = data.get('atiflar', [])
    for i, atif in enumerate(atiflar, 1):
        pdf._set(10, color=COLOR_BLACK)
        kunye = atif.get('künye', atif.get('kunye', ''))
        # Numbered list
        prefix = f'{i}. '
        pdf.set_x(MARGIN)
        pdf.multi_cell(W - 2 * MARGIN, 6, prefix + kunye)
        pdf.ln(1)

    # ══════════════════════════════════════════════
    # Her atıf için 1 bölüm
    # ══════════════════════════════════════════════
    for i, atif in enumerate(atiflar, 1):
        pdf.add_page()

        # Atıf başlığı (arka plan yok)
        pdf._set(13, bold=True, color=COLOR_H1)
        pdf.cell(0, 9, f'Atıf {i}', ln=True)
        pdf.ln(3)

        # Künye
        pdf._set(10, color=COLOR_BLACK)
        kunye = atif.get('künye', atif.get('kunye', ''))
        pdf.multi_cell(0, 6, kunye)
        pdf.ln(2)

        # İndeks bilgisi
        indeks = atif.get('indeks', '')
        if indeks:
            pdf._set(9, bold=True, color=COLOR_GRAY)
            pdf.cell(0, 5, f'İndeks: {indeks}', ln=True)
            pdf.ln(2)

        pdf.set_draw_color(*COLOR_LIGHT)
        pdf.line(MARGIN, pdf.get_y(), W - MARGIN, pdf.get_y())
        pdf.ln(4)

        pages_cfg = atif.get('pages', {})

        # optional=True → seçilmemişse atla (placeholder gösterme)
        slot_labels = [
            ('unvan',         f'A{i}. Yayının Ünvan Sayfası (kitap, dergi, vb.)', False),
            ('unvan2',        f'A{i}. Yayının Ünvan Sayfası (kitap, dergi, vb.)', True),
            ('baslik',        f'A{i}. Eserin Başlık Sayfası',                     False),
            ('baslik2',       f'A{i}. Eserin Başlık Sayfası 2',                   True),
            ('atif_sayfasi',  f'A{i}. Eserde ilk atıf yapılan sayfa',             False),
            ('kaynakca',      f'A{i}. Kaynakça Sayfası',                          False),
        ]

        for slot_key, label, optional in slot_labels:
            slot = pages_cfg.get(slot_key)
            if not slot:
                if optional:
                    continue
                # Placeholder
                _draw_placeholder(pdf, label)
                continue

            img_bytes = _resolve_slot(slot, upload_folder)
            if img_bytes is None:
                _draw_placeholder(pdf, label)
                continue

            tmp_path = _image_bytes_to_temp(img_bytes)
            temps.append(tmp_path)

            # New page if not enough space (need at least ~80mm)
            if pdf.get_y() + 85 > H - MARGIN:
                pdf.add_page()

            _fit_image(pdf, tmp_path, label)

    pdf.output(output_path)

    # Cleanup temp files
    for t in temps:
        try:
            os.unlink(t)
        except Exception:
            pass


def _resolve_slot(slot: dict, upload_folder: str):
    """
    slot can be:
      {"file_id": "...", "page": 0}   -> extract from uploaded PDF
      {"image_path": "/absolute/..."}  -> direct image
      {"image_data": "<base64>"}       -> base64 encoded image
    Returns bytes or None.
    """
    if not slot:
        return None

    if 'file_id' in slot:
        file_id = slot['file_id']
        page_no = int(slot.get('page', 0))
        pdf_path = os.path.join(upload_folder, f'{file_id}.pdf')
        if not os.path.exists(pdf_path):
            return None
        return _extract_page_image(pdf_path, page_no)

    if 'image_path' in slot:
        p = slot['image_path']
        if os.path.exists(p):
            with open(p, 'rb') as f:
                return f.read()
        return None

    if 'image_data' in slot:
        import base64
        return base64.b64decode(slot['image_data'])

    return None


def _draw_placeholder(pdf: AtifPDF, label: str):
    """Draw a dashed placeholder box."""
    content_w = W - 2 * MARGIN
    box_h = 40

    if pdf.get_y() + box_h + 10 > H - MARGIN:
        pdf.add_page()

    pdf._set(11, bold=True, color=COLOR_H1)
    pdf.cell(0, 7, label, ln=True)
    pdf.ln(1)

    y = pdf.get_y()
    pdf.set_draw_color(180, 180, 180)
    pdf.set_dash_pattern(dash=3, gap=2)
    pdf.rect(MARGIN, y, content_w, box_h)
    pdf.set_dash_pattern()

    pdf._set(9, color=(180, 180, 180))
    pdf.set_y(y + box_h / 2 - 3)
    pdf.cell(0, 5, '[ Görsel yüklenmedi ]', align='C', ln=True)
    pdf.ln(4)
