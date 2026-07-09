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
from datetime import datetime, timedelta

# 날씨를 가져올 지역 목록 (탭 순서와 동일)
LOCATIONS = [
    {"name": "알렌", "latitude": 33.10, "longitude": -96.67},
    {"name": "서울", "latitude": 37.57, "longitude": 126.98},
]

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


FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


# 대기질 등급 색상 클래스 (좋음=초록 / 보통=노랑 / 나쁨=주황 / 매우나쁨=빨강)
AQ_GOOD = "aq-good"
AQ_MODERATE = "aq-moderate"
AQ_BAD = "aq-bad"
AQ_VERYBAD = "aq-verybad"
AQ_NONE = "aq-none"


def grade_pm25(value):
    """PM2.5(㎍/m³) 농도를 WHO/EPA(AQI) 기준으로 4단계 등급 분류한다.

    - 좋음   : 0 ~ 12.0
    - 보통   : 12.1 ~ 35.4
    - 나쁨   : 35.5 ~ 55.4
    - 매우나쁨: 55.5 이상
    반환: (등급 한글, 색상 클래스)
    """
    if value is None:
        return ("정보 없음", AQ_NONE)
    if value <= 12.0:
        return ("좋음", AQ_GOOD)
    if value <= 35.4:
        return ("보통", AQ_MODERATE)
    if value <= 55.4:
        return ("나쁨", AQ_BAD)
    return ("매우나쁨", AQ_VERYBAD)


def grade_uv(value):
    """자외선 지수(UV index)를 WHO 기준으로 4단계 등급 분류한다.

    - 좋음(Low)        : 0 ~ 2
    - 보통(Moderate)   : 3 ~ 5
    - 나쁨(High)       : 6 ~ 7
    - 매우나쁨(V.High+): 8 이상
    반환: (등급 한글, 색상 클래스)
    """
    if value is None:
        return ("정보 없음", AQ_NONE)
    if value < 3:
        return ("좋음", AQ_GOOD)
    if value < 6:
        return ("보통", AQ_MODERATE)
    if value < 8:
        return ("나쁨", AQ_BAD)
    return ("매우나쁨", AQ_VERYBAD)


def fetch_air_quality(latitude, longitude):
    """Open-Meteo Air Quality API에서 현재 PM2.5 농도와 자외선 지수를 받아온다.

    반환: {"pm25": float|None, "uv": float|None}
    실패하면 값이 None 인 dict 를 돌려준다.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "pm2_5,uv_index",
        "timezone": "auto",
    }
    url = AIR_QUALITY_URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    current = data.get("current") or {}
    return {"pm25": current.get("pm2_5"), "uv": current.get("uv_index")}


def week_bounds(today):
    """오늘이 속한 주(일요일~토요일)의 시작일/종료일을 돌려준다.

    Python 의 weekday() 는 월=0 ... 일=6 이므로, 일요일까지 거슬러
    올라간 날짜가 그 주의 시작(일요일)이 된다.
    """
    days_since_sunday = (today.weekday() + 1) % 7
    week_start = today - timedelta(days=days_since_sunday)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def fetch_range(base_url, latitude, longitude, start_date, end_date):
    """지정한 API(base_url)에서 start_date~end_date 구간의 일별 데이터를 받아온다."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,temperature_2m_min,weather_code",
        "timezone": "auto",
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
    }
    url = base_url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def merge_daily(data_map, data):
    """API 응답의 daily 블록을 날짜 -> 값 dict 로 data_map 에 채워 넣는다."""
    daily = data.get("daily") or {}
    times = daily.get("time") or []
    t_max = daily.get("temperature_2m_max") or []
    t_min = daily.get("temperature_2m_min") or []
    codes = daily.get("weather_code") or []
    for date, tx, tn, code in zip(times, t_max, t_min, codes):
        # 최고/최저/코드 중 하나라도 결측(None)이면 유효한 데이터로 보지 않는다.
        if tx is None or tn is None or code is None:
            continue
        data_map[date] = {"t_max": tx, "t_min": tn, "code": code}


def collect_weekly_data(today, latitude, longitude):
    """이번 주(일~토) 7일 치 데이터를 예보 + 과거 날씨 API로 채워 모은다.

    - 오늘 ~ 이번 주 토요일 : Open-Meteo 예보 API
    - 이번 주 일요일 ~ 어제 : Open-Meteo 과거 날씨(archive) API
    반환: (week_start, week_end, {날짜문자열: {t_max, t_min, code}})
    """
    week_start, week_end = week_bounds(today)
    data_map = {}

    # 1) 오늘부터 이번 주 토요일까지는 예보 API 로 채운다.
    try:
        forecast_data = fetch_range(FORECAST_URL, latitude, longitude, today, week_end)
        merge_daily(data_map, forecast_data)
    except Exception as e:
        print(f"예보 데이터를 가져오지 못했습니다: {e}", file=sys.stderr)

    # 2) 이번 주에서 이미 지난 날짜(일요일~어제)는 과거 날씨 API 로 채운다.
    yesterday = today - timedelta(days=1)
    if week_start <= yesterday:
        try:
            archive_data = fetch_range(ARCHIVE_URL, latitude, longitude, week_start, yesterday)
            merge_daily(data_map, archive_data)
        except Exception as e:
            print(f"과거 날씨 데이터를 가져오지 못했습니다: {e}", file=sys.stderr)

    return week_start, week_end, data_map


def c_to_f(celsius):
    return celsius * 9 / 5 + 32


