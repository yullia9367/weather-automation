#!/usr/bin/env python3
"""Open-Meteo API를 사용해 일주일 치 최고/최저 기온과 날씨 상태를 출력합니다.

실행하면 다음 순서로 동작합니다.
  1) 날씨 데이터를 받아온다.
  2) 결과를 화면에 출력하고 weather_log.txt 끝에 이어서 기록한다.
  3) 방금 받아온 최신 데이터를 바탕으로 weather.html을 다시 생성한다.

weather_log.txt / weather.html 은 이 스크립트가 있는 디렉터리에 생성됩니다.
따라서 저장소 안의 weather.py는 저장소 안에, ~/weather-alarm/weather.py는
그 폴더 안에 각각 파일을 만들어 git 파이프라인과 launchd 실행이 서로 어긋나지 않습니다.
"""

import os
import sys
import html
import urllib.request
import urllib.parse
import json
from datetime import datetime

LATITUDE = 33.10
LONGITUDE = -96.67
LOCATION_NAME = "알렌"

# 스크립트가 있는 디렉터리(= 결과 파일을 만들 위치)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 실행 결과를 이어서 기록할 로그 파일 경로
LOG_FILE = os.path.join(BASE_DIR, "weather_log.txt")

# 최신 데이터로 다시 생성할 HTML 파일 경로
HTML_FILE = os.path.join(BASE_DIR, "weather.html")

# WMO Weather interpretation codes (날씨 코드 -> 한글 설명)
WEATHER_CODES = {
    0: "맑음",
    1: "대체로 맑음",
    2: "부분적으로 흐림",
    3: "흐림",
    45: "안개",
    48: "서리 안개",
    51: "가벼운 이슬비",
    53: "이슬비",
    55: "짙은 이슬비",
    56: "가벼운 어는 이슬비",
    57: "짙은 어는 이슬비",
    61: "약한 비",
    63: "비",
    65: "강한 비",
    66: "약한 어는 비",
    67: "강한 어는 비",
    71: "약한 눈",
    73: "눈",
    75: "강한 눈",
    77: "싸락눈",
    80: "약한 소나기",
    81: "소나기",
    82: "강한 소나기",
    85: "약한 눈 소나기",
    86: "강한 눈 소나기",
    95: "천둥번개",
    96: "천둥번개(약한 우박)",
    99: "천둥번개(강한 우박)",
}

# 날씨 코드 -> 이모지 아이콘 (HTML 카드에 표시)
WEATHER_EMOJI = {
    0: "☀️",
    1: "🌤️",
    2: "⛅",
    3: "☁️",
    45: "🌫️",
    48: "🌫️",
    51: "🌦️",
    53: "🌦️",
    55: "🌧️",
    56: "🌧️",
    57: "🌧️",
    61: "🌦️",
    63: "🌧️",
    65: "🌧️",
    66: "🌧️",
    67: "🌧️",
    71: "🌨️",
    73: "🌨️",
    75: "❄️",
    77: "🌨️",
    80: "🌦️",
    81: "🌧️",
    82: "⛈️",
    85: "🌨️",
    86: "❄️",
    95: "⛈️",
    96: "⛈️",
    99: "⛈️",
}

WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]
WEEKDAYS_FULL = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


def fetch_weather():
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "daily": "temperature_2m_max,temperature_2m_min,weather_code",
        "timezone": "auto",
        "forecast_days": 7,
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def c_to_f(celsius):
    return celsius * 9 / 5 + 32


def build_forecast(data, today_str):
    """API 응답을 카드/로그 생성에 쓰기 좋은 dict 리스트로 정리한다."""
    daily = data["daily"]
    forecast = []
    for date, t_max, t_min, code in zip(
        daily["time"],
        daily["temperature_2m_max"],
        daily["temperature_2m_min"],
        daily["weather_code"],
    ):
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            weekday_short = WEEKDAYS_KO[dt.weekday()]
            weekday_full = WEEKDAYS_FULL[dt.weekday()]
            date_label = dt.strftime("%m월 %d일")
        except ValueError:
            weekday_short = ""
            weekday_full = ""
            date_label = date
        forecast.append(
            {
                "date": date,
                "date_label": date_label,
                "weekday_short": weekday_short,
                "weekday_full": weekday_full,
                "code": code,
                "desc": WEATHER_CODES.get(code, f"알 수 없음(코드 {code})"),
                "emoji": WEATHER_EMOJI.get(code, "🌡️"),
                "t_max": t_max,
                "t_min": t_min,
                "is_today": date == today_str,
            }
        )
    return forecast


