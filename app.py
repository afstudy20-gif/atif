import os
import uuid
import time
import tempfile
import shutil
import requests
from flask import Flask, request, jsonify, send_file, render_template, abort
from werkzeug.utils import secure_filename
import re
import fitz  # PyMuPDF

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

FILE_TTL_SECONDS = 2 * 60 * 60  # 2 saat


def _validate_pdf(path: str) -> bool:
    """Magic bytes kontrolü: gerçek PDF mi?"""
    try:
        with open(path, 'rb') as f:
            return f.read(4) == b'%PDF'
    except Exception:
        return False


def _cleanup_old_files():
    """TTL geçmiş dosyaları sil (her yüklemede tetiklenir)."""
    now = time.time()
    for fname in os.listdir(UPLOAD_FOLDER):
        fpath = os.path.join(UPLOAD_FOLDER, fname)
        try:
            if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > FILE_TTL_SECONDS:
                os.remove(fpath)
        except Exception:
            pass


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/doi', methods=['GET'])
def lookup_doi():
    doi = request.args.get('doi', '').strip()
    if not doi:
        return jsonify({'error': 'DOI gerekli'}), 400
    try:
        url = f'https://api.crossref.org/works/{doi}'
        resp = requests.get(url, timeout=10, headers={'User-Agent': 'AtifSistemi/1.0'})
        if resp.status_code != 200:
            return jsonify({'error': 'DOI bulunamadı'}), 404
        data = resp.json()['message']
        authors = []
        for a in data.get('author', []):
            name = f"{a.get('family', '')}, {a.get('given', '')[:1]}."
            authors.append(name.strip(', '))
        author_str = '; '.join(authors) if authors else ''
        title = ' '.join(data.get('title', ['']))
        journal = data.get('container-title', [''])[0] if data.get('container-title') else ''
        year = ''
        if data.get('published-print'):
            year = str(data['published-print']['date-parts'][0][0])
        elif data.get('published-online'):
            year = str(data['published-online']['date-parts'][0][0])
        volume = data.get('volume', '')
        issue = data.get('issue', '')
        pages = data.get('page', '')
        citation = author_str
        if title:
            citation += f' "{title}."'
        if journal:
            citation += f' {journal}'
        if volume:
            citation += f' {volume}'
        if issue:
            citation += f'({issue})'
        if year:
            citation += f' ({year})'
        if pages:
            citation += f': {pages}'
        citation += '.'
        return jsonify({
            'citation': citation.strip(),
            'title': title,
            'authors': author_str,
            'journal': journal,
            'year': year,
            'volume': volume,
            'issue': issue,
            'pages': pages,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pdf/info', methods=['POST'])
def pdf_info():
    """Return number of pages in uploaded PDF."""
    if 'file' not in request.files:
        return jsonify({'error': 'Dosya yok'}), 400
    f = request.files['file']
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    f.save(tmp.name)
    tmp.close()
    try:
        # Magic bytes doğrulaması
        if not _validate_pdf(tmp.name):
            os.unlink(tmp.name)
            return jsonify({'error': 'Geçersiz dosya — PDF değil'}), 400

        doc = fitz.open(tmp.name)
        pages = doc.page_count
        doc.close()
        file_id = str(uuid.uuid4())
        dest = os.path.join(UPLOAD_FOLDER, f'{file_id}.pdf')
        shutil.move(tmp.name, dest)

        # Eski dosyaları temizle
        _cleanup_old_files()

        return jsonify({'file_id': file_id, 'pages': pages})
    except Exception as e:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        return jsonify({'error': str(e)}), 500


@app.route('/api/pdf/preview/<file_id>/<int:page>')
def pdf_preview(file_id, page):
    """Return a page of the PDF as JPEG image."""
    # Basic security: only allow hex uuid format
    if not all(c in '0123456789abcdef-' for c in file_id):
        return 'Geçersiz', 400
    path = os.path.join(UPLOAD_FOLDER, f'{file_id}.pdf')
    if not os.path.exists(path):
        return 'Bulunamadı', 404
    try:
        doc = fitz.open(path)
        if page < 0 or page >= doc.page_count:
            doc.close()
            return 'Sayfa yok', 404
        pg = doc.load_page(page)
        mat = fitz.Matrix(1.5, 1.5)
        pix = pg.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes('jpeg')
        doc.close()
        from flask import Response
        return Response(img_bytes, mimetype='image/jpeg')
    except Exception as e:
        return str(e), 500


@app.route('/api/pdf/extract-doi/<file_id>')
def extract_doi(file_id):
    """Extract DOI from first 3 pages of an uploaded PDF."""
    import re
    if not all(c in '0123456789abcdef-' for c in file_id):
        return jsonify({'error': 'Geçersiz'}), 400
    path = os.path.join(UPLOAD_FOLDER, f'{file_id}.pdf')
    if not os.path.exists(path):
        return jsonify({'error': 'Dosya yok'}), 404
    try:
        doc = fitz.open(path)
        text = ''
        for i in range(min(3, doc.page_count)):
            text += doc.load_page(i).get_text()
        doc.close()

        # DOI pattern: 10.XXXX/anything (stops at whitespace or common delimiters)
        pattern = r'\b(10\.\d{4,9}/[^\s\]\[\"\'<>|,;]+)'
        matches = re.findall(pattern, text)
        if matches:
            # Clean trailing punctuation
            doi = re.sub(r'[.,;:)\]]+$', '', matches[0])
            return jsonify({'doi': doi})
        return jsonify({'doi': None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route('/api/pdf/search/<file_id>')
def pdf_search(file_id):
    """Search text in PDF and return matching page numbers."""
    if not all(c in '0123456789abcdef-' for c in file_id):
        return jsonify({'error': 'Geçersiz'}), 400
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'Arama terimi gerekli'}), 400
    path = os.path.join(UPLOAD_FOLDER, f'{file_id}.pdf')
    if not os.path.exists(path):
        return jsonify({'error': 'Dosya yok'}), 404
    try:
        doc = fitz.open(path)
        pages = []
        for i in range(doc.page_count):
            hits = doc.load_page(i).search_for(query, flags=fitz.TEXT_DEHYPHENATE)
            if hits:
                pages.append(i)
        doc.close()
        return jsonify({'pages': pages, 'total': len(pages)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


INDEKS_KISALTMA = {
    'a)': 'SCI',
    'b)': 'BKCI',
    'c)': 'TRDizin',
    'd)': 'Diger',
}

def build_download_name(data):
    eser_adi = (data.get('eser_adi') or '').strip()
    atiflar = data.get('atiflar') or []

    atif_count = len(atiflar)
    title_words = eser_adi.split()[:5]
    title_part = '_'.join(title_words)

    indeks_kisaltma = ''
    if atiflar and isinstance(atiflar, list):
        ilk_indeks = (atiflar[0].get('indeks') or '').strip()
        prefix = ilk_indeks.split()[0].lower() if ilk_indeks else ''
        indeks_kisaltma = INDEKS_KISALTMA.get(prefix, ilk_indeks.split()[0] if ilk_indeks else '')

    parts = [str(atif_count), indeks_kisaltma, title_part]
    raw_name = '-'.join(p for p in parts if p)
    raw_name = re.sub(r'[\\/:*?"<>|;,()]+', '', raw_name)
    raw_name = re.sub(r'\s+', '_', raw_name).strip('_')
    safe_name = secure_filename(raw_name)

    return f"{safe_name or 'atif_belgesi'}.pdf"
@app.route('/api/generate', methods=['POST'])
@app.route('/api/generate', methods=['POST'])
def generate():
    """Generate citation PDF from form data."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Veri yok'}), 400

    from pdf_generator import generate_citation_pdf

    output_id = str(uuid.uuid4())
    output_path = os.path.join(UPLOAD_FOLDER, f'{output_id}_atif.pdf')
    download_name = build_download_name(data)

    try:
        generate_citation_pdf(data, output_path, UPLOAD_FOLDER)
        return jsonify({
            'file_id': output_id,
            'download_name': download_name
        })
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'detail': traceback.format_exc()}), 500


@app.route('/api/download/<file_id>')
def download(file_id):
    if not all(c in '0123456789abcdef-' for c in file_id):
        return 'Geçersiz', 400

    path = os.path.join(UPLOAD_FOLDER, f'{file_id}_atif.pdf')
    if not os.path.exists(path):
        return 'Bulunamadı', 404

    requested_name = request.args.get('name', 'atif_belgesi.pdf')
    safe_name = secure_filename(requested_name) or 'atif_belgesi.pdf'

    return send_file(path, as_attachment=True, download_name=safe_name)


if __name__ == '__main__':
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug, port=5050)
