/* Melody reader: спіс песень, скан побач з нотамі, прайграванне і распазнанне новых сканаў. */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var VARIANTS = ['voice', 'lira', 'duda'];
  var DEFAULT_BPM = 80;
  var FLAGS = {
    disagree: 'два прагоны прачыталі па-рознаму',
    duration: 'даўжыня нот не адпавядае памеру',
    'fermata-dot': 'фэрмата побач з кропкай, магчыма, кропка лішняя',
    range: 'нота далёка ад дыяпазону песні'
  };
  var VOTES = {
    A: 'трэці прагон за паказаны варыянт',
    B: 'трэці прагон за другі варыянт',
    unknown: 'трэці прагон не вырашыў'
  };

  // ---------- small storage helpers ----------
  function load(key, fallback) {
    try { var v = localStorage.getItem('mr.' + key); return v === null ? fallback : JSON.parse(v); } catch (e) { return fallback; }
  }
  function save(key, value) {
    try { localStorage.setItem('mr.' + key, JSON.stringify(value)); } catch (e) {}
  }

  // Songs recognised on this device live in IndexedDB (they hold images).
  var db = (function () {
    var opening = null;
    function open() {
      if (opening) return opening;
      opening = new Promise(function (resolve, reject) {
        if (!window.indexedDB) { reject(new Error('no IndexedDB')); return; }
        var req = indexedDB.open('melody-reader', 1);
        req.onupgradeneeded = function () { req.result.createObjectStore('songs', { keyPath: 'id' }); };
        req.onsuccess = function () { resolve(req.result); };
        req.onerror = function () { reject(req.error); };
      });
      return opening;
    }
    function run(mode, fn) {
      return open().then(function (d) {
        return new Promise(function (resolve, reject) {
          var tx = d.transaction('songs', mode), store = tx.objectStore('songs'), req = fn(store);
          tx.oncomplete = function () { resolve(req && req.result); };
          tx.onerror = function () { reject(tx.error); };
        });
      });
    }
    return {
      all: function () { return run('readonly', function (s) { return s.getAll(); }).catch(function () { return []; }); },
      get: function (id) { return run('readonly', function (s) { return s.get(id); }); },
      put: function (rec) { return run('readwrite', function (s) { return s.put(rec); }); },
      del: function (id) { return run('readwrite', function (s) { return s.delete(id); }); }
    };
  })();

  // ---------- state ----------
  var config = { server: '' };
  var repo = [];       // catalogue of the repository's songs
  var local = [];      // songs recognised on this device
  var current = null;  // {key, song, musicxml, image, local}
  var objectUrls = [];

  function serverUrl() { return (load('server', '') || config.server || '').replace(/\/+$/, ''); }

  function toast(text, ms) {
    var t = $('toast'); t.textContent = text; t.hidden = false;
    clearTimeout(toast.timer); toast.timer = setTimeout(function () { t.hidden = true; }, ms || 4000);
  }

  function songNumber(id) { var m = /^m_(\d+[a-z]?)/i.exec(id); return m ? m[1] : null; }
  function displayTitle(entry) {
    if (entry.title) return entry.title;
    var n = songNumber(entry.id);
    return n ? 'Песня № ' + n : entry.id;
  }
  function plural(n, one, few, many) {
    var m10 = n % 10, m100 = n % 100;
    return n + ' ' + (m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many);
  }
  function doubtful(song) { return song.measures.filter(function (m) { return m.flags && m.flags.length; }); }

  // ---------- list ----------
  function renderList() {
    var q = $('filter').value.trim().toLowerCase();
    function match(e) { return !q || (displayTitle(e) + ' ' + e.id).toLowerCase().indexOf(q) >= 0; }
    function item(e, key) {
      var li = document.createElement('li'), a = document.createElement('a');
      a.href = '#/' + key;
      if (current && current.key === key) a.setAttribute('aria-current', 'page');
      var name = document.createElement('span'); name.className = 'name'; name.textContent = displayTitle(e);
      var badge = document.createElement('span');
      badge.className = 'badge' + (e.doubtful ? '' : ' ok');
      badge.textContent = e.doubtful ? plural(e.doubtful, 'такт', 'такты', 'тактаў') + ' праверыць' : plural(e.notes, 'нота', 'ноты', 'нот');
      a.appendChild(name); a.appendChild(badge); li.appendChild(a);
      return li;
    }
    var rs = $('repoSongs'), ls = $('localSongs');
    rs.textContent = ''; ls.textContent = '';
    repo.filter(match).forEach(function (e) { rs.appendChild(item(e, 's/' + e.id)); });
    if (!repo.length) rs.innerHTML = '<li class="muted pad">Пакуль няма песень.</li>';
    local.filter(match).forEach(function (e) { ls.appendChild(item(e, 'd/' + e.id)); });
    $('localSection').hidden = !local.length;
  }

  function loadLocal() {
    return db.all().then(function (recs) {
      local = recs.filter(function (r) { return r.id.charAt(0) !== '_'; }).sort(function (a, b) { return b.created - a.created; }).map(function (r) {
        return { id: r.id, title: r.title, notes: r.song.stats ? r.song.stats.notes : 0, doubtful: doubtful(r.song).length };
      });
    });
  }

  // ---------- routing ----------
  function route() {
    var m = /^#\/(s|d)\/(.+)$/.exec(location.hash);
    if (!m) { showEmpty(); return; }
    var id = decodeURIComponent(m[2]);
    openSong(m[1], id).catch(function (e) {
      console.error(e); toast('Не атрымалася адкрыць песню'); location.hash = '#/';
    });
  }

  function showEmpty() {
    stop();
    current = null;
    document.body.classList.remove('reading');
    $('view').hidden = true; $('player').hidden = true; $('empty').hidden = false;
    renderList();
    window.scrollTo(0, 0); $('list').scrollTop = 0;
  }

  function fetchJson(url) { return fetch(url).then(function (r) { if (!r.ok) throw new Error(url + ': ' + r.status); return r.json(); }); }
  function fetchText(url) { return fetch(url).then(function (r) { if (!r.ok) throw new Error(url + ': ' + r.status); return r.text(); }); }

  function openSong(kind, id) {
    var key = kind + '/' + id;
    if (current && current.key === key) return Promise.resolve();
    stop();
    objectUrls.forEach(URL.revokeObjectURL); objectUrls = [];
    var got;
    if (kind === 's') {
      var entry = repo.filter(function (e) { return e.id === id; })[0];
      if (!entry) return Promise.reject(new Error('unknown song ' + id));
      got = Promise.all([fetchJson('data/songs/' + id + '.json'), fetchText('data/export/' + id + '.musicxml')]).then(function (r) {
        return { key: key, song: r[0], musicxml: r[1], image: 'data/' + entry.image, title: entry.title, local: false };
      });
    } else {
      got = db.get(id).then(function (rec) {
        if (!rec) throw new Error('no local song ' + id);
        var url = URL.createObjectURL(rec.image); objectUrls.push(url);
        return { key: key, song: rec.song, musicxml: rec.musicxml, image: url, title: rec.title, local: true };
      });
    }
    return got.then(function (c) { current = c; showSong(); });
  }

  // ---------- song view ----------
  function showSong() {
    var c = current, s = c.song, flagged = doubtful(s);
    document.body.classList.add('reading');
    $('empty').hidden = true; $('view').hidden = false; $('player').hidden = false;
    $('title').textContent = displayTitle({ id: s.id, title: c.title || s.title });
    var meta = [s.time ? 'памер ' + s.time : null, s.stats ? plural(s.stats.notes, 'нота', 'ноты', 'нот') : null,
      flagged.length ? plural(flagged.length, 'сумніўны такт', 'сумніўныя такты', 'сумніўных тактаў') : 'сумніўных тактаў няма'];
    $('meta').textContent = meta.filter(Boolean).join(' · ');
    $('remove').hidden = !c.local;
    $('song').scrollTop = 0; window.scrollTo(0, 0);
    renderList();

    // scan with boxes over doubtful bars
    var img = $('scanImg'), svg = $('scanSvg'), W = s.source.width, H = s.source.height;
    img.src = c.image;
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.setAttribute('preserveAspectRatio', 'none');
    var parts = flagged.map(function (m) {
      var b = m.box; if (!b) return '';
      return '<rect class="flagbox" data-m="' + m.index + '" x="' + b[0] + '" y="' + b[1] + '" width="' + (b[2] - b[0]) + '" height="' + (b[3] - b[1]) + '" rx="6"/>';
    });
    svg.innerHTML = parts.join('') + '<circle class="dot" id="dot" r="' + Math.max(8, (s.systems[0] ? s.systems[0].unit : 12) * 0.9) + '" cx="-50" cy="-50"/>';

    // list of doubtful bars
    var list = $('doubtList'); list.textContent = '';
    flagged.forEach(function (m) {
      var li = document.createElement('li'), b = document.createElement('button');
      b.type = 'button'; b.textContent = 'Такт ' + m.index; b.title = 'Іграць з гэтага такта';
      b.onclick = function () { play(s.measures.indexOf(m)); };
      var why = m.flags.map(function (f) { return FLAGS[f] || f; });
      if (m.vote && VOTES[m.vote.choice]) why.push(VOTES[m.vote.choice]);
      var span = document.createElement('span'); span.textContent = why.join('; ');
      li.appendChild(b); li.appendChild(span); list.appendChild(li);
    });
    $('doubts').hidden = !flagged.length;

    $('bpm').value = bpmFor(s); showBpm();
    renderNotation();
  }

  function bpmFor(s) { var all = load('bpm', {}); return all[s.id] || s.bpm || DEFAULT_BPM; }
  function showBpm() { $('bpmV').textContent = $('bpm').value; }

  // ---------- notation (Verovio, loaded on first use) ----------
  var verovioReady = null, tk = null;
  function loadVerovio() {
    if (verovioReady) return verovioReady;
    verovioReady = new Promise(function (resolve, reject) {
      var sc = document.createElement('script');
      sc.src = 'vendor/verovio-toolkit-wasm.js';
      sc.onload = function () {
        function done() { tk = new verovio.toolkit(); resolve(tk); }
        if (verovio.module.calledRun) done(); else verovio.module.onRuntimeInitialized = done;
      };
      sc.onerror = function () { verovioReady = null; reject(new Error('verovio')); };
      document.head.appendChild(sc);
    });
    return verovioReady;
  }

  var noteEls = [];   // per measure: elements of its notes and rests, in the JSON's order
  function renderNotation() {
    var box = $('notation'), c = current;
    return loadVerovio().then(function () {
      if (current !== c) return;
      var width = Math.max(280, box.clientWidth - 16), small = width < 600, scale = small ? 34 : 50;
      tk.setOptions({
        pageWidth: Math.round(width * 100 / scale), scale: scale, adjustPageHeight: true, breaks: 'auto',
        header: 'none', footer: 'none', pageMarginTop: 40, pageMarginBottom: 20, pageMarginLeft: 20, pageMarginRight: 20,
        spacingSystem: small ? 6 : 10, svgViewBox: true
      });
      tk.loadData(c.musicxml);
      var html = '';
      for (var p = 1; p <= tk.getPageCount(); p++) html += tk.renderToSVG(p);
      box.innerHTML = html;
      var measures = box.querySelectorAll('g.measure');
      noteEls = [];
      c.song.measures.forEach(function (m, k) {
        var g = measures[k];
        noteEls.push(g ? Array.prototype.slice.call(g.querySelectorAll('g.note, g.rest, g.mRest')) : []);
        if (!g) return;
        g.dataset.k = k;
        if (m.flags && m.flags.length) {
          g.classList.add('flag');
          try {
            var bb = g.getBBox(), r = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            r.setAttribute('class', 'flagbg'); r.setAttribute('x', bb.x - 40); r.setAttribute('y', bb.y - 80);
            r.setAttribute('width', bb.width + 80); r.setAttribute('height', bb.height + 160); r.setAttribute('rx', 60);
            g.insertBefore(r, g.firstChild);
          } catch (e) {}
        }
      });
    }).catch(function () {
      box.innerHTML = '<p class="muted pad">Не атрымалася загрузіць нотны запіс. Праверце сувязь з інтэрнэтам.</p>';
    });
  }

  $('notation').addEventListener('click', function (e) {
    var g = e.target.closest && e.target.closest('g.measure');
    if (g && g.dataset.k !== undefined) play(+g.dataset.k);
  });
  $('scanSvg').addEventListener('click', function (e) {
    var r = e.target.closest && e.target.closest('rect.flagbox');
    if (!r || !current) return;
    var idx = +r.dataset.m, k = current.song.measures.findIndex(function (m) { return m.index === idx; });
    if (k >= 0) play(k);
  });

  // ---------- playback ----------
  var PC = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
  function midiOf(p) {
    var m = /^([A-G])(#{1,2}|b{1,2})?(-?\d+)$/.exec(p);
    if (!m) return 60;
    var acc = m[2] ? (m[2][0] === '#' ? m[2].length : -m[2].length) : 0;
    return 12 * (+m[3] + 1) + PC[m[1]] + acc;
  }

  // Song JSON -> events for the sound engine: [midi or -1, beats, fermata, system, x, y].
  // `refs[i]` says which notes event i covers, for the cursor.
  function events(song, fromMeasure) {
    var W = song.source.width, H = song.source.height, ev = [], refs = [], tieOpen = null, grace = 0;
    song.measures.forEach(function (m, k) {
      if (k < fromMeasure) return;
      m.notes.forEach(function (n, j) {
        var ref = { k: k, j: j };
        if (n.grace) {  // a short note borrowed from the next one
          if (n.pitch) { ev.push([midiOf(n.pitch), 0.125, 0, m.system, n.x / W, n.y / H]); refs.push([ref]); grace += 0.125; }
          return;
        }
        var dur = Math.max(0.0625, n.dur - grace); grace = 0;
        if (n.pitch && tieOpen && tieOpen.midi === midiOf(n.pitch)) {
          tieOpen.e[1] += dur; tieOpen.refs.push(ref);
          if (n.fermata) tieOpen.e[2] = 1;
          if (n.tie !== 'continue') tieOpen = null;
          return;
        }
        var e = [n.pitch ? midiOf(n.pitch) : -1, dur, n.fermata ? 1 : 0, m.system, n.x / W, n.y / H], r = [ref];
        ev.push(e); refs.push(r);
        tieOpen = n.pitch && (n.tie === 'start' || n.tie === 'continue') ? { midi: e[0], e: e, refs: r } : null;
      });
    });
    return { ev: ev, refs: refs };
  }

  var ctx = null, playing = null, raf = 0, lit = [];
  var variant = load('variant', 'voice');
  if (VARIANTS.indexOf(variant) < 0) variant = 'voice';

  function audio() {
    if (ctx) return ctx;
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    try { if (navigator.audioSession) navigator.audioSession.type = 'playback'; } catch (e) {}
    ctx = new AC({ latencyHint: 'playback' });
    return ctx;
  }

  function play(fromMeasure) {
    if (!current) return;
    stop();
    if (!audio()) { toast('Гэты браўзер не можа іграць гук'); return; }
    if (ctx.state !== 'running') ctx.resume();
    var built = events(current.song, fromMeasure || 0);
    if (!built.ev.length) return;
    var out = ctx.createGain(); out.connect(ctx.destination);
    var song = { bpm: +$('bpm').value, ev: built.ev, syl: 'a' };
    var S = Lab.render(ctx, out, song, variant, { tempo: 1, ornaments: true, rubato: false, just: false, acoustic: 'site', t0: ctx.currentTime + 0.25 });
    playing = { S: S, out: out, refs: built.refs };
    $('playIcon').innerHTML = '<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>';
    $('play').setAttribute('aria-label', 'Спыніць');
    tick();
  }

  function stop() {
    cancelAnimationFrame(raf);
    light([]);
    var dot = $('dot'); if (dot) { dot.setAttribute('cx', -50); dot.setAttribute('cy', -50); }
    $('playIcon').innerHTML = '<path d="M7 4.5v15l13-7.5z"/>';
    $('play').setAttribute('aria-label', 'Іграць');
    if (!playing) return;
    var p = playing, now = ctx.currentTime; playing = null;
    p.out.gain.setTargetAtTime(0, now, 0.03);
    p.S.nodes.forEach(function (n) { try { n.stop(now + 0.2); } catch (e) {} });
    setTimeout(function () { try { p.out.disconnect(); } catch (e) {} }, 400);
  }

  function light(els) {
    lit.forEach(function (el) { el.classList.remove('now'); });
    lit = els; lit.forEach(function (el) { el.classList.add('now'); });
  }

  function tick() {
    if (!playing) return;
    var now = ctx.currentTime, notes = playing.S.tl.notes, n = null;
    for (var i = 0; i < notes.length; i++) { if (notes[i].t <= now) n = notes[i]; else break; }
    if (n) {
      var els = [];
      playing.refs[n.src].forEach(function (r) { var el = (noteEls[r.k] || [])[r.j]; if (el) els.push(el); });
      if (els[0] !== lit[0]) light(els);
      var dot = $('dot'), s = current.song;
      dot.setAttribute('cx', n.x * s.source.width); dot.setAttribute('cy', n.y * s.source.height);
    }
    if (now > playing.S.tl.total + 0.6) { stop(); return; }
    raf = requestAnimationFrame(tick);
  }

  $('play').onclick = function () { if (playing) stop(); else play(0); };
  function markVoices() {
    $('voices').querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.v === variant ? 'true' : 'false'); });
  }
  $('voices').querySelectorAll('button').forEach(function (b) {
    b.onclick = function () { variant = b.dataset.v; save('variant', variant); markVoices(); if (playing) play(0); };
  });
  $('bpm').oninput = showBpm;
  $('bpm').onchange = function () {
    if (!current) return;
    var all = load('bpm', {}); all[current.song.id] = +$('bpm').value; save('bpm', all);
    if (playing) play(0);
  };
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && playing && ctx.state !== 'running') ctx.resume();
  });

  // ---------- downloads, removal ----------
  function download(name, text, type) {
    var url = URL.createObjectURL(new Blob([text], { type: type })), a = document.createElement('a');
    a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    $('view').querySelector('.more').open = false;
  }
  $('dlJson').onclick = function () { download(current.song.id + '.json', JSON.stringify(current.song, null, 1), 'application/json'); };
  $('dlXml').onclick = function () { download(current.song.id + '.musicxml', current.musicxml, 'application/vnd.recordare.musicxml+xml'); };
  $('remove').onclick = function () {
    if (!current || !current.local || !confirm('Выдаліць гэтую песню з прылады?')) return;
    var id = current.key.slice(2);
    db.del(id).then(loadLocal).then(function () { location.hash = '#/'; });
  };
  document.addEventListener('click', function (e) {
    var more = $('view').querySelector('.more');
    if (more.open && !more.contains(e.target)) more.open = false;
  });

  // ---------- recognising a new scan ----------
  // A photo is turned upright and made no larger than the server will use, so it uploads faster.
  var MAX_SIDE = 2400;
  function prepareImage(file) {
    if (/pdf$/i.test(file.type) || /\.pdf$/i.test(file.name)) return Promise.resolve(file);
    if (!window.createImageBitmap) return Promise.resolve(file);
    return createImageBitmap(file, { imageOrientation: 'from-image' }).then(function (bmp) {
      var k = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height));
      var cv = document.createElement('canvas');
      cv.width = Math.round(bmp.width * k); cv.height = Math.round(bmp.height * k);
      cv.getContext('2d').drawImage(bmp, 0, 0, cv.width, cv.height);
      var png = /png$/i.test(file.type);
      return new Promise(function (resolve) {
        cv.toBlob(function (b) { resolve(b || file); }, png ? 'image/png' : 'image/jpeg', 0.92);
      });
    }).catch(function () { return file; });
  }

  function baseName(name) { return (name || 'scan').replace(/\.[^.]+$/, '').replace(/[^\w\-]+/g, '_').slice(0, 60) || 'scan'; }

  var job = null; // {id, server, name, title, started, stage, image}

  function renderJob() {
    var box = $('jobs'); box.textContent = '';
    if (!job) return;
    var d = document.createElement('div'); d.className = 'job' + (job.stage === 'failed' ? ' failed' : '');
    var text = {
      waking: 'Сервер прачынаецца. Калі ім даўно не карысталіся, гэта займае да 2 хвілін.',
      sending: 'Адпраўляю файл…',
      queued: job.ahead ? 'У чарзе, перад вамі ' + job.ahead + '.' : 'У чарзе…',
      running: 'Распазнаю ноты. Звычайна гэта займае 20–90 секунд' + (job.seconds ? ', ужо ' + job.seconds + ' с.' : '.'),
      failed: job.error || 'Не атрымалася распазнаць.'
    }[job.stage] || '';
    d.innerHTML = '<strong></strong><p></p><div class="bar"><i></i></div>';
    d.querySelector('strong').textContent = job.title;
    d.querySelector('p').textContent = text;
    if (job.stage === 'failed') {
      var row = document.createElement('div'); row.className = 'row';
      var close = document.createElement('button'); close.className = 'btn'; close.type = 'button'; close.textContent = 'Закрыць';
      close.onclick = function () { job = null; save('job', null); renderJob(); };
      row.appendChild(close); d.appendChild(row);
    }
    box.appendChild(d);
  }

  function fail(text) {
    job.stage = 'failed'; job.error = text; save('job', null); renderJob();
  }

  function delay(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function wake(server) {
    var until = Date.now() + 4 * 60 * 1000, first = true;
    function attempt() {
      return fetch(server + '/', { cache: 'no-store' }).then(function (r) {
        if (r.ok) return r.json().then(function (j) { if (!j.ok) throw new Error('not ready'); });
        throw new Error('status ' + r.status);
      }).catch(function (e) {
        if (Date.now() > until) throw e;
        if (first) { first = false; job.stage = 'waking'; renderJob(); }
        return delay(5000).then(attempt);
      });
    }
    return attempt();
  }

  function startJob(file) {
    var server = serverUrl();
    if (!server) { toast('Спачатку ўвядзіце адрас сервера ў наладах', 6000); $('settingsDlg').showModal(); return; }
    if (job && job.stage !== 'failed') { toast('Пачакайце, пакуль скончыцца папярэдні скан'); return; }
    var name = baseName(file.name === 'image.jpg' ? 'foto_' + new Date().toISOString().slice(0, 16).replace(/\D/g, '') : file.name);
    job = { server: server, name: name, title: name, stage: 'sending', started: Date.now() };
    renderJob();
    if (window.matchMedia('(max-width: 899px)').matches && location.hash.length > 2) location.hash = '#/';
    window.scrollTo(0, 0); $('list').scrollTop = 0;
    prepareImage(file).then(function (blob) {
      job.image = blob;
      return wake(server).then(function () {
        job.stage = 'sending'; renderJob();
        var fd = new FormData(), ext = /pdf/i.test(blob.type) || /\.pdf$/i.test(file.name) ? '.pdf' : /png/i.test(blob.type) ? '.png' : '.jpg';
        fd.append('file', blob, name + ext);
        return fetch(server + '/jobs', { method: 'POST', body: fd });
      });
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.detail || 'Сервер адказаў памылкай ' + r.status);
        job.id = j.id; job.stage = 'queued'; job.ahead = j.ahead;
        save('job', { id: job.id, server: server, name: name, title: job.title, started: job.started });
        stashImage(job.image);
        renderJob(); poll();
      });
    }).catch(function (e) {
      fail(e && e.message && !/fetch|network|load failed/i.test(e.message) ? e.message : 'Няма сувязі з серверам. Праверце адрас у наладах і інтэрнэт.');
    });
  }

  // The uploaded image waits in IndexedDB too, so a reload during recognition does not lose it.
  function stashImage(blob) { if (blob && !/pdf/i.test(blob.type)) db.put({ id: '_pending', image: blob, song: { measures: [] }, created: 0 }).catch(function () {}); }

  function poll() {
    if (!job || !job.id) return;
    var j = job;
    fetch(j.server + '/jobs/' + j.id, { cache: 'no-store' }).then(function (r) {
      if (r.status === 404) throw new Error('lost');
      return r.json();
    }).then(function (res) {
      if (job !== j) return;
      if (res.status === 'done') return finish(res.pages);
      if (res.status === 'failed') { fail('Не атрымалася распазнаць: ' + res.error); return; }
      j.stage = res.status; j.ahead = res.ahead; j.seconds = res.seconds; renderJob();
      setTimeout(poll, 3000);
    }).catch(function (e) {
      if (job !== j) return;
      if (e.message === 'lost') { fail('Сервер перазапусціўся і згубіў заданне. Паспрабуйце яшчэ раз.'); return; }
      setTimeout(poll, 6000);
    });
  }

  function dataUrlToBlob(url) { return fetch(url).then(function (r) { return r.blob(); }); }

  function finish(pages) {
    var j = job, stamp = Date.now();
    var image = j.image ? Promise.resolve(j.image) : db.get('_pending').then(function (r) { return r && r.image; }).catch(function () { return null; });
    return image.then(function (img) {
      return Promise.all(pages.map(function (p, i) {
        return (p.image ? dataUrlToBlob(p.image) : Promise.resolve(img)).then(function (blob) {
          var rec = {
            id: p.song.id + '-' + stamp.toString(36),
            title: pages.length > 1 ? j.title + ', с. ' + (i + 1) : j.title,
            song: p.song, musicxml: p.musicxml, image: blob, created: stamp + i
          };
          return db.put(rec).then(function () { return rec; });
        });
      }));
    }).then(function (recs) {
      db.del('_pending').catch(function () {});
      job = null; save('job', null); renderJob();
      return loadLocal().then(function () {
        renderList();
        toast(recs.length > 1 ? 'Гатова: ' + recs.length + ' старонкі' : 'Гатова');
        location.hash = '#/d/' + encodeURIComponent(recs[0].id);
      });
    }).catch(function () { fail('Ноты распазнаныя, але не атрымалася захаваць іх на прыладзе.'); });
  }

  function resumeJob() {
    var saved = load('job', null);
    if (!saved || !saved.id) return;
    job = { id: saved.id, server: saved.server, name: saved.name, title: saved.title, started: saved.started, stage: 'queued' };
    renderJob(); poll();
  }

  function picked(input) {
    return function () { var f = input.files && input.files[0]; input.value = ''; if (f) startJob(f); };
  }
  $('camera').onclick = function () { $('cameraInput').click(); };
  $('upload').onclick = function () { $('fileInput').click(); };
  $('cameraInput').onchange = picked($('cameraInput'));
  $('fileInput').onchange = picked($('fileInput'));
  // Desktop: drop a file anywhere on the page.
  document.addEventListener('dragover', function (e) { e.preventDefault(); });
  document.addEventListener('drop', function (e) {
    e.preventDefault();
    var f = e.dataTransfer && e.dataTransfer.files[0];
    if (f) startJob(f);
  });

  // ---------- settings ----------
  $('settings').onclick = function () { $('serverUrl').value = load('server', '') || config.server || ''; $('settingsDlg').showModal(); };
  $('settingsDlg').addEventListener('close', function () {
    if ($('settingsDlg').returnValue !== 'save') return;
    var v = $('serverUrl').value.trim().replace(/\/+$/, '');
    save('server', v && v !== config.server ? v : '');
    toast('Захавана');
  });

  // ---------- start ----------
  var resizeTimer = 0, lastWidth = 0;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      var w = $('notation').clientWidth;
      if (current && tk && Math.abs(w - lastWidth) > 40) { lastWidth = w; stop(); renderNotation(); }
    }, 250);
  });
  $('filter').oninput = renderList;
  window.addEventListener('hashchange', route);
  markVoices();

  Promise.all([
    fetchJson('config.json').then(function (c) { config = c; }).catch(function () {}),
    fetchJson('data/index.json').then(function (list) { repo = list; }).catch(function () { repo = []; }),
    loadLocal()
  ]).then(function () { renderList(); route(); resumeJob(); });

  if ('serviceWorker' in navigator && location.protocol === 'https:') {
    navigator.serviceWorker.register('sw.js').catch(function () {});
  }
})();
