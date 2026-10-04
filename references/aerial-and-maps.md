# 航拍与地图

## 1. Google Earth Studio

Earth Studio（earth.google.com/studio）能做任何地点的航拍镜头：环绕、俯冲、螺旋、两点之间飞行。账号要申请，逐个审批。

### 能不能用

规则散在几个页面，核对日期 2026-10；用之前再看一眼原文（文末有链接）。

| 场景 | 结论 |
|---|---|
| 教育、研究、纪录片、新闻、电影 | 允许，只要署名正确，不用申请 |
| 网络视频有广告分成 | 允许，不用申请；仍须署名 |
| 广告、推广某产品 / 课程 / 机构的片子 | 禁止；要另行申请 |
| 去掉署名或水印 | 禁止，也买不到这种授权 |
| 转售素材、批量下载 | 禁止 |

某一期如果是推广性质的内容，那一期不要用 Earth Studio 的画面。

### 署名

- 署给「Google Earth」**和**第三方影像提供方（渲染图右下角水印的第二行，照抄，不要自己编）。
- 只要画面里是 Earth Studio 的内容，署名就要一直在；不裁、不遮。只写「Google」不够。
- 裁成竖版时原水印会被切掉，要重新烧一份署名，不要直接裁横版成片。

### 流程

Earth Studio 只能在浏览器里操作（可以用浏览器自动化来点）。

1. 新建工程，用 Quick Start 向导起手：Zoom-To（从高空落到地标）、Orbit（环绕）、Spiral（螺旋）、Point-to-Point（两点飞行）、Fly-To and Orbit。向导三步：搜地点 → 参数 → 时长。
2. **一律渲染 4K（3840×2160）**，30 fps。4K 缩到 1080p 能明显减少屋顶、窗格的摩尔纹。
3. 每个镜头 15–25 秒（450–750 帧），正片里截 5–10 秒用。
4. 渲染选云端 MP4。450 帧约 3 分钟，1500 帧约 9 分钟；每天有帧数配额。渲染完在云渲染列表里下载。
5. 入库：
   ```bash
   python3 scripts/earth_studio_import.py ~/Downloads/city_orbit.mp4 --name city_orbit --providers "<水印第二行，照抄>"
   ```
   转成 1080p 工作片放进 `assets/video/ges_<name>.mp4`，在右下角补烧两行署名（防裁切），并把署名记进 `credits_ges.json`。16:9 不裁切且原水印完整时可以 `--no-burn`。母带另存一份。

### 镜头怎么设

- 俯仰角 40–60° 最好；角度越平，远处的几何细节越差。
- 别贴太近：贴图发糊就是太近了。城市镜头保持在屋顶之上几十到几百米；做不了贴地视角。
- 只打两三个关键帧，两端缓入缓出。慢而顺比什么都重要。
- 从高空俯冲到城市的镜头，动画之前先开对数高度（Logarithmic Altitude），否则越接近地面显得越快。
- 环绕时钉住目标点（Camera Target），别让相机正对目标头顶，会翻转。

### 坑

- **螺旋的起止角度相同 = 静止画面**，半径和高度的变化也不会生效。想要「直线推进」也得给一个角度差（比如 90° 的弧线下降，效果很好）。
- 向导里的角度滑块要真实点击滑轨才生效，用脚本改值不行。
- **提交渲染前拖预览条看首、中、尾三帧**，确认相机真的在动。静止的 15 秒成片只有几 MB，是个事后能发现的信号。
- 搜地点要点下拉的联想项，回车无效。
- 偶尔整页不出影像（地图灰、预览纯蓝）。试两三次不行就先跳过，换别的素材，不要耗在上面。
- 大文件第一次下载可能中断，再点一次。下载地址需要登录态，命令行取不了。

## 2. 地形飞越与路线图（`templates/anim/geomap.html`）

基于 MapLibre 的真实地形飞越，逐帧截图（等瓦片到齐才截）。适合讲：位置在哪、路线怎么走、从大范围推到一个点。

```bash
python3 scripts/capture.py templates/anim/geomap.html \
  "dur=8&c0=105,35&z0=3.4&c1=116.3972,39.9163&z1=15.6&p1=62&b1=-25&pts=地标名:116.3972:39.9163:@6.4" out.mp4
```

- `c0/z0/p0/b0` → `c1/z1/p1/b1`：起止的中心、缩放、俯仰、方位；`arrive=0.9` 表示九成时间到位，之后定住给标签留时间。
- `route=` 路线逐段画出；本地 GeoJSON 用 `templates/anim/geomap_url.py` 内联成参数。
- `pts=名:经度:纬度:@秒` 带标签的点，在指定时刻淡入。
- 底图默认 OpenStreetMap 栅格瓦片；卫星底图用 `base=url&tiles=…&attr=…`（开放的无云合成影像分辨率约 10 米，只够城市级，看不清单体建筑）。
- **署名自动烧在右下角**：OSM 和地形瓦片都要求可见署名，自定义底图必须写 `attr=`。
- 公共瓦片服务有使用政策，别高并发抓；一段 8 秒的飞越正常渲染即可。

简单的示意地图（几个城市加一条路线）用平面矢量地图更干净，不必上三维地形。

## 3. 出处

- Earth Studio 署名：<https://earth.google.com/studio/docs/attribution/>
- Earth Studio FAQ：<https://www.google.com/earth/studio/faq/>
- Google 地图与地球内容使用指南：<https://about.google/brand-resource-center/products-and-services/geo-guidelines/>
- 最佳实践（4K 降采样、俯仰角、距离）：<https://earth.google.com/studio/docs/best-practices/>
- 云渲染：<https://earth.google.com/studio/docs/making-animations/cloud-rendering/>
- OSM 瓦片使用政策：<https://operations.osmfoundation.org/policies/tiles/>
