# AI 视频生成、省点混剪与口播包装实操手册（即梦 CLI / Google Flow / 云端 API / 纯实拍 / MotionGit）

> 本手册覆盖 AI 视频与实拍包装相关生产轨道。所有成片均严格遵守 `knowledge/01-brand-rules.md` 合规硬红线，**全片无品牌浮条、无全屏静态尾卡，话音一落利落收尾保完播**，并统一通过 **HeyGen HyperFrames**（`https://github.com/heygen-com/hyperframes`）完成高画质渲染与 `9:16` / `3:4` 双封面产出。

---

## 一、先做「选题 → 档位 → 人物/场景」匹配（绝不盲目花点）

调用即梦或 Google Flow 前，**必须先结合 `knowledge/03-copy-formula.md` 的四维选题矩阵（人群 × 场景 × 品类 × 切角）与 `~/.yidehai-video/used_history.json` 完成选题匹配**，做到「选题决定档位，档位决定字数，场景决定人物与道具」，且相邻视频主动轮换人物与场景，避免画面雷同：

### 1. 选题类型 → 最佳档位与时长匹配表

| 选题类型 | 推荐档位 | 目标时长 & 字数红线 | 为什么这么配 |
| :--- | :--- | :--- | :--- |
| **强情绪钩子 / 单痛点直击**（如换季爆柜、旧羽绒服压箱底、旧鞋旧包） | **8s 真人口播档**（Flow `Omni 1.2` 24点 / 即梦 8s） | `8s` · **40–45 字** | 节奏紧凑、信息密度高，最容易拉高完播率 |
| **3 条避坑干货 / 回收前小细节**（如掏空口袋、保持干燥、打包须知） | **10s 真人口播档**（Flow `Omni 1.2` 30点 / 即梦 10s） | `10s` · **52–58 字** | 3 点干货有呼吸感，不会被 8s 截断 |
| **多品类清单 / 流程科普 / 信任背书**（如一次打包清单、旧衣去哪了、上门取件流程） | **省点混剪档**（Flow `Veo 3.1 Lite` 10点无声开场 / 即梦 5s 无声开场 + 2 段本地实拍 + `Edge-TTS`） | `15–20s` · **80–110 字** | **严禁把 80+ 字长清单硬塞进 8–10s AI 口播**；用 AI 吸睛开场 + 真实实拍画面既省点数又更有说服力 |
| **日常高频场景 / 省点轮换补位**（如退租、周末整理） | **0 点纯实拍混剪**（3 段未用本地实拍 + `Edge-TTS`） | `15–20s` · **80–110 字** | 零点数消耗，搭配付费档轮换把均耗压到 10–15 点/条 |

### 2. 选题场景 → 人物人设与道具参考表（避免千篇一律）

| 选题方向 | 推荐人物（真实中国普通人，拒绝网红摆拍感） | 真实场景与核心道具 |
| :--- | :--- | :--- |
| **换季 / 年末清衣柜** | 28–35 岁中国女生，居家休闲卫衣，扎低马尾 | 卧室打开的塞满衣物大衣柜前，手拎旧羽绒服/毛衣，脚边放鼓囊编织袋 |
| **宝妈清旧童装/绘本/玩偶** | 30 岁左右年轻妈妈，浅色针织衫，亲切自然 | 客厅地毯或儿童房旁，身边放分类好的童装、毛绒玩偶、绘本收纳箱 |
| **旧鞋旧包蓝海专场** | 25–32 岁上班族女生/男生，居家便装 | 入户玄关塞满的鞋柜前，左手拎旧运动鞋、右手拿闲置托特包 |
| **租房退租 / 搬家清杂物** | 24–30 岁打工人，T 恤/休闲外套 | 租房客厅，地面堆着纸箱、大号蛇皮袋和叠好的旧衣物/四件套 |
| **旧棉被 / 毛毯 / 四件套** | 32–45 岁家庭主妇/主夫 | 卧室床边，正在把厚棉被、毛毯塞进大号防尘收纳袋 |
| **帮爸妈整理老衣柜** | 30 岁左右子女（或温和长辈出镜） | 传统温馨中式客厅/老衣柜前，桌上堆着整齐的老款式外套与针织衫 |
| **行业揭秘 / 避坑 / 起收科普** | 30–40 岁朴实中国男性回收员，穿深灰/深绿**无字工作服**、戴蓝白劳保手套 | 干净明亮的旧衣分拣仓库门口或小区门口，身后是打包好的大编织袋 |

