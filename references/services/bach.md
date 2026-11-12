# Bach 1.0 Pro 视频生成

用户选择 Bach 1.0 Pro 且已有可用账号时，可用技能附带的 Python 客户端调用服务方的接口。
这是可选的外部生成服务：模型在服务方运行，接口可用性、素材处理和费用以该账号的服务条款为准。
只有用户已经授权账号和预算时才提交请求；没有账号或密钥时可以继续做分镜与请求预览。

实现依据服务方的[模型概览](https://www.bach.art/api/docs/bach_1_0_pro)、
[创建任务](https://www.bach.art/api/docs/create_task)和[查询任务](https://www.bach.art/api/docs/query_task)。
参考素材字段另见[视频生成接口](https://www.bach.art/docs/videos-bach/v2/bach_video_generation)。
这些接口可能变化，使用前核对当前文档和账号权限；不要把其他平台对同名模型的能力当成直连接口的承诺。

## 选择输入方式

- 文字生成：input.task 为 t2v，由提示词描述主体、动作和镜头。
- 首尾帧生成：input.task 为 i2v，提供首帧、尾帧或两者；用于控制镜头的起点、终点及衔接。
- 多参考生成：input.task 为 r2v，按服务格式提供图片、视频或音频参考，并在提示词中说明各自作用。

模式决定服务读取哪些字段。t2v 不使用帧或参考素材；i2v 的画幅由服务按 auto 处理。
r2v 至少需要图片或视频参考，不能只提供音频；图片、视频、音频分别最多 9、3、3 个，合计最多 12 个。
参考视频与音频的时长、格式、大小和计费，以及不同平台对这些输入的限制，以实际服务文档为准。
参考素材需使用服务方能够访问的 HTTP(S) 地址；只有用户允许将素材交给该服务时才提供地址，
并确保地址在服务读取期间有效。任务文件和返回的下载地址也应按素材敏感程度妥善保存。

## 准备与预览

以下示例是请求文件内容，将其保存到项目目录中的 request.json，并根据分镜修改：

~~~json
{
  "model_name": "Bach-1.0-Pro",
  "input": {
    "task": "t2v",
    "prompt": "一只透明水杯在明亮的厨房台面上缓慢转动，固定机位，柔和晨光。",
    "duration": 5,
    "resolution": "1080p",
    "aspect_ratio": "9:16",
    "generate_audio": false
  }
}
~~~

使用首尾帧时，可将上例的 input 对象替换为以下内容；示例地址必须换成实际可访问的素材：

~~~json
{
  "task": "i2v",
  "prompt": "镜头从产品正面平稳移动到侧面，保持产品外观一致。",
  "image_url": "https://example.com/start.png",
  "end_image_url": "https://example.com/end.png",
  "duration": 5
}
~~~

多参考模式可以分别说明图片、动作和声音参考的作用，并为参考视频或音频指定起始时间：

~~~json
{
  "task": "r2v",
  "prompt": "保持 @Image1 的产品外观，参考 @Video1 的镜头运动和 @Audio1 的声音氛围。",
  "duration": 5,
  "generate_audio": true,
  "reference_inputs": [
    {"type": "image", "url": "https://example.com/product.png"},
    {"type": "video", "url": "https://example.com/camera.mp4", "start_time": 1.5},
    {"type": "audio", "url": "https://example.com/ambience.mp3", "start_time": 0.5}
  ]
}
~~~

`start_time` 是可选的起始时间，以秒为单位且不能小于零；省略时不指定偏移。
素材的实际时长和适用限制、费用以服务方规则为准，预览不会检查素材本身。

从技能目录运行下面的命令；如果当前目录不同，请使用技能目录中脚本的绝对路径。
请求文件和任务记录路径替换为项目中的实际路径。

~~~bash
python3 scripts/bach_video.py preview --request /path/to/request.json
~~~

预览只检查请求结构并显示模式、时长、分辨率与参考数量，不联网、不生成视频。
它不能验证 URL 的可访问性、素材实际编解码、尺寸、时长、账号权限或价格。
服务当前允许 5 至 16 秒的视频和 1080p、4k 两种分辨率；计费前核对服务方最新规则，
包括生成时长取整和参考视频可能产生的费用。

## 提交与查询

通过安全环境配置提供 BACH_API_KEY，不要把密钥放入请求文件、任务记录或共享素材。
在用户授权的范围内运行：

~~~bash
python3 scripts/bach_video.py submit --request /path/to/request.json --task-file /path/to/bach-task.json
python3 scripts/bach_video.py status --task-file /path/to/bach-task.json
~~~

提交会产生外部请求并可能收费。任务记录必须是尚不存在的新文件：脚本在发送前创建它，
成功后保存任务编号；不会自动重试。若超时或记录仍显示 submission_unconfirmed，
先到服务控制台核对是否已经创建任务与计费，再决定是否重试，避免重复消费。

查询结果中的 data.status 表示任务状态。TASK_SUCCEEDED 时可读取 data.video_url，
下载成片并验证文件后再加入项目素材清单；TASK_FAILED 时检查服务返回的原因。
返回地址可能有时效，使用完成后按项目要求处理。
