#!/usr/bin/env python3
"""Open-Meteo API를 사용해 일주일 치 최고/최저 기온과 날씨 상태를 출력합니다."""

import os
import sys
import urllib.request
import urllib.parse
import json
from datetime import datetime

LATITUDE = 33.10
LONGITUDE = -96.67
LOCATION_NAME = "알렌"

# 실행 결과를 이어서 기록할 로그 파일 경로
LOG_FILE = os.path.join(os.path.expanduser("~"), "weather-alarm", "weather_log.txt")

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

WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]


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


def main():
    try:
        data = fetch_weather()
    except Exception as e:
        print(f"날씨 정보를 가져오지 못했습니다: {e}", file=sys.stderr)
        sys.exit(1)

    daily = data["daily"]
    dates = daily["time"]
    maxes = daily["temperature_2m_max"]
    mins = daily["temperature_2m_min"]
    codes = daily["weather_code"]

    loc_str = f"{LOCATION_NAME} (위도 {LATITUDE}, 경도 {LONGITUDE})"

    # 오늘 날짜 (로컬 기준)
    today_str = datetime.now().strftime("%Y-%m-%d")

    line = "=" * 56
    lines = []
    lines.append(line)
    lines.append("        일주일 날씨 예보".center(48))
    lines.append(line)
    lines.append(f"  실행 시각 : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"  위치 : {loc_str}")
    lines.append(line)

    for date, t_max, t_min, code in zip(dates, maxes, mins, codes):
        desc = WEATHER_CODES.get(code, f"알 수 없음(코드 {code})")
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            date_str = dt.strftime("%m월 %d일") + f" ({WEEKDAYS_KO[dt.weekday()]})"
        except ValueError:
            date_str = date
        # 당일에 해당하는 날씨는 'today'라고 표시
        marker = " [today]" if date == today_str else ""
        lines.append(
            f"  {date_str}{marker}  |  {desc:<10}  |  "
            f"최고 {t_max:>5.1f}°C / {c_to_f(t_max):>5.1f}°F  |  "
            f"최저 {t_min:>5.1f}°C / {c_to_f(t_min):>5.1f}°F"
        )

    lines.append(line)

    output = "\n".join(lines)

    # 화면에 출력
    print(output)

    # 로그 파일에 날짜와 함께 계속 이어서 기록
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(output)
            f.write("\n\n")
    except Exception as e:
        print(f"로그 파일 기록에 실패했습니다: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
