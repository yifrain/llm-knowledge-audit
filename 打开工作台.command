#!/bin/zsh
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/llmka ]]; then
  echo '请先按照 README_CN.md 完成一次安装。'
  read -r '?按回车关闭'
  exit 1
fi
.venv/bin/llmka ui --open-browser