---

## 二、真人说话类 AI 视频的 6 条提示词铁律（即梦 & Flow 通用）

生成有人出镜说话的视频时，**必须同时满足以下 6 条**，否则极易出现乱码字幕、变脸、截断或嘴型穿帮：

1. **显式禁字幕、禁衣服印字、禁水印**：AI 听到有人说话极易在底部硬烧乱码字幕或在衣服/墙面印字；提示词必须明确禁止文字、字幕、水印、Logo。
2. **锁死机位与景别**：明确写「真实手机拍摄质感、竖屏 9:16、固定机位、中景（胸/腰以上入镜）、不要切镜头、不要剧烈推拉、自然光、生活化不要摆拍感」。
3. **台词严格控字数 + 注明「只说一遍」**：5s 控制 `22–28 字`，8s 控制 `40–45 字`，10s 控制 `52–58 字`；台词用引号完整包裹，且注明**一字不改、只说一遍、说完保持看镜头自然点头微笑**。
4. **动作绑在具体台词上（拒绝木头人念稿）**：把 2–3 个小手势/道具互动绑到关键句上（如说到“压箱底”时抖一抖手里旧外套，说到“别扔”时轻轻摆手，说到“打包好”时拍一拍编织袋）。
5. **AI 生成画面阶段只留干声 + 真实环境音，严禁让模型自带 BGM**：有声口播写「自然居家/仓库环境音，清晰人声，无背景音乐」；**无声开场镜头绝不写台词，且让人物专注整理/拉拉链/打包动作、不张嘴说话**（避免后期配 `Edge-TTS` 嘴型穿帮）。
   - *（注：这是「生成提示词」约束，防止 AI 画面自带音乐/嘴型穿帮；**成片后期仍按 `01-brand-rules.md` 第三节叠加真实无版权 BGM 12%**，两者不冲突。）*
6. **台词先过合规硬红线**：提交生成前先自检台词 0 出现 `顺丰 / 京东 / 当面称重 / 带秤上门 / 现场结算 / 称重结算 / 秒到账 / 即时到账 / 当场结算 / 微信搜 / 看主页 / 点头像 / 关注 / 评论区扣 / 私信`。

---

## 三、即梦 CLI（`dreamina`）—— 国内直连全自动生视频

**严格 Opt-in**：仅当成员明确要求「用即梦生视频 / 做条即梦片」时调用。

### 1. 前置自检与费用护栏
1. 运行 `python3 scripts/dreamina_runner.py check` 检查 CLI 可用性与当前积分余额（`user_credit`）；
2. 未登录时运行 `dreamina login`，将 OAuth 授权链接与 `user_code` 发给成员完成扫码并确认登录成功；
3. **不硬编码模型**：如成员指定特定模型，提交前先跑 `dreamina <subcommand> -h` 核对当前支持的参数组合（`model_version`、`duration`、`ratio`、`video_resolution`）；
4. **严禁静默重复提交**：统一通过 `scripts/dreamina_runner.py submit` 提交，脚本会把 `submit_id` 持久化到 `<task-dir>/dreamina_task.json`；超时或网络波动时只能用 `query` 续查旧 `submit_id`，绝不重发新任务扣双份积分。

### 2. 即梦高成片率中文提示词模板（全程用自然中文）

- **模板 A：即梦真人口播镜头（8s / 10s，纯即梦或单镜口播）**：
  > 真实手机拍摄质感，竖屏 9:16，固定机位，中景，不要切镜头，自然光，生活化不摆拍。`{场景与道具描述}`。`{人物年龄性别穿着，强调衣服上不要有任何文字图案}`，面向镜头说话，语气真诚自然、语速适中；说到“`{关键句1}`”时`{动作1}`，说到“`{关键句2}`”时`{动作2}`。
  > 台词（普通话）：“`{合规中文台词，严格按 5s=22-28字 / 8s=40-45字 / 10s=52-58字}`”
  > 台词一字不改，只说一遍，说完保持看镜头自然点头微笑。声音：自然`{居家/户外/仓库}`环境音，清晰人声，无背景音乐。画面中不要出现任何文字、字幕、水印和 logo。
