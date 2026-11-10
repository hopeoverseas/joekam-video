# Sume 多模型图片与视频生成

用户选择 Sume 且已有可用账号时，可以使用附带的 Python 客户端调用其图片和视频接口。
这是可选外部服务；模型、账号权限、素材处理和费用以服务方与用户所选工作区为准。
已有素材可继续用本地工具处理，不需要为了使用本技能而开通账号。

接口依据服务方的[模型目录](https://www.sume.com/docs/models)、[图片](https://www.sume.com/docs/images)、
[视频](https://www.sume.com/docs/video)、[素材上传](https://www.sume.com/docs/uploads)及
[任务查询](https://www.sume.com/docs/jobs)文档。模型和接口可能变化，提交前查看当前账号可用的
能力、参数和价格。不同模型对首尾帧、参考图、参考视频、分辨率和时长的支持并不相同。

## 准备账号与选择模型

通过安全环境配置提供 SUME_API_KEY，密钥对应的工作区承担调用费用。不要把密钥写入请求文件、
任务记录或共享素材。下面命令从技能目录运行；在其他目录时使用技能目录下脚本的绝对路径。

~~~bash
python3 scripts/sume_media.py catalog --kind video
python3 scripts/sume_media.py catalog --kind image
~~~

目录查询使用当前密钥访问服务，并返回账号能看到的模型及其信息。选择模型时结合任务、
输入能力与用户预算，不把目录中的模型都当成已授权使用。

## 准备与预览请求

将请求保存为项目中的 JSON 文件。下面是一个视频请求，模型和参数只是示例：

~~~json
{
  "model": "seedance-2.5",
  "prompt": "镜头缓慢靠近桌上的透明水杯，杯中水面轻轻晃动，柔和晨光。",
  "duration": 5,
  "resolution": "480p",
  "aspect_ratio": "9:16"
}
~~~

图片请求示例：

~~~json
{
  "model": "gpt-image-2",
  "prompt": "一只蓝色陶瓷杯放在干净的木桌上，柔和的窗边光线。",
  "quality": "low",
  "aspect_ratio": "1:1"
}
~~~

将路径替换为实际文件，使用对应的 image 或 video 类型预览：

~~~bash
python3 scripts/sume_media.py preview --kind video --request /path/to/video.json
python3 scripts/sume_media.py preview --kind image --request /path/to/image.json
~~~

预览只检查基本结构，不联网、不生成素材，也不能核实模型在当前账号中的可用性、
具体参数限制、素材地址、费用或内容审核结果。实际提交采用异步模式，不注册回调地址。

## 参考素材

首帧使用 image_url，尾帧使用 end_image_url，尾帧需要同时提供首帧。参考图和参考视频等字段
是否受支持，以所选模型目录为准。素材地址需要是服务可访问的 HTTPS 地址，并在任务读取期间有效。
已有可访问地址时可以直接填入请求。

需要上传本地文件时，在用户允许将该素材交给服务方后运行：

~~~bash
python3 scripts/sume_media.py upload --file /path/to/reference.png
~~~

命令先获取上传地址，再将文件传给存储服务，返回素材地址供请求使用。必要时可通过
--content-type 指定正确的 MIME 类型。素材地址可能可凭链接访问，应按素材敏感程度管理。

## 提交、查询与恢复

仅在用户已授权所选工作区和预算时提交。任务记录必须是尚不存在的新文件：

~~~bash
python3 scripts/sume_media.py submit --kind video --request /path/to/video.json --task-file /path/to/sume-task.json
python3 scripts/sume_media.py status --task-file /path/to/sume-task.json
python3 scripts/sume_media.py result --task-file /path/to/sume-task.json
~~~

提交可能收费。脚本发送前保存请求摘要和唯一请求标识，成功后保存任务编号，不保存密钥。
查询一次只读取一次状态；任务仍在排队或处理中时，按服务返回的等待建议再次查询，
不要重新创建任务。完成后从结果中的素材地址下载并检查实际文件，再加入项目素材清单。

如果提交超时且记录仍为 submission_unconfirmed，先检查服务控制台。需要恢复时，核实密钥仍属于
原工作区、请求内容未变，并核对服务方当前的幂等规则；只有确认这些条件后才使用原记录：

~~~bash
python3 scripts/sume_media.py resume --request /path/to/video.json --task-file /path/to/sume-task.json --confirm-same-workspace
~~~

恢复会重用记录中的请求标识，不会自动轮询或自动重试。服务方对标识的作用范围、有效期或错误
处理可能调整，无法确认时先查现有任务和计费记录。结果地址及任务记录不应随意公开。
