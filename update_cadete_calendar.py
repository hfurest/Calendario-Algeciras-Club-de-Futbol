"""Calendario de liga del Algeciras Cadete B: RFAF 2026/27."""
import argparse
import copy
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from update_calendar import build_web_opener, clean_html_text, escape_ics, fold_line, request_text, write_if_changed

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'algecirascadeteb.ics'
DATA_FILE = ROOT / 'cadete_matches.json'
SOURCE = ('https://www.rfaf.es/pnfg/NPcd/NFG_VisCalendario_Vis'
          '?cod_primaria=1000120&codcompeticion=48909282&codgrupo=48909312&codtemporada=22&CDetalle=1')
SEASON = '2026/27'
COMPETITION = '2ª Andaluza Cadete (Cádiz) - Grupo único'
FIELDS = ('date', 'time', 'home', 'away', 'location')


def normalized(value):
    return re.sub('[^a-z0-9]', '', unicodedata.normalize('NFKD', value).lower())


def is_team(value):
    return normalized(value) in ('algecirascf', 'algecirascfsad')


def uid(jornada):
    return f'algeciras-cadete-b-2026-27-jornada-{jornada}@calendario-algeciras'


def validate(matches):
    if [m['jornada'] for m in matches] != list(range(1, 31)):
        raise ValueError('Se necesitan las 30 jornadas, sin duplicados ni ausencias.')
    opponents = []
    for m in matches:
        if sum(is_team(m[k]) for k in ('home', 'away')) != 1:
            raise ValueError(f"J{m['jornada']}: equipo incorrecto.")
        day = datetime.strptime(m['date'], '%Y-%m-%d')
        if not datetime(2026, 7, 1) <= day <= datetime(2027, 6, 30):
            raise ValueError('Fecha fuera de temporada.')
        if m['time'] is not None:
            if not re.fullmatch(r'\d{2}:\d{2}', m['time']):
                raise ValueError('Hora inválida.')
            datetime.strptime(m['time'], '%H:%M')
        opponents.append(normalized(m['away'] if is_team(m['home']) else m['home']))
    if len(set(opponents)) != 15 or any(opponents.count(t) != 2 for t in set(opponents)):
        raise ValueError('Se esperaban 15 rivales, a doble vuelta.')


def parse_source(html):
    heading = normalized(' '.join(clean_html_text(h) for h in re.findall(r'<h4\b[^>]*>(.*?)</h4>', html, re.S)))
    if not all(x in heading for x in ('2aandaluzacadetecadiz', 'grupounico', 'temporada20262027')):
        raise ValueError('RFAF: competición, grupo o temporada incorrectos.')
    markers = list(re.finditer(r'<h5\b[^>]*>\s*Jornada\s+(\d+)\b', html))
    result = {}
    for i, marker in enumerate(markers):
        section = html[marker.end():markers[i+1].start() if i+1 < len(markers) else len(html)]
        for row in re.finditer(r'<table\b[^>]*>(.*?)</table>((?:(?!<table\b).)*?fa-clock[^>]*>\s*</i>[^<]*)', section, re.S):
            cells = re.findall(r'<td\b[^>]*>(.*?)</td>', row[1], re.S)
            if len(cells) != 3:
                continue
            home, away = clean_html_text(cells[0]), clean_html_text(cells[2])
            if not (is_team(home) or is_team(away)):
                continue
            j = int(marker[1])
            clock = re.search(r'fa-clock[^>]*>\s*</i>\s*(\d{2}-\d{2}-\d{4})(?:\s*-\s*(\d{2}:\d{2}))?\s*$', row[2])
            venue = re.search(r'fa-map-marker[^>]*>\s*</i>(.*?)<br', row[2], re.S)
            if not clock or j in result or not venue:
                raise ValueError(f'RFAF: partido incompleto o duplicado en J{j}.')
            result[j] = dict(jornada=j, home=home, away=away,
                             date=datetime.strptime(clock[1], '%d-%m-%Y').strftime('%Y-%m-%d'),
                             time=clock[2], location=clean_html_text(venue[1]))
    matches = [result[j] for j in sorted(result)]
    validate(matches)
    return matches


def fetch_matches():
    opener = build_web_opener()
    request_text(opener, 'https://www.rfaf.es/')
    return parse_source(request_text(opener, SOURCE))


