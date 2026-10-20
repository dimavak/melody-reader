/* Гук: сінтэз голасу, ліры і дуды (той жа рухавік, што ў плэеры сайта). */
var Lab = (function () {
  'use strict';

  // ---------- helpers ----------
  function rng(seed) {
    var a = seed >>> 0;
    return function () { a = (a + 0x6D2B79F5) >>> 0; var t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }
  function db(x) { return Math.pow(10, x / 20); }
  var JUST = [1, 16 / 15, 9 / 8, 6 / 5, 5 / 4, 4 / 3, 45 / 32, 3 / 2, 8 / 5, 5 / 3, 16 / 9, 15 / 8];

  // Tenor formants (Hz, dB, bandwidth Hz); «ы» is set between «і» and «у».
  var VOWELS = {
    a: [[650, 0, 80], [1080, -6, 90], [2650, -7, 120], [2900, -8, 130], [3250, -22, 140]],
    e: [[400, 0, 70], [1700, -14, 80], [2600, -12, 100], [3200, -14, 120], [3580, -20, 120]],
    i: [[290, 0, 40], [1870, -15, 90], [2800, -18, 100], [3250, -20, 120], [3540, -30, 120]],
    o: [[400, 0, 40], [800, -10, 80], [2600, -12, 100], [2800, -12, 120], [3000, -26, 120]],
    u: [[350, 0, 40], [600, -20, 60], [2700, -17, 100], [2900, -14, 120], [3300, -26, 120]],
    y: [[300, 0, 50], [1400, -12, 90], [2450, -15, 100], [2900, -20, 120], [3400, -28, 120]]
  };

  // ---------- timeline: notes in seconds, phrases, syllables ----------
  function timeline(song, o) {
    var spb = 60 / (song.bpm * o.tempo), t = 0.12 + (o.t0 || 0), out = [], ev = song.ev;
    var nNotes = ev.filter(function (e) { return e[0] >= 0; }).length, syl = song.syl || 'a', k = 0, phrase = 0, startNext = true;
    var last = null;
    for (var i = 0; i < ev.length; i++) {
      var e = ev[i], dur = e[1] * spb;
      if (e[2]) dur *= o.rubato ? 2.1 : 1.6;
      if (e[0] < 0) { t += dur; if (last) last.end = true; startNext = true; continue; }
      var nx = ev[i + 1];
      var end = !nx || nx[0] < 0 || !!e[2] || nx[3] !== e[3];
      var si = syl.length >= nNotes ? k : Math.floor(k * syl.length / nNotes);
      if (o.rubato && end && !e[2]) dur *= 1.3;
      if (startNext && out.length) phrase++;
      var n = { t: t, dur: dur, midi: e[0], start: startNext, end: end, phrase: phrase, syl: si, vowel: syl[si] || 'a', newSyl: !last || si !== last.syl, src: i, x: e[4], y: e[5] };
      out.push(n); last = n; k++;
      t += dur;
      startNext = end;
      if (o.rubato && end && nx && nx[0] >= 0) t += 0.35 * spb;   // breath between phrases
    }
    out.length && (out[out.length - 1].end = true);
    for (i = 0; i < out.length; i++) out[i].prev = out[i - 1] || null, out[i].next = out[i + 1] || null;
    var tonic = out.length ? out[out.length - 1].midi : 60;
    return { notes: out, tonic: tonic, total: t + 0.2, spb: spb };
  }
  function freqOf(midi, tonic, just) {
    if (!just) return 440 * Math.pow(2, (midi - 69) / 12);
    var d = midi - tonic, oct = Math.floor(d / 12), s = d - oct * 12;
    return 440 * Math.pow(2, (tonic - 69) / 12) * JUST[s] * Math.pow(2, oct);
  }
  function phrases(notes) {
    var ps = [];
    notes.forEach(function (n) { (ps[n.phrase] = ps[n.phrase] || []).push(n); });
    return ps.filter(Boolean);
  }

  // ---------- shared audio resources per context ----------
  function res(ctx) {
    if (ctx._lab) return ctx._lab;
    var sr = ctx.sampleRate, noise = ctx.createBuffer(1, sr * 2, sr), d = noise.getChannelData(0), r = rng(7);
    for (var i = 0; i < d.length; i++) d[i] = r() * 2 - 1;
    function wave(h) { return ctx.createPeriodicWave(new Float32Array(h.length), new Float32Array(h)); }
    var glottal = [0]; for (i = 1; i < 60; i++) glottal.push(Math.pow(i, -1.15) * (i % 2 ? 1 : 0.92));
    var bow = [0]; for (i = 1; i < 40; i++) bow.push(Math.pow(i, -1.0) * (1 + 0.25 * Math.sin(i * 1.7)));
    var reed = [0, 1, .95, .85, .6, .62, .4, .34, .25, .22, .16, .14, .1, .09, .06, .05];
    var dreed = [0, 1, .7, .8, .5, .55, .35, .38, .25, .24, .15, .14, .1, .08];
    var sap = [0, 1, .42, .2, .12, .06, .03];
    return (ctx._lab = { noise: noise, glottal: wave(glottal), bow: wave(bow), reed: wave(reed), dreed: wave(dreed), sap: wave(sap) });
  }
  function ir(ctx, kind) {
    var sr = ctx.sampleRate, spec = {
      hut: { len: .45, pow: 4, lp: .45, early: [[.009, .5], [.017, .35]] },
      yard: { len: 1.1, pow: 3.2, lp: .25, early: [[.021, .45], [.038, .3]] },
      field: { len: .7, pow: 5, lp: .6, early: [[.31, .22], [.52, .1]] },
      site: { len: 1.3, pow: 3.4, lp: 0, early: [] }
    }[kind];
    var len = Math.floor(sr * Math.max(spec.len, (spec.early.length ? spec.early[spec.early.length - 1][0] : 0) + .1)), b = ctx.createBuffer(2, len, sr), r = rng(kind.length * 31);
    for (var c = 0; c < 2; c++) {
      var d = b.getChannelData(c), y = 0, tail = Math.floor(sr * spec.len);
      for (var i = 0; i < tail; i++) { var x = (r() * 2 - 1) * Math.pow(1 - i / tail, spec.pow); y = spec.lp ? y + (1 - spec.lp) * (x - y) : x; d[i] += y; }
      spec.early.forEach(function (e) { var p = Math.floor(sr * e[0] * (1 + c * .04)); for (var j = 0; j < 160 && p + j < len; j++) d[p + j] += e[1] * (r() * 2 - 1) * Math.pow(1 - j / 160, 2); });
    }
    return b;
  }
  var WET = { hut: .2, yard: .3, field: .16, site: .18 };

  function track(S, node, start, stop) { node.start(start); node.stop(stop); S.nodes.push(node); }

  // ---------- voice ----------
  // One oscillator per phrase, so pitch glides and the syllable dips happen inside one sound.
  function voice(S, notes, p) {
    var ctx = S.ctx, R = res(ctx), o = S.opt, tl = S.tl, r = rng(p.seed);
    phrases(notes).forEach(function (ph) {
      var t0 = ph[0].t + (p.lag || 0) * (r() - .3), A = p.gain;
      var tEnd = ph[ph.length - 1].t + ph[ph.length - 1].dur;
      var osc = ctx.createOscillator(); osc.setPeriodicWave(R.glottal);
      var src = ctx.createGain(); osc.connect(src);
      var nz = ctx.createBufferSource(); nz.buffer = R.noise; nz.loop = true;
      var nzg = ctx.createGain(); nzg.gain.value = .045; nz.connect(nzg); nzg.connect(src);
      var amp = ctx.createGain(), sum = ctx.createGain(), pan = ctx.createStereoPanner ? ctx.createStereoPanner() : null;
      amp.gain.value = 0;
      sum.connect(amp);
      if (pan) { pan.pan.value = p.pan || 0; amp.connect(pan); pan.connect(S.bus); } else amp.connect(S.bus);
      var bright = o.ornaments ? 3 : 0;
      var filt = VOWELS.a.map(function (f, k) {
        var bp = ctx.createBiquadFilter(); bp.type = 'bandpass';
        var g = ctx.createGain(); src.connect(bp); bp.connect(g); g.connect(sum);
        return { bp: bp, g: g, k: k };
      });
      function setVowel(v, t, tau) {
        VOWELS[v].forEach(function (f, k) {
          var fr = f[0] * (p.scale || 1), F = filt[k], bw = f[2] * (k < 2 ? 1.7 : 1.2);
          var gain = db(f[1] + (k === 1 || k === 2 ? bright : 0)) * (k ? 1.4 : 1) * Math.sqrt(fr / bw) * .35;
          if (tau) { F.bp.frequency.setTargetAtTime(fr, t, tau); F.bp.Q.setTargetAtTime(fr / bw, t, tau); F.g.gain.setTargetAtTime(gain, t, tau); }
          else { F.bp.frequency.setValueAtTime(fr, t); F.bp.Q.setValueAtTime(fr / bw, t); F.g.gain.setValueAtTime(gain, t); }
        });
      }
      // vibrato only on long notes, plus slow drift
      var lfo = ctx.createOscillator(), lg = ctx.createGain(); lfo.frequency.value = 4.8 + r() * .8; lg.gain.value = 0; lfo.connect(lg); lg.connect(osc.detune);
      var dr = ctx.createOscillator(), dg = ctx.createGain(); dr.frequency.value = .4 + r() * .5; dg.gain.value = 5; dr.connect(dg); dg.connect(osc.detune);

      var level = 0, lastT = t0;
      function pt(t, v) { t = Math.max(t, lastT + .002); amp.gain.linearRampToValueAtTime(v, t); lastT = t; level = v; }
      amp.gain.setValueAtTime(0, t0);
      ph.forEach(function (n, j) {
        var nt = j ? n.t + (p.jit || 0) * (r() - .5) : t0, f = freqOf(n.midi + o.octave, tl.tonic + o.octave, o.just);
        var cents = (p.spread || 0) * (r() - .5) * 2;
        osc.detune.setValueAtTime(cents, nt);
        if (j === 0) {
          if (o.ornaments) { osc.frequency.setValueAtTime(f * Math.pow(2, -1.6 / 12), nt); osc.frequency.exponentialRampToValueAtTime(f, nt + .11); }
          else osc.frequency.setValueAtTime(f, nt);
          setVowel(n.vowel, nt, 0);
          pt(nt + .07, A);
        } else {
          var glide = o.ornaments ? (Math.abs(n.midi - n.prev.midi) > 2 ? .045 : .022) : .008;
          osc.frequency.setTargetAtTime(f, nt - glide * .6, glide);
          if (n.newSyl) {
            setVowel(n.vowel, nt - .02, .025);
            pt(nt - .03, level); pt(nt - .004, A * .32); pt(nt + .035, A);
          }
        }
        // accent the start of a long note a little, then let it sag
        if (n.dur > .45 && !n.end) pt(n.t + n.dur - .06, A * .82);
        lg.gain.linearRampToValueAtTime(0, nt);
        if (n.dur > .5) lg.gain.linearRampToValueAtTime(o.ornaments ? 14 : 8, nt + Math.min(.6, n.dur * .7));
        if (n.dur > .5) lg.gain.setValueAtTime(o.ornaments ? 14 : 8, nt + n.dur - .02);
        if (n.end) {
          var e0 = nt + n.dur;
          if (o.ornaments && (n.next === null || n.dur > .3)) {
            // phrase-end fall: the voice drops away from the last note
            var fs = nt + Math.max(.12, n.dur * .62);
            osc.frequency.setValueAtTime(f, fs);
            osc.frequency.exponentialRampToValueAtTime(f * Math.pow(2, -(n.next ? 3 : 5) / 12), e0 + .16);
            pt(fs, level); pt(e0 + .18, 0);
            tEnd = e0 + .18;
          } else { pt(e0 - .02, level); pt(e0 + .08, 0); tEnd = e0 + .08; }
        }
      });
      [osc, nz, lfo, dr].forEach(function (s) { track(S, s, t0, tEnd + .1); });
    });
  }

  // ---------- bowed or reed melody on one continuous oscillator ----------
  function body(ctx, dest, peaks, lp) {
    var head = ctx.createGain(), x = head;
    peaks.forEach(function (q) { var f = ctx.createBiquadFilter(); f.type = q[3] || 'peaking'; f.frequency.value = q[0]; f.gain.value = q[1]; f.Q.value = q[2]; x.connect(f); x = f; });
    var l = ctx.createBiquadFilter(); l.type = 'lowpass'; l.frequency.value = lp; x.connect(l); l.connect(dest);
    return head;
  }
  function continuous(S, notes, p) {
    var ctx = S.ctx, R = res(ctx), o = S.opt, tl = S.tl;
    var groups = p.whole ? [notes] : phrases(notes);
    var out = body(ctx, S.bus, p.peaks, p.lp);
    groups.forEach(function (ph) {
      var t0 = ph[0].t, last = ph[ph.length - 1], tEnd = last.t + last.dur + p.rel;
      var osc = ctx.createOscillator(); osc.setPeriodicWave(R[p.wave]);
      var amp = ctx.createGain(); amp.gain.value = 0; osc.connect(amp); amp.connect(out);
      if (p.noise) {
        var nz = ctx.createBufferSource(); nz.buffer = R.noise; nz.loop = true;
        var bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = p.noise[0]; bp.Q.value = p.noise[1];
        var ng = ctx.createGain(); ng.gain.value = p.noise[2]; nz.connect(bp); bp.connect(ng); ng.connect(amp);
        track(S, nz, t0, tEnd + .1);
      }
      if (p.vib) { var lfo = ctx.createOscillator(), lg = ctx.createGain(); lfo.frequency.value = p.vib[0]; lg.gain.value = p.vib[1]; lfo.connect(lg); lg.connect(osc.detune); track(S, lfo, t0, tEnd + .1); }
      var lastT = t0, level = 0;
      function pt(t, v) { t = Math.max(t, lastT + .002); amp.gain.linearRampToValueAtTime(v, t); lastT = t; level = v; }
      amp.gain.setValueAtTime(0, t0);
      ph.forEach(function (n, j) {
        var f = freqOf(n.midi + p.octave, tl.tonic + p.octave, o.just), nt = n.t;
        if (j === 0) { osc.frequency.setValueAtTime(f, nt); pt(nt + p.att, p.gain); return; }
        var same = n.midi === n.prev.midi;
        if (p.grace && (same || (o.ornaments && n.dur > .5 && j % 3 === 0))) {
          // bagpipe: a note cannot be re-struck, so a quick higher grace note separates it
          var gf = freqOf(n.midi + p.octave + (same ? 5 : 2), tl.tonic + p.octave, o.just);
          osc.frequency.setValueAtTime(gf, nt - .032); osc.frequency.setValueAtTime(f, nt);
        } else if (p.slide && o.ornaments && Math.abs(n.midi - n.prev.midi) >= 3) {
          osc.frequency.setTargetAtTime(f, nt - .05, .03);
        } else osc.frequency.setValueAtTime(f, nt);
        if (p.bowDip && (same || p.dipAll)) { pt(nt - .025, level); pt(nt - .004, p.gain * p.bowDip); pt(nt + .03, p.gain); }
      });
      var e0 = last.t + last.dur;
      if (p.sag) { var lf = freqOf(last.midi + p.octave, tl.tonic + p.octave, o.just); osc.frequency.setValueAtTime(lf, e0 - .05); osc.frequency.exponentialRampToValueAtTime(lf * Math.pow(2, -1.2 / 12), e0 + p.rel); }
      pt(e0 - .02, level); pt(e0 + p.rel, 0);
      track(S, osc, t0, tEnd + .1);
    });
    return out;
  }
  // drone over the whole song (or phrase by phrase), on the tonic and optionally its fifth
  function drone(S, p) {
    var ctx = S.ctx, R = res(ctx), o = S.opt, tl = S.tl, notes = tl.notes;
    var spans = p.phrased ? phrases(notes).map(function (ph) { return [ph[0].t, ph[ph.length - 1].t + ph[ph.length - 1].dur]; }) : [[notes[0].t, notes[notes.length - 1].t + notes[notes.length - 1].dur]];
    var out = body(ctx, S.bus, p.peaks || [], p.lp);
    p.parts.forEach(function (part) {
      var f = freqOf(tl.tonic + part[0], tl.tonic, o.just);
      spans.forEach(function (sp) {
        var osc = ctx.createOscillator(); osc.setPeriodicWave(R[p.wave]); osc.frequency.value = f; osc.detune.value = part[2] || 0;
        var s0 = Math.max(0, sp[0] - p.pre), g = ctx.createGain(); g.gain.setValueAtTime(0, s0); g.gain.linearRampToValueAtTime(part[1], s0 + p.att);
        g.gain.setValueAtTime(part[1], sp[1]); g.gain.linearRampToValueAtTime(0, sp[1] + p.rel);
        if (p.sag) { osc.frequency.setValueAtTime(f, sp[1] - .05); osc.frequency.exponentialRampToValueAtTime(f * Math.pow(2, -1.2 / 12), sp[1] + p.rel); }
        osc.connect(g); g.connect(out); track(S, osc, s0, sp[1] + p.rel + .1);
      });
    });
  }

  // ---------- the current site sound: sapilka, note by note (as folk-player.js) ----------
  function sapilka(S, notes) {
    var ctx = S.ctx, R = res(ctx), tl = S.tl;
    notes.forEach(function (n) {
      var f = freqOf(n.midi - 12, 0, false), t0 = n.t, end = t0 + Math.max(.05, n.dur * .93);
      var o = ctx.createOscillator(), g = ctx.createGain(); o.setPeriodicWave(R.sap);
      o.frequency.setValueAtTime(f * .97, t0); o.frequency.exponentialRampToValueAtTime(f, t0 + .05);
      var l = ctx.createOscillator(), lg = ctx.createGain(); l.frequency.value = 5.6; lg.gain.setValueAtTime(0, t0); lg.gain.linearRampToValueAtTime(f * .0045, t0 + .35); l.connect(lg); lg.connect(o.frequency);
      var nz = ctx.createBufferSource(), bp = ctx.createBiquadFilter(), ng = ctx.createGain(); nz.buffer = R.noise; nz.loop = true; bp.type = 'bandpass'; bp.frequency.value = Math.min(9000, f * 2); bp.Q.value = 2.2;
      ng.gain.setValueAtTime(0, t0); ng.gain.linearRampToValueAtTime(.12, t0 + .02); ng.gain.linearRampToValueAtTime(.055, t0 + .09); ng.gain.setValueAtTime(.055, end); ng.gain.linearRampToValueAtTime(0, end + .07);
      nz.connect(bp); bp.connect(ng); ng.connect(g); o.connect(g); g.connect(S.bus);
      g.gain.setValueAtTime(0, t0); g.gain.linearRampToValueAtTime(.3, t0 + .025); g.gain.setTargetAtTime(.255, t0 + .025, .15); g.gain.setValueAtTime(.255, end); g.gain.linearRampToValueAtTime(0, end + .07);
      [o, l, nz].forEach(function (s) { track(S, s, t0, end + .12); });
    });
  }

  // ---------- variants ----------
  var VARIANTS = {
    site: function (S) { sapilka(S, S.tl.notes); },
    voice: function (S) { voice(S, S.tl.notes, { seed: 11, gain: .5 }); },
    choir: function (S) {
      var all = S.tl.notes, rest = all.filter(function (n) { return n.phrase > 0; });
      voice(S, all, { seed: 21, gain: .3, pan: 0, spread: 4 });
      [[-.55, .96, 31], [.5, 1.05, 41], [-.2, 1.02, 51], [.3, .93, 61]].forEach(function (v) {
        voice(S, rest, { seed: v[2], gain: .21, pan: v[0], scale: v[1], spread: 13, jit: .035, lag: .06 });
      });
    },
    lira: function (S) {
      voice(S, S.tl.notes, { seed: 71, gain: .4, pan: -.15 });
      var lp = [[300, 7, 1.2], [720, 3, 1.5], [2300, 6, 1.4], [120, 0, .7, 'highpass']];
      continuous(S, S.tl.notes, { wave: 'bow', octave: 0, gain: .16, att: .06, rel: .12, peaks: lp, lp: 5200, noise: [1800, .8, .25], bowDip: .75, whole: false });
      drone(S, { wave: 'bow', parts: [[-12, .07], [-5, .05, 3], [-24, .06]], peaks: lp, lp: 2600, pre: .5, att: .4, rel: .4 });
    },
    duda: function (S) {
      var ch = [[350, 0, .7, 'highpass'], [1300, 7, 1.1], [2700, 3, 1.5]];
      continuous(S, S.tl.notes, { wave: 'reed', octave: 0, gain: .22, att: .05, rel: .35, peaks: ch, lp: 5500, grace: true, whole: true, sag: true, vib: [5, 3] });
      drone(S, { wave: 'dreed', parts: [[-24, .22], [-24, .08, 6]], peaks: [[600, 4, 1.2]], lp: 1500, pre: .4, att: .35, rel: .35, sag: true });
    },
    skrypka: function (S) {
      var bd = [[280, 6, 1.4], [460, 3, 2], [1050, 2, 1.5], [2900, 7, 1.2], [150, 0, .7, 'highpass']];
      continuous(S, S.tl.notes, { wave: 'bow', octave: 0, gain: .24, att: .05, rel: .1, peaks: bd, lp: 6500, noise: [4000, .7, .12], bowDip: .55, dipAll: true, slide: true, vib: [5.5, 2] });
      drone(S, { wave: 'bow', parts: [[-12, .1]], peaks: bd, lp: 3500, pre: 0, att: .06, rel: .1, phrased: true });
    }
  };

  // ---------- render ----------
  function render(ctx, dest, song, variant, opt) {
    var o = {}; for (var k in opt) o[k] = opt[k];
    if (variant === 'site') { o.just = false; o.ornaments = false; o.rubato = false; o.acoustic = 'site'; }
    o.octave = variant === 'site' ? -12 : (variant === 'voice' || variant === 'choir' || variant === 'lira') ? -12 : 0;
    var tl = timeline(song, o);
    var lim = ctx.createDynamicsCompressor(); lim.threshold.value = -4; lim.knee.value = 0; lim.ratio.value = 20; lim.attack.value = .002; lim.release.value = .1; lim.connect(dest);
    var comp = ctx.createDynamicsCompressor(); comp.threshold.value = -14; comp.ratio.value = 3; comp.connect(lim);
    var master = ctx.createGain(); master.gain.value = (GAIN[variant] || 1) * (opt.volume || 1); master.connect(comp);
    var bus = ctx.createGain(); bus.connect(master);
    var verb = ctx.createConvolver(); verb.buffer = ir(ctx, o.acoustic); var wg = ctx.createGain(); wg.gain.value = WET[o.acoustic]; bus.connect(verb); verb.connect(wg); wg.connect(master);
    var S = { ctx: ctx, bus: bus, opt: o, tl: tl, nodes: [], master: master };
    VARIANTS[variant](S);
    return S;
  }
  var GAIN = { site: 1, voice: 2.5, choir: 2.9, lira: .8, duda: .92, skrypka: .66 };

  return { render: render, timeline: timeline, GAIN: GAIN, VARIANTS: Object.keys(VARIANTS) };
})();
