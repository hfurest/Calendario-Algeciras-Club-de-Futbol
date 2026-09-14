"""Synchronize the subscribed calendar; Python 3.12, standard library only."""
import argparse
import copy
import http.cookiejar
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "matches.json"
OUTPUT = ROOT / "algecirascfcalendar.ics"
EXPECTED_MATCHES = 38
TEAM_NAME = "Algeciras CF"
TIMEZONE = "Europe/Madrid"
RFEF_BASE_URL = "https://marcadores.rfef.es/"
RFEF_CALENDAR_URL = (
    RFEF_BASE_URL + "pnfg/NPcd/NFG_VisCalendario_Vis"
    "?cod_primaria=1000120&codgrupo=33836090&codcompeticion=33836088"
    "&codtemporada=22&CodJornada=&CDetalle=1"
)
AS_JOURNEY_URL = "https://as.com/resultados/futbol/primera_rfef/{season}/jornada/grupos_a_{jornada}/"
USER_AGENT = "Mozilla/5.0 (compatible; AlgecirasCalendar/1.0)"


def clean_html_text(value):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def normalize_text(value):
    value = unicodedata.normalize("NFKD", unescape(value)).lower()
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\b(cf|fc|cd|ad|sd|ue|ce|ud|sad)\b", " ", value)
    value = " ".join(value.split())
    return {
        "gimnastic": "gimnastic de tarragona",
        "gimnastic tarragona": "gimnastic de tarragona",
        "nastic tarragona": "gimnastic de tarragona",
        "hercules": "hercules de alicante",
        "juventud torremolinos": "juventud de torremolinos",
        "murcia": "real murcia",
        "ibiza eivissa": "ibiza",
        "atletico madrid b": "atletico madrileno",
    }.get(value, value)


def same_team(left, right):
    # Exact aliases: never match Algeciras B or an empty name by substring.
    return bool(normalize_text(left)) and normalize_text(left) == normalize_text(right)


def season_years(season):
    match = re.fullmatch(r"(\d{4})/(\d{2})", season)
    if not match or int(match[2]) != (int(match[1]) + 1) % 100:
        raise ValueError("Temporada inválida; se espera YYYY/YY.")
    return int(match[1]), int(match[1]) + 1


def validate_matches(data):
    start_year, end_year = season_years(data["metadata"]["season"])
    matches = data["matches"]
    if [m["jornada"] for m in matches] != list(range(1, EXPECTED_MATCHES + 1)):
        raise ValueError("Se requieren las 38 jornadas ordenadas y sin duplicados.")
    for m in matches:
        day = datetime.strptime(m["date"], "%Y-%m-%d").date()
        if not datetime(start_year, 7, 1).date() <= day <= datetime(end_year, 6, 30).date():
            raise ValueError(f"J{m['jornada']}: fecha fuera de temporada.")
        if m["time"] is not None:
            if not re.fullmatch(r"\d{2}:\d{2}", m["time"]):
                raise ValueError("Hora inválida.")
            datetime.strptime(m["time"], "%H:%M")
        if sum(same_team(m[k], TEAM_NAME) for k in ("home", "away")) != 1:
            raise ValueError(f"J{m['jornada']}: equipo equivocado.")


def build_web_opener():
    return build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request_text(opener, url):
    for attempt in range(3):
        try:
            with opener.open(Request(url, headers={"User-Agent": USER_AGENT}), timeout=20) as response:
                raw = response.read(4_000_001)
                if len(raw) > 4_000_000:
                    raise ValueError("Respuesta excesivamente grande.")
                # RFEF's HTTP header and HTML charset can disagree.
                for charset in dict.fromkeys(["utf-8", response.headers.get_content_charset(), "iso-8859-15"]):
                    if charset:
                        try:
                            return raw.decode(charset)
                        except (UnicodeDecodeError, LookupError):
                            pass
                raise ValueError("No se puede decodificar la respuesta.")
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def parse_rfef_matches(html, season):
    years = season_years(season)
    heading = " ".join(clean_html_text(h) for h in re.findall(r"<h4\b[^>]*>(.*?)</h4>", html, re.S | re.I))
    if (f"Temporada {years[0]}-{years[1]}" not in heading
            or "GRUPO 2" not in heading.upper() or "primera federacion" not in normalize_text(heading)):
        raise ValueError("RFEF: temporada o competición inesperada.")
    markers = list(re.finditer(r"<h5\b[^>]*>\s*Jornada\s+(\d+)\b", html, re.I))
    matches = {}
    for i, marker in enumerate(markers):
        jornada = int(marker[1])
        section = html[marker.end():markers[i + 1].start() if i + 1 < len(markers) else len(html)]
        # One table per fixture: do not mix clubs or clocks across adjacent rows.
        for row in re.finditer(r"<table\b[^>]*>(.*?)</table>((?:(?!<table\b).)*?fa-clock[^>]*>\s*</i>[^<]*)", section, re.S | re.I):
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row[1], re.S | re.I)
            if len(cells) != 3:
                continue
            home, away = clean_html_text(cells[0]), clean_html_text(cells[2])
            if not (same_team(home, TEAM_NAME) or same_team(away, TEAM_NAME)):
                continue
            clock = re.search(r"fa-clock[^>]*>\s*</i>\s*(\d{2}-\d{2}-\d{4})(?:\s*-\s*(\d{2}:\d{2}))?\s*$", row[2])
            if not clock or jornada in matches:
                raise ValueError(f"RFEF: horario ilegible o partido duplicado en J{jornada}.")
            matches[jornada] = dict(jornada=jornada, home=home, away=away,
                date=datetime.strptime(clock[1], "%d-%m-%Y").strftime("%Y-%m-%d"),
                time=clock[2], source="RFEF", source_url=RFEF_CALENDAR_URL)
    return matches


