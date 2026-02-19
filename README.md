# matthes-seitz-catalog

Scrapt den kompletten lieferbaren Katalog von [Matthes & Seitz Berlin](https://www.matthes-seitz-berlin.de) als strukturierte JSON-Datei.

Erfasst alle Imprints:
- **Matthes & Seitz Berlin** (~1.587 Titel)
- **Friedenauer Presse** (~132 Titel)
- **August Verlag** (~97 Titel)

## Erfasste Felder

| Feld | Beschreibung |
|------|-------------|
| `title` | Buchtitel |
| `subtitle` | Untertitel (falls vorhanden) |
| `authors` | Liste der Autor:innen / Herausgeber:innen |
| `isbn` | ISBN-13 |
| `price` | Ladenpreis (z.B. `"22,00 €"`) |
| `pages_binding` | Seitenzahl und Einband (z.B. `"188 Seiten, gebunden"`) |
| `year` | Erscheinungsjahr |
| `series` | Reihe (z.B. `"Naturkunden"`, `"Fröhliche Wissenschaft"`) |
| `keywords` | Schlagworte als Liste |
| `description` | Klappentext |
| `url` | URL der Detailseite |
| `imprint` | Imprint-Zugehörigkeit |

## Installation

```bash
pip install matthes-seitz-catalog
```

Oder direkt aus dem Repo:

```bash
pip install git+https://github.com/ArneJanning/matthes-seitz-catalog.git
```

## Benutzung

### CLI

```bash
# Kompletter Katalog → catalog.json (~15 Minuten)
matthes-seitz-catalog

# Eigener Dateiname
matthes-seitz-catalog --output bücher.json

# Nur 10 Titel (zum Testen)
matthes-seitz-catalog --limit 10

# Nur ein Imprint
matthes-seitz-catalog --imprints friedenauer-presse

# JSON nach stdout (z.B. für Pipes)
matthes-seitz-catalog --stdout --quiet | jq '.[] | .title'
```

### Python API

```python
from matthes_seitz_catalog.scraper import scrape_catalog

# Kompletter Katalog
books = scrape_catalog()

# Nur Friedenauer Presse, max 50 Titel
books = scrape_catalog(imprints=["friedenauer-presse"], limit=50)

for book in books:
    print(f"{book['title']} — {', '.join(book['authors'])}")
```

## Output-Format

```json
[
  {
    "url": "https://www.matthes-seitz-berlin.de/buch/large-language-kabbala.html",
    "imprint": "matthes-seitz-berlin",
    "title": "Large Language Kabbala",
    "subtitle": "Eine kleine Geschichte der Großen Sprachmodelle",
    "authors": ["Martin Warnke"],
    "isbn": "978-3-7518-3060-7",
    "price": "16,00 €",
    "pages_binding": "152 Seiten, Klappenbroschur",
    "year": "2026",
    "series": "Fröhliche Wissenschaft",
    "keywords": ["Künstliche Intelligenz", "AI", "LLM", "Halluzination", "Sprachphilosophie"],
    "description": "Nicht Nerds, sondern Schrift-Gelehrte sind es, die das Feld der generativen Künstlichen Intelligenz wie ChatGPT erklären können ..."
  }
]
```

## Rate-Limiting

Der Scraper ist bewusst konservativ:
- **1 Sekunde** zwischen Katalogseiten
- **0,5 Sekunden** zwischen Detailseiten
- Höflicher User-Agent-String

Ein vollständiger Durchlauf dauert ca. 15 Minuten.

## Lizenz

MIT
