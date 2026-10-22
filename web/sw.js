/* Offline support: the app itself comes from the cache, songs from the network when it is there. */
var VERSION = '__VERSION__';
var SHELL = ['./', 'index.html', 'app.css', 'app.js', 'sound.js', 'icon.svg', 'icon-192.png', 'manifest.webmanifest'];

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open('shell-' + VERSION).then(function (c) { return c.addAll(SHELL); }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k.indexOf('shell-') === 0 && k !== 'shell-' + VERSION; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener('fetch', function (e) {
  var req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;  // the recognition server is never cached
  var isData = url.pathname.indexOf('/data/') >= 0 || /config\.json$/.test(url.pathname);
  var isVendor = url.pathname.indexOf('/vendor/') >= 0;
  if (isData) {
    // network first, so new songs show up; the cache keeps them for offline use
    e.respondWith(fetch(req).then(function (res) {
      var copy = res.clone(); caches.open('data').then(function (c) { c.put(req, copy); });
      return res;
    }).catch(function () { return caches.match(req); }));
    return;
  }
  e.respondWith(caches.match(req, { ignoreSearch: true }).then(function (hit) {
    return hit || fetch(req).then(function (res) {
      if (res.ok && isVendor) { var copy = res.clone(); caches.open('vendor').then(function (c) { c.put(req, copy); }); }
      return res;
    });
  }));
});
