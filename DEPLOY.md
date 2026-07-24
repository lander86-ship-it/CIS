# Desplegar en Railway (o similar) — URL pública

Esta guía deja la app corriendo en la nube con una **URL pública** que abres en
Chrome, sin ejecutar comandos en tu equipo. El despliegue se hace desde la web
de Railway conectando tu repositorio de GitHub.

> ⚠️ **No puedo desplegarlo por ti**: no tengo acceso a tu cuenta de Railway.
> Estos son los pasos (son clics en su panel). El repo ya está preparado
> (`Dockerfile` + `railway.json`, y el servidor escucha en `$PORT`).

---

## 1. Requisitos

- Una cuenta en [railway.app](https://railway.app) (tiene plan gratuito).
- El repo en GitHub: `lander86-ship-it/cis`, rama `claude/cis-benchmark-deployment-bz4teg`
  (o fusiónala a `main` antes de desplegar).

## 2. Crear el proyecto

1. Entra a [railway.app](https://railway.app) → **New Project**.
2. **Deploy from GitHub repo** → autoriza GitHub y elige `lander86-ship-it/cis`.
3. En **Settings → Source**, selecciona la rama a desplegar.
4. Railway detecta el `Dockerfile` (forzado por `railway.json`) y construye la
   imagen automáticamente.

## 3. Variables de entorno

En **Settings → Variables**, añade (los valores sensibles viven aquí, nunca en git):

| Variable | Valor | Obligatoria |
|----------|-------|:-----------:|
| `APP_USERS` | `usuario1:clave1,usuario2:clave2` (usa tus credenciales reales) | ✅ |
| `APP_SECRET` | una cadena aleatoria larga (ej. `openssl rand -hex 32`) | ✅ |
| `APP_SESSION_TTL` | `86400` (opcional, 1 día) | — |
| `CIS_COOKIES_B64` | base64 de tu `cookies.txt` (opcional, ver abajo) | — |
| `ANTHROPIC_API_KEY` | tu API key de Anthropic (opcional; activa la redacción con IA de las secciones narrativas) | — |
| `POLICY_LLM_MODEL` | modelo para la IA (def. `claude-opus-5`; `claude-sonnet-5` para abaratar) | — |

> Las contraseñas no pueden contener `,` ni `:`.

Para pre-autenticar la sesión de CIS WorkBench sin subir el archivo a mano:

```bash
base64 -w0 cookies.txt   # copia la salida al valor de CIS_COOKIES_B64
```

Si no la pones, simplemente inicia sesión desde la UI (paso 1 · Option B) tras desplegar.

## 4. Dominio público

En **Settings → Networking → Generate Domain**. Obtendrás algo como
`https://cis-xxxx.up.railway.app`. Esa es tu URL para Chrome.

Al abrirla verás la **pantalla de login** (usuario/contraseña de `APP_USERS`).

## 5. Persistencia (recomendado)

El disco de Railway es efímero: sin volumen, la sesión de WorkBench y el
`catalog.db` se pierden en cada redeploy.

1. En el proyecto → **New → Volume**.
2. **Mount path**: `/data`  (ahí viven `~/.cis-bench/session.cookies` y `catalog.db`).

*(La carpeta de exportaciones `/work` también es efímera; los `.docx` generados
se descargan al navegador, así que no necesita volumen — pero puedes añadir otro
en `/work` si quieres conservarlos en el servidor.)*

---

## Notas

- **Puerto**: Railway inyecta `$PORT`; el `Dockerfile` ya lo usa
  (`uvicorn --port ${PORT:-8000}`).
- **Red**: `cis-bench` necesita salida HTTPS a `workbench.cisecurity.org`
  (Railway la permite).
- **Recursos**: la generación de políticas grandes usa CPU/tiempo; el plan
  gratuito suele bastar para uso puntual.

## Alternativas

- **Render** ([render.com](https://render.com)): New → Web Service → conecta el
  repo → *Runtime: Docker*. Añade las mismas variables y un *Disk* montado en
  `/data`. Render también inyecta `$PORT`.
- **Fly.io**: `fly launch` detecta el `Dockerfile`; define las variables con
  `fly secrets set` y un volumen en `/data`.
