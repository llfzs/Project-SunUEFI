#!/bin/bash
# SPDX-License-Identifier: MIT
# diagnose_piano_power.sh — read-only power / heat snapshot for piano.
#
# Collects what actually burns watts on this bring-up machine so the ranking can be
# based on numbers instead of guesswork: package thermals, battery power, cpufreq
# (boost and the per-policy ceiling), cpuidle (are the deep states even registered and
# used?), GPU / DDR / devfreq devices, the panel mode the DPU is scanning, and which
# processes own the CPU time.
#
# It never writes to sysfs, never restarts a service, never sleeps longer than the
# sampling window.  Run it twice with a quiet idle period in between to get a
# meaningful comparison:
#
#   bash tools/diagnose_piano_power.sh > before.txt 2>&1
#   # 现在把刷新率降到 60Hz、echo 0 > /sys/devices/system/cpu/cpufreq/boost
#   sleep 120
#   bash tools/diagnose_piano_power.sh > after.txt 2>&1
#
# Some nodes (debugfs, /proc/interrupts for other users, some thermal trip points)
# need root; the script degrades to a "(no permission)" note instead of failing.
set -u
export LC_ALL=C

SAMPLE_SECONDS="${SAMPLE_SECONDS:-5}"

sec() { printf '\n===== %s =====\n' "$*"; }
show() {  # show <path> [label]
    local p="$1" l="${2:-$1}"
    if [ -r "$p" ]; then
        printf '%-44s %s\n' "$l" "$(cat -- "$p" 2>/dev/null | tr '\n' ' ')"
    else
        printf '%-44s (absent or no permission)\n' "$l"
    fi
}
mm_to_w() {  # mA*uV -> W, empty on garbage
    awk -v i="${1:-}" -v v="${2:-}" 'BEGIN{ if(i+0!=0 && v+0!=0) printf "%.2f", (i/1000.0)*(v/1000000.0); else print "?" }'
}

sec "host"
printf 'uname    : %s\n' "$(uname -a)"
printf 'time     : %s\n' "$(date -Is 2>/dev/null || date)"
printf 'uptime   : %s\n' "$(cat /proc/uptime 2>/dev/null)"
show /proc/cmdline "kernel cmdline"
printf 'governor-boost: '; show /sys/devices/system/cpu/cpufreq/boost

