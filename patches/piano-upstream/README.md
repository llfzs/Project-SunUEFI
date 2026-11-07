# 上游 piano 移植候选补丁

这里存放从 [yzddmr6/xiaomipad-8pro-mainline](https://github.com/yzddmr6/xiaomipad-8pro-mainline)
的内核分支 `piano/v0.9.2`（[linux-sm8750-piano](https://github.com/yzddmr6/linux-sm8750-piano)，
基于 Linux 7.2.14，相对上游领先 436 个提交）里挑出的补丁。

**状态：暂存，未接入构建。** 这些补丁的上下文来自 7.2.14 的
`arch/arm64/boot/dts/qcom/sm8750-xiaomi-piano.dts`，本项目基线是
`blu-sharky/linux-piano`，不能直接 `git apply`，需要按本项目的方式重做
（设备树覆盖放 `linux/dts/*.dtso`，驱动改动走 `patches/linux/`）。

保留了原始 `From`/`Subject`/提交信息，便于回溯；来源清单与截断情况见
[`provenance.json`](provenance.json)。

| 补丁 | 解决什么 | 本项目对应位置 |
| --- | --- | --- |
| 0001 RTC 偏移存 SDAM2 | PMK8550 原始计数器不变，用 pm8xxx 已有的 nvmem offset 做墙钟换算，重启后时间正确 | 新覆盖 `linux/dts/piano-rtc-offset.dtso` |
| 0002 xiaomi_mca 允许无源睡眠 | 拔掉充电器后 `quiesce` 仍拒绝睡眠，导致充过一次电的机器在电池上永不挂起 | `patches/linux/`（我们内核有同款驱动） |
| 0003 LLCC 预留 ISLAND1 | SM8750 最后一个 slice 的 `bonus_ways` 改为 `res_ways`，让 LLC 能按 retention 配置 | `patches/linux/` 一行改动 |
| 0004 去掉常态 RF 时钟投票 | `RPMH_RF_CLK1` 会让射频缓冲在 active/wake/sleep 全程持有 AP vote，**挂起时释放不掉** | `patches/linux/` 或覆盖删除属性 |
| 0005 音频宏去掉多余 PM_CLK 依赖 | TX/RX/VA 宏已改用显式时钟，残留依赖多拿一层时钟引用 | `patches/linux/` |
| 0006 键盘改成 attach 命令唤醒 | 取代周期性唤醒，锁屏时不再定时把系统叫醒 | `patches/linux/`（nanosic HID） |
| 0007 键盘桥随面板熄灭断电 | 面板 blank 时同步断键盘桥与配件供电 | `patches/linux/` |
| 0008 geni SPI 在 GPI DMA 期间不进深 idle | 修 DMA 消息期间进深 idle 导致的丢帧，与省电方向相反但对触控可靠性必要 | 视是否复现再定 |
| 0009 触控挂起时跳过电源查询 | 挂起路径里查询充电泵/漏电供电会拖慢或失败 | `patches/linux/` |

## 使用注意

- 0001 是他自己标注的 **RFC**：SDAM2 的 0x72–0x75 是否被固件占用尚未验证，
  原注释写明「不要在对板验证前部署」。移植前要先确认这几字节在 Android
  与关机切换后不会被改写。
- 0007 的 diff 较大，GitHub API 有按文件截断，`provenance.json` 里记录了
  哪些文件没取到；需要完整内容时按 sha 回源取。
- 许可：内核补丁为 GPL-2.0-only，保留提交信息与来源链接即可。
