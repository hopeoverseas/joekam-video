---
name: joekam-video
description: "Joekam 独立视频创作技能。用于参考视频改编、口播、短剧、播客、街访、榜单和产品演示，完成脚本、素材、字幕、声音、动画与可编辑视频交付。"
license: "MIT"
metadata:
  author: "joekam"
  version: "2.0.0"
  repository: "https://github.com/hopeoverseas/joekam-video"
---

# Joekam Video

使用 `$joekam-video`，将创意、参考片和已有素材制作成可以审看、导出和继续修改的视频。
根据当前环境选择视频生成服务、剪辑软件或本地媒体工具，不依赖固定品牌的制作引擎。

## 工作方式

- 从用户已有信息形成制作目标：受众、用途、核心表达、风格和交付规格。只有会影响作品的关键事实缺失时才补充澄清。
- 有参考片时先看完整段落，再定位开场、叙事、镜头、字幕、图形、声音与节奏。将观察和改编方案分别记录。
- 先选择适用的视频形式和专项指南，按需组合。简单修改只读取相关部分。
- 用脚本和分镜落实内容，再准备素材与声音。并行准备互不依赖的部分，但依赖角色参考的镜头应等参考确定后生成。
- 先做有代表性的短段落确认风格，再完成其余部分。用户已给出的制作规格和选择可直接沿用。
- 每次修改保留仍可用的素材和项目文件。交付实际产物，并用实际播放和抽帧检查结果。

项目组织、时间关系和交付检查见[制作方法](references/production.md)。
素材检测、本地合成、字幕和混音命令见[工具使用](references/tools.md)。

## 视频形式

| 内容形式 | 指南 |
| --- | --- |
| 对镜头讲述、UGC、测评口播 | [口播](references/formats/talking-head.md) |
| 人物冲突、情节推进、短剧 | [短剧](references/formats/short-drama.md) |
| 双人对谈、播客、访谈片段 | [双人播客](references/formats/two-person-podcast.md) |
| 街头问答、现场反应、揭晓 | [街访](references/formats/street-interview.md) |
| 排名、清单、对比和逐项说明 | [榜单](references/formats/ranking-listicle.md) |
| 主持人配合图形或实物讲解 | [出镜讲解](references/formats/presenter-led-explainer.md) |
| 旁白组织产品、操作、屏幕或动画 | [旁白演示](references/formats/narration-led-demo.md) |

## 专项制作

| 要解决的问题 | 指南 |
| --- | --- |
| 人物、产品、场景与图片提示词 | [图像指导](references/craft/image-direction.md) |
| 声线、情绪、口音与试音 | [声音指导](references/craft/voice-direction.md) |
| 配音、台词表演与声音连续性 | [声音与表演](references/craft/voice-and-performance.md) |
| 动作、运镜、镜头变化与视频生成 | [视频指导](references/craft/video-direction.md) |
| 人物、服装、道具和场景的一致性 | [参考与连续性](references/craft/reference-continuity.md) |
| 补充画面与解释性镜头 | [B-roll](references/craft/b-roll.md) |
| 网站、App、软件或操作录屏 | [屏幕演示](references/craft/screen-demonstrations.md) |
| 转写、断句、排版与字幕导出 | [字幕](references/craft/captions.md) |
| 字幕跟随说话人物的位置 | [字幕跟踪](references/craft/caption-tracking.md) |
| 人声、音乐、音效与混音 | [声音与混音](references/craft/sound-mix.md) |
| 画面布局、图形层次与文字 | [图形构图](references/craft/graphic-compositions.md) |
| 进出场、转场和动态图形 | [动态图形](references/craft/motion-graphics.md) |

## 工具与执行

使用实际存在、已经授权且支持任务所需能力的工具。先检查本地环境和可用连接，再决定实现方法。
图片、视频、配音和剪辑可以采用不同工具，素材用普通文件与明确的时间信息衔接。

采用本地工具时，使用真实的 FFmpeg、ffprobe 或剪辑软件接口。采用生成服务时，以该服务的
实际文档确认参考图、时长、尺寸、声音等参数；任务提交后保留任务编号和结果文件。

沿用用户已经选择的账号与预算，估算剩余生成工作，复用已有合格素材。新的付费范围或收费账号
需要用户决定。凭据通过工具的安全配置管理，不写进脚本、分镜或交付文件。

## 交付

按本次委托交付成片、工程或修改后的素材。完整视频通常还需要脚本、分镜、字幕文件与素材清单，
以便后续改文案、替换产品和生成不同版本。具体交付项随任务确定。

用播放器或能读取媒体的工具核对实际导出：画面比例、字幕可读性、镜头衔接、音画同步和声音。
检查失败时修正对应素材或时间安排，再导出新版本。仅有文字方案时说明它是方案，不能标为已完成视频。

```text
$joekam-video 分析这个参考片，改成我的产品介绍，沿用现有账号与素材。
$joekam-video 用这些产品图片和中文配音制作竖屏视频，加入字幕与补充画面。
$joekam-video 修改现有项目的开场、榜单顺序和配乐，保留其他已确认内容。
```
