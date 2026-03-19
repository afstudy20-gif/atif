'use strict';

// ── Smart paste: "6944499Eser Başlığı" → YÖK ID + başlık ──
document.addEventListener('DOMContentLoaded', () => {
  const eserInput = document.getElementById('eser-adi');
  const yokInput  = document.getElementById('yok-id');

  eserInput.addEventListener('paste', e => {
    const text = (e.clipboardData || window.clipboardData).getData('text').trim();
    const m = text.match(/^(\d+)(.+)$/s);
    if (m) {
      e.preventDefault();
      yokInput.value  = m[1].trim();
      eserInput.value = m[2].trim();
      showToast(`YÖK ID: ${m[1].trim()} — başlık otomatik ayrıştırıldı`, 'success');
    }
  });
});

// ── Toast ────────────────────────────────────────
function showToast(msg, type = '') {
  let el = document.getElementById('toast');
  if (!el) { el = document.createElement('div'); el.id = 'toast'; document.body.appendChild(el); }
  el.textContent = msg;
  el.className = type ? `show ${type}` : 'show';
  clearTimeout(el._t);
  el._t = setTimeout(() => (el.className = ''), 3000);
}

// ── State ────────────────────────────────────────
// atiflar[i] = { kunye, indeks, fileId, totalPages, jcrFileId, jcrTotalPages,
//               pages: { unvan, baslik, atif_sayfasi, kaynakca } }
// pages[slot] = { file_id, page }
let atiflar = [];
let atifCounter = 0;

// ── Modal state ──────────────────────────────────
let modal = {
  fileId: null,
  totalPages: 1,
  currentPage: 0,
  onSelect: null,    // callback(page)
  title: '',
};

// ── Atıf count badge ─────────────────────────────
function updateBadge() {
  document.getElementById('atif-count-badge').textContent = atiflar.length;
}

// ── Add citation ─────────────────────────────────
document.getElementById('btn-add-atif').addEventListener('click', addAtif);

function addAtif() {
  const idx = atifCounter++;
  atiflar.push({ kunye: '', indeks: '', fileId: null, totalPages: 0, jcrFileId: null, jcrTotalPages: 0, pages: {} });

  const tmpl = document.getElementById('atif-template');
  const clone = tmpl.content.cloneNode(true);
  const card = clone.querySelector('.atif-card');
  card.dataset.index = idx;
  card.querySelector('.num').textContent = atiflar.length;

  // Radio name unique per card
  card.querySelectorAll('.indeks-input').forEach(r => r.name = `indeks_${idx}`);

  // collapse toggle
  card.querySelector('.atif-header').addEventListener('click', e => {
    if (e.target.closest('.atif-header-actions')) return;
    card.classList.toggle('collapsed');
    card.querySelector('.collapse-btn').textContent =
      card.classList.contains('collapsed') ? '▼' : '▲';
  });

  // Remove
  card.querySelector('.remove-atif').addEventListener('click', () => {
    const pos = cardPos(card);
    if (pos !== -1) atiflar.splice(pos, 1);
    card.remove();
    renumber();
    updateBadge();
  });

  // DOI
  card.querySelector('.doi-fetch').addEventListener('click', () => fetchDOI(card, idx));
  card.querySelector('.doi-input').addEventListener('keydown', e => { if (e.key === 'Enter') fetchDOI(card, idx); });

  // İndeks sync
  card.querySelectorAll('.indeks-input').forEach(r => {
    r.addEventListener('change', e => syncField(idx, 'indeks', e.target.value));
  });

  // Künye sync
  card.querySelector('.kunye-input').addEventListener('input', e => syncField(idx, 'kunye', e.target.value));

  // Makale PDF upload
  card.querySelector('.pdf-file-input').addEventListener('change', e => uploadPDF(card, idx, e.target.files[0]));

  // JCR PDF upload
  card.querySelector('.jcr-file-input').addEventListener('change', e => uploadJCR(card, idx, e.target.files[0]));

  // Slot pick buttons
  card.querySelectorAll('.slot').forEach(slot => {
    const slotKey = slot.dataset.slot;
    const btn = slot.querySelector('.slot-pick-btn');
    btn.addEventListener('click', () => {
      const pos = cardPos(card);
      if (pos === -1) return;
      const isJcr = slotKey === 'unvan';
      const fid   = isJcr ? atiflar[pos].jcrFileId  : atiflar[pos].fileId;
      const pages = isJcr ? atiflar[pos].jcrTotalPages : atiflar[pos].totalPages;
      if (!fid) { showToast(isJcr ? 'Önce JCR PDF yükleyin' : 'Önce makale PDF yükleyin', 'error'); return; }
      openModal(fid, pages, slotKey, page => selectPage(card, idx, slotKey, page));
    });
  });

  document.getElementById('atiflar-list').appendChild(clone);
  updateBadge();
}