def reconcile(old, fetched, stamp):
    validate(fetched)
    if old:
        if old['season'] != SEASON or old['source'] != SOURCE:
            raise ValueError('Estado de otra temporada o fuente.')
        validate(old['matches'])
    previous = {m['jornada']: m for m in old['matches']} if old else {}
    result, changes = [], []
    for new in fetched:
        new = copy.deepcopy(new)
        before = previous.get(new['jornada'])
        if before:
            if any(normalized(new[k]) != normalized(before[k]) for k in ('home', 'away')):
                raise ValueError(f"J{new['jornada']}: ha cambiado el enfrentamiento; se requiere revisión.")
            if before['time'] and new['time'] is None:
                print(f"::warning::J{new['jornada']}: sin nueva hora; se conserva el horario conocido.")
                new['date'], new['time'] = before['date'], before['time']
            if all(before[k] == new[k] for k in FIELDS):
                result.append(copy.deepcopy(before))
                continue
        new['uid'] = before['uid'] if before else uid(new['jornada'])
        new['sequence'] = before['sequence'] + 1 if before else 0
        new['modified'] = stamp
        result.append(new)
        changes.append(new['jornada'])
    return dict(season=SEASON, source=SOURCE, matches=result), changes


def render(data):
    validate(data['matches'])
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Algeciras Cadete B//Calendario de liga//ES',
             'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'X-WR-CALNAME:Algeciras CF Cadete B',
             f'X-WR-CALDESC:{escape_ics(COMPETITION + " - " + SEASON)}', 'X-WR-TIMEZONE:Europe/Madrid']
    for m in data['matches']:
        if m['uid'] != uid(m['jornada']):
            raise ValueError('UID inesperado; se conserva el archivo publicado.')
        lines += ['BEGIN:VEVENT', f"UID:{m['uid']}", f"DTSTAMP:{m['modified']}",
                  f"LAST-MODIFIED:{m['modified']}", f"SEQUENCE:{m['sequence']}"]
        if m['time'] is None:
            start = datetime.strptime(m['date'], '%Y-%m-%d')
            lines += [f'DTSTART;VALUE=DATE:{start:%Y%m%d}', f'DTEND;VALUE=DATE:{start + timedelta(days=1):%Y%m%d}']
            status = 'Fecha base de jornada; hora pendiente de confirmación por RFAF'
        else:
            start = datetime.fromisoformat(m['date'] + 'T' + m['time']).replace(tzinfo=ZoneInfo('Europe/Madrid')).astimezone(timezone.utc)
            # UTC avoids relying on clients having an external VTIMEZONE definition.
            lines += [f'DTSTART:{start:%Y%m%dT%H%M%SZ}', f'DTEND:{start + timedelta(hours=2):%Y%m%dT%H%M%SZ}']
            status = 'Horario publicado por RFAF'
        home = 'Algeciras CF Cadete B' if is_team(m['home']) else m['home']
        away = 'Algeciras CF Cadete B' if is_team(m['away']) else m['away']
        description = f"{COMPETITION}\nTemporada {SEASON}\nJornada {m['jornada']}\n{status}"
        lines += [f'SUMMARY:{escape_ics(home + " - " + away)}', f"LOCATION:{escape_ics(m['location'])}",
                  f'DESCRIPTION:{escape_ics(description)}', f'URL:{SOURCE}',
                  'STATUS:TENTATIVE' if m['time'] is None else 'STATUS:CONFIRMED', 'END:VEVENT']
    return '\r\n'.join(fold_line(line) for line in lines + ['END:VCALENDAR']) + '\r\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Consultar sin guardar.')
    parser.add_argument('--offline', action='store_true', help='Regenerar únicamente con los datos guardados.')
    args = parser.parse_args()
    try:
        old = json.loads(DATA_FILE.read_text(encoding='utf-8')) if DATA_FILE.exists() else None
        if args.offline:
            if not old:
                raise ValueError('No hay datos guardados.')
            data, changes = old, []
        else:
            fetched = fetch_matches()
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            data, changes = reconcile(old, fetched, stamp)
        content = render(data)
        print(f"Cadete B: 30/30 jornadas; {sum(m['time'] is not None for m in data['matches'])} con hora; {len(changes)} novedades.")
        if changes:
            print('Jornadas: ' + ', '.join(map(str, changes)))
        if not args.check:
            write_if_changed(OUTPUT, content)
            write_if_changed(DATA_FILE, json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    except (ValueError, KeyError, OSError) as exc:
        print(f'::error::Cadete B: {exc}. Se conservan los archivos publicados.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