def fetch_rfef_matches(season):
    opener = build_web_opener()
    request_text(opener, RFEF_BASE_URL)  # Establish the public session cookie.
    return parse_rfef_matches(request_text(opener, RFEF_CALENDAR_URL), season)


class ASAttributes(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "li" and "441" in (attrs.get("data-team-home-id"), attrs.get("data-team-away-id")):
            self.rows.append(attrs)


def parse_as_match(html, jornada, season):
    years = season_years(season)
    headings = " ".join(clean_html_text(h) for h in re.findall(r"<h1\b[^>]*>(.*?)</h1>", html, re.S | re.I))
    if f"Resultados jornada {jornada} Primera RFEF {years[0]}/{years[1]}" not in headings:
        raise ValueError(f"AS: página incorrecta para J{jornada}.")
    parser = ASAttributes()
    parser.feed(html)
    if len(parser.rows) != 1:
        raise ValueError(f"AS: se esperaba un partido del Algeciras en J{jornada}.")
    row = parser.rows[0]
    if row.get("data-competition") != "primera_rfef":
        raise ValueError("AS: competición incorrecta.")
    start = datetime.fromisoformat(row["data-datetime"].replace("Z", "+00:00"))
    if start.utcoffset() != timedelta(0):
        raise ValueError("AS: se esperaba una fecha UTC explícita.")
    local = start.astimezone(ZoneInfo(TIMEZONE))
    # Opta/AS uses midnight UTC for unknown kickoffs, shown as 01:00/02:00.
    kickoff = None if start.time().isoformat() == "00:00:00" else local.strftime("%H:%M")
    return dict(jornada=jornada, home=row["data-team-home-name"], away=row["data-team-away-name"],
        date=local.strftime("%Y-%m-%d"), time=kickoff, source="AS",
        source_url=AS_JOURNEY_URL.format(season=f"{years[0]}_{years[1]}", jornada=jornada))


def fetch_as_matches(season):
    opener = build_web_opener()
    years = season_years(season)
    result = {}
    for jornada in range(1, EXPECTED_MATCHES + 1):
        url = AS_JOURNEY_URL.format(season=f"{years[0]}_{years[1]}", jornada=jornada)
        result[jornada] = parse_as_match(request_text(opener, url), jornada, season)
    return result


def validate_source(source, data):
    if set(source) != set(range(1, EXPECTED_MATCHES + 1)):
        raise ValueError(f"Fuente incompleta: {len(source)}/38 jornadas.")
    for match in data["matches"]:
        row = source[match["jornada"]]
        if not all(same_team(row[k], match[k]) for k in ("home", "away")):
            raise ValueError(f"J{match['jornada']}: los rivales o la localía no coinciden.")
    validate_matches(dict(metadata=data["metadata"], matches=[source[j] for j in sorted(source)]))


def update_matches_from_sources(data, use_secondary=True):
    sources = [("RFEF", fetch_rfef_matches)]
    if use_secondary:
        sources.append(("AS", fetch_as_matches))
    for name, fetch in sources:
        try:
            source = fetch(data["metadata"]["season"])
            validate_source(source, data)
            print(f"{name}: 38/38 partidos validados; {sum(m['time'] is not None for m in source.values())} con hora.")
            break
        except (ValueError, KeyError, URLError, TimeoutError) as exc:
            print(f"::warning::{name}: {exc}")
    else:
        raise RuntimeError("Ninguna fuente válida. Se conserva el calendario publicado.")
    changes = []
    for match in data["matches"]:
        row = source[match["jornada"]]
        if row["time"] is None and match["time"] is not None:
            print(f"::warning::J{match['jornada']}: fuente sin hora; se conserva el horario conocido.")
            continue
        if (row["date"], row["time"]) == (match["date"], match["time"]):
            continue
        changes.append(f"J{match['jornada']}: {match['date']} {match['time']} -> {row['date']} {row['time']} ({name})")
        for key in ("date", "time", "source", "source_url"):
            match[key] = row[key]
    return changes


def escape_ics(value):
    return str(value).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def properties(block):
    unfolded = re.sub(r"\r?\n[ \t]", "", block)
    return dict(line.split(":", 1) for line in unfolded.splitlines() if ":" in line)


def read_published(text, data):
    events = {}
    for found in re.finditer(r"BEGIN:VEVENT\r?\n.*?END:VEVENT", text, re.S):
        block = found[0]
        props = properties(block)
        uid = re.fullmatch(r"algeciras(?:-cf)?-(\d{4}-\d{2})-jornada-(\d+)@calendario-algeciras", props.get("UID", ""))
        if not uid or uid[1] != data["metadata"]["season"].replace("/", "-"):
            raise ValueError("UID publicado desconocido; no se reemplaza automáticamente.")
        jornada = int(uid[2])
        if jornada in events:
            raise ValueError("UID/jornada duplicado en el ICS publicado.")
        events[jornada] = block
    if set(events) != set(range(1, EXPECTED_MATCHES + 1)):
        raise ValueError("El ICS publicado debe contener las 38 jornadas.")
    # Repair the old workflow's stale JSON from the actual subscribed ICS first.
    for match in data["matches"]:
        props = properties(events[match["jornada"]])
        if props.get("SUMMARY") != escape_ics(f"{match['home']} - {match['away']}"):
            raise ValueError("El partido publicado no coincide con matches.json.")
        start = props.get(f"DTSTART;TZID={TIMEZONE}")
        if start:
            dt = datetime.strptime(start, "%Y%m%dT%H%M%S")
            match.update(date=dt.strftime("%Y-%m-%d"), time=dt.strftime("%H:%M"))
        else:
            day = datetime.strptime(props["DTSTART;VALUE=DATE"], "%Y%m%d")
            match.update(date=day.strftime("%Y-%m-%d"), time=None)
    return events


def fold_line(line):
    pieces, current = [], ""
    for char in line:
        if len((current + char).encode("utf-8")) > 75:
            pieces.append(current)
            current = " "
        current += char
    return "\r\n".join(pieces + [current])


def render_calendar(text, events, data, now=None):
    now = now or datetime.now(timezone.utc)
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for match in data["matches"]:
        block = events[match["jornada"]]
        old = properties(block)
        day = datetime.strptime(match["date"], "%Y-%m-%d")
        if match["time"] is not None:
            start = datetime.fromisoformat(f"{match['date']}T{match['time']}")
            timing = {f"DTSTART;TZID={TIMEZONE}": start.strftime("%Y%m%dT%H%M%S"),
                      f"DTEND;TZID={TIMEZONE}": (start + timedelta(hours=2)).strftime("%Y%m%dT%H%M%S")}
        else:
            timing = {"DTSTART;VALUE=DATE": day.strftime("%Y%m%d"),
                      "DTEND;VALUE=DATE": (day + timedelta(days=1)).strftime("%Y%m%d")}
        old_timing = {k: v for k, v in old.items() if k.split(";")[0] in ("DTSTART", "DTEND")}
        if timing == old_timing:
            continue  # Preserve every byte, DTSTAMP, folding and mtime on no-op.
        updated = {k: v for k, v in old.items() if k not in old_timing and k not in ("BEGIN", "END")}
        updated.update(timing)
        updated.update(DTSTAMP=stamp, **{"LAST-MODIFIED": stamp, "SEQUENCE": str(int(old.get("SEQUENCE", "0")) + 1)})
        status = ("Hora pendiente de confirmación" if match["time"] is None else
                  "Horario oficialmente confirmado (RFEF)" if match.get("source") == "RFEF" else
                  "Horario publicado por AS; pendiente de validación oficial")
        updated["DESCRIPTION"] = escape_ics(f"{data['metadata']['competition']} - {data['metadata']['group']}\nJornada {match['jornada']}\n{status}")
        if match.get("source_url"):
            updated["URL"] = match["source_url"]
        lines = ["BEGIN:VEVENT"] + [f"{k}:{v}" for k, v in updated.items()] + ["END:VEVENT"]
        text = text.replace(block, "\r\n".join(fold_line(line) for line in lines), 1)
    return text


def write_if_changed(path, content):
    raw = content.encode("utf-8")
    if path.exists() and path.read_bytes() == raw:
        return False
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(raw)
    temp.replace(path)
    return True


def synchronize(sync=True, use_secondary=True, check=False):
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    original = copy.deepcopy(data)
    validate_matches(data)
    published = OUTPUT.read_bytes().decode("utf-8")
    events = read_published(published, data)
    validate_matches(data)
    changes = update_matches_from_sources(data, use_secondary) if sync else []
    validate_matches(data)
    result = render_calendar(published, events, data)
    for change in changes:
        print(change)
    print(f"{len(changes)} cambios de horario; ICS {'modificado' if result != published else 'sin cambios'}.")
    if not check:
        # Fetching, parsing and validation have succeeded before any file changes.
        write_if_changed(OUTPUT, result)
        if data != original:
            write_if_changed(DATA_FILE, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return result != published


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", action="store_true", help="Consultar RFEF y, si falla, AS.")
    parser.add_argument("--no-secondary", action="store_true", help="Usar únicamente RFEF.")
    parser.add_argument("--check", action="store_true", help="Validar y mostrar cambios sin escribir archivos.")
    args = parser.parse_args()
    try:
        synchronize(args.sync, not args.no_secondary, args.check)
    except (RuntimeError, ValueError, KeyError, OSError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
