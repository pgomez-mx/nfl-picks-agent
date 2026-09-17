#!/usr/bin/env python3
"""
Arma la grilla de temporada completa para armar estrategia de Survivor Pool
(elegis un equipo ganador distinto cada semana, sin repetir en toda la
temporada).

Para cada uno de los 32 equipos, trae su calendario completo (18 semanas)
y, para cada partido que todavia no se jugo, la misma probabilidad
combinada (modelo ESPN + mercado) que usa fetch.py. Con esto se puede ver
de entrada en que semana le toca facil a cada equipo, para decidir a
quien "guardarse" para mas adelante.

A diferencia de fetch.py (que corre a diario), este script pega ~300
pedidos a ESPN por corrida, asi que se corre una vez por semana via un
workflow separado (ver .github/workflows/survivor.yml).

Escribe el resultado en data/survivor.json, que consume index.html.
"""
import json
from datetime import datetime, timezone

from fetch import fetch_json, moneyline_to_prob, devig, SCOREBOARD_URL, SUMMARY_URL

TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams?limit=32"
TEAM_SCHEDULE_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/schedule"

SAVE_THRESHOLD = 0.12  # si guardarlo suma mas de 12 puntos en otra semana, se sugiere guardarlo
SAFE_ENOUGH = 0.55     # y esta semana igual tiene un pick razonable (>=55%) para no forzarlo


def get_current_week():
    scoreboard = fetch_json(SCOREBOARD_URL)
    return scoreboard.get("week", {}).get("number")


def get_all_teams():
    data = fetch_json(TEAMS_URL)
    teams = data["sports"][0]["leagues"][0]["teams"]
    out = []
    for t in teams:
        team = t["team"]
        logos = team.get("logos") or []
        out.append({
            "id": team["id"],
            "abbr": team["abbreviation"],
            "name": team["displayName"],
            "logo": logos[0]["href"] if logos else None,
        })
    return out


def event_combined_probs(summary):
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

    return combined(home_proj, home_market), combined(away_proj, away_market)


def build_survivor_data():
    current_week = get_current_week()
    teams = get_all_teams()
    event_cache = {}
    teams_out = {}

    for team in teams:
        try:
            schedule = fetch_json(TEAM_SCHEDULE_URL.format(team_id=team["id"]))
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: no se pudo leer el calendario de {team['abbr']}: {exc}")
            continue

        entries = []
        for ev in schedule.get("events", []):
            comp = ev["competitions"][0]
            competitors = {c["homeAway"]: c for c in comp["competitors"]}
            is_home = competitors["home"]["team"]["id"] == team["id"]
            own = competitors["home"] if is_home else competitors["away"]
            opp = competitors["away"] if is_home else competitors["home"]
            completed = comp["status"]["type"].get("completed", False)
            week = ev["week"]["number"]

            entry = {
                "week": week,
                "opponent_abbr": opp["team"]["abbreviation"],
                "opponent_name": opp["team"]["displayName"],
                "is_home": is_home,
                "date": ev["date"],
                "completed": completed,
                "won": bool(own.get("winner")) if completed else None,
                "combined_prob": None,
            }

            if not completed:
                if ev["id"] not in event_cache:
                    try:
                        summary = fetch_json(SUMMARY_URL.format(event_id=ev["id"]))
                        event_cache[ev["id"]] = event_combined_probs(summary)
                    except Exception as exc:  # noqa: BLE001
                        print(f"WARN: no se pudo leer el resumen de {ev['id']}: {exc}")
                        event_cache[ev["id"]] = (None, None)
                home_prob, away_prob = event_cache[ev["id"]]
                entry["combined_prob"] = home_prob if is_home else away_prob

            entries.append(entry)

        bye_week = schedule.get("byeWeek")
        if bye_week:
            entries.append({"week": bye_week, "bye": True})
        entries.sort(key=lambda e: e["week"])

        this_week_entry = next((e for e in entries if e["week"] == current_week), None)
        this_week_prob = this_week_entry["combined_prob"] if this_week_entry else None

        future_entries = [
            e for e in entries
            if e["week"] > current_week and not e.get("bye") and e["combined_prob"] is not None
        ]
        best_future = max(future_entries, key=lambda e: e["combined_prob"], default=None)

        save_for_later = False
        if this_week_prob is not None and best_future is not None:
            save_for_later = (
                best_future["combined_prob"] - this_week_prob >= SAVE_THRESHOLD
                and this_week_prob >= SAFE_ENOUGH
            )

        teams_out[team["abbr"]] = {
            "id": team["id"],
            "name": team["name"],
            "logo": team["logo"],
            "bye_week": bye_week,
            "schedule": entries,
            "this_week_prob": this_week_prob,
            "best_future_week": best_future["week"] if best_future else None,
            "best_future_prob": best_future["combined_prob"] if best_future else None,
            "save_for_later": save_for_later,
        }
        print(f"OK {team['abbr']}: semana {current_week} = "
              f"{'—' if this_week_prob is None else f'{this_week_prob*100:.0f}%'}"
              + (f", mejor semana {best_future['week']} ({best_future['combined_prob']*100:.0f}%)"
                 if best_future else ""))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_week": current_week,
        "save_threshold": SAVE_THRESHOLD,
        "safe_enough": SAFE_ENOUGH,
        "teams": teams_out,
    }


if __name__ == "__main__":
    data = build_survivor_data()
    with open("data/survivor.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"OK: survivor.json generado para {len(data['teams'])} equipos, semana actual {data['current_week']}")
