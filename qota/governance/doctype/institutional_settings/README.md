# Configuración institucional

`Institutional Settings` es el Single administrativo de Governance para la única
oficina de la Junta. Se abre desde la búsqueda del escritorio o la ruta
`/app/institutional-settings`. Solo System Manager puede leer y modificar el
formulario. El historial de cambios utiliza `Version` de Frappe.

La instalación no carga horarios, feriados, direcciones, enlaces ni traslados.
Una tabla vacía significa información pendiente, no apertura ni cierre permanente.

## Administración

- **Horario semanal:** si se configura, registrar explícitamente los siete días,
  de lunes a domingo. Un día cerrado tiene una fila sin horas; un día abierto tiene
  uno o más intervalos ordenados sin superposición. Se permiten intervalos contiguos.
- **Excepciones del calendario:** debajo del horario semanal, una sección HTML lista
  las fechas de hoy en adelante en orden cronológico. La fecha de referencia procede
  del servidor en `America/Tegucigalpa`, nunca del navegador. No se borran filas pasadas.
  Registrar excepción ofrece exactamente tres diálogos nativos: Registrar feriado
  (solo fecha; Closed), Horario extraordinario (fecha, apertura, cierre y motivo;
  Open) y Cierre extraordinario (fecha y motivo; Closed). Un horario extraordinario
  contiene exactamente un intervalo y sustituye toda la jornada semanal de su fecha.
  Las tablas `calendar_exceptions` y `exception_hours` siguen siendo la persistencia,
  ocultas en el formulario. No se admiten reuniones administrativas ni jornadas especiales.
  Editar permite cambiar fecha y horas sin duplicar intervalos; Eliminar pide confirmación
  y limpia los intervalos asociados. Los diálogos no guardan: señalan cambios pendientes
  para el botón general Guardar, preservando las otras modificaciones del formulario.
- **Motivos:** son exclusivamente internos, almacenados en `internal_reason` y
  obligatorios para horario extraordinario y cierre extraordinario. El feriado no los
  solicita. `public_reason` permanece oculto, vacío y validado; nunca se publican motivos
  de excepciones.
- **Ubicaciones:** registrar dirección, referencias opcionales y fecha de vigencia,
  en orden temporal. La primera ubicación debe estar vigente al guardar. Las fechas
  y direcciones no se repiten. Confirmar la aprobación para publicación de cada fila.
  La tabla conserva únicamente la secuencia de una oficina y sus traslados.
- **Mapa:** opcional; se admiten enlaces HTTPS de `google.com/maps`,
  `www.google.com/maps`, `maps.google.com`, `maps.app.goo.gl` y `goo.gl/maps/`.
  La validación estructural no verifica el destino: el administrador debe comprobarlo
  manualmente y marcar `maps_verified`. Sin esa confirmación el enlace se omite.

## Lectores y reloj

`qota.governance.institutional.office_information(value=None)` devuelve `date`,
`timezone`, `hours` y `location`; nunca devuelve el documento administrativo.
Acepta fecha, datetime o cadena ISO. Un datetime sin zona representa hora local
institucional; uno con zona se convierte a `America/Tegucigalpa`. Sin argumento
usa `frappe.utils.get_datetime_in_timezone`. `hours.ordinary_week` proporciona los siete días oficiales para la futura respuesta
principal de horarios; los intervalos del día consultado ya incorporan excepciones.
Una fecha sin hora no determina apertura
instantánea (`within_hours=None`).

`is_within_office_hours(value=None)` es el lector común de horario de oficina.
Requiere un datetime explícito cuando se proporciona argumento. Devuelve
`status`, `reason_code`, `source`, `date`, `timezone` y `within_hours`. Una jornada
no disponible devuelve `within_hours=False`, con `status=Unavailable`; el consumidor
puede distinguirla de un cierre configurado. Esto no autoriza sesiones ni acciones
administrativas por sí mismo.

La apertura es inclusiva y el cierre exclusivo: `[start, end)`. El modelo inicial
rechaza intervalos que crucen medianoche y `24:00`; admite apertura a `00:00`.
Las excepciones sustituyen todo el día y pueden definir un día aislado aunque el
horario semanal todavía no esté disponible. Cualquier contradicción en el calendario
produce `Unavailable/invalid_configuration`, nunca una jornada autorizada.

La ubicación se resuelve por la última fecha de vigencia menor o igual a la fecha
local consultada. Cada traslado entra en vigor a las 00:00 de Honduras; no necesita
scheduler. Si la ubicación ya vigente carece de aprobación, se devuelve
`Unavailable/not_approved`, sin reutilizar la anterior. No se publican ubicaciones
futuras. Un calendario inválido no invalida automáticamente una ubicación válida,
y viceversa.

Los lectores cargan el Single con `frappe.get_doc`, sin caché adicional. Cada llamada
ve los cambios guardados visibles en su transacción. Ambas decisiones se construyen
con el mismo snapshot documental; no se mantiene una dirección resuelta en caché.

Como vista previa administrativa, desde `bench --site qota.localhost console`:

```python
from qota.governance.institutional import office_information, is_within_office_hours
from datetime import date, datetime
information = office_information(date(2026, 10, 12))
working = is_within_office_hours(datetime(2026, 10, 12, 8, 0))
```

Estas fechas son argumentos de consulta, no datos institucionales cargados. La
consulta administrativa GET `calendar_context` entrega solo la fecha del servidor y
la zona institucional, con lectura ordinaria y rol System Manager. No hay endpoints
nuevos de escritura; los motivos internos nunca se exponen en proyecciones públicas.


## Governance Settings and telephone capture

The technical Single remains `Institutional Settings`; its employee-facing name is
`Governance Settings` (`Configuración de Gobernanza`). Existing routes and the four
institutional tables remain unchanged. `default_phone_region` is optional and initially
empty on both upgrades and new installations. It only initializes new captures.

The reviewed historical region assignment is a separate, confirmed System Manager
operation with Subscriber read/write permissions. It records counts, actor, date and
region in native Version, assigns only missing regions and never rewrites original
numbers or invokes Subscriber.save. Invalid historical values survive assignment, but
every later ordinary Subscriber save must correct or explicitly clear them.

Telephone validity is provided by `qota.phones`, independent of office readers. It does
not authorize public disclosure, identify a subscriber or confirm line ownership.
