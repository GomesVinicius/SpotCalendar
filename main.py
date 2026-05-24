import pandas as pd
import json
import webbrowser
import os
from datetime import datetime

def gerar_calendario(arquivo_excel="musicas_data.xlsx", abrir_no_browser=True):
    df = pd.read_excel(arquivo_excel)
    df["added_at"] = pd.to_datetime(df["added_at"], utc=True)
    tracks = df[["id", "name", "playlist", "added_at", "url_song", "image", "artists"]].copy()
    tracks["added_at"] = tracks["added_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    tracks_json = json.dumps(tracks.to_dict(orient="records"), ensure_ascii=False)

    html = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Spotify Memory Calendar</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@latest/tabler-icons.min.css">
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#1f1e1e;color:#f0f0f0;display:flex;flex-direction:column;height:100vh;padding:14px 18px 10px}

.header{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;flex-shrink:0}
.brand{color:#1DB954;font-size:22px}
.label{font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#aaa;margin-bottom:2px}
.month-name{font-size:24px;font-weight:700;color:#fff;line-height:1}
.nav{display:flex;align-items:center;gap:6px}
.nav-btn{background:#2a2a2a;border:1px solid #3a3a3a;color:#ddd;width:34px;height:34px;border-radius:8px;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:16px;transition:background .15s,color .15s}
.nav-btn:hover{background:#1DB954;color:#000;border-color:#1DB954}
.nav-today{background:#2a2a2a;border:1px solid #3a3a3a;color:#ddd;height:34px;padding:0 14px;border-radius:8px;cursor:pointer;font-size:11px;letter-spacing:.08em;text-transform:uppercase;transition:background .15s,color .15s}
.nav-today:hover{background:#333;color:#fff}
.legend{font-size:11px;color:#ccc;letter-spacing:.04em}

.weekdays{display:grid;grid-template-columns:repeat(7,1fr);gap:5px;margin-bottom:5px;flex-shrink:0}
.wd{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:#aaa;text-align:center;padding:4px 0}

.grid{display:grid;grid-template-columns:repeat(7,1fr);gap:5px;flex:1;min-height:0}

/* cada célula tem altura fixa e scroll interno */
.day{
  border-radius:10px;
  border:1px solid #2e2e2e;
  padding:7px;
  background:#272626;
  display:flex;
  flex-direction:column;
  overflow-y:auto;
  overflow-x:hidden;
  transition:border-color .15s;
  scrollbar-width:thin;
  scrollbar-color:#3a3a3a transparent;
}
.day::-webkit-scrollbar{width:3px}
.day::-webkit-scrollbar-thumb{background:#3a3a3a;border-radius:2px}
.day:hover{border-color:#444}
.day.empty{border-color:transparent;background:transparent;overflow:hidden}
.day.today{border-color:#1DB954}
.day-num{font-size:12px;color:#ddd;margin-bottom:5px;flex-shrink:0;font-variant-numeric:tabular-nums;font-weight:500}
.day.today .day-num{color:#1DB954;font-weight:700}

/* grid de capas: tamanho fixo por slot, não distorce */
.covers{display:grid;gap:3px}
.cover-wrap{position:relative;cursor:pointer;border-radius:5px;overflow:hidden;width:100%}
.cover-wrap img{
  display:block;
  width:100%;
  height:100%;
  object-fit:cover;
  border-radius:5px;
  transition:transform .15s,opacity .15s;
}
/* quando só 1 música: altura fixa para não cortar */
.covers.single .cover-wrap{aspect-ratio:unset}
.covers.single .cover-wrap img{height:auto;max-height:100px}
/* múltiplas músicas: quadrado perfeito */
.covers.multi .cover-wrap{aspect-ratio:1}
.cover-wrap:hover img{transform:scale(1.08);opacity:.75}

.tooltip{position:fixed;background:#1a1a1a;border:1px solid #3a3a3a;border-radius:10px;padding:0;pointer-events:none;opacity:0;transition:opacity .1s;z-index:9999;min-width:200px;max-width:260px;overflow:hidden}
.tooltip.visible{opacity:1}
.tooltip-img{width:100%;aspect-ratio:1;object-fit:cover;display:block}
.tooltip-body{padding:10px 12px}
.tip-song{display:block;font-weight:700;font-size:13px;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tip-artist{display:block;font-size:12px;color:#1DB954;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600}
.tip-divider{display:block;height:1px;background:#2e2e2e;margin:8px 0}
.tip-row{display:flex;align-items:center;gap:6px;margin-top:5px}
.tip-row i{font-size:13px;color:#888;flex-shrink:0}
.tip-label{font-size:10px;color:#888;display:block;margin-bottom:1px;text-transform:uppercase;letter-spacing:.06em}
.tip-value{font-size:11px;color:#ccc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

.year-badge{display:inline-block;font-size:12px;font-weight:700;border-radius:5px;padding:2px 7px;letter-spacing:.03em;line-height:1.5}
.modal-item-year-badge{display:inline-block;font-size:12px;font-weight:700;border-radius:5px;padding:2px 7px;letter-spacing:.03em;line-height:1.5;margin-top:6px}

.more-btn{
  font-size:15px;
  font-weight:700;
  background:#1DB954;
  border:none;
  border-radius:5px;
  color:#000;
  cursor:pointer;
  transition:background .12s,transform .1s;
  display:flex;
  align-items:center;
  justify-content:center;
  width:100%;
  aspect-ratio:1;
  letter-spacing:-.5px;
}
.more-btn:hover{background:#1ed760;transform:scale(1.05)}

.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:10000;display:none;align-items:center;justify-content:center}
.modal-overlay.open{display:flex}
.modal{background:#272626;border:1px solid #3a3a3a;border-radius:16px;padding:24px;max-width:720px;width:92vw;max-height:82vh;overflow-y:auto;position:relative}
.modal-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:18px}
.modal-title{font-size:17px;font-weight:700;color:#fff}
.modal-date{font-size:12px;color:#1DB954;margin-top:3px}
.modal-close{background:none;border:1px solid #444;color:#ddd;width:32px;height:32px;border-radius:8px;cursor:pointer;font-size:18px;display:flex;align-items:center;justify-content:center;transition:background .12s;flex-shrink:0}
.modal-close:hover{background:#333;color:#fff}
.modal-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:12px}
.modal-item{cursor:pointer;border-radius:10px;overflow:hidden;background:#2e2e2e;border:1px solid #3a3a3a;transition:border-color .15s,transform .12s}
.modal-item:hover{border-color:#1DB954;transform:scale(1.03)}
.modal-item img{width:100%;aspect-ratio:1;object-fit:cover;display:block}
.modal-item-info{padding:10px}
.modal-item-name{font-size:12px;font-weight:700;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.modal-item-artist{font-size:11px;color:#1DB954;margin-top:2px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.modal-item-divider{height:1px;background:#3a3a3a;margin:8px 0}
.modal-item-row{display:flex;align-items:flex-start;gap:5px;margin-top:5px}
.modal-item-row i{font-size:12px;color:#888;flex-shrink:0;margin-top:1px}
.modal-item-label{font-size:9px;color:#888;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:1px}
.modal-item-value{font-size:10px;color:#ccc;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:150px}
</style>
</head>
<body>

<div class="header">
  <div style="display:flex;align-items:center;gap:10px">
    <i class="ti ti-brand-spotify brand"></i>
    <div>
      <div class="label">memórias musicais</div>
      <div class="month-name" id="month-name">—</div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:20px">
    <div class="legend" id="legend"></div>
    <div class="nav">
      <button class="nav-btn" id="prev-year" title="Ano anterior"><i class="ti ti-chevrons-left"></i></button>
      <button class="nav-btn" id="prev-month" title="Mês anterior"><i class="ti ti-chevron-left"></i></button>
      <button class="nav-today" id="go-today">Hoje</button>
      <button class="nav-btn" id="next-month" title="Próximo mês"><i class="ti ti-chevron-right"></i></button>
      <button class="nav-btn" id="next-year" title="Próximo ano"><i class="ti ti-chevrons-right"></i></button>
    </div>
  </div>
</div>

<div class="weekdays">
  <div class="wd">dom</div><div class="wd">seg</div><div class="wd">ter</div>
  <div class="wd">qua</div><div class="wd">qui</div><div class="wd">sex</div><div class="wd">sáb</div>
</div>
<div class="grid" id="cal-grid"></div>

<div class="modal-overlay" id="modal-overlay">
  <div class="modal">
    <div class="modal-header">
      <div>
        <div class="modal-title" id="modal-title"></div>
        <div class="modal-date" id="modal-date"></div>
      </div>
      <button class="modal-close" id="modal-close"><i class="ti ti-x"></i></button>
    </div>
    <div class="modal-grid" id="modal-grid"></div>
  </div>
</div>

<div class="tooltip" id="global-tooltip"></div>

<script>
const TRACKS = """ + tracks_json + """;
const MESES = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
               'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];

const nowReal = new Date();
let curYear = nowReal.getFullYear();
let curMonth = nowReal.getMonth();

const tooltip = document.getElementById('global-tooltip');

function formatDate(isoStr) {
  const d = new Date(isoStr);
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'long', year: 'numeric', timeZone: 'UTC' });
}

// Calcula cor da escala vermelho → amarelo → azul com base no ano
const ALL_YEARS = [...new Set(TRACKS.map(t => new Date(t.added_at).getUTCFullYear()))];
const MIN_YEAR = Math.min(...ALL_YEARS);
const MAX_YEAR = Math.max(...ALL_YEARS);

function yearColor(year) {
  if (MIN_YEAR === MAX_YEAR) return { bg: 'rgba(99,179,237,0.18)', text: '#63b3ed' };
  const t = (year - MIN_YEAR) / (MAX_YEAR - MIN_YEAR); // 0 = mais antigo, 1 = mais novo
  let r, g, b;
  if (t < 0.5) {
    // vermelho → amarelo
    const tt = t / 0.5;
    r = 220; g = Math.round(80 + tt * 140); b = 30;
  } else {
    // amarelo → azul
    const tt = (t - 0.5) / 0.5;
    r = Math.round(220 - tt * 160); g = Math.round(220 - tt * 90); b = Math.round(30 + tt * 210);
  }
  const bg = `rgba(${r},${g},${b},0.18)`;
  const text = `rgb(${r},${g},${b})`;
  return { bg, text };
}

function yearBadge(year, extraClass) {
  const { bg, text } = yearColor(year);
  const cls = extraClass || 'year-badge';
  return `<span class="${cls}" style="background:${bg};color:${text}">${year}</span>`;
}

function showTooltip(el, song) {
  tooltip.innerHTML = `
    <img class="tooltip-img" src="${song.image}" alt="${song.name}">
    <div class="tooltip-body">
      <span class="tip-song">${song.name}</span>
      <span class="tip-artist">${song.artists || 'Artista desconhecido'}</span>
      ${yearBadge(song.year)}
      <span class="tip-divider"></span>
      <div class="tip-row"><i class="ti ti-calendar"></i><div><span class="tip-label">Adicionado em</span><span class="tip-value">${formatDate(song.added_at)}</span></div></div>
      <div class="tip-row"><i class="ti ti-music"></i><div><span class="tip-label">Playlist</span><span class="tip-value">${song.playlist}</span></div></div>
    </div>`;
  tooltip.classList.add('visible');
  requestAnimationFrame(() => {
    const r = el.getBoundingClientRect();
    const tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
    let top = r.top - th - 8;
    let left = r.left + r.width / 2 - tw / 2;
    if (top < 8) top = r.bottom + 8;
    if (left < 8) left = 8;
    if (left + tw > window.innerWidth - 8) left = window.innerWidth - tw - 8;
    tooltip.style.top = top + 'px';
    tooltip.style.left = left + 'px';
  });
}
function hideTooltip() { tooltip.classList.remove('visible'); }

function openModal(day, songs) {
  document.getElementById('modal-title').textContent = songs.length + ' música' + (songs.length > 1 ? 's' : '') + ' neste dia';
  document.getElementById('modal-date').textContent = day + ' de ' + MESES[curMonth] + ' — vários anos';
  const mgrid = document.getElementById('modal-grid');
  mgrid.innerHTML = '';
  songs.forEach(s => {
    const item = document.createElement('div');
    item.className = 'modal-item';
    item.innerHTML = `<img src="${s.image}" alt="${s.name}"><div class="modal-item-info"><div class="modal-item-name">${s.name}</div><div class="modal-item-artist">${s.artists || 'Artista desconhecido'}</div>${yearBadge(s.year, 'modal-item-year-badge')}<div class="modal-item-divider"></div><div class="modal-item-row"><i class="ti ti-calendar"></i><div><span class="modal-item-label">Adicionado em</span><span class="modal-item-value">${formatDate(s.added_at)}</span></div></div><div class="modal-item-row"><i class="ti ti-music"></i><div><span class="modal-item-label">Playlist</span><span class="modal-item-value">${s.playlist}</span></div></div></div>`;
    item.addEventListener('click', () => window.open(s.url_song, '_blank'));
    mgrid.appendChild(item);
  });
  document.getElementById('modal-overlay').classList.add('open');
}

document.getElementById('modal-close').addEventListener('click', () => {
  document.getElementById('modal-overlay').classList.remove('open');
});
document.getElementById('modal-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('modal-overlay'))
    document.getElementById('modal-overlay').classList.remove('open');
});

// Número de colunas fixo por quantidade de músicas visíveis
// Sempre deixa 1 slot reservado para o +N quando há excesso
const MAX_VISIBLE = 6; // slots visíveis (incluindo o +N)

function getCols(totalSongs) {
  const show = Math.min(totalSongs, MAX_VISIBLE);
  if (show === 1) return 1;
  if (show <= 4) return 2;
  return 3;
}

function buildCalendar() {
  const year = curYear, month = curMonth;
  const isCurrentMonth = (nowReal.getFullYear() === year && nowReal.getMonth() === month);
  const today = nowReal.getDate();

  document.getElementById('month-name').textContent = MESES[month] + ' ' + year;

  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstDow = new Date(year, month, 1).getDay();

  const byDay = {};
  TRACKS.forEach(t => {
    const d = new Date(t.added_at);
    const tm = d.getUTCMonth(), td = d.getUTCDate(), ty = d.getUTCFullYear();
    if (tm === month && ty !== year) {
      if (!byDay[td]) byDay[td] = [];
      byDay[td].push({...t, year: ty});
    }
  });
  Object.values(byDay).forEach(arr => arr.sort((a, b) => b.year - a.year));

  const grid = document.getElementById('cal-grid');
  grid.innerHTML = '';

  for (let i = 0; i < firstDow; i++) {
    const e = document.createElement('div'); e.className = 'day empty'; grid.appendChild(e);
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const cell = document.createElement('div');
    cell.className = 'day' + (isCurrentMonth && d === today ? ' today' : '');

    const num = document.createElement('span');
    num.className = 'day-num';
    num.textContent = d;
    cell.appendChild(num);

    const songs = byDay[d] || [];
    if (songs.length > 0) {
      const hasMore = songs.length > MAX_VISIBLE;
      // reserva 1 slot para o botão +N quando necessário
      const showImgs = hasMore ? MAX_VISIBLE - 1 : songs.length;
      const cols = getCols(songs.length);

      const covers = document.createElement('div');
      covers.className = 'covers ' + (songs.length === 1 ? 'single' : 'multi');
      // grid com colunas fixas — todas as células têm exatamente o mesmo tamanho
      covers.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;

      songs.slice(0, showImgs).forEach(s => {
        const wrap = document.createElement('div');
        wrap.className = 'cover-wrap';
        const img = document.createElement('img');
        img.src = s.image;
        img.alt = s.name;
        // sem width/height inline — o CSS aspect-ratio + grid cuida do tamanho uniforme
        wrap.appendChild(img);
        wrap.addEventListener('mouseenter', () => showTooltip(img, s));
        wrap.addEventListener('mouseleave', hideTooltip);
        wrap.addEventListener('click', ev => { ev.stopPropagation(); window.open(s.url_song, '_blank'); });
        covers.appendChild(wrap);
      });

      if (hasMore) {
        const more = document.createElement('button');
        more.className = 'more-btn';
        more.textContent = '+' + (songs.length - showImgs);
        more.addEventListener('click', ev => { ev.stopPropagation(); openModal(d, songs); });
        covers.appendChild(more);
      }

      cell.appendChild(covers);
    }
    grid.appendChild(cell);
  }

  const total = Object.values(byDay).reduce((a, b) => a + b.length, 0);
  document.getElementById('legend').textContent =
    total > 0 ? total + ' música' + (total > 1 ? 's' : '') + ' neste mês em anos anteriores' : 'nenhuma música neste mês em anos anteriores';
}

document.getElementById('prev-month').addEventListener('click', () => { curMonth--; if(curMonth<0){curMonth=11;curYear--;} buildCalendar(); });
document.getElementById('next-month').addEventListener('click', () => { curMonth++; if(curMonth>11){curMonth=0;curYear++;} buildCalendar(); });
document.getElementById('prev-year').addEventListener('click', () => { curYear--; buildCalendar(); });
document.getElementById('next-year').addEventListener('click', () => { curYear++; buildCalendar(); });
document.getElementById('go-today').addEventListener('click', () => { curYear=nowReal.getFullYear(); curMonth=nowReal.getMonth(); buildCalendar(); });
window.addEventListener('resize', buildCalendar);
buildCalendar();
</script>
</body>
</html>"""

    output_path = "spotify_calendar.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Calendário gerado: {output_path}")
    print(f"📅 Mês: {datetime.now().strftime('%B %Y')}")
    print(f"🎵 Total de registros lidos: {len(df)}")

    if abrir_no_browser:
        webbrowser.open("file://" + os.path.abspath(output_path))

if __name__ == "__main__":
    gerar_calendario()
