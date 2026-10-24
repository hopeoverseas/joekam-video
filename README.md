# Joekam Video

An open agent skill for turning a brief, reference video, or existing assets into an editable video production.

[简体中文](README.zh-CN.md) · [Skill instructions](SKILL.md) · [MIT license](LICENSE)

Joekam Video connects scriptwriting, reference analysis, asset direction, editing, captions, sound, motion graphics, and delivery. Its production guides can be combined across seven video formats and twelve craft topics.

The skill works with the media tools and services available to your agent. Existing footage and images can be edited locally; new generated shots can use your selected image, video, or voice service.

## Install

Use the agent skills CLI with Node.js 22.20 or later:

```bash
npx skills add hopeoverseas/joekam-video --skill joekam-video -g
```

Choose the agent you use when prompted. The `-g` option installs the skill across projects; omit it for a project installation. The installer documentation is maintained in [vercel-labs/skills](https://github.com/vercel-labs/skills).

For a manual installation, place `SKILL.md`, `agents/`, `references/`, and `LICENSE` together in your agent's skill directory under `joekam-video/`.

## Start a production

In Codex, invoke `$joekam-video` and provide your goal plus any reference video, product details, footage, images, recordings, or existing project.

```text
$joekam-video Analyze this reference video. Reuse its pacing and narrative structure,
adapt it to my product and script, and deliver an editable version.
```

```text
$joekam-video Make a vertical product demonstration from these images and this
voice recording. Add readable captions and use my existing assets first.
```

```text
$joekam-video Revise the opening, ranking order, and music in this project.
Keep the approved footage and export a new version.
```

The agent develops the brief and shot plan, prepares the required assets, composes the video, and checks the actual output. Deliverables follow your request and can include the video, editable project, script, shot plan, caption files, and asset inventory.

## Video formats

| Format | Typical work |
| --- | --- |
| [Talking head / UGC](references/formats/talking-head.md) | Presenters, reviews, recommendations, and personal explanations |
| [Short drama](references/formats/short-drama.md) | Characters, conflict, actions, and story-driven scenes |
| [Two-person podcast](references/formats/two-person-podcast.md) | Conversations, contrasting viewpoints, and interview excerpts |
| [Street interview](references/formats/street-interview.md) | Situated questions, answers, reactions, and reveals |
| [Ranking / listicle](references/formats/ranking-listicle.md) | Rankings, comparisons, roundups, and item-by-item explanations |
| [Presenter-led explainer](references/formats/presenter-led-explainer.md) | A presenter working with products, screens, data, and graphics |
| [Narration-led demonstration](references/formats/narration-led-demo.md) | Voiceover with product shots, screen recordings, actions, and animation |

Reference-video adaptation can use any of these formats. The guides describe production decisions rather than promising audience reach or identical generated performances.

## Craft guides

| Topic | Topic |
| --- | --- |
| [Image direction](references/craft/image-direction.md) | [Voice direction](references/craft/voice-direction.md) |
| [Voice and performance](references/craft/voice-and-performance.md) | [Video direction](references/craft/video-direction.md) |
| [Reference continuity](references/craft/reference-continuity.md) | [B-roll](references/craft/b-roll.md) |
| [Screen demonstrations](references/craft/screen-demonstrations.md) | [Captions](references/craft/captions.md) |
| [Caption tracking](references/craft/caption-tracking.md) | [Sound and mix](references/craft/sound-mix.md) |
| [Graphic composition](references/craft/graphic-compositions.md) | [Motion graphics](references/craft/motion-graphics.md) |

Read [Production methods](references/production.md) for project organization, shot planning, timing, revisions, and delivery. Read [Tool use](references/tools.md) for media inspection and local composition examples.

## Tools, services, and costs

The repository contains instructions and production guides. Video editing and generation run through tools that your agent can actually access.

- **Existing media:** FFmpeg, ffprobe, or an available editor can inspect, resize, combine, caption, and mix local assets.
- **Generated assets:** Use your chosen service or a suitable local model for new images, video shots, or speech. A video API is optional when the project can be made from existing media or authored graphics.
- **Capabilities:** Check the installed tool's real features. For example, subtitle burn-in requires a build with the relevant filter; subtitle tracks and separate subtitle files are other delivery options.
- **Billing:** This skill has no subscription or per-render charge. Agent usage, external services, hardware, and media assets may have their own costs and terms.

Account connections and paid generation should follow the user's selected accounts, scope, and budget. Keep secrets outside scripts, production notes, and shared artifacts.

## Contribute and validate

See [CONTRIBUTING.md](CONTRIBUTING.md). Run the dependency-free structural checks with Python 3:

```bash
python3 tools/check_skill.py
```

The checks cover the skill identity, invocation metadata, local document links, and required license files. They do not substitute for watching and listening to a rendered video.

## License

Joekam Video is available under the [MIT License](LICENSE). Commercial use, modification, redistribution, and closed-source derivatives are permitted when the copyright and permission notice are preserved. Third-party tools, services, and media retain their own terms.

Maintained by [gannew1985](https://github.com/gannew1985) in [HopeOverseas](https://github.com/hopeoverseas).
