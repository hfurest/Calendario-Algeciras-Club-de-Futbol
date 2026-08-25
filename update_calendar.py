import argparse
from html import unescape
from html.parser import HTMLParser
import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener
import http.cookiejar


DATA_FILE = Path("matches.json")
OUTPUT = Path("algecirascfcalendar.ics")
TEAM_NAME = "Algeciras CF"
TIMEZONE = "Europe/Madrid"
EXPECTED_MATCHES = 38
MATCH_DURATION_HOURS = 2
RFEF_BASE_URL = "https://marcadores.rfef.es/"
RFEF_CALENDAR_URL = (
    "https://marcadores.rfef.es/pnfg/NPcd/NFG_VisCalendario_Vis"
    "?cod_primaria=1000120&codgrupo=33836090&codcompeticion=33836088"
    "&codtemporada=22&CodJornada=&CDetalle=1"
)
AS_JOURNEY_URL = (
    "https://as.com/resultados/futbol/primera_rfef/2026_2027/"
    "jornada/grupos_a_{jornada}/"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
)


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self):
        return "\n".join(self.parts)


def escape_ics(value):
    """Escapa caracteres especiales utilizados por iCalendar."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def make_uid(season, jornada):
    """
    UID permanente para cada partido.

    Es fundamental que no cambie cuando se actualice la fecha u hora.
    """
    season_slug = str(season).lower().replace("/", "-")
    return f"algeciras-cf-{season_slug}-jornada-{jornada}@calendario-algeciras"


def parse_date(value, jornada):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(
            f"Jornada {jornada}: fecha invalida '{value}'. Usa YYYY-MM-DD."
        ) from exc


def parse_time(value, jornada):
    if value in (None, ""):
        return None

    if not re.fullmatch(r"\d{2}:\d{2}", str(value)):
        raise ValueError(
            f"Jornada {jornada}: hora invalida '{value}'. Usa HH:MM o null."
        )

    hour, minute = map(int, value.split(":"))
    if hour > 23 or minute > 59:
        raise ValueError(f"Jornada {jornada}: hora fuera de rango '{value}'.")

    return hour, minute


def format_date(value):
    return datetime.strptime(value, "%d-%m-%Y").strftime("%Y-%m-%d")


def normalize_text(value):
    value = unescape(str(value))
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower()
    value = value.replace("�", "")
    value = value.replace('"', " ").replace("'", " ")
    value = re.sub(r"\b(c\.?f\.?|club de futbol|sad|s\.?a\.?d\.?)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    if "gimn" in value and "tarragona" in value:
        return "gimnastic de tarragona"
    if "guilas" in value:
        return "aguilas"
    if "hercules" in value:
        return "hercules de alicante"

    replacements = {
        "atletico madrid b": "atletico madrileno",
        "villarreal b": "villarreal b",
        "gimnastic tarragona": "gimnastic de tarragona",
        "nastic tarragona": "gimnastic de tarragona",
        "aguilas": "aguilas",
        "hercules": "hercules de alicante",
        "algeciras": "algeciras",
    }
    return replacements.get(value, value)


def same_team(left, right):
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    return (
        left_norm == right_norm
        or left_norm in right_norm
        or right_norm in left_norm
    )


def request_text(opener, url):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    response = opener.open(request, timeout=30)
    raw = response.read()
    charset = response.headers.get_content_charset() or "utf-8"
    candidates = [charset, "utf-8", "iso-8859-15", "windows-1252"]
    decoded = [raw.decode(candidate, "replace") for candidate in dict.fromkeys(candidates)]
    return min(decoded, key=lambda text: text.count("�"))


def build_web_opener():
    cookie_jar = http.cookiejar.CookieJar()
    return build_opener(HTTPCookieProcessor(cookie_jar))


def parse_rfef_matches(html):
    matches = {}
    journey_positions = list(re.finditer(r"Jornada\s+(\d+)\b", html))

    row_pattern = re.compile(
        r'<td[^>]*align=right[^>]*>\s*<strong><span[^>]*>'
        r"(.*?)</span></strong></td>.*?"
        r"<td[^>]*>\s*<strong><span[^>]*>(.*?)</span>\s*</strong></td>.*?"
        r'<i class="fa fa-map-marker"[^>]*></i>\s*(.*?)\s*<br>'
        r'.*?<i class="fa fa-clock"[^>]*></i>\s*'
        r"(\d{2}-\d{2}-\d{4})(?:\s*-\s*(\d{2}:\d{2}))?",
        re.S,
    )

    for index, marker in enumerate(journey_positions):
        jornada = int(marker.group(1))
        end = (
            journey_positions[index + 1].start()
            if index + 1 < len(journey_positions)
            else len(html)
        )
        section = html[marker.end():end]

        for row in row_pattern.finditer(section):
            home = clean_html_text(row.group(1))
            away = clean_html_text(row.group(2))
            if not (same_team(home, TEAM_NAME) or same_team(away, TEAM_NAME)):
                continue

            matches[jornada] = {
                "jornada": jornada,
                "date": format_date(row.group(4)),
                "home": home,
                "away": away,
                "time": row.group(5) or None,
                "source": "RFEF",
            }

    return matches


def clean_html_text(value):
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def fetch_rfef_matches():
    opener = build_web_opener()
    request_text(opener, RFEF_BASE_URL)
    html = request_text(opener, RFEF_CALENDAR_URL)
    if len(html) < 1000:
        raise RuntimeError("RFEF devolvio una respuesta vacia o incompleta.")
    if "No se ha aceptado el cookie" in html:
        raise RuntimeError("RFEF no devolvio el calendario por cookies.")
    return parse_rfef_matches(html)


def parse_as_date(value):
    months = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "sept": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
        "ene": 1,
        "feb": 2,
        "mar": 3,
        "abr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "ago": 8,
        "oct": 10,
        "nov": 11,
        "dic": 12,
    }
    match = re.search(r"(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóú]+)", value)
    if not match:
        return None
    day = int(match.group(1))
    month_name = normalize_text(match.group(2))
    month = months.get(month_name)
    if not month:
        return None
    return f"2026-{month:02d}-{day:02d}" if month >= 8 else f"2027-{month:02d}-{day:02d}"


def parse_as_match(html, jornada):
    parser = TextExtractor()
    parser.feed(html)
    lines = [line.strip() for line in parser.text().splitlines() if line.strip()]

    current_date = None
    for index, line in enumerate(lines):
        if re.match(r"^(Lunes|Martes|Miércoles|Miercoles|Jueves|Viernes|Sábado|Sabado|Domingo)\s+\d+", line):
            current_date = parse_as_date(line)
            continue

        if not line.lower().startswith("grupo"):
            continue

        if index + 4 >= len(lines):
            continue

        home = lines[index + 1]
        time = lines[index + 2]
        away = lines[index + 4] if lines[index + 3] == "CET" else lines[index + 3]

        if not current_date or not same_team(home, TEAM_NAME) and not same_team(away, TEAM_NAME):
            continue
        if not re.fullmatch(r"\d{2}:\d{2}", time):
            continue
        if time in {"01:00", "02:00"}:
            continue

        return {
            "jornada": jornada,
            "date": current_date,
            "home": home,
            "away": away,
            "time": time,
            "source": "AS",
        }

    return None


def fetch_as_matches():
    opener = build_web_opener()
    matches = {}
    for jornada in range(1, EXPECTED_MATCHES + 1):
        try:
            html = request_text(opener, AS_JOURNEY_URL.format(jornada=jornada))
        except (URLError, TimeoutError):
            continue
        match = parse_as_match(html, jornada)
        if match:
            matches[jornada] = match
    return matches


def find_source_match(source_matches, match):
    source = source_matches.get(match["jornada"])
    if not source:
        return None
    if same_team(source["home"], match["home"]) and same_team(source["away"], match["away"]):
        return source
    if same_team(source["home"], match["away"]) and same_team(source["away"], match["home"]):
        return source
    return None


def update_matches_from_sources(data, use_secondary=True):
    try:
        rfef_matches = fetch_rfef_matches()
        print(f"RFEF: {len(rfef_matches)} partidos del Algeciras encontrados.")
    except Exception as exc:
        print(f"RFEF: no se pudo consultar ({exc}).")
        rfef_matches = {}

    as_matches = {}
    if use_secondary:
        try:
            as_matches = fetch_as_matches()
            print(f"AS: {len(as_matches)} partidos del Algeciras encontrados.")
        except Exception as exc:
            print(f"AS: no se pudo consultar ({exc}).")

    changes = []
    for match in data["matches"]:
        source = find_source_match(rfef_matches, match)
        if not source and use_secondary:
            source = find_source_match(as_matches, match)
        if not source:
            continue

        old_date = match["date"]
        old_time = match["time"]
        new_date = source["date"]
        new_time = source["time"]

        if new_date != old_date or new_time != old_time:
            match["date"] = new_date
            match["time"] = new_time
            changes.append(
                f"Jornada {match['jornada']}: {old_date} {old_time or 'sin hora'} "
                f"-> {new_date} {new_time or 'sin hora'} ({source['source']})"
            )

    if changes:
        DATA_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("Horarios actualizados:")
        for change in changes:
            print(f"- {change}")
    else:
        print("No hay horarios nuevos que aplicar.")

    return len(changes)


def load_calendar_data(path=DATA_FILE):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"No existe el archivo de datos: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON invalido en {path}: {exc}") from exc


def validate_metadata(metadata):
    required = {"competition", "group", "season", "dtstamp"}
    missing = required - set(metadata)
    if missing:
        raise ValueError(
            "Faltan campos en metadata: " + ", ".join(sorted(missing))
        )
    if not re.fullmatch(r"\d{8}T\d{6}Z", metadata["dtstamp"]):
        raise ValueError("metadata.dtstamp debe usar el formato YYYYMMDDTHHMMSSZ.")


def validate_matches(matches):
    if len(matches) != EXPECTED_MATCHES:
        raise ValueError(
            f"Se esperaban {EXPECTED_MATCHES} partidos y hay {len(matches)}."
        )

    seen_jornadas = set()
    previous_jornada = 0

    for match in matches:
        required_fields = {"jornada", "date", "home", "away", "time"}
        missing = required_fields - set(match)
        if missing:
            raise ValueError(
                "Faltan campos en un partido: " + ", ".join(sorted(missing))
            )

        jornada = match["jornada"]
        if not isinstance(jornada, int):
            raise ValueError(f"La jornada debe ser un numero entero: {jornada}")
        if jornada in seen_jornadas:
            raise ValueError(f"Jornada duplicada: {jornada}")
        if jornada != previous_jornada + 1:
            raise ValueError(
                f"Jornada fuera de orden: se esperaba {previous_jornada + 1} "
                f"y aparece {jornada}."
            )

        seen_jornadas.add(jornada)
        previous_jornada = jornada

        parse_date(match["date"], jornada)
        parse_time(match["time"], jornada)

        home = match["home"].strip()
        away = match["away"].strip()
        if not home or not away:
            raise ValueError(f"Jornada {jornada}: local y visitante son obligatorios.")
        if TEAM_NAME not in (home, away):
            raise ValueError(f"Jornada {jornada}: el partido no incluye a {TEAM_NAME}.")
        if home == away:
            raise ValueError(f"Jornada {jornada}: local y visitante son iguales.")


def create_event(match, metadata):
    jornada = match["jornada"]
    date = parse_date(match["date"], jornada)
    confirmed_time = parse_time(match["time"], jornada)

    summary = f"{match['home']} - {match['away']}"

    if confirmed_time:
        hour, minute = confirmed_time
        start = datetime(date.year, date.month, date.day, hour, minute)
        end = start + timedelta(hours=MATCH_DURATION_HOURS)

        dtstart = f"DTSTART;TZID={TIMEZONE}:{start.strftime('%Y%m%dT%H%M%S')}"
        dtend = f"DTEND;TZID={TIMEZONE}:{end.strftime('%Y%m%dT%H%M%S')}"
        description_status = "Horario oficialmente confirmado"
    else:
        next_day = date + timedelta(days=1)
        dtstart = "DTSTART;VALUE=DATE:" + date.strftime("%Y%m%d")
        dtend = "DTEND;VALUE=DATE:" + next_day.strftime("%Y%m%d")
        description_status = "Hora pendiente de confirmación oficial"

    location = (
        "Estadio Nuevo Mirador, Algeciras"
        if match["home"] == TEAM_NAME
        else "Estadio por confirmar"
    )

    description = (
        f"{metadata['competition']} - {metadata['group']}\\n"
        f"Jornada {jornada}\\n"
        f"{description_status}"
    )

    return [
        "BEGIN:VEVENT",
        f"UID:{make_uid(metadata['season'], jornada)}",
        "DTSTAMP:" + metadata["dtstamp"],
        dtstart,
        dtend,
        f"SUMMARY:{escape_ics(summary)}",
        f"LOCATION:{escape_ics(location)}",
        f"DESCRIPTION:{escape_ics(description)}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
    ]


def generate_calendar(data=None):
    data = data or load_calendar_data()
    metadata = data["metadata"]
    matches = data["matches"]

    validate_metadata(metadata)
    validate_matches(matches)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Algeciras CF//Calendario de partidos//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Algeciras CF",
        "X-WR-CALDESC:"
        + escape_ics(
            f"Partidos del {TEAM_NAME} {metadata['competition']} "
            f"{metadata['season']}"
        ),
        f"X-WR-TIMEZONE:{TIMEZONE}",
    ]

    for match in matches:
        lines.extend(create_event(match, metadata))

    lines.append("END:VCALENDAR")

    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(matches)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Consulta RFEF y AS antes de generar el calendario.",
    )
    parser.add_argument(
        "--no-secondary",
        action="store_true",
        help="No usa AS como fuente secundaria.",
    )
    args = parser.parse_args()

    calendar_data = load_calendar_data()
    if args.sync:
        update_matches_from_sources(calendar_data, use_secondary=not args.no_secondary)
        calendar_data = load_calendar_data()

    total_matches = generate_calendar(calendar_data)
    print(f"Calendario generado correctamente: {OUTPUT}")
    print(f"Partidos incluidos: {total_matches}")