# 날씨 코드 -> 아이콘 애니메이션 종류(CSS 클래스)
# 맑음은 은은한 회전+발광, 구름/안개는 좌우 흔들림, 비는 빗방울이 떨어지는
# 느낌, 눈은 살랑살랑, 천둥번개는 가볍게 떨리는 정도로 과하지 않게 매핑한다.
def weather_anim_class(code):
    if code is None:
        return ""
    if code in (0, 1):
        return "icon-sun"
    if code in (95, 96, 99):
        return "icon-storm"
    if code in (71, 73, 75, 77, 85, 86):
        return "icon-snow"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "icon-rain"
    if code in (45, 48):
        return "icon-fog"
    # 나머지(2 부분적으로 흐림, 3 흐림 등)는 구름 흔들림
    return "icon-cloud"


def build_forecast(week_start, data_map, today_str):
    """이번 주 7일(일~토)을 고정 날짜 셀로 만들고, 있는 데이터만 채운다.

    week_start(일요일)부터 하루씩 7칸을 만든다. 요일 순서는 항상 일~토로
    고정되며, 데이터가 없는 셀(예: 아직 archive 에 없거나 API 실패)은
    has_data=False 로 두어 '지난 날씨'/빈 칸 처리를 할 수 있게 한다.
    """
    forecast = []
    for offset in range(7):
        dt = week_start + timedelta(days=offset)
        date = dt.strftime("%Y-%m-%d")
        weekday_short = WEEKDAYS_KO[dt.weekday()]
        weekday_full = WEEKDAYS_FULL[dt.weekday()]
        date_label = dt.strftime("%m월 %d일")

        entry = data_map.get(date)
        is_today = date == today_str
        is_past = date < today_str

        if entry is not None:
            code = entry["code"]
            day = {
                "date": date,
                "date_label": date_label,
                "weekday_short": weekday_short,
                "weekday_full": weekday_full,
                "code": code,
                "desc": WEATHER_CODES.get(code, f"알 수 없음(코드 {code})"),
                "emoji": WEATHER_EMOJI.get(code, "🌡️"),
                "t_max": entry["t_max"],
                "t_min": entry["t_min"],
                "is_today": is_today,
                "is_past": is_past,
                "has_data": True,
            }
        else:
            day = {
                "date": date,
                "date_label": date_label,
                "weekday_short": weekday_short,
                "weekday_full": weekday_full,
                "code": None,
                "desc": "지난 날씨" if is_past else "예보 없음",
                "emoji": "🗓️" if is_past else "❔",
                "t_max": None,
                "t_min": None,
                "is_today": is_today,
                "is_past": is_past,
                "has_data": False,
            }
        forecast.append(day)
    return forecast


def build_log_text(forecast, run_time, location, air=None):
    """weather_log.txt 에 이어 붙일 텍스트 블록을 만든다."""
    loc_str = f"{location['name']} (위도 {location['latitude']}, 경도 {location['longitude']})"
    line = "=" * 56
    lines = [
        line,
        "        일주일 날씨 예보".center(48),
        line,
        f"  실행 시각 : {run_time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"  위치 : {loc_str}",
    ]

    # 현재 대기질(PM2.5)·자외선 지수 한 줄 추가
    if air is not None:
        pm25 = air.get("pm25")
        uv = air.get("uv")
        pm_label, _ = grade_pm25(pm25)
        uv_label, _ = grade_uv(uv)
        pm_str = f"{pm_label}({pm25:.0f}㎍/m³)" if pm25 is not None else "정보 없음"
        uv_str = f"{uv_label}({uv:.0f})" if uv is not None else "정보 없음"
        lines.append(f"  대기질 : PM2.5 {pm_str}  |  UV {uv_str}")

    lines.append(line)
    for day in forecast:
        if day["weekday_short"]:
            date_str = f"{day['date_label']} ({day['weekday_short']})"
        else:
            date_str = day["date_label"]
        marker = " [today]" if day["is_today"] else ""
        if day["has_data"]:
            lines.append(
                f"  {date_str}{marker}  |  {day['desc']:<10}  |  "
                f"최고 {day['t_max']:>5.1f}°C / {c_to_f(day['t_max']):>5.1f}°F  |  "
                f"최저 {day['t_min']:>5.1f}°C / {c_to_f(day['t_min']):>5.1f}°F"
            )
        else:
            lines.append(f"  {date_str}{marker}  |  {day['desc']:<10}  |  (데이터 없음)")
    lines.append(line)
    return "\n".join(lines)


def build_cards_html(forecast):
    """한 지역의 forecast 리스트를 카드 HTML 문자열로 만든다."""
    cards = []
    for day in forecast:
        classes = ["card"]
        if day["is_today"]:
            classes.append("latest")
        if not day["has_data"]:
            classes.append("nodata")
        if day["is_past"]:
            classes.append("past")
        card_class = " ".join(classes)
        badge = '\n        <span class="badge">TODAY</span>' if day["is_today"] else ""

        if day["has_data"]:
            temps_html = f'''<div class="temps">
          <div class="t-item">
            <span class="t-label">최고</span>
            <span class="high temp-primary" data-c="{day["t_max"]:.1f}" data-f="{c_to_f(day["t_max"]):.1f}"></span>
            <span class="fahrenheit temp-secondary" data-c="{day["t_max"]:.1f}" data-f="{c_to_f(day["t_max"]):.1f}"></span>
          </div>
          <div class="t-item">
            <span class="t-label">최저</span>
            <span class="low temp-primary" data-c="{day["t_min"]:.1f}" data-f="{c_to_f(day["t_min"]):.1f}"></span>
            <span class="fahrenheit temp-secondary" data-c="{day["t_min"]:.1f}" data-f="{c_to_f(day["t_min"]):.1f}"></span>
          </div>
        </div>'''
        else:
            temps_html = '<div class="temps no-temps">데이터 없음</div>'

        cards.append(
            f'''      <div class="{card_class}">{badge}
        <div class="date">{html.escape(day["date_label"])}</div>
        <div class="day">{html.escape(day["weekday_full"])}</div>
        <div class="icon {weather_anim_class(day["code"])}">{day["emoji"]}</div>
        <div class="condition">{html.escape(day["desc"])}</div>
        {temps_html}
      </div>'''
        )
    return "\n\n".join(cards)


