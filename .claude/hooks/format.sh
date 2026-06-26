#!/usr/bin/env bash
# Format-on-edit 分发器:按扩展名格式化 Claude 刚写入的文件。
# 工具未安装时静默跳过,绝不阻塞编辑(始终 exit 0)。
f=$(jq -r '.tool_response.filePath // .tool_input.file_path // empty')
[ -z "$f" ] && exit 0
[ -f "$f" ] || exit 0

case "$f" in
  *.py)
    if command -v ruff >/dev/null 2>&1; then
      ruff format "$f"; ruff check --fix "$f"
    elif command -v uvx >/dev/null 2>&1; then
      uvx ruff format "$f"; uvx ruff check --fix "$f"
    fi
    ;;
  *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.json|*.css)
    # 仅当 prettier 已本地安装时运行(--no-install 避免钩子里联网拉取导致卡顿)
    if command -v prettier >/dev/null 2>&1; then
      prettier --write --ignore-unknown "$f"
    elif command -v npx >/dev/null 2>&1; then
      npx --no-install prettier --write --ignore-unknown "$f" 2>/dev/null
    fi
    ;;
esac
exit 0
