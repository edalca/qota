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

Las proyecciones públicas de horario y ubicación están en la aplicación puente.
QOTA conserva los validadores que utiliza este formulario, sus reglas de privacidad,
la zona America/Tegucigalpa y las operaciones administrativas nativas. No depende
de Messaging ni ofrece wrappers de lectura usados únicamente por sus Processes.