// ── Helpers ──────────────────────────────────────
function cardPos(card) {
  const idx = parseInt(card.dataset.index);
  let pos = -1;
  document.querySelectorAll('.atif-card').forEach((c, i) => {
    if (parseInt(c.dataset.index) === idx) pos = i;
  });
  return pos;
}

function syncField(idx, field, value) {
  document.querySelectorAll('.atif-card').forEach((c, i) => {
    if (parseInt(c.dataset.index) === idx) atiflar[i][field] = value;
  });
}

function renumber() {
  document.querySelectorAll('.atif-card').forEach((c, i) => {
    c.querySelector('.num').textContent = i + 1;
  });
}

// ── DOI Lookup ───────────────────────────────────
async function fetchDOI(card, idx) {
  const doi = card.querySelector('.doi-input').value.trim();
  if (!doi) { showToast('DOI girin', 'error'); return; }
  const btn = card.querySelector('.doi-fetch');
  btn.textContent = '...'; btn.disabled = true;
  try {
    const resp = await fetch(`/api/doi?doi=${encodeURIComponent(doi)}`);
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || 'Hata');
    card.querySelector('.kunye-input').value = data.citation;
    syncField(idx, 'kunye', data.citation);
    showToast('Künye oluşturuldu', 'success');
  } catch (e) {
    showToast('DOI sorgulanamadı: ' + e.message, 'error');
  } finally {
    btn.textContent = 'DOI Sorgula'; btn.disabled = false;
  }
}

// ── JCR PDF Upload ───────────────────────────────
async function uploadJCR(card, idx, file) {
  if (!file) return;
  const area = card.querySelector('.pdf-upload-area[data-pdftype="jcr"]');
  area.querySelector('.pdf-status-text').textContent = 'Yükleniyor...';
  const fd = new FormData();
  fd.append('file', file);
  try {
    const resp = await fetch('/api/pdf/info', { method: 'POST', body: fd });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error);

    const pos = cardPos(card);
    if (pos !== -1) {
      atiflar[pos].jcrFileId     = data.file_id;
      atiflar[pos].jcrTotalPages = data.pages;
    }

    area.classList.add('has-pdf');
    area.querySelector('.pdf-name-text').textContent = file.name;
    area.querySelector('.pdf-pages-text').textContent = `(${data.pages} sayfa)`;

    // Enable unvan slot pick + auto-select page 0
    card.querySelector('.slot[data-slot="unvan"] .slot-pick-btn').disabled = false;
    selectPage(card, idx, 'unvan', 0);

    showToast(`JCR PDF yüklendi — ünvan sayfası otomatik seçildi`, 'success');
  } catch (e) {
    showToast('JCR PDF yüklenemedi: ' + e.message, 'error');
  }
}

