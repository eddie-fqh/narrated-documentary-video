---
name: narrated-documentary-video
description: 把一篇口播稿做成 7–10 分钟的讲解类横版视频（历史、建筑、艺术、科普、人物、产品拆解都适用）的完整方法：写稿与事实核查、TTS 配音与验收、找素材与授权、按口播逐字对齐的分镜和运镜、three.js 逐帧确定的三维/示意动画、航拍与地图、字幕配乐合成、逐镜目检、封面与发布闸门。用户要「做一期讲解视频 / 纪录片式短片 / 把稿子配成视频 / 给视频加动画 / 提高画面丰富度」时使用。Narrated explainer / documentary video pipeline: script, voice-over QA, asset sourcing, narration-anchored shot lists, camera moves, deterministic HTML/three.js animation, subtitles, music, review and publishing gates.
---

# 讲解类视频制作（口播驱动）

一期视频 = 一篇口播稿 + 一条配音 + 一张镜头表。**配音是时间轴的唯一来源**：镜头切点、卡片弹出、动画提示点、字幕、配乐换段，全部锚定在「口播里某句话第一个字的发音时刻」上，不靠字数估时间。稿子或配音一改，重跑对齐，画面自动跟上。

成片规格：1920×1080、30 fps、7–10 分钟、80–100 个镜头、烧录字幕、分章配乐加现场环境声。

## 流程

| 步骤 | 做什么 | 产物 | 细则 |
|---|---|---|---|
| 1 写稿 | 查证 → 写成「听」的稿子 → 检查 | `script.txt`、`factcheck.md`、`numbers.json`、`timeline.json` | [references/script.md](references/script.md) |
| 2 配音 | 克隆音色 → 分段合成 → 声学和内容验收 → 插停顿 → 逐字对齐 | `audio/narration.mp3`、`audio/segments/`、`work/chars.json` | [references/voice.md](references/voice.md)、[references/voice-cloning.md](references/voice-cloning.md) |
| 3 找素材 | 候选池 → 样张目检 → 下载 → 记授权 | `img/`、`video/`、`credits.json` | [references/assets.md](references/assets.md) |
| 4 分镜与运镜 | 用生成器脚本排镜头、叠层、转场 | `shots_src.json` → `shots.json` | [references/shots-and-camera.md](references/shots-and-camera.md) |
| 5 动画 | 专属三维/示意动画，逐帧截图成片段 | `anim/*.mp4` | [references/animation.md](references/animation.md) |
| 6 航拍与地图 | Earth Studio 航拍、地形飞越 | `assets/video/` | [references/aerial-and-maps.md](references/aerial-and-maps.md) |
| 7 合成 | 画面 → 字幕、配乐、环境声、响度 | `final.mp4` | [references/finish.md](references/finish.md) |
| 8 审片 | 逐镜样张、独立复核、人听一遍 | 修改清单 | [references/qa-review.md](references/qa-review.md) |
| 9 封面与发布 | 竖版封面、文案、发布闸门 | `cover_*.png`、`publish.json` | [references/cover-publish.md](references/cover-publish.md) |
| 贯穿 | 并行、排队、长任务、清理、密钥 | — | [references/ops.md](references/ops.md) |

第 2 步和第 3、5 步可以并行：配音在跑的时候找素材、建动画模型；配音对齐完成后才能定镜头时间。

## 目录约定

```
project/
  music/                 配乐（<曲名>.mp3）
  assets/video/          各期共用的视频（航拍、库存片段）
  assets/sfx/            环境声
  episodes/<EP>/
    script.txt           口播稿（唯一真源）
    factcheck.md         每条事实 + 出处
    numbers.json  timeline.json  tts_subs.json  music.json  ambience.json  cover.json  publish.json
    audio/               narration.mp3、segments/manifest.json、segments/seg_NNN.flac
    img/  video/  anim/  本期素材与专属动画
    credits.json         每个素材的作者、授权、来源页
    work/                build_shots.py、chars.json、日志、QA 样张（可删可重建）
    shots_src.json       生成器写的镜头表
    shots.json           合并短镜头、挂上时间线条之后，真正拿去渲染的那份
    final.mp4
```

脚本通过 `EP_DIR`（或命令行里的期目录）找到这一期；共用素材在 `PROJECT_DIR`（默认是期目录往上两级）。

## 一期从头到尾

