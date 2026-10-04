# 音色克隆：Fish Audio 或 ElevenLabs

讲解视频最好用**自己的声音**：先克隆一个音色，之后每一期都用它念。推荐这两家，都支持克隆和中文，都是「上传一段录音 → 得到一个音色 ID → 合成时带上这个 ID」。

接口信息核对于 2026-10，以官方文档为准（文末有链接）。价格、套餐、模型更新很快，用之前现查。

## 怎么选

| | Fish Audio | ElevenLabs |
|---|---|---|
| 克隆需要的录音 | 10 秒起；10–30 秒干净录音效果最好，可传多段 | 即时克隆：1–2 分钟干净录音（超过 3 分钟提升很小）；专业克隆：30 分钟以上，建议 1–3 小时 |
| 克隆的档位 | 一种（即时） | 即时克隆；专业克隆（Creator 及以上套餐，需验证是本人声音）。各档对套餐的要求以官网为准 |
| 语速参数 | `prosody.speed`，0.5–2.0 | `voice_settings.speed`，0.7–1.2 |
| 鉴权 | 请求头 `Authorization: Bearer <key>` | 请求头 `xi-api-key: <key>` |
| 模型选择 | 请求头 `model`（如 `s1`、`s2-pro`、`s2.1-pro`） | 请求体 `model_id`（默认 `eleven_multilingual_v2`） |

选哪家用耳朵定：同一段稿子两家各念一遍，听哪个更像你在讲故事。同一家的不同模型差别也很大，新模型不一定更适合你的声音——逐个听。定下来之后，音色 ID 和模型就是不变量（见 voice.md 第 1 节）。

只克隆自己的声音，或者有对方明确授权的声音。

## 录参考音频

- 安静的房间，离麦克风近一点，没有回声、背景音乐、别人的声音。
- 用你做视频时想要的语气来录：像讲故事那样，有停顿、有起伏。克隆会连语气一起学，平着念出来的参考，合成出来也是平的。
- 录完整的一段话，而不是零散的句子。Fish Audio 建议 2–3 段、每段 15–20 秒。
- 参考音频本身是敏感资料（别人拿到就能克隆你的声音），不要放进公开仓库。

## 密钥怎么放

key 创建出来就立刻存好。**密钥和音色 ID 都放环境变量，不写进脚本、命令行、仓库、日志。**

```bash
mkdir -p ~/.config/tts && chmod 700 ~/.config/tts
cat > ~/.config/tts/env <<'EOF'
FISH_API_KEY=在这里粘贴
FISH_VOICE_ID=在这里粘贴
ELEVENLABS_API_KEY=在这里粘贴
ELEVENLABS_VOICE_ID=在这里粘贴
EOF
chmod 600 ~/.config/tts/env

set -a; . ~/.config/tts/env; set +a      # 每个要用的 shell 里加载一次
```

- 能设权限和额度的就设：ElevenLabs 的 key 可以限制权限范围、每月字符上限和来源 IP；Fish Audio 的 key 可以设过期时间。
- 怀疑泄漏（贴进过聊天、日志、截图、提交记录）就立刻在后台作废重建。排查时按 key 的**值**搜，而不是按变量名搜。
- 推送代码前跑 `bash scripts/scan_secrets.sh .`。

## Fish Audio

1. 注册 fish.audio，在 <https://fish.audio/app/api-keys> 创建 API key。
2. 克隆音色：网页上「创建声音」上传录音最省事；也可以走接口——

   ```bash
   curl -X POST https://api.fish.audio/model \
     -H "Authorization: Bearer $FISH_API_KEY" \
     -F type=tts -F train_mode=fast -F visibility=private \
     -F title="my-voice" -F voices=@sample1.wav -F voices=@sample2.wav
   # 返回的 JSON 里 _id 就是音色 ID → 写进 FISH_VOICE_ID
   ```

   `visibility` 保持 `private`。`voices` 可传 1–20 个文件；`texts` 可选，是各段录音对应的文字。
