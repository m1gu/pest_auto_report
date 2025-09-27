# Pest Auto Report

Pest Auto Report es una aplicacion de escritorio en PySide6 para automatizar la generacion de reportes de pesticidas. Se integra con QBench para recuperar informacion de muestras, cruza los resultados de un Excel de laboratorio y publica los reportes finales en Supabase, ademas de exportar archivos Excel con los calculos normalizados.

## Flujo funcional
- Autenticacion contra Supabase para validar operadores del laboratorio.
- Ingreso de identificadores de batch y seleccion del archivo Excel con resultados crudos.
- Descarga de metadata de muestras desde QBench (`core.qbench_client.QBenchClient`).
- Normalizacion y calculo de resultados (`app.services.ps_processing`).
- Visualizacion de resumenes en la UI (`app.ui.main_window.MainWindow`).
- Exportacion de reportes Excel y registro historico en Supabase (`app.services.storage`).

## Requisitos
- Python 3.11 o superior.
- Pip y virtualenv (recomendado).
- Credenciales validas de QBench y Supabase.
- Librerias del sistema necesarias para PySide6 (Qt) y openpyxl.

## Instalacion
```bash
# clonar el repositorio
$ git clone <url>
$ cd PestAutoReport

# crear entorno virtual
$ python -m venv .venv

# activar entorno
# Windows
$ .\.venv\Scripts\activate
# macOS / Linux
$ source .venv/bin/activate

# instalar dependencias
$ pip install --upgrade pip
$ pip install -r requirements.txt
```

### Variables de entorno
Crea un archivo `.env` en la raiz con los siguientes valores:

```
APP_NAME=pest_auto_report
APP_ENV=dev

SUPABASE_URL=https://<project>.supabase.co
SUPABASE_ANON_KEY=<public-anon-key>

QBENCH_BASE_URL=https://<dominio-qbench>
QBENCH_CLIENT_ID=<client-id>
QBENCH_CLIENT_SECRET=<client-secret>
QBENCH_JWT_LEEWAY_S=20
QBENCH_JWT_TTL_S=3580
```

`core.config.ensure_env()` valida que las claves esenciales de Supabase esten presentes. El cliente QBench rechaza la inicializacion si faltan las variables `QBENCH_*`.

## Ejecucion
```bash
$ python -m app.main
```
La aplicacion aplica `style.qss` si esta presente y levanta un flujo de trabajo con una ventana de login y la ventana principal. Para construir ejecutables puedes utilizar PyInstaller (no incluido) utilizando `app.main:main` como punto de entrada.

## Estructura del proyecto
```
app/
  main.py                # punto de entrada de la UI
  services/
    ps_processing.py     # parser de Excel y motor de calculos/normalizacion
    storage.py           # integracion con Supabase para persistir reportes
  ui/
    login_window.py      # dialogo de autenticacion
    main_window.py       # ventana principal: batches, resultados y exportacion
    processed_results_window.py
    samples_window.py
    style.qss            # estilos Qt opcionales
  workers/
    batch_process_worker.py  # hilos Qt que coordinan QBench, Excel y calculos
    qbench_fetch_worker.py   # hilo para vistas auxiliares
core/
  config.py              # carga de .env y constantes
  qbench_client.py       # cliente REST con reintentos y parsing de payloads
  supa.py                # inicializacion lazy de Supabase
Excel reports/           # salida de reportes generados
tests/
  test_qbench_client.py  # pruebas unitarias iniciales (pytest)
```

## Detalles tecnicos
- **QBenchClient** maneja autenticacion JWT, reintentos con backoff y extraccion de metadata (`_extract_sample_ids_from_batch`, `_sample_rows_from_payload`).
- **Procesamiento de resultados**: `process_batch_dataframe` consume la hoja `"raw results"`, normaliza IDs, calcula concentraciones y genera objetos `ProcessedSample`/`ProcessedAnalyte` que luego se exportan a Excel o a Supabase.
- **UI multiproceso**: los workers (`QThread`) emiten se�ales `progressed`/`finished` para actualizar la UI sin bloquear.
- **Persistencia**: `app.services.storage.save_samples` convierte los resultados en payload JSON y los inserta en la tabla `ps_reports` via Supabase.
- **Exportacion**: `export_sample_to_excel` crea reportes con formato, auto-ajuste de columnas y metadatos de la muestra.

## Ejecutar pruebas
```bash
$ python -m pytest
```
El directorio `tests/` contiene pruebas para la logica de parsing y normalizacion del cliente QBench. Agrega mas pruebas para `ps_processing` y servicios segun se vayan incorporando casos edge.

- La carpeta `Excel reports/` se crea automaticamente con subcarpetas por fecha (YYYYMMDD).

