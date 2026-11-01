# gnome-shell patches

These patches change `js/ui/keyboard.js` of the running GNOME Shell. Since GNOME Shell 47
that file is no longer installed on disk: it is compiled into the `js-resources` GResource
linked into `libshell-<api>.so`, so verification has to look inside the binary (see the
last section).

## Read this first: nothing in the image pipeline consumes this directory

`linux/desktops/gnome/patches/` has three sub-directories and only two of them are
wired into a build:

| directory | consumed by | effect |
| --- | --- | --- |
| `mutter/` | `tools/build_mutter_packages.py` (`PATCHES`), `tools/build_nyarch_rootfs.py` | lands in the mutter package / rootfs |
| `control-center/` | `tools/build_nyarch_rootfs.py` | lands in the rootfs |
| `gnome-shell/` | `tools/build_gnome_shell_packages.py` (Debian) + `tools/build_release_rootfs.py` installs `build/gnome-shell/runtime` | lands in the gnome-shell package; the on-screen-keyboard fix now reaches the tablet image |

A patch dropped in this directory therefore never reaches the tablet. That is why the
on-screen-keyboard fix did not change anything on the device: it was not overridden or
reverted, it was simply never packaged. Grep before you assume otherwise:

```sh
grep -rn "patches/gnome-shell" . --include="*.py" --include="*.sh" --include="PKGBUILD"
```

A Debian packaging channel now exists: `tools/build_gnome_shell_packages.py` builds the
patched `gnome-shell`/`gnome-shell-common` packages (mirroring `build_mutter_packages.py`)
and `tools/build_release_rootfs.py` installs them into the release rootfs when
`desktop == 'gnome'`. There is still no Arch/Nyarch `PKGBUILD` for gnome-shell
(compare `linux/desktops/gnome/arch/mutter/PKGBUILD`); Nyarch builds still need a PKGBUILD
that applies these three patches, or a manual `apt-get source gnome-shell` rebuild as below.

## Patches here

- `0001-keyboard-open-on-enable-while-focused.patch` — the real fix.
  `_syncEnabled()` only ever constructed the `Keyboard` actor; on Wayland the actor is
  opened exclusively by the input controller's `panel-state` notification, and the
  focus-changed path is guarded by `!Meta.is_wayland_compositor()`. If the actor did not
  exist yet when the field took focus, that notification was delivered to nobody and is
  never replayed. Tap the phone-number field, no keyboard; paste, mutter notifies again
  and it appears.
- `0002-osk-purpose-layout-fallback.patch` — defensive. The reported symptom is not
  caused by it (the phone layout renders fine), but the purpose branch of `_updateLayout()`
  really had no try/catch and no fallback while the password branch did.
  It replaces the old `0001-osk-purpose-layout-fallback.patch` — a zero-byte duplicate
  that has since been deleted so the directory does not keep two copies of one patch.
- `0003-osk-missing-level-guard.patch` — the empty-keyboard fix. `_setActiveLevel()`
  assigns `layers[activeLevel]` to `_currentPage` without checking the layer exists, and
  the purpose layouts have exactly one level (`phone.json` defines `default`, no `shift`).
  A stale `shift` request therefore sets `_currentPage` to `undefined`; the `connect()`
  on the next line throws, `_updateCurrentPageVisible()` never runs, and since
  `_updateLayout()` hides every layer it builds, the keyboard is open but shows **no keys
  at all**. That is what a phone-number field in a browser produced: 102 consecutive
  `TypeError: this._currentPage is undefined` lines in the journal between 13:49 and
  13:53. The patch also drops the pending `surrounding-text-set` request when the layout
  changes (the handler outlives the layout it was registered for) and guards
  `maybeHandleEvent()` against a null event actor.

All three are written against the `gnome-48` branch of GNOME Shell (the Debian 13 source is
`gnome-shell 48.7-0+deb13u2`). 0001 and 0002 were verified by applying them in order to a
pristine `js/ui/keyboard.js` with `patch --forward --fuzz=0 -p1` — clean, no offsets on the
first hunk of each — and `node --check` on the result. 0003 was verified the same way on
top of the tree 0001+0002 produce (the exact file the shipped `48.7-0+deb13u2+sunuefi1`
package carries, extracted from `libshell-16.so`): all five hunks apply with `--fuzz=0`,
no rejects, and the result passes `node --check`.

## Confirm the diagnosis without rebuilding anything

```sh
gsettings set org.gnome.desktop.a11y.applications screen-keyboard-enabled true
# tap the phone-number field now; the keyboard must appear
gsettings set org.gnome.desktop.a11y.applications screen-keyboard-enabled false
```

If it appears with the setting on and not with it off, the gate is `_syncEnabled()` and
patch 0001 addresses the right line. To find out which device is stealing
"last input device" (the pen's tablet-tool uinput, a keyboard touchpad, a Bluetooth mouse):

```sh
sudo libinput list-devices | grep -E "Device:|Capabilities:"
sudo libinput debug-events   # do not touch the screen, watch for events on their own
```

## Debian (the session in the screenshots)

```sh
sudo apt-get source gnome-shell
cd gnome-shell-48.*
cp ../../linux/desktops/gnome/patches/gnome-shell/000*.patch debian/patches/
printf '0001-keyboard-open-on-enable-while-focused.patch\n0002-osk-purpose-layout-fallback.patch\n0003-osk-missing-level-guard.patch\n' >> debian/patches/series
sudo apt-get build-dep gnome-shell
dpkg-buildpackage -us -uc -b
sudo apt install ../gnome-shell_*.deb
sudo apt-mark hold gnome-shell   # otherwise the next upgrade silently drops the fix
```

## Arch / Nyarch

Follow `linux/desktops/gnome/arch/mutter/PKGBUILD` as the shape: add all three patches to
`source=()` and, in `prepare()`,

```sh
patch --forward --fuzz=0 -Np1 -i ../0001-keyboard-open-on-enable-while-focused.patch
patch --forward --fuzz=0 -Np1 -i ../0002-osk-purpose-layout-fallback.patch
patch --forward --fuzz=0 -Np1 -i ../0003-osk-missing-level-guard.patch
```

Either way, after installing, log out and back in (gnome-shell does not reload `js/`),
then check the patch really reached the binary.

GNOME Shell 47 stopped installing `js/` as plain files. `js/js-resources.gresource.xml`
is compiled into a GResource (prefix `/org/gnome/shell`, uncompressed) and meson links
it into `libshell-<api>.so` and `gnome-shell-perf-helper`, so
`/usr/share/gnome-shell/js/ui/keyboard.js` does not exist on Debian 13 at all — grepping
for that path only proves the path is missing, not that the patch is:

```sh
grep -al "inputMethod?.currentFocus" \
    /usr/lib/gnome-shell/libshell-*.so /usr/lib/*/gnome-shell/libshell-*.so 2>/dev/null
```

Note the two paths: Debian 13 arm64 installs the library as
`/usr/lib/gnome-shell/libshell-16.so`, **without** a multiarch directory, so the
`/usr/lib/*/` form alone matches nothing and looks like a missing patch. Empty output from
both means the running shell does not carry the fix. That is the same check
`tools/build_gnome_shell_packages.py` runs on the built `.deb` (it records the carrier
file as `verified_in_package` in `build/gnome-shell/SOURCE.json`), extended with a third
marker — `_clearSurroundingTextRequest` — for patch 0003.