- **进阶稳脸技巧（图生视频）**：对人物长相/服装一致性要求高时，先用 `dreamina text2image --ratio=9:16` 生成无文字首帧图，再用 `dreamina_runner.py submit --mode image2video --image <首帧图>`，提示词开头加上 `保持首帧画面的人物、服装和场景完全不变，固定机位，不要切镜头`。
- **模板 B：即梦省积分无声开场镜头（4–5s，供混剪用）**：
  > 真实手机拍摄质感，竖屏 9:16，固定中景，白天自然光，生活化。`{人物与场景}`正在专注`{打开爆满衣柜拿出一叠旧外套 / 把旧衣旧鞋装进大编织袋 / 整理打包}`，动作利落自然，全程不张嘴说话。无背景音乐，画面中不要出现任何文字、字幕、水印和 logo。

### 3. 两种出片档位与包装
- **档位 A：省积分混剪（推荐）**：用模板 B 生成 1 段 4–5s 开场镜头 + `media_manager.py footage --count 2` 抽 2 段未用本地实拍 + `package_ai_video.py`（`mode: "montage"` + `Edge-TTS` 干声旁白）。
- **档位 B：纯即梦全片**：用模板 A 生成 8–10s 原片 + `package_ai_video.py`（`mode: "native_audio"`）叠加顶标、防孤字大字幕、双封面与 8 帧质检图。

### 4. 常见报错处理
- **`AigcComplianceConfirmationRequired`**：提示成员先在即梦 Web 端使用该模型完成一次合规确认生成，再重试；
- **`ExceedConcurrencyLimit` (ret `1310`)**：立刻停止继续提交，用 `dreamina list_task` / `query` 跟进排队任务，或在成员预算允许下尝试一次对应 VIP 变体；
- **排队超过 1 小时**：保存 `submit_id` 汇报进度并结束当前轮次，后续直接用 `dreamina_runner.py query --task-dir <dir> --download` 取片。

---

## 四、Google Flow（`flow.google.com`）—— `ego-lite` 全自动生视频

**严格 Opt-in + 强前置 `ego-lite`**：仅当成员明确要求「用 Flow / Omni / Veo 生视频」时调用；开始前必须按 `knowledge/00-auto-setup.md` 第三节确认 `ego-browser` 已安装并输出 `ego-browser ready`。

### 1. 省点混合轮换策略（均耗 10–18 点/条）
1. **主力口播档（24–30 点）**：`Omni 1.2 Flash`（720p、9:16、原生中文口播，零乱码字幕/零水印）
   - **8s（24 点，高完播首选）**：口播台词 **40–45 个汉字**；
   - **10s（30 点，干货清单）**：口播台词 **52–58 个汉字**。
2. **省点混剪档（10 点）**：`Veo 3.1 - Lite`（720p、8s **无声模式**开场吸睛镜头）+ 2 段未用过的本地实拍（`media_manager.py footage`）+ `Edge-TTS` 干声旁白（15–20s）。
3. **0 点纯实拍档（0 点）**：3 段未用过的本地实拍视频/图片 + `Edge-TTS` 干声旁白（15–20s）。

> 注意：`Veo 3.1 - Fast`、`Veo 3.1 - Quality`、`Omni 1.1 Flash` 已/即将下线，不要选用。

### 2. Google Flow 高成片率提示词模板（英文写画面约束 + 中文引号写台词）

- **模板 A：Omni 1.2 Flash 原生中文口播（8s / 10s）**：
  > `9:16 vertical smartphone UGC shot, fixed camera, medium shot, no camera cuts, realistic Chinese {home bedroom / entryway / living room / clean sorting room} background, soft natural daylight, candid everyday look. A friendly Chinese {woman/man in their early 30s} wearing plain casual clothes with no text or logos, {holding an old jacket / standing beside an overflowing wardrobe and woven bag}, making natural hand gestures while speaking directly to camera in clear, natural-paced Mandarin Chinese (say the lines once, then smile and nod naturally): "{合规中文台词：8s=40-45字 / 10s=52-58字}". Natural room ambience only, clear voice, no background music. No on-screen text, no subtitles, no captions, no watermarks, no logos.`