def build_air_quality_html(air):
    """지역 카드 상단에 표시할 PM2.5·UV 배지 HTML을 만든다."""
    pm25 = air.get("pm25") if air else None
    uv = air.get("uv") if air else None

    pm_label, pm_class = grade_pm25(pm25)
    uv_label, uv_class = grade_uv(uv)

    if pm25 is not None:
        pm_text = f"PM2.5: {pm_label}({pm25:.0f}㎍/m³)"
    else:
        pm_text = "PM2.5: 정보 없음"

    if uv is not None:
        uv_text = f"UV: {uv_label}({uv:.0f})"
    else:
        uv_text = "UV: 정보 없음"

    return f'''      <div class="air-quality">
        <span class="aq-badge {pm_class}">{html.escape(pm_text)}</span>
        <span class="aq-badge {uv_class}">{html.escape(uv_text)}</span>
      </div>'''


def build_chart_data(location_data):
    """지역별 주간 기온 라인 그래프에 쓸 데이터를 dict 로 만든다.

    panel-{idx} 를 키로, 각 지역의 요일 라벨·최고/최저(℃·℉)·오늘 인덱스를
    담는다. 이 dict 를 JSON 으로 HTML 에 심어 Chart.js 가 읽어 쓴다.
    데이터가 없는 날(has_data=False)은 None 으로 두어 선이 끊기게 한다.
    """
    result = {}
    for idx, (location, forecast, air) in enumerate(location_data):
        labels = []
        highs_c, highs_f, lows_c, lows_f = [], [], [], []
        today_index = -1
        for i, day in enumerate(forecast):
            # 라벨은 [요일, MM/DD] 두 줄로 (Chart.js 는 배열을 여러 줄로 렌더)
            mmdd = day["date"][5:].replace("-", "/")
            labels.append([day["weekday_short"], mmdd])
            if day["has_data"]:
                highs_c.append(round(day["t_max"], 1))
                highs_f.append(round(c_to_f(day["t_max"]), 1))
                lows_c.append(round(day["t_min"], 1))
                lows_f.append(round(c_to_f(day["t_min"]), 1))
            else:
                highs_c.append(None)
                highs_f.append(None)
                lows_c.append(None)
                lows_f.append(None)
            if day["is_today"]:
                today_index = i
        result[f"panel-{idx}"] = {
            "name": location["name"],
            "labels": labels,
            "highsC": highs_c,
            "highsF": highs_f,
            "lowsC": lows_c,
            "lowsF": lows_f,
            "todayIndex": today_index,
        }
    return result


