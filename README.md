# NFL Picks Agent

Dashboard que se actualiza solo durante toda la temporada NFL con:

- **Top 3 de equipos más probables a ganar** esa semana.
- Probabilidad de victoria combinando dos fuentes de datos duros:
  - Modelo de proyección de ESPN (tipo FPI) por partido.
  - Probabilidad implícita del mercado de apuestas (moneyline de DraftKings, vía ESPN).
- Parte de lesiones por equipo (Out / Doubtful / Questionable) para cada partido.

No usa ninguna API de pago ni requiere cuentas: todo sale de los endpoints
públicos de `site.api.espn.com`.

## Cómo funciona

- `fetch.py` descarga el calendario de la semana actual y, por cada partido,
  el resumen de ESPN (proyección de victoria, líneas de apuestas y lesiones).
  Combina ambas probabilidades y escribe todo en `data/latest.json`.
- `index.html` es un dashboard estático que lee ese JSON y lo muestra
  (top 3, ranking completo de la semana, partidos con lesiones clave).
- `.github/workflows/update.yml` corre `fetch.py` **todos los días a las
  13:00 UTC** durante toda la temporada y commitea `data/latest.json` si
  cambió. Así el dashboard queda al día sin que nadie tenga que tocar nada.

## Puesta en marcha (una sola vez)

1. Crear un repositorio nuevo en GitHub (puede ser privado o público) y
   subir este proyecto:

   ```bash
   cd /Users/king/nfl-picks-agent
   git add -A
   git commit -m "NFL Picks Agent: dashboard inicial"
   git remote add origin <URL_DE_TU_REPO_EN_GITHUB>
   git branch -M main
   git push -u origin main
   ```

2. En GitHub: **Settings → Pages** → Source: `Deploy from a branch` →
   Branch: `main` / carpeta `/ (root)`. Guardar. GitHub te da una URL tipo
   `https://<tu-usuario>.github.io/nfl-picks-agent/` — esa es la que abrís
   en el celular o donde quieras durante toda la temporada.

3. En **Settings → Actions → General → Workflow permissions**, marcar
   "Read and write permissions" para que el workflow pueda commitear
   `data/latest.json` automáticamente.

4. (Opcional) Para forzar una actualización manual sin esperar al cron:
   pestaña **Actions** del repo → "Actualizar datos NFL" → "Run workflow".

## Correr localmente

```bash
python3 fetch.py          # genera data/latest.json
python3 -m http.server    # sirve el dashboard en http://localhost:8000
```

## Notas sobre el cálculo

- La "probabilidad combinada" es el promedio entre el modelo de ESPN y la
  probabilidad de mercado (moneyline sin vig). No es una garantía de
  resultado — es una lectura de datos duros (modelo + mercado), no una
  apuesta seguida.
- Las lesiones que se muestran son solo las que afectan la semana en curso
  (Out, Doubtful, Questionable). Los jugadores en Injured Reserve de larga
  data no se muestran para no ensuciar la lectura semanal.
- Los endpoints de ESPN son públicos pero no oficiales/documentados;
  si en algún momento cambian de formato, el workflow lo va a mostrar
  como fallo en la pestaña Actions.
