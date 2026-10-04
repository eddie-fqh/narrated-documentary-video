#!/usr/bin/env python3
"""把一段文字交给云端 TTS（Fish Audio 或 ElevenLabs）用你克隆的音色念出来。给 tts_segments.py 的 TTS_CMD 用。
用法: tts_cloud.py fish|elevenlabs --in <text_file> --out <out.mp3|out.wav> [--speed 0.95]

密钥和音色 ID 只从环境变量读——不要写进命令行、脚本、仓库：
  Fish Audio : FISH_API_KEY  FISH_VOICE_ID   可选 FISH_MODEL（如 s1；不设则用服务端默认）
  ElevenLabs : ELEVENLABS_API_KEY  ELEVENLABS_VOICE_ID   可选 ELEVENLABS_MODEL（默认 eleven_multilingual_v2）
建议放在 ~/.config/tts/env（chmod 600），用之前:  set -a; . ~/.config/tts/env; set +a
接法:
  export TTS_OUT_EXT=mp3
  export TTS_CMD='python3 scripts/tts_cloud.py fish --speed 0.95 --in {text_file} --out {out}'
出错时只打印状态码和服务端返回的说明，不打印请求头。接口细节与出处见 references/voice-cloning.md。"""
import os, sys, json, time, urllib.request, urllib.error
def opt(name, default=None):
    return sys.argv[sys.argv.index(name)+1] if name in sys.argv else default
def need(var):
    v = os.environ.get(var)
    if not v: raise SystemExit(f"缺环境变量 {var}（见本文件开头）")
    return v
provider = sys.argv[1] if len(sys.argv) > 1 else ""; text = open(opt("--in"), encoding="utf-8").read().strip(); out = opt("--out")
speed = float(opt("--speed", "1.0")); fmt = "wav" if out.lower().endswith(".wav") else "mp3"
if provider == "fish":
    url = os.environ.get("FISH_API_BASE", "https://api.fish.audio") + "/v1/tts"
    headers = {"Authorization": "Bearer " + need("FISH_API_KEY"), "Content-Type": "application/json"}
    if os.environ.get("FISH_MODEL"): headers["model"] = os.environ["FISH_MODEL"]
    body = {"text": text, "reference_id": need("FISH_VOICE_ID"), "format": fmt, "normalize": True}
    if fmt == "mp3": body["mp3_bitrate"] = 192
    if abs(speed - 1) > 1e-3: body["prosody"] = {"speed": speed}            # 0.5–2.0
elif provider == "elevenlabs":
    if not 0.7 <= speed <= 1.2: raise SystemExit("ElevenLabs 的 speed 只能在 0.7–1.2")
    of = "wav_44100" if fmt == "wav" else "mp3_44100_128"                   # 更高规格的输出格式按套餐开放；默认用 mp3
    url = f'{os.environ.get("ELEVENLABS_API_BASE", "https://api.elevenlabs.io")}/v1/text-to-speech/{need("ELEVENLABS_VOICE_ID")}?output_format={of}'
    headers = {"xi-api-key": need("ELEVENLABS_API_KEY"), "Content-Type": "application/json"}
    body = {"text": text, "model_id": os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")}
    if abs(speed - 1) > 1e-3: body["voice_settings"] = {"speed": speed}
else:
    raise SystemExit(__doc__)
for attempt in range(4):
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST"), timeout=300).read()
        if len(data) < 1000: raise SystemExit(f"返回的音频只有 {len(data)} 字节，当作失败")
        tmp = out + ".part"; open(tmp, "wb").write(data); os.replace(tmp, out); sys.exit(0)
    except urllib.error.HTTPError as e:
        msg = e.read()[:300].decode("utf-8", "replace")
        if e.code in (429, 500, 502, 503, 504) and attempt < 3: time.sleep(5*(attempt+1)); continue     # 限流/服务端错误：退避重试
        raise SystemExit(f"{provider} HTTP {e.code}: {msg}")                 # 401/402/403 是密钥、余额或权限问题，重试没用
    except urllib.error.URLError as e:
        if attempt < 3: time.sleep(5*(attempt+1)); continue
        raise SystemExit(f"{provider} 连接失败: {e.reason}")
