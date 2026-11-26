# Noiz 配音、音效与歌曲

用户选用 Noiz 且已有可用账号时，可用技能附带的 Python 客户端准备配音、声音克隆、音效、带人声的歌曲和翻唱。
这是可选的外部服务：只有用户授权账号、素材和费用后才提交；没有密钥也能离线预览请求。
服务能力与价格可能变化，使用前核对[音效说明](https://github.com/NoizAI/skills/tree/main/skills/sound-fx)
和[歌曲与翻唱说明](https://github.com/NoizAI/skills/tree/main/skills/text-to-music)，并确认素材使用权。
配音和声音克隆的输入、音频返回格式及账号功能，以服务商的[语音合成](https://docs.noiz.ai/api-documentation/text-to-speech)
和[声音接口](https://docs.noiz.ai/api-documentation/voices)文档为准。

客户端使用服务商的直连接口：音效同步返回结果地址，歌曲和翻唱返回任务编号，需另行查询。
歌曲模式需要歌词或歌词主题，不是纯器乐模式。`noiz_audio.py` 使用公开 HTTPS 地址作为歌曲参考或翻唱素材，
不自动上传本地歌曲素材，也不自动识别歌词；配音与声音克隆由另一个客户端 `noiz_voice.py` 处理。

## 配音和授权声音克隆

先取得说话人对声音克隆及具体用途的明确授权；提交前再确认用户允许上传样本以及外部服务费用。
服务会保存克隆出的声音 ID，音频样本和请求记录可能涉及隐私，应按项目要求保存。
使用现有声音 ID 生成配音时，`speech` 请求中的文字最长 5000 字符；可选 `speed`、`target_lang` 和 `trim_silence`：

~~~json
{
  "kind": "speech",
  "text": "欢迎了解我们的产品。",
  "voice_id": "your-voice-id",
  "output_format": "wav",
  "speed": 1.0
}
~~~

如需克隆声音，将本人的授权录音放在请求文件同一目录，或把 `audio_path` 改成实际路径：

~~~json
{
  "kind": "clone",
  "audio_path": "voice-sample.wav",
  "display_name": "Authorized voice",
  "consent": true
}
~~~

音频样本支持 WAV、MP3、M4A，非空且不超过 25 MiB；也可用 `voice_url` 代替 `audio_path`，
提供服务可访问的 HTTPS 地址。`audio_path` 和 `voice_url` 只能选一个。地址及其签名可能使其他人访问素材。
克隆请求可选 `denoise` 和 `language`。布尔字段使用 JSON 的 `true` 或 `false`。

从技能目录执行；`voices` 会连接服务，`preview` 只检查请求和本地样本，不上传或生成：

~~~bash
python3 scripts/noiz_voice.py voices --type built-in
python3 scripts/noiz_voice.py preview --request /path/to/clone.json
python3 scripts/noiz_voice.py clone --request /path/to/clone.json --task-file /path/to/clone-task.json
python3 scripts/noiz_voice.py preview --request /path/to/speech.json
python3 scripts/noiz_voice.py speak --request /path/to/speech.json --task-file /path/to/speech-task.json --output /path/to/speech.wav
~~~

克隆成功后，从结果或任务记录取出 `voice_id`，填入配音请求；也可从账号提供的内置或已有声音中选择。
每次提交必须指定尚不存在的任务记录；配音直接返回音频，输出文件不会覆盖已有文件。
发生超时或任务记录仍是 `submission_unconfirmed` 时，先检查服务控制台、费用和输出文件，再决定是否重试。
代码使用环境变量 `NOIZ_API_KEY`，不要把密钥、口播文字或声音样本放入共享的任务记录。

## 准备音效和歌曲请求

把下列任一 JSON 对象保存为项目中的 `request.json`，按实际画面和素材修改。
音效时长可选，填写时使用 1 至 30 的整数秒；格式可以是 `wav` 或 `mp3`：

~~~json
{
  "kind": "effect",
  "prompt": "A small glass bottle lands gently on a wooden table, close and dry.",
  "duration": 3,
  "output_format": "wav"
}
~~~

带人声的歌曲需要风格描述，以及 `lyrics` 或 `lyrics_prompt` 其中一项：

~~~json
{
  "kind": "music",
  "prompt": "Warm acoustic pop for a short product introduction, gentle tempo.",
  "lyrics_prompt": "A brief, cheerful song about a morning routine.",
  "title": "Morning routine"
}
~~~

翻唱需要用户授权的源音频地址、歌词，以及 `music_description` 或 `style`：

~~~json
{
  "kind": "cover",
  "source_audio_url": "https://example.com/authorized-source.mp3",
  "lyrics": "[Verse]\nA new day begins",
  "music_description": "A gentle acoustic arrangement with a clear vocal.",
  "melody_adherence": "main_melody"
}
~~~

歌曲可选 `title`、`tags`、`negative_tags`、`vocal_gender` 和 `reference_audio_url`；翻唱可选
`title` 和 `vocal_gender`。`vocal_gender` 可填 `Male` 或 `Female`。
示例地址只是占位符。公开地址及其签名可能让他人访问素材，上传或提供前先确认用户允许。
预览不会检查素材实际可访问性、账号权限或价格。

## 预览、提交和取回

从技能目录执行，并将路径替换为项目中的实际路径：

~~~bash
python3 scripts/noiz_audio.py preview --request /path/to/request.json
~~~

预览只检查结构，不联网、不生成音频。用户授权后，通过安全环境配置提供 `NOIZ_API_KEY`，
不要将密钥写进请求、任务记录、命令参数或交付材料：

~~~bash
python3 scripts/noiz_audio.py submit --request /path/to/request.json --task-file /path/to/noiz-task.json
python3 scripts/noiz_audio.py status --task-file /path/to/noiz-task.json
python3 scripts/noiz_audio.py download --task-file /path/to/noiz-task.json --variant 1 --output /path/to/result.wav
~~~

任务记录必须是尚不存在的新文件，下载不会覆盖已有文件。歌曲和翻唱通常返回多个版本，
先查询状态，再按结果序号下载；歌曲和翻唱的输出扩展名通常使用 `.mp3`。
下载地址可能过期；任务记录可能包含临时下载地址，应按素材敏感程度保护。

提交可能收费。脚本不会自动重试，也不会自动轮询；超时或记录显示 `submission_unconfirmed` 时，
先到服务控制台核对任务与费用，再决定是否重新提交。下载不会把服务密钥发送给存储地址；
若地址发生跳转，脚本会停止，由用户选择授权的下载工具。取回后用播放器或 `ffprobe` 检查音频，
再与对白、画面按时间对齐并混音。