// ── PDF Upload (shared per atıf) ─────────────────
async function uploadPDF(card, idx, file) {
  if (!file) return;
  const area = card.querySelector('.pdf-upload-area[data-pdftype="makale"]');
  const statusText = area.querySelector('.pdf-status-text');
  statusText.textContent = 'Yükleniyor...';

  const fd = new FormData();
  fd.append('file', file);
  try {
    const resp = await fetch('/api/pdf/info', { method: 'POST', body: fd });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error);

    // Save to state
    const pos = cardPos(card);
    if (pos !== -1) {
      atiflar[pos].fileId = data.file_id;
      atiflar[pos].totalPages = data.pages;
    }

    // Update UI
    area.classList.add('has-pdf');
    area.querySelector('.pdf-name-text').textContent = file.name;
    area.querySelector('.pdf-pages-text').textContent = `(${data.pages} sayfa)`;

    // Enable makale slotlarını (unvan JCR'a ait, ayrı yönetiliyor)
    ['baslik', 'baslik2', 'atif_sayfasi', 'kaynakca'].forEach(s => {
      card.querySelector(`.slot[data-slot="${s}"] .slot-pick-btn`).disabled = false;
    });

    // Auto-set defaults: başlık = sayfa 1, kaynakça = son sayfa
    selectPage(card, idx, 'baslik',   0);
    selectPage(card, idx, 'kaynakca', data.pages - 1);

    // İlk atıf sayfası = manual, vurgula
    const atifSlot = card.querySelector('.slot[data-slot="atif_sayfasi"]');
    atifSlot.querySelector('.slot-pick-btn').classList.add('btn-primary');
    atifSlot.querySelector('.slot-pick-btn').classList.remove('btn-secondary');

    showToast(`${data.pages} sayfalı PDF yüklendi — DOI aranıyor...`, 'success');

    // DOI çıkar ve otomatik künye sorgula
    extractAndFetchDOI(card, idx, data.file_id);
  } catch (e) {
    showToast('PDF yüklenemedi: ' + e.message, 'error');
    statusText.textContent = 'Hata: ' + e.message;
  }
}

// ── DOI çıkarma + otomatik künye ─────────────────
async function extractAndFetchDOI(card, idx, fileId) {
  const doiInput   = card.querySelector('.doi-input');
  const kunyeInput = card.querySelector('.kunye-input');

  try {
    const resp = await fetch(`/api/pdf/extract-doi/${fileId}`);
    const data = await resp.json();

    if (!data.doi) {
      showToast('PDF\'den DOI bulunamadı — manuel girebilirsiniz', '');
      return;
    }

    doiInput.value = data.doi;

    // Künye zaten doluysa üzerine yazma
    if (kunyeInput.value.trim()) {
      showToast(`DOI bulundu: ${data.doi}`, 'success');
      return;
    }

    // CrossRef'ten künye çek
    showToast(`DOI bulundu: ${data.doi} — künye çekiliyor...`, 'success');
    const cr = await fetch(`/api/doi?doi=${encodeURIComponent(data.doi)}`);
    const crData = await cr.json();
    if (cr.ok && crData.citation) {
      kunyeInput.value = crData.citation;
      syncField(idx, 'kunye', crData.citation);
      showToast('Künye otomatik dolduruldu', 'success');
    } else {
      showToast(`DOI bulundu ama künye çekilemedi — manuel girebilirsiniz`, '');
    }
  } catch (e) {
    // Sessizce geç, kullanıcıyı engelleme
  }
}

// ── Page Selection ───────────────────────────────
function selectPage(card, idx, slotKey, page) {
  const pos = cardPos(card);
  if (pos === -1) return;
  const isJcr = slotKey === 'unvan';
  const fileId = isJcr ? atiflar[pos].jcrFileId : atiflar[pos].fileId;
  if (!fileId) return;

  atiflar[pos].pages[slotKey] = { file_id: fileId, page };

  const slot = card.querySelector(`.slot[data-slot="${slotKey}"]`);
  slot.classList.add('has-page');
  slot.querySelector('.slot-thumb').src = `/api/pdf/preview/${fileId}/${page}`;

  const btn = slot.querySelector('.slot-pick-btn');
  btn.textContent = `Sayfa ${page + 1} ✓`;

  // atif_sayfasi seçilince primary rengi kaldır (tamamlandı)
  if (slotKey === 'atif_sayfasi') {
    btn.classList.remove('btn-primary');
    btn.classList.add('btn-secondary');
  }
}

// ── Modal ─────────────────────────────────────────
const modalEl       = document.getElementById('page-modal');
const modalImg      = document.getElementById('modal-preview-img');
const modalPageInfo = document.getElementById('modal-page-info');
const modalTitle    = document.getElementById('modal-title');

