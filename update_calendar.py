from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

OUTPUT = "algecirascfcalendar.ics"
TZ = ZoneInfo("Europe/Madrid")

# Calendario oficial base del Algeciras CF - Primera Federación Grupo 2 2026/27.
# Las fechas corresponden a las jornadas publicadas por la RFEF.
# Cuando el horario todavía no está confirmado, el evento se crea como
# evento de día completo.
#
# Formato:
# jornada, fecha, local, visitante, hora_confirmada
#
# hora_confirmada = None cuando todavía no conocemos la hora oficial.

MATCHES = [
    (1,  "2026-08-29", "Algeciras CF", "FC Cartagena", "19:15"),
    (2,  "2026-09-04", "Villarreal CF B", "Algeciras CF", "19:00"),
    (3,  "2026-09-13", "Gimnàstic de Tarragona", "Algeciras CF", None),
    (4,  "2026-09-20", "Algeciras CF", "Águilas FC", None),
    (5,  "2026-09-27", "Juventud de Torremolinos CF", "Algeciras CF", None),
    (6,  "2026-10-04", "Algeciras CF", "CF Rayo Majadahonda", None),
    (7,  "2026-10-11", "CE Europa", "Algeciras CF", None),
    (8,  "2026-10-18", "Algeciras CF", "Hércules de Alicante CF", None),
    (9,  "2026-10-25", "Algeciras CF", "Real Madrid Castilla", None),
    (10, "2026-11-01", "Real Jaén CF", "Algeciras CF", None),
    (11, "2026-11-08", "Real Murcia CF", "Algeciras CF", None),
    (12, "2026-11-15", "Algeciras CF", "Antequera CF", None),
    (13, "2026-11-22", "AD Alcorcón", "Algeciras CF", None),
    (14, "2026-11-29", "Algeciras CF", "SD Huesca", None),
    (15, "2026-12-06", "UE Sant Andreu", "Algeciras CF", None),
    (16, "2026-12-13", "Algeciras CF", "CD Teruel", None),
    (17, "2026-12-20", "Atlético Madrileño", "Algeciras CF", None),
    (18, "2027-01-03", "Algeciras CF", "Real Zaragoza", None),
    (19, "2027-01-10", "UD Ibiza", "Algeciras CF", None),
    (20, "2027-01-17", "Real Madrid Castilla", "Algeciras CF", None),
    (21, "2027-01-24", "Algeciras CF", "Gimnàstic de Tarragona", None),
    (22, "2027-01-31", "Águilas FC", "Algeciras CF", None),
    (23, "2027-02-07", "Algeciras CF", "CE Europa", None),
    (24, "2027-02-14", "SD Huesca", "Algeciras CF", None),
    (25, "2027-02-21", "Algeciras CF", "Real Murcia", None),
    (26, "2027-02-28", "Antequera CF", "Algeciras CF", None),
    (27, "2027-03-07", "Algeciras CF", "Real Jaén CF", None),
    (28, "2027-03-14", "Algeciras CF", "Atlético Madrileño", None),
    (29, "2027-03-21", "CF Rayo Majadahonda", "Algeciras CF", None),
    (30, "2027-03-28", "Algeciras CF", "Juventud de Torremolinos CF", None),
    (31, "2027-04-04", "Hércules de Alicante CF", "Algeciras CF", None),
    (32, "2027-04-11", "Algeciras CF", "UD Ibiza", None),
    (33, "2027-04-18", "CD Teruel", "Algeciras CF", None),
    (34, "2027-04-25", "Algeciras CF", "Villarreal CF B", None),
    (35, "2027-05-02", "FC Cartagena", "Algeciras CF", None),
    (36, "2027-05-09", "Algeciras CF", "UE Sant Andreu", None),
    (37, "2027-05-16", "Real Zaragoza", "Algeciras CF", None),
    (38, "2027-05-23", "Algeciras CF", "AD Alcorcón", None),
]


def escape_ics(value):
    """Escapa caracteres especiales del formato iCalendar."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def make_uid(jornada):
    """UID permanente para que Google Calendar modifique el evento
    en lugar de crear uno nuevo."""
    return f"algeciras-2026-27-jornada-{jornada}@calendario-algeciras"


def create_event(match):
    jornada, date_str, home, away, confirmed_time = match

    date = datetime.strptime(date_str, "%Y-%m-%d").date()

    summary = f"{home} - {away}"

    if confirmed_time:
        hour, minute = map(int, confirmed_time.split(":"))

        start = datetime(
            date.year,
            date.month,
            date.day,
            hour,
            minute,
            tzinfo=TZ
        )

        end = start + timedelta(hours=2)

        dtstart = (
            f"DTSTART;TZID=Europe/Madrid:"
            f"{start.strftime('%Y%m%dT%H%M%S')}"
        )

        dtend = (
            f"DTEND;TZID=Europe/Madrid:"
            f"{end.strftime('%Y%m%dT%H%M%S')}"
        )

        description = (
            f"Primera Federación - Grupo 2\\n"
            f"Jornada {jornada}\\n"
            f"Horario confirmado"
        )

    else:
        # Todavía no conocemos la hora oficial.
        # Se crea como evento de día completo.
        next_day = date + timedelta(days=1)

        dtstart = f"DTSTART;VALUE=DATE:{date.strftime('%Y%m%d')}"
        dtend = f"DTEND;VALUE=DATE:{next_day.strftime('%Y%m%d')}"

        description = (
            f"Primera Federación - Grupo 2\\n"
            f"Jornada {jornada}\\n"
            f"⚠️ Hora pendiente de confirmación oficial"
        )

    return [
        "BEGIN:VEVENT",
        f"UID:{make_uid(jornada)}",
        f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
        dtstart,
        dtend,
        f"SUMMARY:{escape_ics(summary)}",
        "LOCATION:Nuevo Mirador / estadio por confirmar",
        f"DESCRIPTION:{escape_ics(description)}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
    ]


def generate_calendar():
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Algeciras CF//Calendario oficial de partidos//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Algeciras CF",
        "X-WR-CALDESC:Partidos Algeciras CF - Primera Federación 2026/27",
        "X-WR-TIMEZONE:Europe/Madrid",
    ]

    for match in MATCHES:
        lines.extend(create_event(match))

    lines.append("END:VCALENDAR")

    Path(OUTPUT).write_text(
        "\r\n".join(lines) + "\r\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    generate_calendar()
    print(f"Calendario generado correctamente: {OUTPUT}")
    print(f"Partidos incluidos: {len(MATCHES)}")