# 주간 기온 라인 그래프(Chart.js) 모듈.
# build_html 의 f-string 안에 {chart_js} 로 그대로 삽입되므로, 여기서는
# 일반 문자열이라 중괄호를 이중으로 쓸 필요가 없다. 탭 전환/테마/단위 변경 시
# 다른 IIFE 들이 __chartApi 를 호출하므로 이 모듈이 스크립트 맨 위에 온다.
CHART_JS = r"""
    // ── 주간 기온 라인 그래프 (Chart.js) ─────────────────────
    var __chartApi = (function () {
      var dataEl = document.getElementById("chart-data");
      var canvas = document.getElementById("tempChart");
      if (!dataEl || !canvas || typeof Chart === "undefined") {
        return null;
      }

      var CHART_DATA = {};
      try {
        CHART_DATA = JSON.parse(dataEl.textContent);
      } catch (e) {
        return null;
      }

      var HIGH_COLOR = "#ef4444";  // 최고기온 = 빨강
      var LOW_COLOR = "#3b82f6";   // 최저기온 = 파랑
      var currentPanel = null;

      function currentUnit() {
        try {
          return localStorage.getItem("weather-unit") === "f" ? "f" : "c";
        } catch (e) {
          return "c";
        }
      }

      function isDark() {
        return document.documentElement.getAttribute("data-theme") === "dark";
      }

      // 다크/라이트에 맞는 축·글자·격자·툴팁 색을 돌려준다.
      function themeColors() {
        if (isDark()) {
          return {
            tick: "#94a3b8",
            grid: "rgba(255, 255, 255, 0.10)",
            legend: "#e2e8f0",
            tooltipBg: "rgba(15, 23, 42, 0.95)",
            tooltipText: "#e2e8f0",
            pointBorder: "#1e293b"
          };
        }
        return {
          tick: "#64748b",
          grid: "rgba(15, 23, 42, 0.08)",
          legend: "#1e293b",
          tooltipBg: "rgba(255, 255, 255, 0.96)",
          tooltipText: "#1e293b",
          pointBorder: "#ffffff"
        };
      }

      // 오늘 지점만 점을 크게 강조 (데이터 없는 날은 기본값 유지)
      function pointRadii(arr, todayIndex, base, todaySize) {
        var out = [];
        for (var i = 0; i < arr.length; i++) {
          out.push(i === todayIndex && arr[i] !== null ? todaySize : base);
        }
        return out;
      }

      var chart = new Chart(canvas.getContext("2d"), {
        type: "line",
        data: {
          labels: [],
          datasets: [
            {
              label: "최고기온",
              data: [],
              borderColor: HIGH_COLOR,
              backgroundColor: HIGH_COLOR,
              borderWidth: 2.5,
              tension: 0.35,
              spanGaps: true,
              pointBorderWidth: 2
            },
            {
              label: "최저기온",
              data: [],
              borderColor: LOW_COLOR,
              backgroundColor: LOW_COLOR,
              borderWidth: 2.5,
              tension: 0.35,
              spanGaps: true,
              pointBorderWidth: 2
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: {
            legend: {
              labels: { color: "#1e293b", usePointStyle: true, padding: 16 }
            },
            tooltip: {
              backgroundColor: "rgba(255, 255, 255, 0.96)",
              titleColor: "#1e293b",
              bodyColor: "#1e293b",
              borderColor: "rgba(15, 23, 42, 0.1)",
              borderWidth: 1,
              padding: 10,
              callbacks: {
                label: function (ctx) {
                  var v = ctx.parsed.y;
                  var u = currentUnit() === "f" ? "°F" : "°C";
                  if (v === null || v === undefined) {
                    return ctx.dataset.label + ": -";
                  }
                  return ctx.dataset.label + ": " + v + u;
                }
              }
            }
          },
          scales: {
            x: {
              grid: { color: "rgba(15, 23, 42, 0.08)" },
              ticks: { color: "#64748b", font: { size: 12 } }
            },
            y: {
              grid: { color: "rgba(15, 23, 42, 0.08)" },
              ticks: {
                color: "#64748b",
                callback: function (value) {
                  return value + (currentUnit() === "f" ? "°" : "°");
                }
              },
              title: { display: true, text: "기온 (°C)", color: "#64748b" }
            }
          }
        }
      });

      // 지정 패널(지역) 데이터 + 현재 단위/테마로 그래프를 다시 그린다.
      function render(panelId) {
        if (panelId) {
          currentPanel = panelId;
        }
        var d = CHART_DATA[currentPanel];
        if (!d) {
          return;
        }
        var unit = currentUnit();
        var highs = unit === "f" ? d.highsF : d.highsC;
        var lows = unit === "f" ? d.lowsF : d.lowsC;
        var c = themeColors();

        chart.data.labels = d.labels;
        chart.data.datasets[0].data = highs;
        chart.data.datasets[1].data = lows;

        chart.data.datasets[0].pointRadius = pointRadii(highs, d.todayIndex, 3.5, 8);
        chart.data.datasets[0].pointHoverRadius = pointRadii(highs, d.todayIndex, 6, 10);
        chart.data.datasets[1].pointRadius = pointRadii(lows, d.todayIndex, 3.5, 8);
        chart.data.datasets[1].pointHoverRadius = pointRadii(lows, d.todayIndex, 6, 10);

        chart.data.datasets[0].pointBackgroundColor = HIGH_COLOR;
        chart.data.datasets[1].pointBackgroundColor = LOW_COLOR;
        chart.data.datasets[0].pointBorderColor = c.pointBorder;
        chart.data.datasets[1].pointBorderColor = c.pointBorder;

        var sc = chart.options.scales;
        sc.x.ticks.color = c.tick;
        sc.x.grid.color = c.grid;
        sc.y.ticks.color = c.tick;
        sc.y.grid.color = c.grid;
        sc.y.title.text = "기온 (" + (unit === "f" ? "°F" : "°C") + ")";
        sc.y.title.color = c.tick;

        var pl = chart.options.plugins;
        pl.legend.labels.color = c.legend;
        pl.tooltip.backgroundColor = c.tooltipBg;
        pl.tooltip.titleColor = c.tooltipText;
        pl.tooltip.bodyColor = c.tooltipText;
        pl.tooltip.borderColor = c.grid;

        chart.update();
      }

      return {
        // 탭 전환 시: 해당 지역 데이터로 그래프 교체
        update: function (panelId) { render(panelId); },
        // 테마/단위 변경 시: 현재 지역 그대로 색·값만 갱신
        refresh: function () { render(null); }
      };
    })();
"""


