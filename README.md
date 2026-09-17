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
  13:00 UTC** durante toda la temporada y commitea `data/latest.json` y
  `data/history.json` si cambiaron. Así el dashboard queda al día sin que
  nadie tenga que tocar nada.

## Tracker de resultados (`data/history.json`)

Cada vez que `fetch.py` ve una semana nueva, guarda una "foto" de los picks
de esa semana (favoritos y top 3) — esa foto queda fija, no se pisa después
aunque cambien las lesiones o las cuotas. Cuando **todos** los partidos de
esa semana ya están `Final` según ESPN, el script compara los picks contra
quién ganó de verdad y calcula:

- % de favoritos acertados (de los 16 partidos de la semana).
- % del top 3 que efectivamente ganó.

Eso se acumula semana a semana en `data/history.json` y se muestra en la
sección **"Resultados y precisión histórica"** del dashboard. No hay
aprendizaje automático acá — el cálculo (promedio modelo + mercado) es
fijo — pero con varias semanas de historial se puede ver si conviene
pesarlo distinto (por ejemplo, darle más peso al mercado si resulta ser
más preciso que el modelo de ESPN).

## Estrategia de Survivor Pool (`data/survivor.json`)

Pensado para el juego de "Survivor": cada semana elegís un equipo que
creas que va a ganar, no podés repetir equipo en toda la temporada, y si
el que elegiste pierde quedás eliminado. La estrategia no es solo "quién
gana esta semana" sino también "a quién me conviene guardarme para una
semana donde le toque más fácil".

- `survivor.py` trae el calendario completo (18 semanas) de los 32
  equipos y, para cada partido que todavía no se jugó, la misma
  probabilidad combinada (modelo ESPN + mercado) que usa `fetch.py` —
  ESPN devuelve esa proyección para partidos de varias semanas en el
  futuro, no solo el de esta semana. Con eso arma `data/survivor.json`.
- A diferencia de `fetch.py`, este script pega ~300 pedidos por corrida
  (uno por partido de la temporada), así que corre **una vez por semana**
  (miércoles 14:00 UTC) vía `.github/workflows/survivor.yml`, en vez de
  a diario.
- En el dashboard, la sección **"🏆 Mi Survivor"** deja marcar qué
  equipos ya usaste (queda guardado en `localStorage` de ese
  dispositivo, no es una cuenta en la nube) y muestra:
  - Una recomendación para la semana actual, con una alerta ⚠️ cuando
    ese equipo tiene una semana bastante más fácil más adelante (la
    diferencia supera `SAVE_THRESHOLD`, 12 puntos por defecto) y el
    pick de esta semana ya es razonablemente seguro (`SAFE_ENOUGH`,
    55% o más) — o sea, cuando conviene más guardarlo que gastarlo ya.
  - Un mapa completo equipo × semana para planear a mano vos mismo.
- Esto **no es un plan rígido de toda la temporada**: las lesiones y las
  cuotas cambian semana a semana, así que la idea es revisar la
  recomendación cada vez que vayas a elegir, no comprometerte de
  entrada a los 18 picks.

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
python3 fetch.py          # genera data/latest.json y data/history.json
python3 survivor.py       # genera data/survivor.json (tarda ~2-3 min, ~300 pedidos)
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