sec "battery / charger (instantaneous power)"
for psu in /sys/class/power_supply/*; do
    [ -d "$psu" ] || continue
    name=$(basename "$psu")
    type=$(cat "$psu/type" 2>/dev/null)
    printf '%s (%s):\n' "$name" "${type:-?}"
    for f in status voltage_now current_now charge_now energy_full power temp \
             charge_full_design voltage_min_design type; do
        [ -r "$psu/$f" ] || continue
        printf '    %-20s %s\n' "$f" "$(cat "$psu/$f" 2>/dev/null | tr '\n' ' ')"
    done
    if [ -r "$psu/current_now" ] && [ -r "$psu/voltage_now" ]; then
        printf '    %-20s %s W (|current|*voltage)\n' "estimate" \
            "$(mm_to_w "$(cat "$psu/current_now")" "$(cat "$psu/voltage_now")")"
    fi
done

sec "thermal zones (millidegrees -> C)"
for tz in /sys/class/thermal/thermal_zone*; do
    [ -d "$tz" ] || continue
    t=$(cat "$tz/temp" 2>/dev/null)
    ty=$(cat "$tz/type" 2>/dev/null)
    if [ -n "${t:-}" ] && [ "$t" != "-1" ]; then
        printf '%-28s %6.1f C\n' "${ty:-$tz}" "$(awk -v x="$t" 'BEGIN{print x/1000}')"
    else
        printf '%-28s (no reading)\n' "${ty:-$tz}"
    fi
done | sort -k2 -r -n
printf 'cooling devices:\n'
for cd in /sys/class/thermal/cooling_device*; do
    [ -d "$cd" ] || continue
    printf '    %-20s cur=%s max=%s\n' "$(cat "$cd/type" 2>/dev/null)" \
        "$(cat "$cd/cur_state" 2>/dev/null)" "$(cat "$cd/max_state" 2>/dev/null)"
done

sec "cpufreq"
for pol in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -d "$pol" ] || continue
    d=$(basename "$pol")
    printf '%s: gov=%s min=%s cur=%s max=%s\n' "$d" \
        "$(cat "$pol/scaling_governor" 2>/dev/null)" \
        "$(cat "$pol/scaling_min_freq" 2>/dev/null)" \
        "$(cat "$pol/scaling_cur_freq" 2>/dev/null)" \
        "$(cat "$pol/scaling_max_freq" 2>/dev/null)"
    printf '    related cpus : %s\n' "$(cat "$pol/related_cpus" 2>/dev/null | tr '\n' ' ')"
    printf '    available    : %s\n' "$(cat "$pol/scaling_available_frequencies" 2>/dev/null | tr '\n' ' ')"
    [ -r "$pol/stats/total_trans" ] && printf '    trans %s  time_in_state %s\n' \
        "$(cat "$pol/stats/total_trans")" "$(tr '\n' ' ' < "$pol/stats/time_in_state" 2>/dev/null)"
done

sec "cpuidle (this is the bring-up trap: no states = no deep idle = warm standby)"
any=0
for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
    [ -d "$cpu/cpuidle" ] || continue
    d=$(basename "$cpu")
    any=1
    printf '%s:\n' "$d"
    for st in "$cpu"/cpuidle/state*; do
        [ -d "$st" ] || continue
        printf '    %-12s lat=%-5s res=%-5s usage=%-9s time=%-10s disabled=%s\n' \
            "$(cat "$st/name" 2>/dev/null)" "$(cat "$st/latency" 2>/dev/null)" \
            "$(cat "$st/residency" 2>/dev/null)" "$(cat "$st/usage" 2>/dev/null)" \
            "$(cat "$st/time" 2>/dev/null)" "$(cat "$st/disable" 2>/dev/null)"
    done
done
[ "$any" = 1 ] || echo "NO cpuidle directory for any cpu -> the CPUs never enter idle states; this alone explains warm standby."
printf '\n/proc/stat sample (%s s):\n' "$SAMPLE_SECONDS"
# /proc/stat cpu fields: name user nice system idle iowait irq softirq steal guest guest_nice
# paste gives sample1 in $1..$11 and sample2 in $12..$22; guest/guest_nice are already
# counted inside user/nice, so they are excluded from the total.
s1=$(grep -E '^cpu([0-9]+)? ' /proc/stat 2>/dev/null)
sleep "$SAMPLE_SECONDS"
s2=$(grep -E '^cpu([0-9]+)? ' /proc/stat 2>/dev/null)
if [ -n "$s1" ] && [ -n "$s2" ]; then
    paste <(printf '%s\n' "$s1") <(printf '%s\n' "$s2") | awk '{
        busy = ($13-$2)+($14-$3)+($15-$4)+($18-$7)+($19-$8)+($20-$9);
        idle = ($16-$5)+($17-$6);
        tot  = busy + idle;
        if (tot > 0) printf "    %-6s busy %5.1f%%  idle %5.1f%%\n", $1, 100*busy/tot, 100*idle/tot;
        else         printf "    %-6s (no jiffies accounted in the window)\n", $1;
    }'
    printf '    iowait is counted as idle above; a busy%% with iowait means the CPU is idle\n'
    printf '    but woken constantly -- on this machine the usual causes are the userspace\n'
    printf '    touch decoder, the pen HID poller and a 120Hz scan out of a non-idle DPU.\n'
else
    echo "    (no /proc/stat cpu lines?)"
fi

sec "devfreq (GPU / DDR / other bus devices)"
for df in /sys/class/devfreq/*; do
    [ -d "$df" ] || continue
    printf '%-24s gov=%-14s cur=%-12s\n' "$(basename "$df")" \
        "$(cat "$df/governor" 2>/dev/null)" "$(cat "$df/cur_freq" 2>/dev/null)"
    [ -r "$df/trans_stat" ] && printf '    trans_stat: %s\n' "$(tr '\n' ' ' < "$df/trans_stat" | cut -c1-200)"
done

sec "display mode (120Hz at 3200x2136 with no VRR/PSR is usually the single biggest load)"
for c in /sys/class/drm/*; do
    [ -e "$c/status" ] || continue
    printf '%-26s %s\n' "$(basename "$c")" "$(cat "$c/status" 2>/dev/null)"
    [ -r "$c/modes" ] && head -2 "$c/modes" | sed 's/^/    mode: /'
done
[ -r /sys/class/drm/card0/device/gpu_busy_percent ] && \
    show /sys/class/drm/card0/device/gpu_busy_percent "gpu_busy_percent"
show /sys/module/drm/parameters/vblankoffdelay "drm vblankoffdelay"

sec "remoteproc (adsp running = pmic_glink + PD + port notify, a fixed bring-up cost)"
for rp in /sys/class/remoteproc/remoteproc*; do
    [ -d "$rp" ] || continue
    printf '%-12s %-22s\n' "$(cat "$rp/name" 2>/dev/null)" "$(cat "$rp/state" 2>/dev/null)"
done

sec "who owns the CPU (cumulative time, since boot)"
ps -eo pid,comm,time,%cpu --sort=-time 2>/dev/null | head -18
printf '\npiano services:\n'
for s in /proc/[0-9]*; do
    [ -r "$s/comm" ] || continue
    case "$(cat "$s/comm" 2>/dev/null)" in
        piano-*|touch-input|gsd-*|gnome-shell|pipewire*|Xorg|wayland*)
            printf '    %-22s %s\n' "$(cat "$s/comm")" "$(tr '\0' ' ' < "$s/cmdline" 2>/dev/null | cut -c1-70)";;
    esac
done | sort -u

sec "wakeup sources (needs root; debugfs)"
if [ -r /sys/kernel/debug/wakeup_sources ]; then
    sort -k5 -r -n /sys/kernel/debug/wakeup_sources 2>/dev/null | head -15 |
        awk '{printf "    %-26s active_count=%-8s total_time_ms=%s\n", $1,$5,$6}'
else
    echo "(no permission or debugfs not mounted — re-run with sudo for this section)"
fi

sec "suspend / idle hints"
show /sys/power/state "pm states"
show /sys/power/sync_resume "sync_resume"
[ -r /sys/kernel/debug/suspend_stats ] && cat /sys/kernel/debug/suspend_stats
printf '\nDone. This script made no changes to the system.\n'
