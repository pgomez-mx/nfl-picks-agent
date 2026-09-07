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
        "games": games,
        "ranking": team_rows,
        "top3": top3,
    }


if __name__ == "__main__":
    data = build_week()
    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"OK: semana {data['week_number']} -> {len(data['games'])} partidos, top3: "
          + ", ".join(t['abbr'] for t in data['top3']))
