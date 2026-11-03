# 并入上游 piano 整合方案的成果

小米平板 8 Pro 上现在有两套独立的 Linux 整合：

- 本项目：SunUEFI（EDK2）+ 合体 BOOT 选择页，内核在 ESP，rootfs 在
  `sunuefi_root`，保留原厂 Android 与 Recovery，Windows 路线仍开着。
- [xiaomipad-8pro-mainline](https://github.com/yzddmr6/xiaomipad-8pro-mainline)：
  自建 boot set 写进 `boot_a`（Android boot image + AVB 签名 + `boot-profile.json`），
  把 `userdata` 拆成 `linux_rootfs` + `linux_data`，Android 侧用 KernelSU
  模块切换。同一块板子（`piano`，SM8750P），README 里把本项目列为参考。

两边引导栈和分区布局不同，**整包镜像不能互换刷入**。可复用的是内核与
设备树层面针对同一块板子的根因修复，以及部分用户空间组件。

## 对方领先的地方

按他 v0.9.2 的发布说明与本项目实测对照：

| 能力 | 对方 | 本项目 |
| --- | --- | --- |
| 挂起深度 | v0.8.0 起「整颗芯片进入深省电，CX 逻辑供电关闭、内存自刷新」 | 能挂起、能唤醒，但平台不掉压：空闲 1.19 W、挂起 1.46 W |
| RTC | 重启后时间正确 | `rtc0` 纪元是 1970，每次开机靠 timesyncd 对时 |
| 硬件解码 | H.264/H.265/VP9 解码，1080p/4K 编码 | 未完成 |
| 摄像头 | 前后摄可用，v4l2loopback 输出 | `camera-*` 覆盖已在，未打通应用侧 |
| 显示 | 双 DSI 链路修复、144 Hz、BOE/CSOT 自动识别 | 有 `piano-touch-panel.dtso`，双链路修复未跟 |
| UFS | MCQ 多循环队列 | 已有 `piano-ufs-mcq.dtso` |
| 电源模式 | tuned 三档（节能/平衡/性能） | 无 |
| 传感器/音频 | 完整 SSC 栈、AudioReach UCM2 | 有 `sensors.md`，音频仅时钟域 |

本项目独有：**笔支持**（对方明确列为未支持）、UEFI 引导与 Windows 路线。

## 已导入的补丁

`patches/piano-upstream/` 有 9 个候选补丁与 `provenance.json`，来源
`linux-sm8750-piano` 分支 `piano/v0.9.2`（Linux 7.2.14 + 436 提交）。
挑选标准是「与本项目已知问题直接相关且体积小」，说明见该目录 README。

优先级最高三条：

1. **0004 去掉常态 RF 时钟投票**：`RPMH_RF_CLK1` 让射频缓冲在
   active/wake/sleep 全程持有 AP vote，挂起时释放不掉。这条与我们的
   `ath12k` 挂起表现吻合。
2. **0001 RTC 偏移存 SDAM2**：纯设备树改动，用 pm8xxx 现成的 nvmem
   offset 机制，能把 1970 纪元问题从「靠网络对时」变成「开机就对」。
3. **0003 LLCC 预留 ISLAND1**：一行改动，直接影响 LLC 在深睡时的状态。

排序依据是「改了能复测」：挂起功耗有 1.46 W 这个基线，改完再测一次就能
判断有没有效，不需要等整套用户空间。

## 落地方式

不要把补丁直接塞进 `patches/linux/series.json`——那份序列有 sha256 与
原始提交绑定，手工加条目会破坏校验。每条按下面的路子走：

- 设备树改动 → 新写 `linux/dts/piano-*.dtso`，由
  `tools/build_piano_full_dtb.py` 参与合成。
- 驱动改动 → 进 `patches/linux/7.3/` 并同步 `series.json` 与哈希，
  或先由 `tools/apply_*.py` 的定点改写承担。
- 每条都要有对应的单元测试或上机复测记录，再合并回 `dev`。

## 不建议照搬的部分

- **boot set / `piano-boot-switch` / KernelSU 模块**：与 SunUEFI 的合体
  BOOT 和 ESP 布局冲突，属于二选一。
- **音频 AudioReach 整套与摄像头 `piano-camerad`**：依赖他那套内核 ABI
  与固件分片，跟进成本高于收益，等内核侧对齐再说。
- **Mesa / 硬解打包**：绑定他的 Ubuntu 26.04 打包版本，本项目是
  Debian/Nyarch/SteamOS 多目标，需要重做打包而不是拷文件。

## 许可与署名

对方整合代码 MIT、内核 GPL-2.0-only，`NOTICE` 逐文件记录了来源（包括从
本项目拿的部分）。导入的补丁保留原始 `From`/`Subject`/提交哈希与仓库链接；
后续改写进本项目格式时，在提交信息里注明原始 sha。