```bash
S=<本技能目录>/scripts; export EP_DIR=project/episodes/<EP>

python3 $S/lint_script.py $EP_DIR/script.txt                      # 1 稿子检查
export TTS_CMD='<你的 TTS 命令> --in {text_file} --out {out}'      # 2 配音（服务无关；Fish Audio / ElevenLabs 克隆音色见 voice-cloning.md）
python3 $S/tts_segments.py && python3 $S/check_segments.py --reroll 3
python3 $S/pace.py && <装了 openai-whisper 的 python> $S/align.py
python3 $S/pool.py search $EP_DIR "检索词" … && python3 $S/pool.py sheet $EP_DIR   # 3 候选图 → 看样张 → pick
python3 $EP_DIR/work/build_shots.py                                # 4 镜头表（模板见 templates/episode/）
python3 $S/render_anims.py $EP_DIR anim/model3d.html               # 5 动画（时长和提示点来自 anim/jobs.json）
cd $EP_DIR && cp shots_src.json shots.json && python3 $S/merge_short.py . 2.4 && python3 $S/add_tlstrip.py .
python3 $S/richness.py .                                           # 画面丰富度自检
bash $S/glock.sh render 2 bash $S/render_ep.sh .                   # 7 渲染 + 合成 + QA 样张
python3 $S/make_cover.py .                                         # 9 封面
```

依赖：`ffmpeg`、Python（`numpy opencv-python pillow playwright jieba`）、`openai-whisper`（对齐）、`whisper.cpp`（验收转写）、可选 `realesrgan-ncnn-vulkan`（小图放大）。字体默认取系统中文字体，可用环境变量换（`scripts/fonts.py`）。

## 红线

这些每一条都对应过一次返工或事故，不是建议。

1. **画面必须是口播正在说的那个对象。** 说谁给谁的像，说哪件作品给哪件作品。同名不同物、父子同名、别处的同类建筑、朝向相反的照片（说「往下看」却给了仰拍），都算错图。错图是最严重的错误。
2. **每一步产出都用眼睛看。** 候选图看样张，动画先出测试帧，标注圈/聚焦框看原图算坐标，渲染后逐镜看 QA 样张。不盲写、不盲信脚本返回成功。
3. **事实先核实再写。** 每个年份、数字、人名、尺寸都有出处记录；拿不准的不写，或明说「据说」。画面里的说明文字同样算事实。
4. **配音过了机器闸门不等于没问题。** 读错字、多音字、吞字是声学指标抓不到的，要转写核对，最终要有人听过。
5. **动画片段要比它所在的镜头长。** 短了会被放慢凑时长，重复帧让运动画面一顿一顿。
6. **一部片子只有一套视觉语言。** 动画沿用正片的底色、字体、卡片样式；「科技感」来自模型和镜头运动，不来自另换一套配色。
7. **授权按源头的写，署名按授权的要求给。** 转传平台上的授权标签可能被改过。带「非商业」限制的素材只能用于非商业频道。航拍和地图的署名要一直留在画面上。
8. **隐私。** 稿子、字幕、叠字里不出现作者的行程、住处、具体日期；不用以清晰路人正脸为主体的照片。
9. **发布是不可逆的对外动作。** 没有人明确说「发」，就只做到成片和文案；发布脚本默认空跑。密钥不进仓库、不进命令行、不进日志。
10. **异常是信号。** 一个操作在不该失败的地方失败了，先想是不是对象搞错了，而不是再试一次。

## 质量标准（一期 9 分钟左右）

- 镜头 80–100 个，平均 ≥5 秒，最短不低于约 2.4 秒；同一张图全片最多两次，两次隔开并换运镜。
- 不同素材 ≥70 个，其中视频 ≥10 段；开场第一镜和片尾用视频，每章至少一段。
- 专属动画 ≥2 段；局部聚焦巡游 ≥3 处；左右对比 ≥2 处；并列拼贴 ≥1 处。
- 大数字卡 ≥3、引文卡 ≥1、指示标注 ≥4；人物首次出现有人名牌，作品有作品牌；每章一张章节卡，全片一条顶部时间线。
- 静态图连放不超过 3 个；问句处画面停住，答案落下的那一刻切镜或弹卡。
- 运镜舒缓：推拉幅度在 5%–10%，默认 0.7 秒叠化，章节用柔和的焦点转移；不用闪白、甩镜、猛推。
- 配音约 4.4 字/秒，句间有真实停顿；每章用一个问题带入。
- 每章一段现场环境声，压在人声下面 15–20 dB。

`scripts/richness.py` 会数这些项目。数字是下限，不是目标——目标是观众每一分钟都有新东西看，而且每个画面都在帮口播把话说清楚。

## 和用户的分工

需要用户决定的事不多，但这几件不能替他定：发不发布、哪一天发；声音（音色、语速）听着对不对；整体画风；涉及付费的生成或授权。其余按本文的默认做，做完说明做了什么选择。

用户说「不够好看」这类笼统的话时，先去找同题材里做得好的片子拆分镜（[references/animation.md](references/animation.md) 末尾有做法），再动手改，不要凭感觉加特效。
