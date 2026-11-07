# Linux 7.3 发布内核

从正式的 `v7.3` 提交开始，依次应用 `series.json` 中的主题补丁和接口修正：

| 补丁 | 内容 |
| --- | --- |
| `0001-platform` | 板级描述、总线、存储、时钟、电源、固件通信与原有启动适配 |
| `0002-display` | DPU、双 DSI、面板、背光、色彩曲线和无缝 VFP 更新 |
| `0003-input-wireless` | 触摸、触控笔、键盘、蓝牙和无线网络 |
| `0004-media` | 相机传感器、CAMSS、Iris 和闪光灯 |
| `0005-audio` | 四扬声器、TDM 和麦克风 |
| `0006-gunyah` | Android Gunyah 驱动及主线接口适配 |
| `0007-bore` | CachyOS 的 BORE 6.8.0 调度改动 |
| `0008-drm-msm-gem-api` | 适配 7.3 的显存分配接口，保持色彩校正 DMA 使用独立缓冲区 |
| `0009-gunyah-rmap-api` | 适配内存反向映射接口，借出页面前仍检查用户映射 |
| `0010-gunyah-dt-availability` | 尊重资源管理器节点的禁用状态，避免使用其他启动中的旧句柄，并修正设备树引用重复释放 |
| `0023-dpu-shared-video-ctl` | 双 DSI 共用一个 CTL 时每帧只提交一次，避免从通道重复提交和待完成计数增长；超时日志附带控制器、接口和提交掩码 |
| `0024-hid-nanosic-feature-and-release` | 触控板使用描述符声明的能力，不再查询 MCU 未实现的 HID Feature 报告；合盖释放触点时按型号发送完整报文 |

这些文件由迁移结果按子系统整理，不再把旧 stable 分支的回移修复
重复合并到新主线。清单保留每一步的来源、SHA-256、提交父子关系和结果树；
准备工具在独立构建副本中应用，不修改上游检出。

Piano 硬件基线来自 blu-sharky/linux-piano，既有本地修复来自项目的
7.2.9 补丁。迁移保留了上游 7.3 的新增设备支持；对连接器状态创建、
DSI 原子回调、FastRPC 响应等待、QMP 电源管理及 PCIe MSI 初始化顺序
进行了接口适配。各源文件版权声明保留，详细第三方说明见
[THIRD_PARTY.md](../../../THIRD_PARTY.md)。

默认配置启用 BORE、MGLRU、300 Hz tick 和完整抢占，继续使用
`NO_HZ_IDLE`、`schedutil` 和 Zstd ZRAM。300 Hz 是内核时钟频率，
不是屏幕或触控刷新率。保留 BORE 自身的运行参数默认值；
`kernel.sched_bore=0` 可用于同一内核的对照，但不宣称它与完全未打补丁的
EEVDF 内核等价。性能、功耗和硬件支持以对应版本的运行结果为准。

## 0003 中的本地修复：笔扫描状态恢复

`0003-input-wireless.patch` 里的 `nvt_thp_restore_stylus()` 原先在
`thp_stylus_mode == 0` 时直接返回。但每次固件重新下载都会把 IC 恢复成笔扫描
开启，于是用户态写进 `/proc/nvt_thp_stylus` 的 mode 0 在 resume 或 ESD 恢复后
失效：实测中断从 0/10s 回到约 120/s，`piano-touch-view` 空转 7.6% CPU，
整机空闲功耗随之抬升。

现在该函数与写入路径对称——无条件执行 `nvt_set_custom_cmd(0x04, mode != 0)`，
只有 mode 非零时才继续发 `nvt_thp_set_pen_switch(mode)`。

## 修改补丁后必须重算 `series.json` 的 `tree`

`series.json` 里每一步的 `tree` 都是**累积**结果树——该补丁应用后内核根树的对象
哈希。`tools/prepare_release_kernel.py` 会逐步 `git am` 并与记录值比对，不一致就
中止（CI 也照此执行，报 `Applied patch tree mismatch`）。所以改动任何一个补丁，
它自己的 `tree` 和其后所有补丁的 `tree`、以及 `target_tree` 都会跟着变。

改完后重算，`config/release.json` 的 `kernel.target_tree` 也要同步。只需要基线
提交的对象，用临时索引重放即可，不必检出工作树：

```
git init --bare /tmp/kv && git --git-dir=/tmp/kv fetch --depth=1 <source_url> <base_commit>
export GIT_INDEX_FILE=/tmp/kv.idx
git --git-dir=/tmp/kv read-tree <base_commit>          # 结果应等于 series.json 的 base_tree
for p in patches/linux/7.3/00*.patch; do
    git --git-dir=/tmp/kv apply --cached --whitespace=error "$p" &&
    echo "$p $(git --git-dir=/tmp/kv write-tree)"
done
```

第一步 `read-tree` 的哈希必须等于记录的 `base_tree`，前两个补丁的 `write-tree` 也
必须与记录值一致——这两处对不上说明源基线不对，后面的值不能采信。