- **模板 B：Veo 3.1 - Lite 无声吸睛开场（8s · 10 点，供混剪用）**：
  > `9:16 vertical smartphone UGC shot, realistic Chinese {home / entryway / bedroom} scene, natural daylight, smooth handheld realism. A Chinese {person} {opening a packed wardrobe / neatly folding old winter jackets and placing them with old shoes and bags into a large woven bag}, focused and natural movement, mouth closed, not speaking. No on-screen text, no subtitles, no watermarks, no logos.`

### 3. `ego-browser` 实操防踩坑铁律（含跨会话防重扣点持久化）
- **费用核对与点击前强制前置检查（P0 防重复扣点硬规则）**：
  1. **每次点击前必查本地任务锁**：先检查任务目录是否已存在 `flow_task.json` 且 `status != "done"`；若已存在未终结记录，**严禁再次点击生成**，必须直接进入下方恢复流程；
  2. 点击 `button[aria-label="开始生成"]` **之前**，必须先读页面 DOM 核对 `生成将消耗 X 个点数` 与预期一致（`24 / 30 / 10`），并采集当前项目网格页中所有已有的 `img[alt="生成的视频缩略图"]` 数量与完整 `src` URL 列表；
  3. **先在任务目录原子写入 `flow_task.json`**（必含字段：`task_id`、`project_url`、`model`、`quoted_credits`、`existing_thumbnails_count`、`existing_thumbnail_urls`、`submitted_at`、`status: "submitting"`），然后再执行点击；
  4. 异常高价立刻中止并告知成员；完成后务必调用 `task.finish({ keep: [] })` 关闭 TaskSpace。
- **跨会话中断恢复与终态闭环规则**：
  - 若浏览器断开、当前 Agent 重启或点击后状态不明，**严禁直接再次点击生成**；必须读取 `flow_task.json` 回到同一个 `project_url`，将当前网格缩略图 URL 集合减去 `existing_thumbnail_urls`：
    - 仅当差集**恰好新增 1 条**且对应任务属于当前会话时，才进入详情页下载 720p 原片；
    - 若差集为空、新增多条或无法唯一归属本次提交，立刻暂停并向成员汇报，等待人工确认，绝不自动重试或盲目下载。
  - 720p 原片下载并通过 `ffprobe` 校验后，立即将 `flow_task.json` 更新为 `status: "done"` 并记录 `downloaded_file`，完成闭环。
- **Omni 1.2 Flash（有声口播）**：
  1. 打开 `button[aria-label="设置"]`，确认 **`button[name="return-silent-videos"]` 为关闭（OFF）**；
  2. 模式选 **视频 + 竖屏（9:16）+ `Omni 1.2 Flash`（720p，严禁 360p）**；
  3. **时长滑块精确点击法**：`input[aria-label="时长"]` 范围 `0..12` 对应 `3s..15s`，**禁止点中心**（会重置到 4s）。先取 boundingBox `(x, y, w, h)`：
     - 目标 **8s**：`x + w * (5 / 12)`
     - 目标 **10s**：`x + w * (7 / 12)`
     点击后读 DOM 核实 `时长 8 秒 / 24 点`（或 `10 秒 / 30 点`）。
- **Veo 3.1 - Lite（10 点无声开场）**：
  1. 打开设置面板，**务必打开 `button[name="return-silent-videos"]`（ON）**（避免触发「音频生成失败」）；
  2. 选 **`Veo 3.1 - Lite`**、竖屏 `9:16`、默认 8s，核对点数为 **10 点**。
- **提交与 720p 无损下载**：
  - 点击生成后等待 4–5 秒检查进度百分比（如 `7%`），**未确认状态前绝不盲目二次点击**；
  - 项目网格页出现 `img[alt="生成的视频缩略图"]` 且百分比消失即完成 → 点入详情页 → `button[aria-label="下载媒体内容"]` → 选 `720p` → 等待 `.mp4` 下载完成后移入任务目录；
  - 立刻运行 `python3 scripts/package_ai_video.py --job job.json --out-dir outputs --organize-by-date` 完成 HeyGen HyperFrames 渲染、8 帧质检与双封面产出。

