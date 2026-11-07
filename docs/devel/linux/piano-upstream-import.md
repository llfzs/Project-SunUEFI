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

**已完成筛选，两条被实测排除**（2026-11-04，详见文末「对照实验结果」）：

1. **0001 RTC 偏移存 SDAM2**：纯设备树改动，用 pm8xxx 现成的 nvmem
   offset 机制，能把 1970 纪元问题从「靠网络对时」变成「开机就对」。
   原注释标了 RFC，上线前要核验 SDAM2 的 `0x72..0x75` 不被固件改写。
2. **0003 LLCC 预留 ISLAND1**：一行改动，直接影响 LLC 在深睡时的状态。
   属驱动表改动，只能在有内核仓库的构建机上进 `patches/linux/7.3/`。
3. **0004 去掉常态 RF 时钟投票**：~~与 `ath12k` 挂起表现吻合~~
   **已排除**——关掉 Wi-Fi 后挂起功耗只从 1.47 W 降到 1.46 W。

排序依据是「改了能复测」：挂起功耗有 1.46 W 这个基线，改完再测一次就能
判断有没有效，不需要等整套用户空间。

## 落地方式

先确认一件容易搞错的事：**设备启动的 `board.dtb` 不是内核树编出来的**。
`./build.sh linux` 只上传 `Image`、`System.map`、`config`、`manifest.json`、
`modules`；打包时 `tools/package_release.py` 用的是
`vendor/piano-linux/board.dtb`，再把 `kernel.additional_dtb_overlays` 里的
`linux/dts/*.dtso` 用 `fdtoverlay` 叠上去。因此：

- 改内核树里的 `arch/arm64/boot/dts/qcom/sm8750-xiaomi-piano.dts`
  （例如 `patches/linux/7.3/0001-platform.patch`）**到不了设备**，只影响
  在树内编 dtbs 的场合。
- 覆盖层只能增加或改写属性，**不能用 `/delete-property/` 删属性**
  （`fdtoverlay` 没有删除语义）。要删属性只能改 `board.dtb` 本身。
- 驱动改动必须进 `patches/linux/7.3/`。那份序列有 sha256、原始提交父链和
  最终 `target_tree` 三重绑定，加一条要重算 tree，只能在有内核仓库的
  构建机上做：加条目（tree 先填占位）→ 跑
  `python3 tools/prepare_release_kernel.py --refresh` 让它失败并在
  `build/kernel-worktrees/<name>.failure.json` 里记下每一步的
  `applied_tree` → 把真实 tree 填回 `series.json` 与 `config/release.json`
  的 `target_tree` → 重跑通过。

所以三条候选的实际归属是：

| 补丁 | 落点 | 状态 |
| --- | --- | --- |
| 0004 去掉 RF 时钟投票 | 打包期定点改写 `board.dtb`（`--board-property-removal`） | 已实现并测试，默认未开启 |
| 0001 RTC 偏移存 SDAM2 | `linux/dts/drafts/piano-rtc-offset.dtso` | 已写好，等占用核查 |
| 0003 LLCC 预留 ISLAND1 | `patches/linux/7.3/` + `series.json` | 卡在构建机，未动 |

## 2026-11-03：RF 时钟改打包期删除

`vendor/piano-linux/board.dtb` 里 `/wcn7850-pmu` 的
`clocks = <&rpmhcc 6>`（`RPMH_RF_CLK1`）就是这个投票的来源。属性删不掉，
所以 `tools/package_release.py` 新增 `--board-property-removal NODE:PROPERTY`，
在既有的 `normalize_mainline_bindings()` 里执行，并对这一条加了形状校验：
必须是一个 cell pair、provider 必须是 `/soc/rsc@16500000/clock-controller-ml`、
时钟号必须是 6。`config/release.json` 的 `kernel.board_property_removals`
默认是空数组，翻转只需一行：

```json
"board_property_removals": [{ "node": "/wcn7850-pmu", "property": "clocks" }]
```

**先别开**。删掉之后如果 `pwrseq-qcom-wcn` 用的是非 optional 的
`devm_clk_get()`，探测会失败，WiFi 和蓝牙直接起不来，而 SSH 是这台设备
唯一的通道。上线前先做不需要构建的对照实验：

1. 当前镜像，锁屏等 `bl_power=4`，`rfkill block wifi` 后再挂起 8 分钟，
   量两路 `current_now`。基线是挂起 1.46 W、清醒 1.19 W。
2. 明显下降 → 关闭射频投票确实有效，翻转上面那一行重建镜像。
3. 几乎不变 → WLAN 芯片在挂起里本来就没断电，RF 时钟不是主因，不要动
   `board.dtb`，转去看 `ath12k` 的挂起路径和面板。

### 对照实验结果（2026-11-04）：按第 3 条处理

`rfkill` 未安装，改用 `nmcli radio wifi off` + `echo freeze > /sys/power/state`
做 8 分钟能量对照：

| 状态 | 时长 | 掉电 | 折算 |
| --- | --- | --- | --- |
| s2idle，Wi-Fi 开 | 491 s | 47 mAh | 1.47 W |
| s2idle，Wi-Fi 关 | 487 s | 46 mAh | 1.46 W |
| 清醒，Wi-Fi 关 | 120 s | 8 mAh | 0.92 W |

关掉射频后挂起功耗只降 0.01 W，而清醒态能省 0.27 W。**射频不是挂起
功耗的主因**，因此 `kernel.board_property_removals` 继续保持空数组，
0004 的优先级下调。同一轮还排除了 s2idle（1.47 W，与 deep 的 1.46 W
一致）和 GPU 持有 CX（`3d00000.gpu-vddcx` 的 `use_count` 是 0，
`pm_genpd` 里 `cx`/`cx_ao`/`ebi` 待机时已 off），细节见
[硬件/睡眠](../hardware/sleep.md)。

上游 v0.7.1→v0.8.0 那 25 个提交里，与深度睡眠相关的是 GPU 那组
（`drm/msm: Always use component model for standalone GPU`、
`Attach a driver to the GMU`、`a6xx: Mark cxpd device_link as stateless`）
和 `usb: dwc3: qcom: Defer VBUS override update during system suspend`
（对应我们的 `HS-PHY not in L2` 告警）。GPU 那组在本机没有可释放的 CX
引用，**不建议照搬**；USB 那条值得单独评估。

## 2026-11-03：RTC 偏移的占用核查

`linux/dts/drafts/piano-rtc-offset.dtso` 给 `sdam@7100` 加一个
`rtc-offset@72`（4 字节），并给 `rtc@6100` 加 `nvmem-cells` / `offset` 名。
`tests/unit/test_piano_rtc_offset.py` 已经锁定：两个目标路径在 board.dtb
里都存在、`0x72..0x75` 与现有子节点（`restart@48`、`wr_thermal-flag@58`、
`xo_calib-data@59`、`alarm-log@76` 起于 0x76、`fmd-*` ≥ 0x9a）不重叠、
board.dtb 目前还没有这个 cell。

还差上机核查三条（原作者标了 RFC，就是因为这个）：写一段花样到
`sdam@7100` 的 `0x72..0x75`，分别在一次热重启后、一次进 Android 后、
一次关机再开机后读回。任何一字节变化就说明固件拥有这个窗口，放弃这条
改动，不要改成更小的窗口。通过后再把文件加进
`kernel.additional_dtb_overlays`，并确认 `hwclock -w` 之后重启 `rtc0`
仍然是墙上时间。

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
