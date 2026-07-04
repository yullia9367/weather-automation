#!/usr/bin/env bash
#
# weather.py를 실행해 결과 파일(weather_log.txt, weather.html)을 갱신하고,
# 변경사항이 있으면 오늘 날짜를 담은 커밋 메시지로 커밋한 뒤 origin main에 푸시한다.
# 변경사항이 없으면 커밋 없이 조용히 종료한다.

set -euo pipefail

# 스크립트가 있는 디렉터리(= 저장소 루트)로 이동
cd "$(dirname "$0")"

# 1) weather.py 실행 -> weather_log.txt, weather.html 갱신
python3 weather.py

# 2) 변경사항 스테이징
git add -A

# 스테이징된 변경사항이 없으면 조용히 종료
if git diff --cached --quiet; then
    exit 0
fi

# 3) 오늘 날짜를 포함한 커밋 후 푸시
TODAY="$(date '+%Y-%m-%d')"
git commit -m "chore: 날씨 데이터 자동 갱신 (${TODAY})"
git push origin main
