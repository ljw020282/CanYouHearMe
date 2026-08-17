# CanYouHearMe

魔兽世界里打字，语音进 **YY**。给坦克指挥用：置顶输入条、常用语、本地缓存。

语音走阿里云百炼 **CosyVoice-v3-flash**（默认音色龙天），播放到 VB-Cable 的 `CABLE Input`，YY 麦克风选 `CABLE Output`。

## 和 HearMe 的关系

产品思路受开源项目 [HearMe](https://github.com/steamyvino/HearMe)（GPL-3.0）启发：文本转语音、虚拟声卡进语音软件。本仓库是按自己的交互和数据模型重写的实现，不包含该项目源码。

## 热键（仅程序运行期间）

| 按键 | 作用 |
|---|---|
| Caps Lock | 显示 / 隐藏悬浮窗（不切换系统大小写） |
| Alt + Caps Lock | 空闲则朗读，生成或播放中则停止 |
| Enter（窗口内） | 朗读输入框；空则朗读当前常用语 |

退出程序后 Caps Lock 恢复系统行为。

## 数据目录

默认：`G:\CanYouHearMeVoice\cosyvoice-v3-flash\`

- `config.json` — 配置（含 API Key，不要提交 git）
- `app.sqlite` — 语料与命中次数
- `voices\<音色>\<哈希>.wav` — 缓存音频

换模型请换同名文件夹重新开。

缓存策略：十条常用语和缩写展开句一律缓存；自由输入少于 6 字立刻缓存，否则成功朗读 3 次后再缓存。实时合成占 1 条通道，扫库最多 2 条，互不堵塞。

## 运行

请把 Cursor 工作区开到 `F:\software\CanYouHearMe`。原来的 `HearMe` 目录只作参考，不再改。

Python 3.11+。先装 [VB-Cable](https://vb-audio.com/Cable/)。

```bash
pip install -r requirements.txt
python main.py
```

在设置里填百炼 API Key。YY 输入设备选 `CABLE Output (VB-Audio Virtual Cable)`。魔兽建议无边框窗口。

## 许可证

MIT。
