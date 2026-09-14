# Algeciras CF Cadete B — calendario automático

30 jornadas de **2ª Andaluza Cadete (Cádiz), grupo único, 2026/27**.
Fuente oficial: [calendario extendido de RFAF](https://www.rfaf.es/pnfg/NPcd/NFG_VisCalendario_Vis?cod_primaria=1000120&codcompeticion=48909282&codgrupo=48909312&codtemporada=22&CDetalle=1).
El club figura como `ALGECIRAS C.F., S.A.D.` en esta competición. Se identifica
por nombre exacto y categoría, sin confundirlo con Monitores o Atlético Pastores.

Suscripción pública:
[algecirascadeteb.ics](https://raw.githubusercontent.com/hfurest/Calendario-Algeciras-Club-de-Futbol/main/algecirascadeteb.ics).

En Google Calendar web: **Otros calendarios → + → Desde URL**, pega esa dirección.
Una importación de archivo es una copia estática; para recibir cambios hay que
suscribirse a la URL. Google determina cuándo descarga las actualizaciones y puede
retrasarlas. Si ya tienes eventos manuales del Cadete B, ocultarlos evita ver ambas
copias al mismo tiempo. Este calendario incluye exclusivamente liga, no amistosos.

El workflow **Actualizar calendario Algeciras Cadete B** consulta RFAF cada día a
las 07:25 UTC (08:25 en invierno, 09:25 en verano en España peninsular). Puede
ejecutarse manualmente desde Actions. Es independiente de la consulta del primer
equipo; ambos workflows coordinan sus escrituras para evitar conflictos.

`cadete_matches.json` guarda el último estado válido. Los eventos pendientes son
de día completo; al publicarse el horario se actualizan fecha y hora con el mismo
UID por jornada. Solo los eventos modificados cambian SEQUENCE, DTSTAMP y
LAST-MODIFIED. También se actualiza el campo cuando cambia en RFAF. Sin novedades
no se reescriben archivos. Si la página falla, cambia la competición o faltan
jornadas, no se publica un calendario parcial. Una hora vacía no borra una conocida.

La duración del evento es de dos horas para reservar margen alrededor del partido;
no pretende indicar la duración reglamentaria de un encuentro cadete. Las horas
confirmadas se guardan en UTC para que cada aplicación muestre su zona local.

Verificación:

```sh
python -m unittest discover -s tests -v
python update_cadete_calendar.py --check
python update_cadete_calendar.py
python update_cadete_calendar.py --offline
```

El registro muestra `Cadete B: 30/30 jornadas`, cuántas tienen hora y las jornadas
actualizadas. La instantánea HTML de prueba fue descargada el 14/09/2026. La liga
termina, según el calendario base, el 22/05/2027. Una temporada nueva requiere
configurar de nuevo los identificadores de competición y grupo. Aplazamientos sin
nueva hora y cambios de estructura de la web requieren revisión; no se inventan
horarios ni se incorporan datos de jugadores menores de edad.
