# CIS Benchmark — CLI + Interfaz Web (local / on-premise)

Empaqueta la herramienta [`mitre/cis-bench`](https://github.com/mitre/cis-bench)
(una **CLI en Python** para descargar y exportar benchmarks de seguridad CIS
desde [CIS WorkBench](https://workbench.cisecurity.org/)) y le añade una
**interfaz web (UI)** para usarla desde el navegador.

Puedes ejecutarlo de tres maneras, todas **en local / on-premise**:

| Modo | Cómo | Requisitos |
|------|------|-----------|
| 🌐 **Web UI (Docker)** | `docker compose up ui` → http://localhost:8000 | Docker |
| 🌐 **Web UI (nativo)** | `./run-local.sh` → http://localhost:8000 | Python 3.12+ |
| ⌨️ **CLI (Docker)** | `docker compose run --rm cli <args>` | Docker |

No expone servicios a Internet: solo hace peticiones **HTTPS salientes** a CIS
WorkBench. El servidor web escucha en `localhost:8000`.

---

## Arquitectura

```
Navegador ──HTTP──> FastAPI (app/main.py) ──subprocess──> cis-bench (CLI) ──HTTPS──> CIS WorkBench
                          │                                     │
                       app/static/ (UI)                 ~/.cis-bench (sesión + catalog.db)
```

El backend **no reimplementa** nada: envuelve la CLI de forma segura
(`subprocess`, sin shell, con listas de argumentos validadas) y sirve una UI
estática. Los archivos exportados se guardan en el volumen de trabajo y se
descargan desde el navegador.

```
.
├── Dockerfile            # Imagen python:3.12-slim: cis-bench + FastAPI/uvicorn
├── docker-compose.yml    # Servicios: ui (web) y cli (one-shot)
├── requirements.txt      # cis-bench + fastapi + uvicorn + python-multipart
├── run-local.sh          # Ejecutar la Web UI sin Docker (crea venv)
├── Makefile              # Atajos: build, up, login, ...
├── app/
│   ├── main.py           # FastAPI: API REST + sirve la UI
│   ├── cis.py            # Wrapper seguro alrededor de la CLI
│   └── static/           # index.html, styles.css, app.js
├── scripts/cis-bench     # Wrapper para usar la CLI como si fuera nativa
├── data/                 # (volumen) sesión + catalog.db — NO se commitea
└── work/                 # (volumen) archivos exportados — NO se commitea
```

Rutas dentro del contenedor: `./data → /data` (`HOME`, estado de la app) y
`./work → /work` (`CIS_WORK_DIR`, exportaciones). Ambos volúmenes se comparten
entre la UI y la CLI, así que **autenticarte en cualquiera vale para las dos**.

---

## Opción A — Web UI con Docker (recomendada)

```bash
docker compose up ui        # construye la imagen y arranca el servidor
# o en segundo plano:  docker compose up -d ui   /   make up
```

Abre **http://localhost:8000**. La UI tiene 4 pasos:

1. **Autenticación** — sube tu `cookies.txt` (ver más abajo).
2. **Catálogo** — botón *Refrescar catálogo* (primera vez / periódicamente).
3. **Buscar** — busca benchmarks por texto o `platform-type`.
4. **Exportar** — elige ID/consulta, formato y estilo → genera un archivo
   descargable (aparece en *Archivos exportados*).

Parar: `docker compose down` (o `make down`).

---

## Opción B — Web UI nativa (sin Docker)

Requiere **Python 3.12+** en la máquina.

```bash
./run-local.sh              # crea .venv, instala deps y arranca el servidor
# o:  make local
```

Abre **http://localhost:8000**. El estado se guarda en `./data` y las
exportaciones en `./work`, igual que con Docker. Cambia el puerto con
`PORT=9000 ./run-local.sh`.

---

## Opción C — CLI (Docker)

```bash
docker compose run --rm cli auth login --cookies /data/cookies.txt
docker compose run --rm cli search "ubuntu 22"
docker compose run --rm cli get "ubuntu 22.04" --format xccdf --style cis -o /work/ubuntu.xml
```

O con el wrapper (se comporta como la CLI nativa):

```bash
./scripts/cis-bench search "ubuntu 22"
# opcional: instalarlo en el PATH
sudo ln -s "$(pwd)/scripts/cis-bench" /usr/local/bin/cis-bench
```

---

## Autenticación (headless con cookies)

Ni el contenedor ni el servidor tienen navegador, así que se usa el método
headless oficial con un archivo de cookies en **formato Netscape**:

1. Inicia sesión en <https://workbench.cisecurity.org/> en tu navegador.
2. Exporta las cookies con una extensión tipo *"Get cookies.txt LOCALLY"*.
3. **Desde la UI**: súbelas en el paso *Autenticación*.
   **Desde la CLI**: guárdalas como `data/cookies.txt` y ejecuta
   `docker compose run --rm cli auth login --cookies /data/cookies.txt`
   (o `make login`).

La sesión queda en `data/.cis-bench/session.cookies` y persiste. La UI no
conserva el `cookies.txt` subido: lo borra tras iniciar sesión.

> 🔒 `cookies.txt`, `*.cookies` y `.env` están en `.gitignore` y `.dockerignore`.

---

## API REST

La UI consume esta API (útil también para automatizar):

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET`  | `/api/health` | Estado de la CLI y del servidor |
| `GET`  | `/api/auth/status` | Estado de autenticación |
| `POST` | `/api/auth/login` | Login (multipart: `cookies`) |
| `POST` | `/api/catalog/refresh` | Refrescar catálogo |
| `GET`  | `/api/search?q=&platform_type=` | Buscar benchmarks |
| `GET`  | `/api/list` | Listar catálogo (JSON) |
| `POST` | `/api/export` | Exportar (`identifier`, `fmt`, `style`, `filename`) |
| `GET`  | `/api/files` | Listar archivos exportados |
| `GET`  | `/api/files/{name}` | Descargar un archivo |

Docs interactivas (Swagger) en **http://localhost:8000/docs**.

---

## Configuración

| Variable | Valores | Descripción |
|----------|---------|-------------|
| `CIS_BENCH_ENV` | `production` (def), `dev`, `test` | Directorio de datos (`~/.cis-bench`, ...) |
| `CIS_BENCH_SSL_VERIFY` | `true` (def), `false` | `false` solo detrás de proxy con TLS interception |
| `CIS_BENCH_VERSION` | ej. `0.5.2` | Versión de la CLI a instalar (build arg) |
| `CIS_WORK_DIR` | ruta | Dónde se escriben las exportaciones (def `/work`) |
| `PORT` | ej. `8000` | Puerto del servidor en modo nativo |

Copia `.env.example` a `.env` (lo lee `docker compose`).

---

## Makefile

```bash
make help          # Lista todos los atajos
make build         # Construir la imagen
make up            # Web UI (Docker) en :8000
make down          # Parar la Web UI
make local         # Web UI nativa (sin Docker)
make login         # CLI: login headless con ./data/cookies.txt
make auth-status   # CLI: estado de autenticación
make shell         # Shell dentro de la imagen (debug)
make clean         # Borrar la imagen
```

---

## Solución de problemas

- **"CLI no encontrada" en la UI:** en modo nativo necesitas Python 3.12+
  (la instala `run-local.sh` dentro del venv). Con Docker, reconstruye:
  `docker compose build --no-cache`.
- **Permisos en `./work`:** el contenedor corre como `root`; ajusta con
  `sudo chown -R "$USER" work/` o añade `--user "$(id -u):$(id -g)"`.
- **Sesión caducada:** vuelve a exportar `cookies.txt` y repite el login.
- **Proxy con TLS interception:** `CIS_BENCH_SSL_VERIFY=false` (solo si es
  imprescindible).

---

## Créditos y licencia

`cis-bench` es de **MITRE**, bajo **Apache 2.0** (ver
[mitre/cis-bench](https://github.com/mitre/cis-bench)). Este repositorio
aporta el empaquetado en contenedor y la interfaz web.