---

## 五、云端聚合视频 API（`API片` / `api_video`）—— 零浏览器、全平台直连

**严格 Opt-in + 金额上限护栏**：仅当成员明确要求「用 API / 词元 / Seedance / MiniMax / Omni API 生成」时调用，严禁在普通免费出片/批量任务中静默扣费。Windows / macOS 纯 HTTP 标准库直出，无需安装浏览器扩展或 CLI，稳定性最高。

### 1. 一次配置（零硬编码密钥 + 后台分组额度护栏）
1. **财务安全建议**：在聚合 API 控制台单独新建一个「视频专用令牌」，**只勾选所需分组（如 `default` / `sd2.0` / `minimax-h3专属` 等低倍率分组）并设置明确金额上限**（不要勾选「无限额度」）；
2. 将网关根地址（例如 `https://api.tiantoken.com`）与令牌写入本机 `~/.yidehai-video/config.json`（也可通过环境变量 `YIDEHAI_VIDEO_API_BASE_URL` / `YIDEHAI_VIDEO_API_KEY` 传入）：
   ```sh
   python3 scripts/media_manager.py config --set-video-api-url "https://api.tiantoken.com" --set-video-api-key "<YOUR_LIMIT_TOKEN>"
   # 可选：若需 check 时顺带查令牌余额，可再配 New-Api-User ID
   python3 scripts/media_manager.py config --set-video-api-user-id "<USER_ID>"
   # 生成前硬门禁
   python3 scripts/media_manager.py preflight --track api_video
   ```
3. 提交前先跑 **0 扣费连通性与可用模型核验**，确认当前令牌分组确实包含目标模型：
   ```sh
   python3 scripts/api_video_runner.py check
   ```

### 2. 主力模型选型与 5 套协议 Adapter 自动路由
`scripts/api_video_runner.py` 会按 `--model` 自动选择协议（亦可用 `--adapter` 显式指定）：

| 推荐模型 | 自动匹配协议 | 最适合场景 | 关键能力与默认参数 |
| :--- | :--- | :--- | :--- |
| **`gemini-omni-1.2-flash`** | `omni`（`/v1/videos` JSON） | 8–10s 原生中文口播全片 | 720p、`9:16`、`seconds` 3–15s（11–15s 仅支持竖屏），无需浏览器直出 |
| **豆包 `sd-2.0` / `sd-2.5`** | `generations`（`/v1/video/generations`） | 中文人像/居家实景口播 & 图生视频 | `9:16`、去水印 `watermark=false`、支持 `--image` 本地/URL 首帧图（可选 `--upload-doubao` 传私有文件） |
| **`MiniMax-H3`** | `generations`（`/v1/video/generations`） | 强表现力生活剧情/动作与首帧图生 | `9:16`、`768P`、`aigc_watermark=false`，同样兼容 `--image` |
| **`veo_3_1-fast` / `veo_3_1`** | `veo_oai`（`/v1/videos` Multipart） | 5–8s 无声高画质吸睛开场 + 本地实拍省钱混剪 | 竖屏 `720x1280`、支持 `--image` 二进制直传首帧、完成后自动走 `/content` 下载 |
| **`kling-v3-omni` / `kling-4.0`** | `kling_compat`（`/v1/kling/video/task/*`） | 动作稳定性优先、带原生音频 | `9:16`、3–15s、支持 `--image` 首帧 |
| **`wan3.0-video` / `wan2.7-t2v`** | `wan`（`/api/v1/services/aigc/video-generation/video-synthesis`） | 国产多镜头与自动配音视频 | 720P、`9:16`、2–30s、自动配音、支持 `--image` 首帧图 |

