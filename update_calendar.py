import json
import re
from datetime import datetime, timedelta
from pathlib import Path


DATA_FILE = Path("matches.json")
OUTPUT = Path("algecirascfcalendar.ics")
TEAM_NAME = "Algeciras CF"
TIMEZONE = "Europe/Madrid"
EXPECTED_MATCHES = 38
MATCH_DURATION_HOURS = 2


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


def generate_calendar():
    data = load_calendar_data()
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
    total_matches = generate_calendar()
    print(f"Calendario generado correctamente: {OUTPUT}")
    print(f"Partidos incluidos: {total_matches}")
