#!/usr/bin/env python3
"""
Descarga datos publicos de ESPN (sin API key) para la semana actual de la NFL:
- Proyeccion de victoria por equipo (modelo ESPN, tipo FPI)
- Lineas de casas de apuestas (moneyline / spread) -> probabilidad implicita de mercado
- Parte de lesiones por equipo

Combina ambas fuentes de probabilidad y arma un top 3 de equipos mas
probables a ganar en la semana, con el contexto de lesiones clave.

Escribe el resultado en data/latest.json, que consume index.html.
"""
import json
import urllib.request
from datetime import datetime, timezone

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={event_id}"

GAME_WEEK_STATUSES = {"out", "doubtful", "questionable"}


def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "curl/8.4.0",
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def moneyline_to_prob(moneyline):
    if moneyline is None:
        return None
    ml = float(moneyline)
    if ml < 0:
        return -ml / (-ml + 100)
    return 100 / (ml + 100)


def devig(prob_a, prob_b):
    if prob_a is None or prob_b is None:
        return prob_a, prob_b
    total = prob_a + prob_b
    if total == 0:
        return prob_a, prob_b
    return prob_a / total, prob_b / total


def key_injuries_for_team(injuries_block, team_id):
    for team in injuries_block or []:
        if team.get("team", {}).get("id") == team_id:
            out = []
            for item in team.get("injuries", []):
                status = (item.get("status") or "").lower()
                if status not in GAME_WEEK_STATUSES:
                    continue
                position = (item.get("athlete", {}).get("position", {}) or {}).get("abbreviation", "")
                out.append({
                    "name": item.get("athlete", {}).get("displayName", "?"),
                    "position": position,
                    "status": item.get("status"),
                })
            return out
    return []


def build_week():
    scoreboard = fetch_json(SCOREBOARD_URL)
    week_label = scoreboard.get("leagues", [{}])[0].get("season", {}).get("type", {}).get("abbreviation", "")
    week_number = scoreboard.get("week", {}).get("number")
    season_type_num = scoreboard.get("season", {}).get("type")
    season_year = scoreboard.get("season", {}).get("year")

    games = []
    for event in scoreboard.get("events", []):
        event_id = event["id"]
        competition = event["competitions"][0]
        competitors = {c["homeAway"]: c for c in competition["competitors"]}
        home = competitors.get("home", {})
        away = competitors.get("away", {})

        try:
            summary = fetch_json(SUMMARY_URL.format(event_id=event_id))
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: no se pudo leer el resumen de {event_id}: {exc}")
            summary = {}

        predictor = summary.get("predictor", {})
        home_proj = predictor.get("homeTeam", {}).get("gameProjection")
        away_proj = predictor.get("awayTeam", {}).get("gameProjection")
        home_proj = float(home_proj) / 100 if home_proj not in (None, "") else None
        away_proj = float(away_proj) / 100 if away_proj not in (None, "") else None

        pickcenter = summary.get("pickcenter") or []
        book = pickcenter[0] if pickcenter else {}
        home_ml = (book.get("homeTeamOdds") or {}).get("moneyLine")
        away_ml = (book.get("awayTeamOdds") or {}).get("moneyLine")
        home_market, away_market = devig(moneyline_to_prob(home_ml), moneyline_to_prob(away_ml))

        def combined(model_p, market_p):
            values = [v for v in (model_p, market_p) if v is not None]
            return sum(values) / len(values) if values else None

        home_combined = combined(home_proj, home_market)
        away_combined = combined(away_proj, away_market)

        injuries_block = summary.get("injuries") or []
        home_injuries = key_injuries_for_team(injuries_block, home.get("id"))
        away_injuries = key_injuries_for_team(injuries_block, away.get("id"))

        game = {
            "event_id": event_id,
            "date": event.get("date"),
            "status": event.get("status", {}).get("type", {}).get("shortDetail"),
            "book": book.get("provider", {}).get("name"),
            "spread_details": book.get("details"),
            "home": {
                "id": home.get("id"),
                "name": home.get("team", {}).get("displayName"),
                "abbr": home.get("team", {}).get("abbreviation"),
                "logo": (home.get("team", {}).get("logo")),
                "model_prob": home_proj,
                "market_prob": home_market,
                "moneyline": home_ml,
                "combined_prob": home_combined,
                "key_injuries": home_injuries,
            },
            "away": {
                "id": away.get("id"),
                "name": away.get("team", {}).get("displayName"),
                "abbr": away.get("team", {}).get("abbreviation"),
                "logo": (away.get("team", {}).get("logo")),
                "model_prob": away_proj,
                "market_prob": away_market,
                "moneyline": away_ml,
                "combined_prob": away_combined,
                "key_injuries": away_injuries,
            },
        }
        games.append(game)

    team_rows = []
    for g in games:
        for side in ("home", "away"):
            team = g[side]
            opponent = g["away"] if side == "home" else g["home"]
            if team["combined_prob"] is None:
                continue
            team_rows.append({
                "team": team["name"],
                "abbr": team["abbr"],
                "logo": team["logo"],
                "opponent": opponent["name"],
                "opponent_abbr": opponent["abbr"],
                "is_home": side == "home",
                "combined_prob": team["combined_prob"],
                "model_prob": team["model_prob"],
                "market_prob": team["market_prob"],
                "moneyline": team["moneyline"],
                "own_injuries": team["key_injuries"],
                "opponent_injuries": opponent["key_injuries"],
                "game_date": g["date"],
            })

    team_rows.sort(key=lambda r: r["combined_prob"], reverse=True)
    top3 = team_rows[:3]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "week_number": week_number,
        "season_type": week_label,
        "season_type_num": season_type_num,
        "season_year": season_year,
        "games": games,
        "ranking": team_rows,
        "top3": top3,
    }