### 3. 标准出片流程与防重复扣费铁律
1. **提示词合规与写法**：套用本手册第二节 6 条铁律（`gemini-omni` / `veo` 推荐用第四节模板 A/B；豆包 / `MiniMax-H3` / `kling` 可直接用第三节自然中文模板）。`api_video_runner.py submit` 在发送 HTTP 请求前会先自动跑 `check_forbidden_terms`，命中禁用词直接拦截（**0 扣费**）。
2. **防重提交 + 轮询下载**：
   ```sh
   python3 scripts/api_video_runner.py submit --task-dir outputs/tmp-api-01 --model gemini-omni-1.2-flash --duration 8 --ratio 9:16 --prompt "<合规提示词>" --poll 300
   ```
   - 提交前自动锁目录并将 `gen_status="submitting"` 原子写入 `api_video_task.json` 并同步记录到 `task_tracker.py`（`track="api_video"`）；
   - 网络超时标为 `uncertain_timeout`，已存在记录时再次 `submit` 会被硬拦截（退出码 2）。断点续查统一使用：
     `python3 scripts/api_video_runner.py query --task-dir outputs/tmp-api-01 --poll 180 --download`
3. **HyperFrames 后期包装（全片口播 vs 省钱混剪）**：
   - **全片口播**：把下载好的 `*_raw.mp4` 传入 `package_ai_video.py`（`mode: "native_audio"`），自动补顶标、防孤字大字幕、`-14/-16 LUFS` 混音、`9:16`/`3:4` 双封面与 8 帧质检；
   - **省钱混剪**：用 `veo_3_1-fast` 或豆包无声开场（加 `--no-audio` 提示词要求人物不张嘴）+ `media_manager.py footage --count 2` 抽 2 段本地实拍，传入 `package_ai_video.py`（`mode: "montage"` + `Edge-TTS` 旁白）。
4. **隐私红线**：使用 `--image` 做图生视频时，**严禁上传含真实客户人脸、门牌号、快递单号的隐私原图**；只使用脱敏场景图或 AI 生成首帧图。

---

## 六、0 点纯实拍混剪（`实拍混剪` / `montage`）

完全零 AI 点数消耗，适合高频日常出片或配合省点轮换：
1. 调用 `python3 scripts/media_manager.py footage --count 3` 从本机 `local_footage_dirs` 自动抽取 3 个**未在全局账本用过**的真实实拍视频或图片（静态图片在包装时会自动加上平滑 Ken Burns 轻推镜，绝不呆板）；
2. 写好合规旁白稿（80–110 字，15–20s）写入 `job.json`（`mode: "montage"`）；
3. 一键运行 `python3 scripts/package_ai_video.py --job job.json --out-dir outputs --organize-by-date`，自动完成 `Edge-TTS` 干声合成 → 片段拼接 → HeyGen HyperFrames 渲染（顶标 + 防孤字字幕 + 无浮条利落收尾）→ 8 帧 `qc-contact.jpg` → `9:16` & `3:4` 双封面 → 写入防重账本。

---

## 七、MotionGit 免费口播模板包装（`口播包装` / `motiongit`）

当成员手头已有**真人实拍口播视频**，想做成高质感综艺/杂志/海报风动效口播片时使用（如 MotionGit 官网免费模板「活力海报」「现代编辑」「纸张透视」等）：

1. **模板准备（零凭据隔离）**：
   - 本公开 Skill 仓库**不包含**任何个人 `.motion` 模板文件；
   - 成员从 MotionGit 官网自行下载免费 `.motion` 模板保存到本机目录（如 `~/Documents/motion-templates/`），并配置一次：
     `python3 scripts/media_manager.py config --set-motion-templates-dir "<本机模板目录>"`
2. **执行包装**：
   - 检测本机模板目录中的可用免费 `.motion` 模板，按成员指定的风格（或默认选用竖屏 9:16 模板）调用 MotionGit 官方 runtime，将真人实拍口播视频与合规字幕/关键词传入渲染；
   - **硬约束**：严格保留原始模板包与原素材不修改；严禁提取、打印或上传任何模板内凭据；渲染完成后同样做抽帧目视质检与 `9:16` / `3:4` 双封面补齐。

---

## 八、统一交付前质检清单（不可跳过）

任何轨道出片后，交付前必须查看 `qc-contact.jpg`、`cover-9x16.jpg`、`cover-3x4.jpg`，核验：
1. 画面无 AI 乱码字幕、无衣服乱印字、无第三方平台水印、无畸形手/脸；
2. 顶标与字幕在安全区内、无单字孤行换行、无底部品牌浮条与静态全屏尾卡；
3. 双封面两行大字居中清晰、无边缘裁切；
4. 发布文案已标注按平台要求勾选「AI 生成」声明（纯实拍且未用 AI 配音的除外）。
