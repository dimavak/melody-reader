# melody-reader

Праграма распазнае аднагалосыя мелодыі з выяў нотаў (сканаў або PDF). Яна стварае JSON песні, з якім працуе рэдактар, і файл MusicXML.

Праект архітэктуры: [Праграма распазнання нот](https://claude.ai/artifact/QEAbdanZg6BzZpiixh9mWi).

## Як гэта працуе

1. Скан (PNG, JPG або PDF) кладзецца ў тэчку `scans/`.
2. GitHub Actions ([recognize.yml](.github/workflows/recognize.yml)) распазнае яго двойчы праз [homr](https://github.com/liebharc/homr): спачатку арыгінал, потым копію, павялічаную ў 2 разы. Асноўным лічыцца прагон 2x.
3. Вынікі параўноўваюцца па тактах. Такт пазначаецца як сумніўны, калі:
   - прагоны разышліся (`disagree`);
   - сума працягласцей не адпавядае памеру (`duration`);
   - над нотай з кропкай стаіць фэрмата (`fermata-dot`);
   - нота выходзіць далёка за дыяпазон песні (`range`).
4. Калі ёсць ключ Claude API, Claude разглядае выразку скана кожнага такта, дзе прагоны разышліся, і выбірае варыянт A або B (або адказвае «невядома»). Гэта толькі падказка: такт застаецца пазначаным для праверкі чалавекам.
5. Вынік запісваецца ў `songs/<назва>.json` і `export/<назва>.musicxml`. Старонкі PDF захоўваюцца як выявы ў `pages/`.

## JSON песні

Каардынаты падаюцца ў пікселях арыгінальнай выявы.

```json
{
 "id": "m_473_1",
 "source": {"file": "scans/m_473_1.png", "width": 1380, "height": 548},
 "clef": "G2", "key": 0, "time": "4/4",
 "systems": [{"lines": [88.1, 100.6, 113.1, 125.6, 138.1], "x0": 79, "x1": 1348, "unit": 12.5}],
 "measures": [
  {"index": 1, "time": "4/4", "system": 0, "box": [79, 38, 752, 187],
   "flags": ["disagree"], "alt": [...], "llm": {"choice": "A", "reason": "..."},
   "notes": [{"pitch": "A4", "dur": 1.0, "dots": 0, "tie": null, "fermata": false,
              "grace": false, "x": 222.3, "y": 116.9, "matched": true, "system": 0}]}
 ]
}
```

- `pitch` мае выгляд `F#4` або `Bb4`, для паўзы стаіць `null`.
- `dur` задае працягласць у чвэртках: 0,5 азначае восьмую, 1,5 азначае чвэртку з кропкай.
- `matched: false` азначае, што галоўку ноты на скане не знойдзена, і месца ноты вызначана прыблізна.

## Запуск на сваім кампутары

```sh
pip install -r requirements.txt
python -m melody_reader recognize scans/          # усе сканы
python -m melody_reader recognize scans/x.pdf --no-llm
python -m pytest tests                            # хуткія тэсты
python tests/evaluate.py songs tests/etalon.json  # параўнанне з эталонам
```

Пры першым запуску homr спампоўвае свае мадэлі з GitHub.

## Ключ Claude API

Ключ трэба дадаць у **Settings → Secrets and variables → Actions → New repository secret** пад назвай `ANTHROPIC_API_KEY`. Без ключа ўсё працуе, але праверкі праз Claude не будзе.

## Ліцэнзія

Праект распаўсюджваецца па ліцэнзіі AGPL-3.0, як і homr, на якім ён пабудаваны.
