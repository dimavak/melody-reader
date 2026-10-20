---
title: Melody reader
emoji: 🎼
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 7860
pinned: false
license: agpl-3.0
short_description: Recognises one-voice melodies from score scans
---

# Melody reader: сервер распазнання

Сервер для вэб-праграмы [Melody reader](https://github.com/dimavak/melody-reader). Ён прымае скан, фота або PDF і вяртае ноты ў JSON і MusicXML.

Гэты Space абнаўляецца аўтаматычна з рэпазіторыя на GitHub, таму змяняць файлы трэба там.

- `GET /` правярае, ці працуе сервер.
- `POST /jobs` прымае поле `file` і вяртае `{"id": ...}`.
- `GET /jobs/<id>` вяртае `status` (`queued`, `running`, `done` або `failed`), а калі гатова, то `pages` з полямі `song`, `musicxml` і `image` для старонак PDF.
