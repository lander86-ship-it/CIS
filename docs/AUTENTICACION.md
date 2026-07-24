# Cómo autenticarte (obtener tu `cookies.txt`)

Esta guía explica **qué son las cookies** que pide la app y **cómo obtenerlas**
paso a paso. No necesitas conocimientos técnicos.

---

## ¿Por qué hace falta esto?

[CIS WorkBench](https://workbench.cisecurity.org/) **obliga a iniciar sesión**
para descargar benchmarks. La herramienta `cis-bench` no guarda tu usuario ni
tu contraseña: en su lugar **reutiliza la sesión que ya iniciaste en tu
navegador**, representada por unas *cookies de sesión*.

- Una **cookie de sesión** es un identificador temporal que tu navegador
  recibe al iniciar sesión. Equivale a un "pase" que dice *"este usuario ya
  está autenticado"*.
- **No es tu contraseña.** Caduca al cerrar sesión o pasado un tiempo. Cuando
  eso ocurre, simplemente repites estos pasos.
- Se exportan a un archivo de texto en **formato Netscape** (el estándar que
  espera `cis-bench`), llamado por convención `cookies.txt`.

---

## Dos formas de hacerlo

- **Opción A — Automático desde el navegador** (más cómoda, solo en modo
  nativo `./run-local.sh`): en la UI eliges tu navegador y pulsas *Iniciar
  sesión con el navegador*; la herramienta lee las cookies de tu navegador
  local. Requiere haber iniciado sesión en WorkBench en ese navegador. Chrome
  reciente cifra las cookies y a veces falla — entonces usa la Opción B.
- **Opción B — Exportar `cookies.txt`** (funciona siempre, también con Docker):
  es lo que se explica a continuación.

## Paso a paso (Opción B)

### Chrome, Edge o Brave

1. **Instala una extensión de exportación de cookies.**
   Recomendada: **"Get cookies.txt LOCALLY"** (Chrome Web Store). Es
   open-source y funciona **localmente** — no envía tus cookies a ningún sitio.

2. **Inicia sesión en CIS WorkBench.**
   Abre <https://workbench.cisecurity.org/> y entra con tu cuenta.

3. **Exporta las cookies.**
   Con la pestaña de WorkBench abierta y con la sesión iniciada, haz clic en el
   icono de la extensión (barra de extensiones, arriba a la derecha) y pulsa
   **"Export"**. Verifica que el formato sea **Netscape**.

4. **Guarda el archivo `cookies.txt`.**
   Se descargará a tu carpeta de descargas.

### Firefox

Igual que arriba, pero instala la extensión **"cookies.txt"** (de Lennon Hill).
Entra a WorkBench logueado → clic en la extensión → exportar.

---

## Usar el `cookies.txt`

### Desde la interfaz web (UI)

1. Abre la app (http://localhost:8000).
2. En **"1 · Autenticación"**, pulsa el selector de archivo y elige tu
   `cookies.txt`.
3. Pulsa **"Iniciar sesión"**. El indicador *auth* pasará a verde si todo va
   bien.

La UI **no conserva** el archivo subido: lo borra en cuanto valida la sesión.

### Desde la CLI

1. Copia tu `cookies.txt` a la carpeta `data/` del proyecto.
2. Ejecuta:
   ```bash
   docker compose run --rm cli auth login --cookies /data/cookies.txt
   #  o:  make login
   ```

---

## Preguntas frecuentes

**¿Es seguro?**
Sí, siempre que uses una extensión reputada y *local* (como las recomendadas).
Las cookies dan acceso a **tu** sesión de WorkBench, así que trátalas como una
credencial: no las compartas ni las subas a repositorios. En este proyecto
están excluidas por `.gitignore` y `.dockerignore`.

**¿Cada cuánto tengo que repetir esto?**
Solo cuando la sesión caduque (verás fallos de autenticación). Entonces vuelves
a exportar el `cookies.txt` y a iniciar sesión.

**¿Puedo evitar las extensiones?**
Las extensiones son la vía más fiable. La instalación *nativa* de `cis-bench`
puede extraer cookies del navegador automáticamente
(`cis-bench auth login --browser chrome`), pero eso requiere ejecutar la
herramienta directamente en tu equipo (no dentro del contenedor) y algunos
navegadores cifran las cookies, lo que puede fallar. Por eso aquí usamos el
método del `cookies.txt`, que funciona siempre.

**Borré el `cookies.txt`, ¿pasa algo?**
No. Una vez iniciada la sesión, `cis-bench` la guarda en
`data/.cis-bench/session.cookies`. Puedes borrar el `cookies.txt` original.
