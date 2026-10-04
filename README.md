# narrated-documentary-video

A Claude skill for making narration-driven explainer / documentary videos (1920×1080, 7–10 minutes): history, architecture, art, science, biography, product teardowns.

一个 Claude Skill：把一篇口播稿做成 7–10 分钟的讲解类视频。方法是从几十期实际制作里总结出来的，每条规则背后都有一次返工。

核心思路：**配音是时间轴的唯一来源**。镜头切点、卡片、动画提示点、字幕、配乐换段，全部锚定在口播里某句话第一个字的发音时刻上。

## 内容

| | |
|---|---|
| [SKILL.md](SKILL.md) | 入口：流程、目录约定、红线、质量标准 |
| [references/script.md](references/script.md) | 写稿：查证、结构、叙述姿态、为 TTS 写 |
| [references/voice.md](references/voice.md) | 配音：分段合成、两层验收、读音修正、停顿、逐字对齐 |
| [references/voice-cloning.md](references/voice-cloning.md) | 音色克隆：Fish Audio / ElevenLabs 的注册、克隆、密钥配置、接口用法 |
| [references/assets.md](references/assets.md) | 找素材：来源、候选池、目检、授权 |
| [references/shots-and-camera.md](references/shots-and-camera.md) | 分镜与运镜：锚点、镜头类型、叠层、节奏 |
| [references/animation.md](references/animation.md) | 动画：逐帧确定的 HTML / three.js，画风、建模、场景设计 |
| [references/aerial-and-maps.md](references/aerial-and-maps.md) | 航拍（Google Earth Studio）与地形飞越 |
| [references/finish.md](references/finish.md) | 合成：字幕、配乐、环境声、响度 |
| [references/qa-review.md](references/qa-review.md) | 审片：逐镜样张、自动扫描、独立复核 |
| [references/cover-publish.md](references/cover-publish.md) | 封面与发布闸门 |
| [references/ops.md](references/ops.md) | 并行、排队、长任务、清理、密钥 |
| `scripts/` | 可运行的参考实现（渲染引擎、配音工具、素材工具、动画截图） |
| `templates/anim/` | 动画页面模板（三维模型、年表、高度对比、聚光巡游、胶卷、地形飞越） |
| `templates/episode/` | 一期的配置文件示例和镜头表生成器示例 |

## 安装

```bash
git clone https://github.com/<you>/narrated-documentary-video ~/.claude/skills/narrated-documentary-video
pip install numpy opencv-python pillow playwright jieba && playwright install chromium
# 另需：ffmpeg；openai-whisper（逐字对齐）；whisper.cpp + ggml 模型（配音验收）
```

## 不包含什么

- **TTS 账号和音色**：`tts_segments.py` 通过 `TTS_CMD` 命令模板调用配音程序；`tts_cloud.py` 是 Fish Audio / ElevenLabs 的接入脚本（密钥和音色 ID 用你自己的，只从环境变量读）。声学验收（音色相似度、音高、循环检测）依赖具体音色的参考数据，这里只给判据（voice.md），内容验收（口头语、截断、数字）有实现。
- **发布脚本**：各平台接口不同；cover-publish.md 给的是闸门设计。
- **任何素材、成片、密钥**。

脚本在 macOS 上开发和测试；字体与编码器按平台自动选择，可用环境变量覆盖（`scripts/fonts.py`、`RENDER_X264=1`）。渲染出的卡片和字幕按中文排版设计。

## License

MIT