def build_log_text(forecast, run_time):
    """weather_log.txt 에 이어 붙일 텍스트 블록을 만든다."""
    loc_str = f"{LOCATION_NAME} (위도 {LATITUDE}, 경도 {LONGITUDE})"
    line = "=" * 56
    lines = [
        line,
        "        일주일 날씨 예보".center(48),
        line,
        f"  실행 시각 : {run_time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"  위치 : {loc_str}",
        line,
    ]
    for day in forecast:
        if day["weekday_short"]:
            date_str = f"{day['date_label']} ({day['weekday_short']})"
        else:
            date_str = day["date_label"]
        marker = " [today]" if day["is_today"] else ""
        lines.append(
            f"  {date_str}{marker}  |  {day['desc']:<10}  |  "
            f"최고 {day['t_max']:>5.1f}°C / {c_to_f(day['t_max']):>5.1f}°F  |  "
            f"최저 {day['t_min']:>5.1f}°C / {c_to_f(day['t_min']):>5.1f}°F"
        )
    lines.append(line)
    return "\n".join(lines)


def build_html(forecast, run_time):
    """최신 예보 데이터로 weather.html 전체 문서를 생성한다."""
    cards = []
    for day in forecast:
        card_class = "card latest" if day["is_today"] else "card"
        badge = '\n        <span class="badge">TODAY</span>' if day["is_today"] else ""
        cards.append(
            f'''      <div class="{card_class}">{badge}
        <div class="date">{html.escape(day["date_label"])}</div>
        <div class="day">{html.escape(day["weekday_full"])}</div>
        <div class="icon">{day["emoji"]}</div>
        <div class="condition">{html.escape(day["desc"])}</div>
        <div class="temps">
          <div class="t-item">
            <span class="t-label">최고</span>
            <span class="high">{day["t_max"]:.1f}°C</span>
            <span class="fahrenheit">{c_to_f(day["t_max"]):.1f}°F</span>
          </div>
          <div class="t-item">
            <span class="t-label">최저</span>
            <span class="low">{day["t_min"]:.1f}°C</span>
            <span class="fahrenheit">{c_to_f(day["t_min"]):.1f}°F</span>
          </div>
        </div>
      </div>'''
        )
    cards_html = "\n\n".join(cards)
    run_time_str = run_time.strftime("%Y-%m-%d %H:%M")

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>일주일 날씨 예보</title>
<style>
  * {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }}

  :root {{
    --accent: #2563eb;
    --accent-light: #3b82f6;
    --accent-soft: #eff6ff;
    --text: #1e293b;
    --text-muted: #64748b;
    --bg: #f8fafc;
    --card-bg: #ffffff;
  }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo",
                 "Malgun Gothic", sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 48px 20px;
    -webkit-font-smoothing: antialiased;
  }}

  .container {{
    max-width: 1100px;
    margin: 0 auto;
  }}

  header {{
    text-align: center;
    margin-bottom: 40px;
  }}

  header h1 {{
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin-bottom: 10px;
  }}

  header h1 .dot {{
    color: var(--accent);
  }}

  .meta {{
    display: inline-flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px 20px;
    font-size: 0.9rem;
    color: var(--text-muted);
  }}

  .meta span strong {{
    color: var(--text);
    font-weight: 600;
  }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 20px;
  }}

  .card {{
    background: var(--card-bg);
    border-radius: 18px;
    padding: 24px 22px;
    box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
    border: 1px solid #eef2f7;
    transition: transform 0.18s ease, box-shadow 0.18s ease;
    position: relative;
    overflow: hidden;
  }}

  .card:hover {{
    transform: translateY(-4px);
    box-shadow: 0 12px 28px rgba(15, 23, 42, 0.12);
  }}

  .card .date {{
    font-size: 1.15rem;
    font-weight: 700;
    margin-bottom: 2px;
  }}

  .card .day {{
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-bottom: 18px;
  }}

  .card .icon {{
    font-size: 2.6rem;
    line-height: 1;
    margin-bottom: 14px;
  }}

  .card .condition {{
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: 18px;
  }}

  .temps {{
    display: flex;
    gap: 18px;
    font-size: 0.92rem;
  }}

  .temps .t-item {{
    display: flex;
    flex-direction: column;
    gap: 2px;
  }}

  .temps .t-label {{
    font-size: 0.72rem;
    color: var(--text-muted);
    letter-spacing: 0.04em;
  }}

  .temps .high {{ color: #dc2626; font-weight: 700; }}
  .temps .low  {{ color: var(--accent); font-weight: 700; }}

  .temps .fahrenheit {{
    font-size: 0.72rem;
    color: var(--text-muted);
    font-weight: 400;
  }}

  /* Badge for today */
  .badge {{
    position: absolute;
    top: 16px;
    right: 16px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 0.68rem;
    font-weight: 700;
    padding: 3px 9px;
    border-radius: 999px;
    letter-spacing: 0.03em;
  }}

  /* Highlighted (latest) card */
  .card.latest {{
    background: linear-gradient(150deg, var(--accent) 0%, var(--accent-light) 100%);
    color: #ffffff;
    box-shadow: 0 12px 30px rgba(37, 99, 235, 0.35);
    border: none;
    transform: translateY(-2px);
  }}

  .card.latest:hover {{
    transform: translateY(-6px);
    box-shadow: 0 18px 38px rgba(37, 99, 235, 0.42);
  }}

  .card.latest .day,
  .card.latest .temps .t-label,
  .card.latest .temps .fahrenheit {{
    color: rgba(255, 255, 255, 0.75);
  }}

  .card.latest .temps .high,
  .card.latest .temps .low {{
    color: #ffffff;
  }}

  .card.latest .badge {{
    background: rgba(255, 255, 255, 0.22);
    color: #ffffff;
  }}

  footer {{
    text-align: center;
    margin-top: 40px;
    font-size: 0.8rem;
    color: var(--text-muted);
  }}
</style>
</head>
<body>
  <div class="container">
    <header>
      <h1>일주일 날씨 예보<span class="dot">.</span></h1>
      <div class="meta">
        <span>📍 위치 : <strong>{html.escape(LOCATION_NAME)}</strong> (위도 {LATITUDE}, 경도 {LONGITUDE})</span>
        <span>🕒 실행 시각 : <strong>{run_time_str}</strong></span>
      </div>
    </header>

    <div class="grid">
{cards_html}
    </div>

    <footer>
      데이터 출처 : weather_log.txt · 알렌(Allen) 일주일 날씨 예보
    </footer>
  </div>
</body>
</html>
'''


def main():
    try:
        data = fetch_weather()
    except Exception as e:
        print(f"날씨 정보를 가져오지 못했습니다: {e}", file=sys.stderr)
        sys.exit(1)

    run_time = datetime.now()
    today_str = run_time.strftime("%Y-%m-%d")

    forecast = build_forecast(data, today_str)

    # 1) 텍스트 결과 만들기 + 화면 출력
    log_text = build_log_text(forecast, run_time)
    print(log_text)

    # 2) 로그 파일에 계속 이어서 기록
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_text)
            f.write("\n\n")
    except Exception as e:
        print(f"로그 파일 기록에 실패했습니다: {e}", file=sys.stderr)

    # 3) 방금 받은 최신 데이터로 weather.html 다시 생성
    try:
        html_text = build_html(forecast, run_time)
        with open(HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html_text)
    except Exception as e:
        print(f"HTML 파일 생성에 실패했습니다: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
