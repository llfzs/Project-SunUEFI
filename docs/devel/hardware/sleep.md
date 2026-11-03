# 桌面电源管理与睡眠

目标行为由桌面和 logind 的标准接口管理：短按电源或合盖先灭屏、
锁屏，空闲一段时间后按 GNOME/KDE 电源设置进入睡眠。
不增加独立的用户空间睡眠计时服务。

休眠与睡眠分别处理。休眠需要可恢复的磁盘交换空间、内核恢复入口
及固件启动路径；当前的 zram 在断电后不会保存内容，不能作为休眠存储。
仅有内核 `CONFIG_HIBERNATION=y` 不代表系统已经可以休眠。

## 当前状态

2026-10-13，Nyarch 上的内核提供 `freeze mem disk`，
`mem_sleep` 提供 `s2idle` 和 `deep`，当前默认 `deep`。
发行版镜像仍屏蔽睡眠/休眠目标，GNOME 的电池及插电自动睡眠动作
均为 `nothing`。合盖及电源键的现有适配只控制背光。

RTC 节点和 `rtc_pm8xxx` 模块存在，但初始没有加载。手动加载后
注册 `rtc0`，其定时唤醒接口可接受闹钟，设备 wakeup 已启用。
不过硬件计数器的时间偏移尚未对齐；加载时 HCTOSYS 将系统时间
设置到了 1970 年。测试后恢复系统时间，尚未将该模块添加到自动加载。
后续应对照原厂持久化时间偏移，使用 RTC/nvmem 标准接口实现。

一次 `rtcwake -m freeze -s 12` 测试后 SSH 中断，随后连接到的系统
已是新启动，未确认成功睡眠恢复。新启动的 suspend_stats 为零，
上一启动的 journal 没有留下失败阶段；读回的 ramoops 内容被固件
启动日志占用，未提供这次睡眠的内核调用栈。

因此当前不能启用默认自动睡眠。下一步需要捕获设备暂停阶段及
唤醒路径，验证恢复后显示、UFS、USB、无线和输入设备仍可使用，
再解除目标屏蔽并接入桌面现有的自动睡眠时间设置。

## GNOME 锁屏与唤醒对照

显示恢复修正后，测试了通过 `org.gnome.ScreenSaver.Lock` 锁屏，
再用 Mutter 的 `PowerSaveMode` 关闭和开启显示。
logind 报告 `LockedHint=yes`，但物理屏幕仍黑：打开显示链路
没有唤醒 GNOME 屏保。当前助手独占读取电源键，Mutter 收不到
对应的用户活动。

`org.gnome.Mutter.IdleMonitor.ResetIdletime` 虽然能在 introspection
中看到，仅允许设置调试环境变量后调用，不能作为产品方案。
`ScreenSaver.SetActive(false)` 则会退出屏保和锁定状态，不能用于
正常唤醒，不能让物理按键跳过密码认证。

GNOME 标准实现通过 ScreenShield 的 `WakeUpScreen` 通知电源组件
临时退出空闲状态。后续应从输入事件进入这条路径，同时保留
长按关机菜单和开盖唤醒。实验运行配置已撤回，合盖和短按电源恢复
原有的背光控制，没有部署调试环境变量、虚拟输入或自动解锁。

## 2026-11-02 实测：挂起可用，但不省电

在一台 `7.3.0-piano-sunuefi-cachy` 上连续验证 4 次，全部成功：

```
echo +N > /sys/class/rtc/rtc0/wakealarm
systemctl suspend
```

- 内核走 `PM: suspend entry (deep)`，PSCI 依次关闭 CPU1–7
  （`psci: CPU7 killed` …），恢复时全部重新拉起；
  `suspend_stats/success` 逐次累加，`fail=0`。
- 闹钟准点：`+60` 与 `+480` 两次实测唤醒误差均小于 5 秒；
  唤醒后 Wi-Fi 自动重连、墙上时间正确、SSH 可回。
- `rtc0` 纪元仍是 1970 也不影响：`+N` 按 RTC 自身计数值相对计时，
  触发后 `wakealarm` 自动清零。`wakeup8 rtc@6100` 与
  `wakeup7 pwrkey` 都是已启用的唤醒源，闹钟失效也能按电源键救回。
- **日志时间假象**：`PM: suspend entry` 与 `Freezing user space`
  相差近一分钟，是 journald 按 boottime 把睡前消息推到醒来之后，
  不是真的卡在某个阶段。

**功耗没有改善，反而更高。** 屏灭状态下同长度对照（能量法，
两个电池包的 `charge_now` 相加）：

| 状态 | 时长 | 掉电 | 折算 |
| --- | --- | --- | --- |
| 清醒（屏灭，笔扫描关） | 480 s | 38 mAh | 1.19 W |
| 挂起（deep） | 481 s | 47 mAh | 1.46 W |
| 挂起（deep，短测复核） | 408 s | 42 mAh | 1.55 W |

即 CPU 确实断电了，但平台没有跟着掉压，挂起期间还比空闲多耗
0.3 W 左右。日志里能对上的一条：`dwc3-qcom a600000.ssusb:
port-1 HS-PHY not in L2`，USB PHY 没进低功耗态；
`hwmon hwmon52: PM: parent phy0 should not be sleeping` 说明
ath12k 的挂起顺序也有问题，WLAN 是否真正断电没确认。

**因此自动睡眠仍保持关闭**：现在挂起既不省电，又会断 Wi-Fi
（微信收不到），没有收益。先在挂起状态下把 USB PHY、WLAN 和
调压这几条查清，再谈启用。

**测量口径注意**：本机是两个独立电池包（`bq27z561-0/-1`，
各 4.6 Ah 设计容量），必须把两路 `current_now` 相加。
此前文档与记录里 0.68 W 的待机值只算了一路，真实空闲约 1.2 W。
`power_avg` 属性不可用（两路都报 41.7 W，驱动单位错误）。

挂起到不了深省电的候选修法见
[并入上游 piano 整合方案的成果](../linux/piano-upstream-import.md)：
RF 时钟投票、LLCC ISLAND1、RTC 偏移三条优先级最高。

其中 RF 时钟投票已经可以从设备启动用的 `board.dtb` 里删掉
（`kernel.board_property_removals`），但**默认关闭**。开启前先做一次
不需要重新构建的对照：锁屏熄灭后 `rfkill block wifi` 再挂起 8 分钟，
和 1.46 W 的基线比。这一条既能判断射频投票是不是主因，也能避免直接
刷入一个可能让 WiFi 探测失败的 DTB。
