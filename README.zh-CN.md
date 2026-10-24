# Joekam Video

面向 AI Agent 的开源视频创作技能：从创作目标、参考视频或现有素材，推进到可审看、可导出、可继续编辑的视频项目。

[English](README.md) · [技能入口](SKILL.md) · [MIT 许可证](LICENSE)

技能覆盖参考片拆解、脚本、素材指导、剪辑、字幕、声音、动态图形和交付，提供 **7 类视频形式** 与 **12 个专项制作模块**，可以按作品需要组合。

## 安装

使用 Node.js 22.20 或更新版本运行技能安装器：

```bash
npx skills add hopeoverseas/joekam-video --skill joekam-video -g
```

根据提示选择使用的 Agent。`-g` 表示全局安装，省略后为当前项目安装。安装器选项以 [vercel-labs/skills 官方文档](https://github.com/vercel-labs/skills)为准。

手动安装时，将 `SKILL.md`、`agents/`、`references/` 和 `LICENSE` 一起放入 Agent 技能目录中的 `joekam-video/` 文件夹。

## 使用

在 Codex 中通过 `$joekam-video` 调用，并提供制作目标、参考视频，以及已有的产品资料、视频、图片、录音或工程文件。

参考片改编：

```text
$joekam-video 拆解这个参考视频的开头、脚本、镜头、字幕、声音和节奏，
保留适合我的表达结构，替换成我的产品与文案，制作可编辑版本。
```

现有素材制作：

```text
$joekam-video 用这些产品图片和中文配音制作竖屏演示视频，
加入字幕与补充画面，优先复用现有素材。
```

修改已有项目：

```text
$joekam-video 修改这个项目的开场、榜单顺序和配乐，
保留已经确认的镜头，导出新版本。
```

Agent 根据实际工具完成目标整理、分镜、素材准备、合成与审看。交付按委托确定，可以包含成片、可编辑工程、脚本、分镜、字幕文件和素材清单。

## 视频形式

| 形式 | 适合的内容 |
| --- | --- |
| [口播 / UGC](references/formats/talking-head.md) | 人物讲述、产品推荐、测评、经验分享 |
| [短剧](references/formats/short-drama.md) | 人物冲突、剧情变化、情景广告、故事 |
| [双人播客](references/formats/two-person-podcast.md) | 双人对谈、观点交锋、访谈片段 |
| [街访](references/formats/street-interview.md) | 现场问答、采访、反应和答案揭晓 |
| [榜单 / 清单](references/formats/ranking-listicle.md) | 产品排名、横向对比、盘点、逐条说明 |
| [出镜讲解](references/formats/presenter-led-explainer.md) | 主持人配合产品、屏幕、数据或图形讲解 |
| [旁白演示](references/formats/narration-led-demo.md) | 配音结合产品特写、录屏、操作过程或动画 |

参考视频改编可以使用以上任意形式。技能指导制作与表达，不保证播放量、传播效果或生成表演与原片完全一致。

## 专项制作模块

| 模块 | 模块 |
| --- | --- |
| [图像指导](references/craft/image-direction.md) | [声音指导](references/craft/voice-direction.md) |
| [声音与表演](references/craft/voice-and-performance.md) | [视频指导](references/craft/video-direction.md) |
| [参考与连续性](references/craft/reference-continuity.md) | [B-roll 补充画面](references/craft/b-roll.md) |
| [屏幕演示](references/craft/screen-demonstrations.md) | [字幕](references/craft/captions.md) |
| [字幕跟踪](references/craft/caption-tracking.md) | [声音与混音](references/craft/sound-mix.md) |
| [图形构图](references/craft/graphic-compositions.md) | [动态图形](references/craft/motion-graphics.md) |

[制作方法](references/production.md)介绍项目组织、分镜、时间安排、修改和交付。[工具使用](references/tools.md)提供素材检测与本地合成示例。

## 是否需要视频 API

本仓库提供技能说明与制作指南，实际编辑和生成通过 Agent 能访问的工具完成。

- **现有视频、图片或录屏：**可以用 FFmpeg、ffprobe 或已有剪辑软件在本地处理。
- **榜单和图形动画：**可以通过绘制和本地渲染完成，不强制接视频 API。
- **新生成的人物、镜头或声音：**使用你选择的生成服务，也可以使用具备条件的本地模型。
- **字幕与导出：**先检查工具实际能力。烧录字幕需要相应滤镜；也可以按交付要求使用字幕轨或外挂字幕。

技能本身没有订阅费和按次渲染费。Agent、生成服务、算力与外部素材可能另有费用和条款。沿用用户已选择的账号、制作范围和预算，不把密钥写进共享文件。

## 贡献与检查

修改指南见 [CONTRIBUTING.md](CONTRIBUTING.md)。使用 Python 3 运行结构检查，无额外依赖：

```bash
python3 tools/check_skill.py
```

检查覆盖技能标识、调用提示、本地文档链接和许可证文件。实际成片仍需播放检查画面、字幕与声音。

## 开源与商用

采用 [MIT 许可证](LICENSE)，允许使用、修改、分发、商用和制作闭源衍生版本。分发时须保留版权与许可声明。第三方工具、服务和素材按各自条款使用。

由 [gannew1985](https://github.com/gannew1985) 在 [HopeOverseas](https://github.com/hopeoverseas) 维护。
