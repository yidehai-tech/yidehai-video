# 本地实拍素材库专用爆款形态手册（`实拍快剪` & `前后对比片` · 0 积分离线直出）

> 适用场景：当同事本机已配置 `local_footage_dirs`（例如数百至数千个真实衣柜、翻找、打包装袋、门口成品袋视频与客户照片）时，使用 `scripts/render_footage_video.py` **纯离线秒级出片（无需 Node / 浏览器，0 积分，不卡终端）**。

---

## 一、开工前强制门禁（`preflight`）与按场景分桶抽素材

1. **硬门禁校验**：
   ```sh
   python3 scripts/media_manager.py preflight --track fastcut
   # 或
   python3 scripts/media_manager.py preflight --track before_after
   ```
2. **按场景关键词分桶抽取（全局防重，绝不乱拼）**：
   ```sh
   # 抽 3 个衣柜/整理类视频作开场痛点
   python3 scripts/media_manager.py footage --count 3 --kind video --include-keyword 客多多 --include-keyword 客户视频

   # 抽 3 张打包袋/成果类照片作后半段爽感镜头
   python3 scripts/media_manager.py footage --count 3 --kind image --include-keyword 客户图片 --include-keyword 照片
   ```
   > 若目录下有杂乱非业务文件（如程序图标、证件、人脸、联系方式），严禁选用或先排除。

---

## 二、形态一：`实拍快剪`（`fastcut` · 6–8 镜头快节奏高完播）

- **结构建议（12–15 秒，55–75 字口播）**：
  - 镜头 1–2（痛点）：衣柜塞爆 / 床上堆满旧衣；
  - 镜头 3–5（过程）：翻找、装袋、四季衣/成双鞋/闲置包混装；
  - 镜头 6–8（结果）：装满几大袋放门口，干净清爽。
- **单条 `fastcut_job.json` 示例**：
  ```json
  {
    "slug": "closet-fastcut-01",
    "title_line1": "换季衣柜塞不下了？",
    "title_line2": "5公斤起专人免费上门",
    "voiceover": {
      "text": "换季清衣柜别硬塞了。四季旧衣、成双旧鞋、闲置包包和床单被罩都能混装进大袋子，凑满五公斤就能预约，专人免费上门取件，回收款按订单流程结算。",
      "voice": "zh-CN-XiaoxiaoNeural",
      "rate": "+12%"
    },
    "clips": [
      {"path": "/path/to/clip1.mp4", "start": 0.0},
      {"path": "/path/to/clip2.mp4", "start": 1.0},
      {"path": "/path/to/photo1.jpg"},
      {"path": "/path/to/clip3.mp4", "start": 0.5},
      {"path": "/path/to/photo2.jpg"},
      {"path": "/path/to/photo3.jpg"}
    ],
    "hashtags": ["#旧衣回收", "#断舍离", "#换季整理", "#亿德海"]
  }
  ```
- **一键渲染**：
  ```sh
  python3 scripts/render_footage_video.py --mode fastcut --job fastcut_job.json --out-dir outputs --organize-by-date
  ```

---

## 三、形态二：`前后对比片`（`before_after` · 上下分屏强视觉冲击）

- **结构建议（10–12 秒，45–60 字口播）**：
  - **上屏（`before`）**：衣柜爆满 / 床上杂乱旧衣视频或照片（自动配深色徽章 `清理前 · 衣柜塞爆`）；
  - **下屏（`after`）**：装满几大袋放门口 / 衣柜清空视频或照片（自动配生态绿徽章 `清空后 · 装袋待上门`）；
  - 静态照片自动做 Ken Burns 缓慢推镜，杜绝死图。
- **单条 `before_after_job.json` 示例**：
  ```json
  {
    "slug": "closet-before-after-01",
    "title_line1": "周末花半小时清衣柜",
    "title_line2": "满屋旧衣瞬间变清爽",
    "before_label": "清理前 · 衣柜塞爆",
    "after_label": "清空后 · 装袋待上门",
    "before": {"path": "/path/to/messy_closet.mp4", "start": 0.0},
    "after": {"path": "/path/to/packed_bags.jpg"},
    "voiceover": {
      "text": "周末花半小时把不穿的旧衣、成双旧鞋和闲置包包一起装袋，凑满五公斤预约专人免费上门取件，回收款按订单流程结算，衣柜瞬间空出一半。",
      "voice": "zh-CN-XiaoxiaoNeural",
      "rate": "+12%"
    },
    "hashtags": ["#旧衣回收", "#衣柜整理", "#断舍离", "#亿德海"]
  }
  ```
- **一键渲染**：
  ```sh
  python3 scripts/render_footage_video.py --mode before_after --job before_after_job.json --out-dir outputs --organize-by-date
  ```

---

## 四、合规与质量硬红线
1. **0 禁用词**：脚本内置 `media_manager.check_forbidden_terms`，严禁出现 `当面称重 / 带秤上门 / 现场结算 / 秒到账 / 顺丰 / 京东 / 微信搜 / 点头像 / 关注我` 等红线词；
2. **音频标准**：人声 `-14 LUFS` + BGM `-16 LUFS × 18%` 响度标准化，缺 BGM 硬拦截（除非显式传 `--silent`）；
3. **无浮条无尾卡**：自动产出 `1080×1920 MP4`、`9:16` 与 `3:4` 双封面、`8 帧质检图 qc-contact.jpg`、`发布文案.md` 并自动回写全局防重账本。
