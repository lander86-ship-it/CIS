# CIS Benchmark CLI — Contenedor (local / on-premise)

Contenerización de la herramienta [`mitre/cis-bench`](https://github.com/mitre/cis-bench):
una **CLI en Python** para descargar, gestionar y exportar benchmarks de seguridad
CIS desde [CIS WorkBench](https://workbench.cisecurity.org/) a múltiples formatos
(YAML, CSV, JSON, Markdown, XCCDF / DISA STIG).

Este repositorio **no reimplementa** la herramienta: la empaqueta en una imagen
Docker reproducible para ejecutarla on-premise sin instalar Python 3.12 ni las
dependencias en la máquina anfitriona.

> ℹ️ `cis-bench` es una herramienta de **línea de comandos**, no un servicio web.
> El contenedor no expone puertos; solo hace peticiones HTTPS salientes a CIS
> WorkBench. Se ejecuta bajo demanda (`docker compose run --rm ...`), no con `up`.

---

## Requisitos

- Docker Engine 20.10+ con el plugin **Docker Compose v2** (`docker compose`).
- Una cuenta en **CIS WorkBench** (gratuita) para autenticarte.

---

## Estructura del repo

```
.
├── Dockerfile            # Imagen basada en python:3.12-slim + cis-bench (pip)
├── docker-compose.yml    # Servicio "cis-bench" con volúmenes ./data y ./work
├── Makefile              # Atajos: build, login, auth-status, shell, ...
├── scripts/cis-bench     # Wrapper para usar la CLI como si fuera nativa
├── data/                 # (volumen) sesión + catalog.db  — NO se commitea
├── work/                 # (volumen) archivos exportados  — NO se commitea
└── .env.example          # Variables de entorno de ejemplo
```

Rutas dentro del contenedor:

| Host      | Contenedor | Contenido                                   |
|-----------|------------|---------------------------------------------|
| `./data`  | `/data`    | Sesión (`.cis-bench/session.cookies`) + `catalog.db` (persistente) |
| `./work`  | `/work`    | Archivos exportados (directorio de trabajo) |

`HOME=/data` dentro del contenedor, por lo que el estado de la app (`~/.cis-bench`)
vive en `./data/.cis-bench` y persiste entre ejecuciones.

---

## 1. Construir la imagen

```bash
docker compose build
# o:  make build
```

Para fijar otra versión de la CLI:

```bash
docker compose build --build-arg CIS_BENCH_VERSION=0.5.2
```

Verifica:

```bash
docker compose run --rm cis-bench --version
# o:  make version
```

---

## 2. Autenticarse (modo headless con cookies)

El contenedor **no tiene navegador**, así que no puede extraer cookies
automáticamente como la instalación nativa. Se usa el método headless oficial
con un archivo de cookies en **formato Netscape (`cookies.txt`)**:

1. Inicia sesión en <https://workbench.cisecurity.org/> en tu navegador.
2. Exporta las cookies con una extensión tipo *"Get cookies.txt / cookies.txt LOCALLY"*.
3. Guarda el archivo como **`data/cookies.txt`** en este repo.
4. Ejecuta:

   ```bash
   docker compose run --rm cis-bench auth login --cookies /data/cookies.txt
   # o:  make login
   ```

La sesión queda guardada en `data/.cis-bench/session.cookies` y persiste.
Comprueba el estado:

```bash
docker compose run --rm cis-bench auth status
# o:  make auth-status
```

> 🔒 `data/cookies.txt`, `*.cookies` y `.env` están en `.gitignore`: no se
> suben al repositorio. Bórralo del host cuando termines si lo prefieres.

> ¿Ya tienes una instalación nativa autenticada? Copia tu
> `~/.cis-bench/session.cookies` del host a `./data/.cis-bench/session.cookies`
> y omite el paso de login.

---

## 3. Usar la CLI

Con `docker compose run --rm`:

```bash
# Refrescar el catálogo (primera vez / periódicamente)
docker compose run --rm cis-bench catalog refresh

# Buscar
docker compose run --rm cis-bench search "ubuntu 22"
docker compose run --rm cis-bench search --platform-type cloud

# Descargar un benchmark por ID
docker compose run --rm cis-bench download 23598

# Exportar a un archivo (queda en ./work del host)
docker compose run --rm cis-bench export 23598 --format csv -o /work/output.csv
docker compose run --rm cis-bench get "ubuntu 22.04" --format xccdf --style cis -o /work/ubuntu.xml
```

### Wrapper (más cómodo)

`scripts/cis-bench` monta los volúmenes por ti y se comporta como la CLI nativa:

```bash
./scripts/cis-bench search "ubuntu 22"
./scripts/cis-bench get "ubuntu 22.04" --format xccdf --style cis -o /work/ubuntu.xml
```

Opcional — instalarlo en tu `PATH`:

```bash
sudo ln -s "$(pwd)/scripts/cis-bench" /usr/local/bin/cis-bench
cis-bench --help
```

---

## Configuración

Copia `.env.example` a `.env` (lo lee `docker compose`):

```bash
cp .env.example .env
```

| Variable               | Valores                     | Descripción                                        |
|------------------------|-----------------------------|----------------------------------------------------|
| `CIS_BENCH_ENV`        | `production` (def), `dev`, `test` | Selecciona el directorio de datos (`~/.cis-bench`, `~/.cis-bench-dev`, temp). |
| `CIS_BENCH_SSL_VERIFY` | `true` (def), `false`       | Pon `false` solo detrás de un proxy que intercepta TLS. |
| `CIS_BENCH_VERSION`    | ej. `0.5.2`                 | Versión de la CLI a instalar (build arg).          |

---

## Comandos útiles del Makefile

```bash
make help          # Lista todos los atajos
make build         # Construir la imagen
make rebuild       # Reconstruir sin caché
make login         # Login headless con ./data/cookies.txt
make auth-status   # Ver estado de autenticación
make version       # Versión de la CLI
make shell         # Shell dentro del contenedor (debug)
make clean         # Borrar la imagen (conserva ./data y ./work)
```

---

## Notas y solución de problemas

- **Persistencia:** todo el estado vive en `./data`. Bórralo para empezar de cero.
- **Permisos de archivos exportados:** el contenedor corre como `root`; los
  archivos en `./work` pueden pertenecer a `root`. Ajusta con
  `sudo chown -R "$USER" work/` si hace falta, o usa `--user "$(id -u):$(id -g)"`.
- **Sesión caducada:** vuelve a exportar `cookies.txt` y repite el paso 2.
- **Proxy corporativo con TLS interception:** exporta `CIS_BENCH_SSL_VERIFY=false`
  (solo si es imprescindible).

---

## Créditos y licencia

La herramienta `cis-bench` es de **MITRE** y se distribuye bajo **Apache 2.0**
(ver [mitre/cis-bench](https://github.com/mitre/cis-bench)). Este repositorio
solo aporta el empaquetado en contenedor.
