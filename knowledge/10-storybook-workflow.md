# 图文故事片（AI 分镜图 + 推镜视频 + 小红书轮播一鱼两吃）实战手册

> **定位**：用 4–6 张风格统一的插画/生活分镜图，一键同时产出 **① 15–20 秒高留存竖屏故事短视频**（自动平滑 Ken Burns 推镜 + `Edge-TTS` 旁白 + EBU R128 `-14/-16 LUFS` 无版权 BGM + HeyGen HyperFrames 渲染，无品牌浮条）与 **② `xhs-carousel/` 3:4 小红书/抖音图文轮播套图**。
> 成本仅为 AI 视频的约 1/10，且**零人脸畸形、零手部穿帮、零口型错位**。

---

## 一、生图渠道由成员自主选择（严禁静默扣积分）

市面上主流 Agent 工具（WorkBuddy、豆包、通义千问、扣子等）大多自带生图/生视频能力，但往往消耗宿主积分。因此制作 `图文故事片` 前，**先查 `media_manager.py config --show` 中的 `default_image_source`**：

- 若 `default_image_source` 为空（尚未设定默认渠道），**必须先用简明 5 选 1 询问成员本条分镜图从哪来**（成员选完可顺手询问是否记住为默认）：
  1. **选项 A · 当前 Agent 内置生图工具**（直接调 WorkBuddy / 豆包 / 千问等自带生图能力 —— 最省事，会消耗当前工具积分）；
  2. **选项 B · 即梦 CLI（`dreamina text2image`）**（走本机已登录即梦账号出图 —— 扣即梦积分，画风极稳）；
  3. **选项 C · 云端聚合 API 生图（`api_image` · 推荐复用已有 API 余额）**（直接复用本机已配置的 `video_api_base_url` + `video_api_key`，支持 `gemini-3.1-flash-lite-image` / `gemini-2.5-flash-image` / `doubao-seedream-5-5` / `gpt-image-2` 等，单套 4–5 张图成本仅为 AI 视频的约 1/10，且自带已生成图片跳过防重扣费）：
     ```sh
     python3 scripts/api_image_runner.py check
     python3 scripts/media_manager.py config --set-image-source api_image
     ```
  4. **选项 D · 免费外部图库 API（0 积分）**（走本机已配的 Pexels / Pixabay 免费 API 拉取真实生活家居图：`python3 scripts/media_manager.py fetch --kind stock_images --count 5 --query "tidy closet folding clothes"`）；
  5. **选项 E · 本地已有图片目录（0 积分）**（直接从成员指定的本地图片目录或 `local_footage_dirs` 抽图：`python3 scripts/media_manager.py footage --kind image --count 5`）。

> **硬红线**：未获成员选择或明确授权前，**绝不静默调用宿主内置生图/生视频工具、云端 API 扣费命令或即梦扣分命令**。

---

## 二、4–6 幕爆款故事结构与画风统一铁律

### 1. 经典 4 幕 / 6 幕旧衣回收故事结构（总旁白 80–110 字，约 15–20s）
- **第 1 幕（痛点共鸣）**：换季打开塞爆的衣柜/鞋柜，满脸发愁（感觉词开场）；
- **第 2 幕（常见误区/避坑）**：想直接扔垃圾桶可惜，扛下楼又太沉，或者踩过口袋忘掏空/衣服潮湿的坑；
- **第 3 幕（解决方案）**：把四季旧衣、旧鞋、旧包、床单被套一起装进大袋子，预约专人免费上门取件；
- **第 4 幕（爽感结果）**：衣柜瞬间空出一半、阳光照进整洁房间，回收款按订单流程结算进余额，心里特别踏实。

### 2. 分镜 Prompt 风格统一铁律（避免每张像不同画师）
无论走选项 A（宿主生图）还是选项 B（即梦 `text2image`），同一条故事片的 4–6 张图**必须共享完全相同的画风前缀 + 主角设定 + 禁字后缀**：
- **推荐画风前缀**（按题材二选一）：
  - 治愈绘本风：`温暖治愈系现代生活水彩绘本插画，柔和晨光，低饱和暖米与森绿配色，干净线条，9:16 竖屏构图。`
  - 写实生活风：`真实手机生活摄影质感，中国现代温馨居家环境，自然柔光，干净整洁，9:16 竖屏构图。`
- **主角锁定**：4–6 张图重复同一句主角描述（如 `同一位30岁左右扎低马尾、穿米色针织衫的中国女生`）。
- **防乱码禁字后缀（每张必带）**：`画面中绝对不要出现任何文字、汉字、英文字母、数字、气泡框、水印和 logo。`

### 3. 复用已有图片前必做「无字核验」（严防两层文字重影）
- 若复用的不是本轮刚按禁字铁律生成的图（例如成员丢来的历史绘本图或上一轮通用生图产物），**在调用 `storybook_builder.py` 之前，必须先用图片查看工具检查原图是否已包含内嵌标题/旁白文字**；
- 若原图本身已带文字，**严禁直接叠加后期顶标和字幕**（会导致两层文字重叠遮挡），应立刻提醒成员二选一：① 按禁字铁律重出纯画面无字分镜图（推荐）；② 保留原图文字并关闭后期文字叠加。

---

## 三、一键一鱼两吃构建（短视频 + 小红书 3:4 轮播套图）

- **方式 1 · 已有分镜图片**：准备好 4–6 张无字分镜图后，写好 `storybook_job.json`（含 `slug`、`title`、`panels: [{"image": "...", "caption": "...", "narration": "..."}]`、`cover`、`hashtags`），执行：
  ```sh
  python3 scripts/storybook_builder.py --job storybook_job.json --out-dir outputs --organize-by-date
  ```
- **方式 2 · 复用云端聚合 API 自动生图 + 一键出片**（单套成本约 AI 视频 1/10）：在 `storybook_job.json` 的每个 `panel` 中写明 `prompt`（并在顶层设 `style_prefix`、`character_lock`），加上 `--generate-images`（已生过的分镜自动跳过，断点不重复扣费）：
  ```sh
  python3 scripts/storybook_builder.py --job storybook_job.json --generate-images --image-model gemini-3.1-flash-lite-image --out-dir outputs --organize-by-date
  ```
- 若成员只需要**小红书图文轮播**（不渲视频），加 `--carousel-only` 秒出 `xhs-carousel/01-封面.jpg` … `04-分镜.jpg`；
- 若成员要求视频不要 BGM（留纯人声干声），加 `--silent`；
- 交付前必须查看 `qc-contact.jpg`、`cover-9x16.jpg`、`cover-3x4.jpg` 以及 `xhs-carousel/01-封面.jpg`，核验无 AI 乱码字、无孤字换行、0 合规禁用词，并提醒发布时按平台要求勾选「AI 生成」声明。
