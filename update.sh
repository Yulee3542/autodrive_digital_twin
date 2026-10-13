#!/usr/bin/env bash
# 이미 설정된 환경을 최신 코드로 갱신 (setup.sh는 최초 1회).
# git pull은 --ff-only — 로컬에 커밋 안 한 실험 값이 있으면 여기서 멈춘다(자동 머지·덮어쓰기 안 함).
# 이 폴더가 다른 저장소의 하위 폴더(예: 개인 노트 저장소 안)면 pull은 건너뛰고 재빌드만 한다.
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ "$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null)" = "$ROOT" ]; then
    echo "== git pull --ff-only =="
    git -C "$ROOT" pull --ff-only
else
    echo "== 독립 저장소가 아님 — pull 건너뜀, 재빌드만 =="
fi
bash "$ROOT/setup.sh" --build-only
echo "완료 — 새 터미널에서 실행하거나 'source ${KIIS_WS:-$HOME/kiis_ws}/install/setup.bash'"
