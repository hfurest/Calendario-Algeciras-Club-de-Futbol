from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen
import json
import re

TEAM_ID = 4489
OUT_FILE = "algecirascfcalendar.ics"
TZ = ZoneInfo("Europe/Madrid")
API = f"https://www.sofascore.com/api/v1/team/{TEAM_ID}/events/next/"

def get_json(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as response:
        return json.load(response)

def ics_escape(value):
    value = str(value or "")
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

events = []
for page in range(0, 10):
    data = get_json(API + str(page))
    page_events = data.get("events", [])
    if not page_events:
        break
    events.extend(page_events)
    if not data.get("hasNextPage", False):
        break

# Solo partidos oficiales futuros; se excluyen amistosos.
future = []
now = datetime.now(timezone.utc).timestamp()

for e in events:
    if e.get("startTimestamp", 0) < now:
        continue

    tournament = e.get("tournament", {})
    tournament_name = tournament.get("name", "")
    if "friendly" in tournament_name.lower() or "club friendly" in tournament_name.lower():
        continue

    home = e.get("homeTeam", {}).get("name", "Algeciras CF")
    away = e.get("awayTeam", {}).get("name", "")
    # Nos quedamos con eventos donde participa el Algeciras.
    if "Algeciras" not in home and "Algeciras" not in away:
        continue

    future.append(e)

# Eliminar duplicados y ordenar.
unique = {str(e["id"]): e for e in future}
future = sorted(unique.values(), key=lambda e: e["startTimestamp"])

lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Algeciras CF//Calendario de partidos//ES",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "X-WR-CALNAME:Algeciras CF",
    "X-WR-CALDESC:Partidos oficiales del Algeciras CF",
    "X-WR-TIMEZONE:Europe/Madrid",
]

for e in future:
    start_utc = datetime.fromtimestamp(e["startTimestamp"], timezone.utc)
    start_local = start_utc.astimezone(TZ)

    # Duración estándar de 2 horas para mostrar correctamente el partido.
    end_local = start_local.replace(hour=(start_local.hour + 2) % 24)
    # Si el cambio de hora cruza medianoche, calculamos mediante timestamp.
    end_local = datetime.fromtimestamp(
        e["startTimestamp"] + 2 * 3600, timezone.utc
    ).astimezone(TZ)

    event_id = str(e["id"])
    home = e.get("homeTeam", {}).get("name", "Algeciras CF")
    away = e.get("awayTeam", {}).get("name", "")
    venue = (e.get("venue") or {}).get("name", "")
    tournament = (e.get("tournament") or {}).get("name", "Fútbol")

    # Sofascore publica el timestamp UTC; el calendario lo expresa en hora local.
    dtstart = start_local.strftime("%Y%m%dT%H%M%S")
    dtend = end_local.strftime("%Y%m%dT%H%M%S")

    summary = f"{home} - {away}"
    description = (
        f"Competición: {tournament}\\n"
        f"Fuente de datos: Sofascore\\n"
        f"Partido ID: {event_id}"
    )

    lines += [
        "BEGIN:VEVENT",
        f"UID:sofascore-{event_id}@algeciras-cf",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;TZID=Europe/Madrid:{dtstart}",
        f"DTEND;TZID=Europe/Madrid:{dtend}",
        f"SUMMARY:{ics_escape(summary)}",
        f"LOCATION:{ics_escape(venue)}",
        f"DESCRIPTION:{ics_escape(description)}",
        "END:VEVENT",
    ]

lines.append("END:VCALENDAR")

Path(OUT_FILE).write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
print(f"Calendario generado: {len(future)} partidos futuros.")