function openModal(fileId, totalPages, slotKey, onSelect) {
  const labels = {
    unvan:         'Yayının Ünvan Sayfası',
    baslik:        'Eserin Başlık Sayfası',
    baslik2:       'Eserin Başlık Sayfası 2',
    atif_sayfasi:  'İlk Atıf Yapılan Sayfa',
    kaynakca:      'Kaynakça Sayfası',
  };
  modal.fileId     = fileId;
  modal.totalPages = totalPages;
  modal.currentPage = 0;
  modal.onSelect   = onSelect;
  modal.title      = labels[slotKey] || slotKey;
  modalTitle.textContent = modal.title;
  modalEl.classList.remove('hidden');
  loadModalPage(0);
}

function loadModalPage(page) {
  modal.currentPage = Math.max(0, Math.min(page, modal.totalPages - 1));
  modalPageInfo.textContent = `Sayfa ${modal.currentPage + 1} / ${modal.totalPages}`;
  modalImg.src = `/api/pdf/preview/${modal.fileId}/${modal.currentPage}`;
}

function closeModal() { modalEl.classList.add('hidden'); }

document.getElementById('modal-prev').addEventListener('click', () => loadModalPage(modal.currentPage - 1));
document.getElementById('modal-next').addEventListener('click', () => loadModalPage(modal.currentPage + 1));
document.getElementById('modal-select').addEventListener('click', () => {
  if (modal.onSelect) modal.onSelect(modal.currentPage);
  closeModal();
  showToast(`Sayfa ${modal.currentPage + 1} seçildi`, 'success');
});
document.querySelector('.modal-close').addEventListener('click', closeModal);
document.querySelector('.modal-backdrop').addEventListener('click', closeModal);

// Keyboard nav in modal
document.addEventListener('keydown', e => {
  if (modalEl.classList.contains('hidden')) return;
  if (e.key === 'ArrowLeft')  loadModalPage(modal.currentPage - 1);
  if (e.key === 'ArrowRight') loadModalPage(modal.currentPage + 1);
  if (e.key === 'Enter')      document.getElementById('modal-select').click();
  if (e.key === 'Escape')     closeModal();
});

// ── Generate PDF ─────────────────────────────────
document.getElementById('btn-generate').addEventListener('click', async () => {
  const eserAdi = document.getElementById('eser-adi').value.trim();
  const yokId   = document.getElementById('yok-id').value.trim();
  if (!eserAdi)          { showToast('Eser adı gerekli', 'error'); return; }
  if (!atiflar.length)   { showToast('En az bir atıf ekleyin', 'error'); return; }

  // Sync all text fields from DOM
  document.querySelectorAll('.atif-card').forEach((card, pos) => {
    atiflar[pos].kunye = card.querySelector('.kunye-input').value;
    const checked = card.querySelector('.indeks-input:checked');
    if (checked) atiflar[pos].indeks = checked.value;
  });

  const payload = {
    eser_adi: eserAdi,
    yok_id:   yokId,
    atiflar: atiflar.map((a, i) => ({
      sira:   i + 1,
      künye:  a.kunye,
      indeks: a.indeks,
      pages:  a.pages,
    })),
  };

  const prog = document.getElementById('progress-bar');
  const dl   = document.getElementById('download-area');
  prog.classList.remove('hidden');
  dl.classList.add('hidden');
  document.getElementById('generate-info').textContent = 'PDF oluşturuluyor...';

  try {
    const resp = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || 'Sunucu hatası');
const link = document.getElementById('download-link');

const fallbackTitle = eserAdi.trim().split(/\s+/).slice(0, 5).join('_').replace(/[\\/:*?"<>|;,]/g, '');
const fallbackIndeks = (atiflar[0]?.indeks || '').trim().split(/\s+/)[0].replace(/[\\/:*?"<>|;,()]/g, '');
const fallbackName = (fallbackTitle + (fallbackIndeks ? '_' + fallbackIndeks : '')) + '.pdf';

const finalName = data.download_name || fallbackName;

link.href = `/api/download/${data.file_id}?name=${encodeURIComponent(finalName)}`;
link.download = finalName;
dl.classList.remove('hidden');
    document.getElementById('generate-info').textContent = 'PDF hazır!';
    showToast('PDF oluşturuldu', 'success');
  } catch (e) {
    document.getElementById('generate-info').textContent = 'Hata: ' + e.message;
    showToast('PDF oluşturulamadı: ' + e.message, 'error');
  } finally {
    prog.classList.add('hidden');
  }
});

// Start with one empty citation
addAtif();
