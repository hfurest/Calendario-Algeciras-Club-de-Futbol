"""Read-only integration check, run on code changes and manual Actions runs."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import update_calendar as c

data = json.loads(c.DATA_FILE.read_text(encoding='utf-8'))
healthy = 0
for name, fetch in [('RFEF', c.fetch_rfef_matches), ('AS', c.fetch_as_matches)]:
    try:
        source = fetch(data['metadata']['season'])
        c.validate_source(source, data)
        print(f'{name}: OK, 38/38 jornadas verificadas desde este equipo.')
        healthy += 1
    except (ValueError, KeyError, OSError) as exc:
        print(f'::warning::{name}: {exc}')
if not healthy:
    sys.exit('Ninguna fuente accesible y válida.')
