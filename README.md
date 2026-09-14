# Calendario automático del Algeciras CF

También está disponible el [calendario automático del Cadete B](CADETE-B.md),
con las 30 jornadas de 2ª Andaluza Cadete de Cádiz.

El calendario mantiene los 38 partidos de Primera Federación, Grupo 2, temporada
2026/27. GitHub Actions consulta los horarios **cada día a las 07:15 UTC**
(08:15 en invierno y 09:15 en verano en Madrid). También se puede ejecutar desde
**Actions → Actualizar calendario Algeciras CF → Run workflow → main**.

## Fuentes

1. [Marcadores oficiales RFEF](https://marcadores.rfef.es/pnfg/NPcd/NFG_VisCalendario_Vis?cod_primaria=1000120&codgrupo=33836090&codcompeticion=33836088&codtemporada=22&CodJornada=&CDetalle=1).
   Se abre primero la portada para obtener la cookie pública y después el
   calendario extendido. No necesita navegador, cuenta ni clave. Se comprueban
   temporada, grupo, las 38 jornadas y cada rival con su condición local/visitante.
   La lectura admite las diferencias de espacios entre primera y segunda vuelta.
2. [Resultados de AS / Opta, ejemplo J6](https://as.com/resultados/futbol/primera_rfef/2026_2027/jornada/grupos_a_6/).
   Respaldo si RFEF falla o devuelve un calendario incompleto/incompatible. Lee
   atributos estructurados del HTML, identifica al Algeciras por el ID 441 y
   convierte fechas UTC a Europe/Madrid, incluyendo el cambio de hora. Una fecha
   a medianoche UTC significa hora pendiente: nunca se publica como 01:00/02:00.
   Un cambio procedente de AS se describe como pendiente de validación oficial.

La prioridad es RFEF. AS no sustituye un calendario oficial completo. Si ambas
fuentes fallan, el proceso termina con error **sin modificar ninguno de los dos
archivos**. Una fuente sin hora no borra un horario previamente publicado y deja
un aviso en Actions. No se utiliza SofaScore.

## Persistencia y suscripción

- `matches.json` conserva automáticamente los datos conocidos. No hay que editar
  horarios manualmente. En la primera ejecución se recuperan del ICS los datos que
  el workflow anterior no había guardado en JSON.
- Se mantienen exactamente los UID publicados, incluso la variante antigua sin
  `-cf`. No se cambian el nombre, la ruta ni la URL del ICS.
- Solo un cambio de fecha/hora cambia el evento correspondiente. Su `SEQUENCE`
  aumenta y se actualizan `DTSTAMP` y `LAST-MODIFIED`. Los demás eventos se
  conservan literalmente. Si no hay cambios, ni se reescribe el ICS ni cambia su
  fecha de modificación. Los nuevos bloques usan plegado UTF-8 de 75 octetos.
- Actions guarda `matches.json` y `algecirascfcalendar.ics` en el mismo commit, solo
  cuando hay diferencias. Las ejecuciones no se solapan y el push no es forzado.
- **Conserva tu suscripción actual de Google Calendar**. No importes el archivo
  otra vez ni crees otro calendario. Google decide cuándo vuelve a consultar la
  URL; una actualización en GitHub no implica una actualización inmediata allí.

URL pública del archivo, sin cambios:
[algecirascfcalendar.ics](https://raw.githubusercontent.com/hfurest/Calendario-Algeciras-Club-de-Futbol/main/algecirascfcalendar.ics).

El 14/09/2026 se repararon también las revisiones históricas de J3–J7: el
generador anterior había cambiado sus horarios sin aumentar la versión del
evento. Contrastando las transiciones reales del historial Git, se asignó
`SEQUENCE:1` y se actualizaron sus marcas de modificación una sola vez, sin
cambiar los UID ni los horarios. Las siguientes ejecuciones conservan estas
revisiones y no vuelven a generar cambios. Esta reparación no fuerza una
consulta inmediata de Google: la recepción debe comprobarse en la suscripción.

## Cómo verificar una actualización

1. Abre la última ejecución en Actions. El registro debe mostrar `RFEF: 38/38
   partidos validados` o el respaldo AS, junto con las jornadas modificadas.
   `0 cambios de horario; ICS sin cambios` es una comprobación correcta sin novedades.
2. Si hubo cambios, abre el commit automático: debe incluir JSON e ICS según las
   diferencias reales. El UID de cada evento debe seguir siendo el mismo.
3. Contrasta `DTSTART` en el ICS con RFEF; después espera la actualización de la
   suscripción. Si GitHub está actualizado y Google aún no, comprueba que Google
   esté suscrito por URL y no sea una importación única.
4. Si Actions falla, revisa los avisos de fuente: no es equivalente a «sin cambios».
   Las ejecuciones manuales y los cambios de código prueban ambas fuentes en un
   runner de GitHub. Los dos mensajes `OK, 38/38` confirman su accesibilidad.

Pruebas locales con Python 3.12 (Linux incluye la zona horaria; en Windows puede
ser necesario instalar `tzdata`):

```sh
python -m unittest discover -s tests -v
python tests/live_sources.py
python update_calendar.py --sync --check
python update_calendar.py --sync
```

`--check` no escribe. `--no-secondary` limita la comprobación a RFEF. Sin `--sync`
solo se valida/reconcilia el estado ya publicado, sin consultar la red.

Las pruebas cubren las dos vueltas, horarios pendientes, conversión de hora,
fuentes fallidas, temporadas/rivales erróneos, UID, revisiones y escrituras nulas.
Los HTML de `tests/fixtures` son fragmentos reales descargados el 14/09/2026;
el ICS y JSON de prueba son una instantánea fija para que las regresiones no
dependan de los horarios que se publiquen después.

## Límites

Los sitios pueden cambiar su HTML, bloquear servidores o publicar datos erróneos.
El programa detecta respuestas incompletas y conserva el último estado válido.
No interpreta comunicados en imagen/PDF ni cancelaciones/aplazamientos sin una
nueva hora explícita: esos casos dejan el horario anterior y requieren revisar
el aviso. El estadio existente se conserva; no se infiere de nombres de equipos.
La duración de los partidos sigue siendo dos horas.

El calendario es para esta temporada. Una nueva temporada o cambio de grupo
requiere revisar los identificadores RFEF y el calendario base, conservando la
identidad de los eventos antiguos. El proceso no inventa jornadas de otra liga.
Los horarios de ejecución de GitHub y la actualización de Google pueden retrasarse.
