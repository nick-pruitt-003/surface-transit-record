"""Read Omnibus Express (AE) schedules straight from its public booking site.

The site's own page makes four plain calls and needs no login: CreaSesion (a session number), RecuperaCorridas
(departures for a stop pair and a dd/mm/yyyy date) and consultaItinerario (stop-by-stop times for one departure).
This only reads the public timetable; it never touches booking.

    py omnibus_fetch.py MCI ELP 2026-11-20            # departures and full stop tables for one day
    py omnibus_fetch.py MCI ELP 2026-11-09 --days 14  # which weekdays run, and whether the times hold

Times come back as each stop's local clock (Texico MT next to Farwell CT), exactly as the site prints them.
"""
import argparse, datetime, http.cookiejar, json, sys, urllib.parse, urllib.request

B = 'https://venta.omnibusexpress.com/OExpress/Filtros/Paso1/'


class Site:
    def __init__(s):
        s.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        s.cons = s._get('CreaSesion').strip()

    def _get(s, path):
        return s.op.open(B + path, timeout=30).read().decode('utf-8', 'ignore')

    def _post(s, path, data):
        req = urllib.request.Request(B + path, urllib.parse.urlencode(data).encode())
        return s.op.open(req, timeout=60).read().decode('utf-8', 'ignore')

    def departures(s, o, d, day):
        r = s._post('RecuperaCorridas', dict(salidaCode=o, regresoCode=d, salida=day.strftime('%d/%m/%Y'), adultos=1,
                                             senectud=0, menores=0, estudiantes=0, profesores=0, V1_V2='V1',
                                             consecutivo=s.cons, modo=1)).strip()
        try:
            return json.loads(r) if r.startswith('[') else []
        except json.JSONDecodeError:
            return []

    def itinerary(s, o, d, run):
        r = s._post('consultaItinerario', dict(
            ClaveCorrida=run['claveCorrida'].strip(), FechaSalidaInicio=run['FechaSalidaInicio'],
            FechaSalidaIBoleto=run['FechaSalidaBoleto'], HoraSalidaBoleto=run['HoraSalida'],
            ClaveOficinaOrigen=o, ClaveOficinaDestino=d, empresaCorrida=run['EmpresaCorrida'],
            CadenaEmpresas=run['EmpresaCorrida'], CadenaCorridas=run['CadenaCorridaTKN'],
            FechaCadena=run['CadenaFechaTKN'], CadenaPuntoInicial=run['CadenaPuntoInicialTKN'],
            CadenaPuntoFinal=run['CadenaPuntoFinalTKN'])).strip()
        try:
            return json.loads(r) if r.startswith('[') else []
        except json.JSONDecodeError:
            return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('origin'); ap.add_argument('dest'); ap.add_argument('date')
    ap.add_argument('--days', type=int, default=1)
    ap.add_argument('--raw', action='store_true', help='print the itinerary JSON as returned')
    a = ap.parse_args()
    site = Site()
    d0 = datetime.date.fromisoformat(a.date)
    for i in range(a.days):
        day = d0 + datetime.timedelta(days=i)
        runs = site.departures(a.origin, a.dest, day)
        print(f'{day} {day.strftime("%a")}: {len(runs)} departures '
              + ', '.join(f'{r["HoraSalida"]}->{r["HoraLlegada"]}' for r in runs))
        for r in runs:
            it = site.itinerary(a.origin, a.dest, r)
            if a.raw:
                print(json.dumps(it, indent=1, ensure_ascii=False)); continue
            for row in it:
                print('    ' + ' | '.join(str(v).strip() for v in row.values()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