HISTORY_PATH = "data/history.json"


def load_history():
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"weeks": {}, "summary": {}}


def save_history(history):
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def snapshot_current_week(history, data):
    """Guarda el pick de la semana la primera vez que se la ve. No se
    vuelve a pisar despues: es la prediccion 'oficial' que se va a
    comparar contra el resultado real."""
    key = str(data["week_number"])
    if key in history["weeks"]:
        return
    picks = [
        {
            "abbr": row["abbr"],
            "team": row["team"],
            "opponent_abbr": row["opponent_abbr"],
            "is_home": row["is_home"],
            "combined_prob": row["combined_prob"],
        }
        for row in data["ranking"]
        if row["combined_prob"] is not None and row["combined_prob"] > 0.5
    ]
    top3 = [
        {"abbr": t["abbr"], "team": t["team"], "combined_prob": t["combined_prob"]}
        for t in data["top3"]
    ]
    history["weeks"][key] = {
        "week_number": data["week_number"],
        "season_type_num": data["season_type_num"],
        "season_year": data["season_year"],
        "snapshot_at": data["generated_at"],
        "picks": picks,
        "top3": top3,
        "resolved": False,
        "resolved_at": None,
        "results": None,
    }


def resolve_pending_weeks(history):
    for wk in history["weeks"].values():
        if wk["resolved"]:
            continue
        url = (f"{SCOREBOARD_URL}?week={wk['week_number']}"
               f"&seasontype={wk['season_type_num']}&year={wk['season_year']}")
        try:
            scoreboard = fetch_json(url)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: no se pudo revisar resultados de la semana {wk['week_number']}: {exc}")
            continue

        events = scoreboard.get("events", [])
        if not events:
            continue
        all_final = all(
            e["competitions"][0]["status"]["type"].get("completed") for e in events
        )
        if not all_final:
            continue

        winners = {}
        for e in events:
            for c in e["competitions"][0]["competitors"]:
                winners[c["team"]["abbreviation"]] = bool(c.get("winner"))

        def grade(entries):
            correct = 0
            total = 0
            graded = []
            for entry in entries:
                won = winners.get(entry["abbr"])
                if won is None:
                    continue
                total += 1
                correct += 1 if won else 0
                graded.append({**entry, "won": won})
            return graded, correct, total

        graded_picks, fav_correct, fav_total = grade(wk["picks"])
        graded_top3, top3_hits, top3_total = grade(wk["top3"])

        wk["resolved"] = True
        wk["resolved_at"] = datetime.now(timezone.utc).isoformat()
        wk["results"] = {
            "favorites_correct": fav_correct,
            "favorites_total": fav_total,
            "top3_hits": top3_hits,
            "top3_total": top3_total,
            "picks_graded": graded_picks,
            "top3_graded": graded_top3,
        }
        print(f"OK: semana {wk['week_number']} resuelta -> favoritos {fav_correct}/{fav_total}, "
              f"top3 {top3_hits}/{top3_total}")


def recompute_summary(history):
    fav_correct = fav_total = top3_hits = top3_total = 0
    weekly = []
    for wk in sorted(history["weeks"].values(), key=lambda w: w["week_number"]):
        if not wk["resolved"]:
            continue
        r = wk["results"]
        fav_correct += r["favorites_correct"]
        fav_total += r["favorites_total"]
        top3_hits += r["top3_hits"]
        top3_total += r["top3_total"]
        weekly.append({
            "week_number": wk["week_number"],
            "favorites_correct": r["favorites_correct"],
            "favorites_total": r["favorites_total"],
            "top3_hits": r["top3_hits"],
            "top3_total": r["top3_total"],
        })
    history["summary"] = {
        "weeks_resolved": len(weekly),
        "favorites_correct": fav_correct,
        "favorites_total": fav_total,
        "favorite_accuracy": (fav_correct / fav_total) if fav_total else None,
        "top3_hits": top3_hits,
        "top3_total": top3_total,
        "top3_accuracy": (top3_hits / top3_total) if top3_total else None,
        "weekly": weekly,
    }


if __name__ == "__main__":
    data = build_week()
    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"OK: semana {data['week_number']} -> {len(data['games'])} partidos, top3: "
          + ", ".join(t['abbr'] for t in data['top3']))

    history = load_history()
    snapshot_current_week(history, data)
    resolve_pending_weeks(history)
    recompute_summary(history)
    save_history(history)
    s = history["summary"]
    if s.get("favorites_total"):
        print(f"Historial: favoritos {s['favorites_correct']}/{s['favorites_total']} "
              f"({s['favorite_accuracy']*100:.1f}%), top3 {s['top3_hits']}/{s['top3_total']} "
              f"({s['top3_accuracy']*100:.1f}%) en {s['weeks_resolved']} semana(s)")