3. 合成：

   ```bash
   curl -X POST https://api.fish.audio/v1/tts \
     -H "Authorization: Bearer $FISH_API_KEY" -H "Content-Type: application/json" -H "model: s1" \
     -d "{\"text\": \"要念的话\", \"reference_id\": \"$FISH_VOICE_ID\", \"format\": \"mp3\", \"mp3_bitrate\": 192, \"prosody\": {\"speed\": 0.95}}" \
     -o out.mp3
   ```

   常用字段：`format`（`mp3`/`wav`/`pcm`/`opus`）、`mp3_bitrate`（64/128/192）、`prosody.speed`（0.5–2.0）、`temperature` 和 `top_p`（0–1，默认 0.7）、`normalize`（文本规范化，默认开）、`chunk_length`（100–300）。响应体直接是音频。

## ElevenLabs

1. 注册 elevenlabs.io，在后台的 API Keys 页面创建 key。
2. 克隆音色：网页上 Voices →「Instant Voice Clone」上传录音；或走接口——

   ```bash
   curl -X POST https://api.elevenlabs.io/v1/voices/add \
     -H "xi-api-key: $ELEVENLABS_API_KEY" \
     -F name="my-voice" -F files=@sample.wav -F remove_background_noise=false
   # 返回的 voice_id → 写进 ELEVENLABS_VOICE_ID
   ```

   想要更像本人的效果用专业克隆（网页上操作，要更多录音和本人验证，训练需要时间）。
3. 合成：

   ```bash
   curl -X POST "https://api.elevenlabs.io/v1/text-to-speech/$ELEVENLABS_VOICE_ID?output_format=mp3_44100_128" \
     -H "xi-api-key: $ELEVENLABS_API_KEY" -H "Content-Type: application/json" \
     -d '{"text": "要念的话", "model_id": "eleven_multilingual_v2", "voice_settings": {"speed": 0.95}}' \
     -o out.mp3
   ```

   常用字段：`model_id`；`voice_settings` 里的 `stability`（默认 0.5，越高越稳、越低越有起伏）、`similarity_boost`（默认 0.75）、`style`、`speed`（0.7–1.2）；`language_code`；`seed`（固定后同样输入尽量得到同样结果）；`previous_text` / `next_text`（把前后文传进去，分段合成时段与段的语气衔接更自然）。`output_format` 在查询参数里，默认 `mp3_44100_128`。响应体直接是音频。

## 接到本技能的配音流程里

`scripts/tts_cloud.py` 把上面两个合成接口包成了 `tts_segments.py` 要的命令形式：

```bash
set -a; . ~/.config/tts/env; set +a
export EP_DIR=project/episodes/<EP> TTS_OUT_EXT=mp3
export TTS_CMD='python3 scripts/tts_cloud.py fish --speed 0.95 --in {text_file} --out {out}'          # 或 elevenlabs
python3 scripts/tts_segments.py && python3 scripts/check_segments.py --reroll 3
```

- 密钥只从环境变量读；出错时只打印状态码和服务端的说明，不打印请求头。
- 429 和 5xx 会退避重试；401/402/403 是密钥、余额或权限问题，重试没用，直接报错。
- 这个包装脚本只对照官方文档写成，并用本地模拟服务验证过请求的构造（地址、请求头、请求体）；**没有用真实账号跑过**。第一次用先拿一句话试，听一下结果。

分段合成的注意事项（语速对所有重掷生效、间隔号、多音字替换、验收）见 voice.md。

## 出处

- Fish Audio 文本转语音接口：<https://docs.fish.audio/api-reference/endpoint/openapi-v1/text-to-speech>
- Fish Audio 创建音色模型：<https://docs.fish.audio/api-reference/endpoint/model/create-model>
- Fish Audio 获取 API key：<https://docs.fish.audio/developer-guide/getting-started/api-key>
- Fish Audio 克隆最佳实践：<https://docs.fish.audio/developer-guide/best-practices/voice-cloning>
- ElevenLabs 文本转语音接口：<https://elevenlabs.io/docs/api-reference/text-to-speech/convert>
- ElevenLabs 创建即时克隆：<https://elevenlabs.io/docs/api-reference/voices/ivc/create>
- ElevenLabs 即时克隆说明：<https://elevenlabs.io/docs/eleven-creative/voices/voice-cloning/instant-voice-cloning>
- ElevenLabs 专业克隆说明：<https://elevenlabs.io/docs/eleven-creative/voices/voice-cloning/professional-voice-cloning>
- ElevenLabs API key 管理：<https://elevenlabs.io/docs/overview/administration/workspaces/api-keys>
