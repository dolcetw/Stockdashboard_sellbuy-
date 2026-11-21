#!/bin/bash
# Synology DSM「任務排程表」用：從 GitHub 拉最新的分點前 15 大資料到 NAS
# 設定：控制台 → 任務排程表 → 新增 → 排程的任務 → 使用者定義的指令碼
#       每週一~五 21:30 執行：bash /volume1/docker/broker_top15/pull_broker_top15.sh
set -euo pipefail

REPO="dolcetw/Stockdashboard_sellbuy-"           # ← 你的 repo
BRANCH="main"
DEST="/volume1/docker/broker_top15"    # ← NAS 存放位置
TOKEN_FILE="$DEST/.github_token"       # private repo 才需要：放 fine-grained PAT (Contents: Read-only)

mkdir -p "$DEST/daily"
AUTH=()
[ -s "$TOKEN_FILE" ] && AUTH=(-H "Authorization: Bearer $(cat "$TOKEN_FILE")")

get() {  # get <repo 內路徑> <本機檔案>
  curl -fsSL --retry 3 "${AUTH[@]}" -H "Accept: application/vnd.github.raw" \
       "https://api.github.com/repos/$REPO/contents/$1?ref=$BRANCH" -o "$2.tmp" && mv "$2.tmp" "$2"
}

get data/latest.json "$DEST/latest.json"
DATE=$(grep -o '"date": *"[0-9]*"' "$DEST/latest.json" | grep -o '[0-9]\{8\}')
FILE=$(grep -o '"file": *"[^"]*"'  "$DEST/latest.json" | sed 's/.*"\(data[^"]*\)"/\1/')
OUT="$DEST/daily/broker_top15_${DATE}.csv"

if [ -f "$OUT" ]; then
  echo "$(date '+%F %T') $DATE already on NAS, nothing to do" >> "$DEST/pull.log"
  exit 0
fi

get "$FILE" "$OUT.gz"
gunzip -f "$OUT.gz"                      # → daily/broker_top15_YYYYMMDD.csv
cp -f "$OUT" "$DEST/latest.csv"          # 儀表板固定讀這個
echo "$(date '+%F %T') pulled $DATE ($(wc -l < "$OUT") lines)" >> "$DEST/pull.log"
