#!/bin/bash
# 发布/推送前的密钥与隐私扫描：scan_secrets.sh [目录=.]   有命中则退出码 1。
# 查三类：常见密钥格式；个人信息（邮箱、家目录路径、内网/隧道地址）；不该进仓库的文件（env、密钥、媒体成品）。
# 这是兜底，不是许可：密钥本来就不该出现在工作目录的任何文件里（放 ~/.config/<服务>/env，权限 600）。
D="${1:-.}"; rc=0; cd "$D" || exit 2
G() { grep -rnIE --exclude-dir=.git --exclude=scan_secrets.sh "$@" . ; }
echo "── 密钥格式"; G '(sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|xox[abprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.)' && rc=1
echo "── 疑似写死的凭据"; G -i '(api[_-]?key|secret|token|passwd|password|authorization)["'"'"' ]*[:=] *["'"'"'][A-Za-z0-9_\-\.]{16,}["'"'"']' && rc=1
echo "── 32 位以上的十六进制串（多为 key / 音色 ID / 会话 ID，逐条确认）"; G '\b[0-9a-f]{32,}\b' && rc=1
echo "── 个人信息"; G '([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}|/Users/[a-z][a-z0-9_-]+|/home/[a-z][a-z0-9_-]+|\b100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]+\.[0-9]+\b|\b192\.168\.[0-9]+\.[0-9]+\b|trycloudflare\.com|\.ts\.net)' && rc=1
echo "── 不该进仓库的文件"; find . -path ./.git -prune -o -type f \( -name '.env*' -o -name '*.pem' -o -name '*.key' -o -name 'storage_state.json' -o -name 'cookies*.txt' -o -name '*.mp4' -o -name '*.mp3' -o -name '*.flac' -o -name '*.wav' \) -print | grep . && rc=1
[ $rc -eq 0 ] && echo "✅ 没有命中" || echo "❌ 有命中：逐条看过、处理完再推送"
exit $rc