def build_html(location_data, run_time):
    """여러 지역의 예보 데이터로 weather.html 전체 문서를 생성한다.

    location_data: [(location dict, forecast list), ...] 순서대로 탭 구성.
    """
    run_time_str = run_time.strftime("%Y-%m-%d %H:%M")

    # 지역별 그래프 데이터를 JSON 으로 만들어 HTML 에 심는다.
    chart_json = json.dumps(build_chart_data(location_data), ensure_ascii=False)
    chart_js = CHART_JS

    # 탭 버튼과 각 지역 패널(그리드)을 만든다.
    tab_buttons = []
    panels = []
    for idx, (location, forecast, air) in enumerate(location_data):
        active = " active" if idx == 0 else ""
        name = html.escape(location["name"])
        tab_buttons.append(
            f'''      <button class="tab-btn{active}" type="button" role="tab"
              data-target="panel-{idx}" aria-selected="{"true" if idx == 0 else "false"}">{name}</button>'''
        )
        cards_html = build_cards_html(forecast)
        aq_html = build_air_quality_html(air)
        panels.append(
            f'''    <div class="panel{active}" id="panel-{idx}" role="tabpanel"
         data-name="{name}" data-lat="{location["latitude"]}" data-lon="{location["longitude"]}">
{aq_html}
      <div class="grid">
{cards_html}
      </div>
    </div>'''
        )
    tabs_html = "\n".join(tab_buttons)
    panels_html = "\n\n".join(panels)

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>일주일 날씨 예보</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
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
    --card-border: #eef2f7;
    --card-shadow: rgba(15, 23, 42, 0.06);
    --card-shadow-hover: rgba(15, 23, 42, 0.12);
    --toggle-bg: #ffffff;
    --toggle-border: #e2e8f0;
  }}

  html[data-theme="dark"] {{
    --accent: #60a5fa;
    --accent-light: #3b82f6;
    --accent-soft: rgba(96, 165, 250, 0.16);
    --text: #e2e8f0;
    --text-muted: #94a3b8;
    --bg: #0f172a;
    --card-bg: #1e293b;
    --card-border: #334155;
    --card-shadow: rgba(0, 0, 0, 0.35);
    --card-shadow-hover: rgba(0, 0, 0, 0.5);
    --toggle-bg: #1e293b;
    --toggle-border: #334155;
  }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo",
                 "Malgun Gothic", sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 48px 20px;
    -webkit-font-smoothing: antialiased;
    transition: background 0.4s ease, color 0.4s ease;
  }}

  .theme-toggle {{
    position: fixed;
    top: 20px;
    right: 20px;
    width: 44px;
    height: 44px;
    border-radius: 999px;
    border: 1px solid var(--toggle-border);
    background: var(--toggle-bg);
    color: var(--text);
    font-size: 1.3rem;
    line-height: 1;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 14px var(--card-shadow);
    transition: background 0.4s ease, border-color 0.4s ease,
                box-shadow 0.2s ease, transform 0.2s ease;
    z-index: 100;
  }}

  .theme-toggle:hover {{
    transform: translateY(-2px) scale(1.05);
    box-shadow: 0 8px 20px var(--card-shadow-hover);
  }}

  .unit-toggle {{
    position: fixed;
    top: 20px;
    right: 74px;
    height: 44px;
    min-width: 44px;
    padding: 0 14px;
    border-radius: 999px;
    border: 1px solid var(--toggle-border);
    background: var(--toggle-bg);
    color: var(--text);
    font-size: 0.95rem;
    font-weight: 700;
    line-height: 1;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 14px var(--card-shadow);
    transition: background 0.4s ease, border-color 0.4s ease,
                box-shadow 0.2s ease, transform 0.2s ease;
    z-index: 100;
  }}

  .unit-toggle:hover {{
    transform: translateY(-2px) scale(1.05);
    box-shadow: 0 8px 20px var(--card-shadow-hover);
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

  /* ── 지역 전환 탭 ─────────────────────────────────────────── */
  .tabs {{
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
    margin-bottom: 28px;
  }}

  .tab-btn {{
    padding: 9px 22px;
    border-radius: 999px;
    border: 1px solid var(--toggle-border);
    background: var(--card-bg);
    color: var(--text-muted);
    font-size: 0.95rem;
    font-weight: 600;
    font-family: inherit;
    cursor: pointer;
    transition: background 0.2s ease, color 0.2s ease,
                border-color 0.2s ease, box-shadow 0.2s ease,
                transform 0.15s ease;
  }}

  .tab-btn:hover {{
    transform: translateY(-2px);
    box-shadow: 0 6px 16px var(--card-shadow);
    color: var(--text);
  }}

  .tab-btn.active {{
    background: var(--accent);
    border-color: var(--accent);
    color: #ffffff;
    box-shadow: 0 6px 18px rgba(37, 99, 235, 0.35);
  }}

  /* 패널: 활성 패널만 보이게 */
  .panel {{
    display: none;
  }}

  .panel.active {{
    display: block;
    animation: panel-fade 0.35s ease;
  }}

  @keyframes panel-fade {{
    from {{ opacity: 0; transform: translateY(6px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 20px;
  }}

  /* ── 대기질 배지 (지역별 PM2.5 / UV) ───────────────────── */
  .air-quality {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 20px;
  }}

  .aq-badge {{
    display: inline-flex;
    align-items: center;
    font-size: 0.8rem;
    font-weight: 700;
    padding: 5px 12px;
    border-radius: 999px;
    line-height: 1;
    border: 1px solid transparent;
    letter-spacing: -0.01em;
  }}

  /* 좋음=초록 / 보통=노랑 / 나쁨=주황 / 매우나쁨=빨강 */
  .aq-badge.aq-good {{
    background: #dcfce7;
    color: #15803d;
    border-color: #86efac;
  }}
  .aq-badge.aq-moderate {{
    background: #fef9c3;
    color: #a16207;
    border-color: #fde047;
  }}
  .aq-badge.aq-bad {{
    background: #ffedd5;
    color: #c2410c;
    border-color: #fdba74;
  }}
  .aq-badge.aq-verybad {{
    background: #fee2e2;
    color: #b91c1c;
    border-color: #fca5a5;
  }}
  .aq-badge.aq-none {{
    background: var(--card-border);
    color: var(--text-muted);
  }}

  /* 다크 모드에서는 채도를 낮춘 반투명 배경으로 대비 확보 */
  html[data-theme="dark"] .aq-badge.aq-good {{
    background: rgba(34, 197, 94, 0.18);
    color: #86efac;
    border-color: rgba(134, 239, 172, 0.4);
  }}
  html[data-theme="dark"] .aq-badge.aq-moderate {{
    background: rgba(234, 179, 8, 0.18);
    color: #fde047;
    border-color: rgba(253, 224, 71, 0.4);
  }}
  html[data-theme="dark"] .aq-badge.aq-bad {{
    background: rgba(249, 115, 22, 0.18);
    color: #fdba74;
    border-color: rgba(253, 186, 116, 0.4);
  }}
  html[data-theme="dark"] .aq-badge.aq-verybad {{
    background: rgba(239, 68, 68, 0.2);
    color: #fca5a5;
    border-color: rgba(252, 165, 165, 0.4);
  }}

  .card {{
    background: var(--card-bg);
    border-radius: 18px;
    padding: 24px 22px;
    box-shadow: 0 4px 16px var(--card-shadow);
    border: 1px solid var(--card-border);
    transition: transform 0.18s ease, box-shadow 0.18s ease,
                background 0.4s ease, border-color 0.4s ease, color 0.4s ease;
    position: relative;
    overflow: hidden;
  }}

  .card:hover {{
    transform: translateY(-4px);
    box-shadow: 0 12px 28px var(--card-shadow-hover);
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
    display: inline-block;
    position: relative;
    transform-origin: center;
    /* GPU 가속 힌트 + 애니메이션 기본값 */
    will-change: transform, filter;
  }}

  /* ── 날씨 아이콘 CSS 애니메이션 ─────────────────────────────
     라이트/다크 공통으로 자연스럽게 보이도록 glow 색은 currentColor
     대신 은은한 파랑/노랑 톤을 쓰고, 과하지 않은 폭·속도로 움직인다. */

  /* 맑음 : 아주 천천히 회전 + 은은한 발광 */
  .icon-sun {{
    animation: icon-spin 18s linear infinite,
               icon-sun-glow 3.5s ease-in-out infinite;
  }}
  @keyframes icon-spin {{
    from {{ transform: rotate(0deg); }}
    to   {{ transform: rotate(360deg); }}
  }}
  @keyframes icon-sun-glow {{
    0%, 100% {{ filter: drop-shadow(0 0 2px rgba(250, 204, 21, 0.35)); }}
    50%      {{ filter: drop-shadow(0 0 10px rgba(250, 204, 21, 0.75)); }}
  }}

  /* 구름 : 좌우로 살짝 흔들림 */
  .icon-cloud {{
    animation: icon-sway 4.5s ease-in-out infinite;
  }}
  @keyframes icon-sway {{
    0%, 100% {{ transform: translateX(-3px); }}
    50%      {{ transform: translateX(3px); }}
  }}

  /* 안개 : 흐릿하게 옅어졌다 진해짐 + 미세한 흔들림 */
  .icon-fog {{
    animation: icon-fog-drift 5s ease-in-out infinite;
  }}
  @keyframes icon-fog-drift {{
    0%, 100% {{ transform: translateX(-2px); opacity: 0.65; }}
    50%      {{ transform: translateX(2px);  opacity: 1; }}
  }}

  /* 비 : 아이콘은 살짝 떠 있고, 아래로 빗방울이 떨어진다 */
  .icon-rain {{
    animation: icon-bob 3s ease-in-out infinite;
  }}
  @keyframes icon-bob {{
    0%, 100% {{ transform: translateY(0); }}
    50%      {{ transform: translateY(-2px); }}
  }}
  .icon-rain::before,
  .icon-rain::after {{
    content: "";
    position: absolute;
    bottom: -2px;
    width: 3px;
    height: 9px;
    border-radius: 2px;
    background: linear-gradient(to bottom,
      rgba(96, 165, 250, 0), var(--accent));
    opacity: 0;
  }}
  .icon-rain::before {{
    left: 38%;
    animation: icon-drop 1.4s linear infinite;
  }}
  .icon-rain::after {{
    left: 58%;
    animation: icon-drop 1.4s linear infinite 0.7s;
  }}
  @keyframes icon-drop {{
    0%   {{ transform: translateY(-6px); opacity: 0; }}
    30%  {{ opacity: 0.9; }}
    100% {{ transform: translateY(14px); opacity: 0; }}
  }}

  /* 눈 : 살랑살랑 좌우로 흔들리며 위아래로 떠다님 */
  .icon-snow {{
    animation: icon-snow-float 4s ease-in-out infinite;
  }}
  @keyframes icon-snow-float {{
    0%, 100% {{ transform: translate(-2px, 0) rotate(-4deg); }}
    50%      {{ transform: translate(2px, -3px) rotate(4deg); }}
  }}

  /* 천둥번개 : 가끔 번쩍 + 미세한 진동 */
  .icon-storm {{
    animation: icon-shake 3.2s ease-in-out infinite,
               icon-flash 3.2s steps(1, end) infinite;
  }}
  @keyframes icon-shake {{
    0%, 92%, 100% {{ transform: translateX(0); }}
    94%  {{ transform: translateX(-2px); }}
    96%  {{ transform: translateX(2px); }}
    98%  {{ transform: translateX(-1px); }}
  }}
  @keyframes icon-flash {{
    0%, 90%, 100% {{ filter: none; }}
    93%  {{ filter: drop-shadow(0 0 8px rgba(250, 204, 21, 0.9)) brightness(1.4); }}
  }}

  /* 다크 모드에서 빗방울 대비 보정 (더 밝은 파랑으로) */
  html[data-theme="dark"] .icon-rain::before,
  html[data-theme="dark"] .icon-rain::after {{
    background: linear-gradient(to bottom,
      rgba(147, 197, 253, 0), #93c5fd);
  }}

  /* latest(오늘) 카드는 배경이 파랑이라 빗방울을 흰색 계열로 */
  .card.latest .icon-rain::before,
  .card.latest .icon-rain::after {{
    background: linear-gradient(to bottom,
      rgba(255, 255, 255, 0), rgba(255, 255, 255, 0.9));
  }}

  /* nodata 카드(지난 날씨/예보 없음)는 움직이지 않게 정지 */
  .card.nodata .icon {{
    animation: none !important;
  }}
  .card.nodata .icon::before,
  .card.nodata .icon::after {{
    display: none;
  }}

  /* 접근성 : 모션 최소화를 원하는 사용자는 애니메이션 끔 */
  @media (prefers-reduced-motion: reduce) {{
    .card .icon,
    .card .icon::before,
    .card .icon::after {{
      animation: none !important;
    }}
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

  /* No-data / past cells (지난 날씨 · 예보 없음) */
  .card.nodata {{
    background: repeating-linear-gradient(
      135deg, var(--card-bg), var(--card-bg) 10px,
      var(--card-border) 10px, var(--card-border) 20px);
    color: var(--text-muted);
    box-shadow: none;
  }}

  .card.nodata .icon,
  .card.nodata .condition {{
    opacity: 0.7;
  }}

  .card.nodata .no-temps {{
    font-size: 0.85rem;
    color: var(--text-muted);
  }}

  footer {{
    text-align: center;
    margin-top: 40px;
    font-size: 0.8rem;
    color: var(--text-muted);
  }}

  /* ── 주간 기온 라인 그래프 카드 ─────────────────────────────
     카드 목록 아래쪽에 배치. 배경/테두리는 카드와 동일한 테마
     변수를 써서 다크모드에서도 자연스럽게 전환된다. Chart.js 캔버스
     자체의 축·글자·격자 색은 JS 에서 테마에 맞춰 다시 칠한다. */
  .chart-section {{
    margin-top: 36px;
  }}

  .chart-card {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 18px;
    padding: 24px 22px;
    box-shadow: 0 4px 16px var(--card-shadow);
    transition: background 0.4s ease, border-color 0.4s ease,
                box-shadow 0.2s ease;
  }}

  .chart-card h2 {{
    font-size: 1.05rem;
    font-weight: 700;
    margin-bottom: 4px;
    letter-spacing: -0.01em;
  }}

  .chart-card .chart-sub {{
    font-size: 0.82rem;
    color: var(--text-muted);
    margin-bottom: 16px;
  }}

  .chart-wrap {{
    position: relative;
    width: 100%;
    height: 340px;
  }}

  @media (max-width: 768px) {{
    .chart-section {{
      margin-top: 24px;
    }}
    .chart-card {{
      padding: 18px 16px;
      border-radius: 14px;
    }}
    .chart-wrap {{
      height: 260px;
    }}
  }}

  footer {{
    text-align: center;
    margin-top: 40px;
    font-size: 0.8rem;
    color: var(--text-muted);
  }}

  /* ── 모바일 반응형 (폭 768px 이하) ─────────────────────────
     카드가 좁게 찌그러지지 않도록 1열로 세로 정렬하고, 폰트와
     여백을 작은 화면에 맞게 줄인다. 다크모드 버튼은 조금 작게
     만들고, header 에 위쪽 여백을 줘서 고정된 토글 버튼과
     제목/카드가 서로 겹치지 않게 한다. */
  @media (max-width: 768px) {{
    body {{
      padding: 24px 14px;
    }}

    .theme-toggle {{
      top: 12px;
      right: 12px;
      width: 38px;
      height: 38px;
      font-size: 1.1rem;
    }}

    .container {{
      max-width: 100%;
    }}

    /* 제목이 고정된 다크모드 버튼 아래로 내려오도록 위 여백 확보 */
    header {{
      margin-bottom: 28px;
      padding-top: 34px;
    }}

    header h1 {{
      font-size: 1.5rem;
      margin-bottom: 8px;
    }}

    .meta {{
      font-size: 0.8rem;
      gap: 4px 14px;
    }}

    /* 핵심: 카드들을 무조건 1열로 세로로 쌓는다 */
    .grid {{
      grid-template-columns: 1fr;
      gap: 14px;
    }}

    .card {{
      padding: 18px 18px;
      border-radius: 14px;
    }}

    /* latest 카드가 위로 뜨는 transform 때문에 겹쳐 보이지 않도록 정리 */
    .card.latest {{
      transform: none;
    }}

    .card .date {{
      font-size: 1.05rem;
    }}

    .card .day {{
      font-size: 0.8rem;
      margin-bottom: 12px;
    }}

    .card .icon {{
      font-size: 2.2rem;
      margin-bottom: 10px;
    }}

    .card .condition {{
      font-size: 0.92rem;
      margin-bottom: 12px;
    }}

    .temps {{
      gap: 14px;
      font-size: 0.85rem;
    }}

    /* today 배지가 카드 안쪽에 안전하게 들어가도록 위치·크기 조정 */
    .badge {{
      top: 12px;
      right: 12px;
      font-size: 0.62rem;
      padding: 2px 7px;
    }}

    footer {{
      margin-top: 28px;
      font-size: 0.75rem;
    }}
  }}
</style>
<script>
  // 저장된 테마를 body 렌더 전에 적용해 깜빡임(FOUC)을 막는다.
  (function () {{
    try {{
      var saved = localStorage.getItem("weather-theme");
      if (saved === "dark") {{
        document.documentElement.setAttribute("data-theme", "dark");
      }}
    }} catch (e) {{}}
  }})();
</script>
</head>
<body>
  <button class="unit-toggle" id="unitToggle" type="button"
          aria-label="온도 단위 전환" title="섭씨/화씨 전환">°C</button>
  <button class="theme-toggle" id="themeToggle" type="button"
          aria-label="다크모드 전환" title="다크모드 전환">🌙</button>
  <div class="container">
    <header>
      <h1>일주일 날씨 예보<span class="dot">.</span></h1>
      <div class="meta">
        <span>📍 위치 : <strong id="metaLoc"></strong> <span id="metaCoord"></span></span>
        <span>🕒 실행 시각 : <strong>{run_time_str}</strong></span>
      </div>
    </header>

    <div class="tabs" role="tablist">
{tabs_html}
    </div>

{panels_html}

    <section class="chart-section">
      <div class="chart-card">
        <h2>이번 주 기온 변화</h2>
        <div class="chart-sub" id="chartSub">최고기온(빨강) · 최저기온(파랑) — 오늘은 크게 표시</div>
        <div class="chart-wrap">
          <canvas id="tempChart"></canvas>
        </div>
      </div>
    </section>

    <footer>
      데이터 출처 : weather_log.txt · 알렌 · 서울 일주일 날씨 예보
    </footer>
  </div>
  <script type="application/json" id="chart-data">{chart_json}</script>
  <script>
{chart_js}
    (function () {{
      var root = document.documentElement;
      var toggle = document.getElementById("themeToggle");

      function syncIcon() {{
        var isDark = root.getAttribute("data-theme") === "dark";
        toggle.textContent = isDark ? "☀️" : "🌙";
      }}

      syncIcon();

      toggle.addEventListener("click", function () {{
        var isDark = root.getAttribute("data-theme") === "dark";
        if (isDark) {{
          root.removeAttribute("data-theme");
        }} else {{
          root.setAttribute("data-theme", "dark");
        }}
        try {{
          localStorage.setItem("weather-theme", isDark ? "light" : "dark");
        }} catch (e) {{}}
        syncIcon();
        if (__chartApi) {{ __chartApi.refresh(); }}
      }});
    }})();

    (function () {{
      var unitToggle = document.getElementById("unitToggle");
      var unit = "c";
      try {{
        var savedUnit = localStorage.getItem("weather-unit");
        if (savedUnit === "f") {{
          unit = "f";
        }}
      }} catch (e) {{}}

      function render() {{
        var isF = unit === "f";
        var primary = document.querySelectorAll(".temp-primary");
        var secondary = document.querySelectorAll(".temp-secondary");
        var i;
        for (i = 0; i < primary.length; i++) {{
          var el = primary[i];
          if (isF) {{
            el.textContent = el.getAttribute("data-f") + "°F";
          }} else {{
            el.textContent = el.getAttribute("data-c") + "°C";
          }}
        }}
        for (i = 0; i < secondary.length; i++) {{
          var s = secondary[i];
          if (isF) {{
            s.textContent = s.getAttribute("data-c") + "°C";
          }} else {{
            s.textContent = s.getAttribute("data-f") + "°F";
          }}
        }}
        unitToggle.textContent = isF ? "°F" : "°C";
      }}

      render();

      unitToggle.addEventListener("click", function () {{
        unit = unit === "c" ? "f" : "c";
        try {{
          localStorage.setItem("weather-unit", unit);
        }} catch (e) {{}}
        render();
        if (__chartApi) {{ __chartApi.refresh(); }}
      }});
    }})();

    // ── 지역 전환 탭 ──────────────────────────────────────────
    (function () {{
      var buttons = document.querySelectorAll(".tab-btn");
      var panels = document.querySelectorAll(".panel");
      var metaLoc = document.getElementById("metaLoc");
      var metaCoord = document.getElementById("metaCoord");

      function activate(targetId) {{
        var i;
        for (i = 0; i < buttons.length; i++) {{
          var isActive = buttons[i].getAttribute("data-target") === targetId;
          buttons[i].classList.toggle("active", isActive);
          buttons[i].setAttribute("aria-selected", isActive ? "true" : "false");
        }}
        for (i = 0; i < panels.length; i++) {{
          var panel = panels[i];
          var on = panel.id === targetId;
          panel.classList.toggle("active", on);
          if (on && metaLoc) {{
            metaLoc.textContent = panel.getAttribute("data-name");
            if (metaCoord) {{
              metaCoord.textContent =
                "(위도 " + panel.getAttribute("data-lat") +
                ", 경도 " + panel.getAttribute("data-lon") + ")";
            }}
          }}
        }}
      }}

      for (var j = 0; j < buttons.length; j++) {{
        buttons[j].addEventListener("click", function () {{
          activate(this.getAttribute("data-target"));
        }});
      }}

      // 첫 번째 탭을 초기 활성 상태로 (meta 정보도 채움)
      if (buttons.length) {{
        activate(buttons[0].getAttribute("data-target"));
      }}
    }})();
  </script>
</body>
</html>
'''


def main():
    run_time = datetime.now()
    today = run_time.replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = run_time.strftime("%Y-%m-%d")

    location_data = []   # [(location, forecast), ...] — HTML 탭 구성용
    log_blocks = []      # 지역별 로그 텍스트 블록

    # 지역별로 이번 주(일~토) 데이터를 예보 + 과거 날씨 API 로 모은다.
    for location in LOCATIONS:
        week_start, week_end, data_map = collect_weekly_data(
            today, location["latitude"], location["longitude"]
        )

        if not data_map:
            print(
                f"[{location['name']}] 날씨 정보를 가져오지 못했습니다.",
                file=sys.stderr,
            )
            continue

        forecast = build_forecast(week_start, data_map, today_str)

        # 현재 대기질(PM2.5)·자외선 지수 가져오기 (실패해도 예보는 계속 진행)
        try:
            air = fetch_air_quality(location["latitude"], location["longitude"])
        except Exception as e:
            print(
                f"[{location['name']}] 대기질 정보를 가져오지 못했습니다: {e}",
                file=sys.stderr,
            )
            air = {"pm25": None, "uv": None}

        location_data.append((location, forecast, air))

        # 텍스트 결과 만들기 + 화면 출력 (지역명으로 구분)
        log_text = build_log_text(forecast, run_time, location, air)
        print(log_text)
        print()
        log_blocks.append(log_text)

    if not location_data:
        print("모든 지역의 날씨 정보를 가져오지 못했습니다.", file=sys.stderr)
        sys.exit(1)

    # 2) 로그 파일에 계속 이어서 기록 (지역 블록을 이어붙임)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n\n".join(log_blocks))
            f.write("\n\n")
    except Exception as e:
        print(f"로그 파일 기록에 실패했습니다: {e}", file=sys.stderr)

    # 3) 방금 받은 최신 데이터로 weather.html 다시 생성 (지역별 탭)
    try:
        html_text = build_html(location_data, run_time)
        with open(HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html_text)
    except Exception as e:
        print(f"HTML 파일 생성에 실패했습니다: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
