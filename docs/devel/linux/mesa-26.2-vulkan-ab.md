# Mesa 26.2 的 Turnip 相对 26.1.6 没有带来 Vulkan 跑分提升

2026-11-04，在 `192.168.31.89`（Debian 13，内核
`7.3.0-piano-sunuefi-cachy`）上做的一次 A/B，用来核实「Vulkan 计算跑分提升约
24%」这条来自上游整合方案的说法。

## 结论

同机、同档位、同场景下，Mesa 26.2.6 与镜像里的 26.1.6 在误差内打平：

| GPU 上限 | 26.1.6（中位） | 26.2.6（中位） | 差 |
| --- | --- | --- | --- |
| 1.1 GHz | 8421 FPS | 8433 FPS | +0.1% |
| 342 MHz | 3205 FPS | 3167 FPS | −1.2% |

真正能拉开差距的是电源档：342 MHz → 1.1 GHz 是 **+156%**（3184 → 8168）。
所以 24% 这个量级更可能来自「跑分时机器在哪个功率档 / 基线是发行版自带的旧
Mesa」，不是某个可移植的补丁。

**因此不把 Debian 路径的 Mesa 升到 26.2。** 升级还要连带引入
`libdisplay-info3` 与 wayland 1.26，收益为零。

## 版本选择的说明

Debian 没有 26.2.4 的源包：sid 里是 26.2.5-1 / 26.2.6-1，trixie-backports 停在
26.1.6-1~bpo13+1。实验用 26.2.6（同为 26.2 分支，比 26.2.4 更新）。
Arch 路径的 `linux/bsp/arch/mesa/PKGBUILD` 本来就是 26.2.4，不受影响。

## 方法

1. **先试 sid 的预编译包**（`mesa-vulkan-drivers_26.2.6-1_arm64.deb` 解包到
   `/tmp`，不安装）。缺 `libdisplay-info.so.3` 和 `wl_fixes_interface`，补
   `libdisplay-info3`、`libwayland-client0 1.26` 后能加载，但**报
   `chip_id = E844050001 unsupported`**——上游 26.2.6 仍未收录 A830v1，
   `patches/0001-freedreno-Add-chip-id-support-for-A830v1.patch` 依旧必需。
2. **源码自建 Turnip**：`mesa_26.2.6.orig.tar.xz` + 上面的补丁，只编 Vulkan：

   ```sh
   meson setup build -Dvulkan-drivers=freedreno -Dgallium-drivers= \
     -Dglx=disabled -Degl=disabled -Dgbm=disabled -Dllvm=disabled \
     -Dplatforms=x11,wayland -Dbuild-tests=false
   ninja -C build
   ```

3. 用 `VK_ICD_FILENAMES=<build>/src/freedreno/vulkan/freedreno_icd.json` +
   `LD_LIBRARY_PATH=<build>/src/freedreno/vulkan` 跑，不动系统库。
4. 基准：`vkmark --winsys xcb -b vertex:duration=3 -s 1280x720`，每档各三次。

## 踩到的坑

- **上游打包下载极慢**：`archive.mesa3d.org` 在设备上只有 ~13 KB/s，
  `deb.debian.org` 的大文件也只有 ~45 KB/s；换
  `mirrors.tuna.tsinghua.edu.cn/debian/...` 后 8 秒下完 68 MB。注意个别
  Debian 包名与 soname 不同（`libdisplay-info3` 的文件名带 `+b1`）。
- **meson 会尝试从 GitHub 拉 fallback**（expat、libarchive），在这台机器上必然
  超时。装 `libexpat1-dev`、`libarchive-dev` 让它用系统库。
- **`-Dplatforms=x11,wayland` 需要一整套 xcb dev 包**：
  `libxcb-randr0-dev`、`libxcb-shm0-dev`、`libxcb-xfixes0-dev`、
  `libxcb-present-dev`、`libxcb-sync-dev`、`libxcb-dri3-dev`、`libx11-xcb-dev`、
  `libxcb-keysyms1-dev`。
- **首轮跑到 931 FPS 是冷启动**：新库首次运行要编译 pipeline 缓存，随后
  3148–3376 与旧库一致。基准要先预热一次再取数。
- vkmark 走 Xwayland 需要
  `XAUTHORITY=/run/user/1000/.mutter-Xwaylandauth.* DISPLAY=:0`，并显式
  `--winsys xcb`（默认会试 kms 并报 `getDisplayPropertiesKHR`）。

## 现场留存

设备上 `/home/piano/build-mesa/` 留有源码与构建树（约 960 MB），
`mesa-26.2.6/build/src/freedreno/vulkan/libvulkan_freedreno.so` 可直接复测。
设备补装了 `vulkan-tools`、`vkmark` 与上述构建依赖；系统 Mesa 未被替换。
