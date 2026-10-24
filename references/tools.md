# 工具使用

读取本页来检测素材、使用本地工具合成或决定外部服务如何接入。
命令示例中的文件名需替换为当前项目的实际路径。

## 检查环境与素材

先确认工具是否已经安装，使用其实际版本支持的选项：

```bash
ffmpeg -version
ffprobe -version
ffprobe -v error -show_format -show_streams -of json input.mp4
```

记录时长、宽高、旋转信息、视频帧率、像素格式、音轨与采样率。旋转后的显示比例可能不同于
编码宽高；处理手机素材时应以实际显示方向为准。若缺工具，按任务已经授权的环境准备范围处理。

需要抽帧时指定具体时间；阅读长视频时按段取样，发现关键变化后再细看该片段。

```bash
ffmpeg -n -ss 2 -i input.mp4 -frames:v 1 frame-002.png
```

## 统一画幅

按目标选择留边或裁切，保留人物、产品和文字的重要区域。以下示例将画面完整放入竖屏：

```bash
ffmpeg -n -i input.mp4 -vf "scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1" -c:v libx264 -pix_fmt yuv420p -c:a aac output.mp4
```

需要铺满时，先放大到覆盖目标，再按构图裁切。不能以裁切方式隐藏用户要求保留的信息。
拼接多个片段前统一画幅、像素比例、帧率和音频规格。

## 静态图片与字幕

静态图可以作为明确时长的镜头。以下仅演示五秒图片片段：

```bash
ffmpeg -n -loop 1 -i input.png -t 5 -r 30 -vf "scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1" -c:v libx264 -pix_fmt yuv420p -an image-shot.mp4
```

字幕先保存为 SRT 或 ASS，再决定烧录还是单独交付。烧录前检查 `ffmpeg -hide_banner -filters`
的实际列表包含 `subtitles`，并确认字体支持所用语言。复杂路径需要按滤镜语法转义，
也可以在工作目录使用简单的字幕文件名。

```bash
ffmpeg -n -i input.mp4 -vf "subtitles=filename=captions.srt" -c:v libx264 -pix_fmt yuv420p -c:a copy captioned.mp4
```

如果当前安装不包含该滤镜，可以交付外挂字幕，或将字幕封装为 MP4 的可选字幕轨：

```bash
ffmpeg -n -i input.mp4 -i captions.srt -map 0:v:0 -map "0:a?" -map 1:0 -c:v copy -c:a copy -c:s mov_text caption-track.mp4
```

字幕轨的显示依赖播放器，需要在实际交付环境中检查。用户要求固定在画面上的字幕时，
仍需使用支持烧录的工具完成相应输出。

## 混音

先测听人声，再加入音乐与音效。此示例要求输入视频已有声音，循环配乐直到片段结束：

```bash
ffmpeg -n -i input.mp4 -stream_loop -1 -i music.wav -filter_complex "[0:a]aresample=48000[voice];[1:a]volume=0.12[music];[voice][music]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -shortest mixed.mp4
```

音乐音量是起点，需要按素材调整。没有原声时不要引用不存在的音轨；改用实际存在的配音、音乐或静音。

## 图形、录屏与生成服务

动态图形可由剪辑软件、可用的动画工具或逐帧生成画面实现，再合成为普通视频。
先确认画面、时长和透明通道的需要，避免依赖当前环境不存在的插件或私有格式。

录屏使用能够读取真实界面和实际交互的浏览器或桌面工具。先准备干净的演示状态，再录制目标操作；
交互录制、静态截图和作者绘制的示意图分别按其实际用途使用。

调用生成服务前检查准确的输入协议、参考素材、输出类型、长度限制与费用。模型名称相似不代表
接口或能力相同。下载完成的图片、视频和音频进入素材清单，后续合成使用实际文件。

本地合成完成后，用 ffprobe 检查文件，再实际播放画面和声音。命令使用 `-n` 避免覆盖已有输出；
需要替换旧版本时使用新的文件名，或在明确选择覆盖后单独执行。
