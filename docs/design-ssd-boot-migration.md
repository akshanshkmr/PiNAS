# Design: SD → SSD boot migration (plus SSD image backup)

Status: **proposal / awaiting hardware** · Last updated: 2026-07-11

The SD card is the single weakest link in a PiNAS install — roughly 100–1000×
more likely to fail than a healthy RAID of SSDs. Once an SSD is present in the
Pironman (M.2 NVMe) or on the USB bus, the sensible shape is:

- Boot from the **SSD** as primary
- Keep the **SD** in the slot as an emergency fallback (fresh Pi OS)
- **Snapshot the SSD** to the NAS instead of snapshotting the SD

This document plans the migration wizard and the replacement of the current
SD-image backup feature. It **is not implemented** because this dev Pi has no
SSD attached; building it blind is one wrong `PARTUUID` away from a bricked
boot, so we wait for hardware.

---

## 1. Prerequisites

Detected at wizard start:

- Pi 5 (the Pi 4 EEPROM boot order works differently, ignore for MVP).
- A single, non-boot block device that is **NVMe** (`tran=nvme`) or **USB**
  attached and non-rotational (`rota=0`).
- Target size ≥ source size × 1.05 (small safety margin).
- No mounted RAID member on the target (would ruin the array).
- Enough free space on the running SD (nothing to check — we don't write to
  the SD during clone).
- `rpi-eeprom-config`, `rsync`, `sfdisk`, `mkfs.ext4`, `mkfs.vfat`, `blkid`
  present — `setup.sh` will install any that are missing.

If more than one candidate SSD exists, list them and require the user to
choose. **Never guess.**

## 2. The plan (idempotent, resumable, verified before commit)

Each step is a discrete, restartable job with its own log entry so a failure
at step N leaves the system bootable from SD and step N is safe to redo.

1. **Snapshot the SD state** for reference: `lsblk -J`, `blkid`,
   `/boot/firmware/cmdline.txt`, `/etc/fstab`, `raspi-config nonint
   get_boot_order`.
2. **Partition the target** with the same layout as the SD:
   - `p1`: 512 MB FAT32 boot partition (`/boot/firmware`)
   - `p2`: ext4 root, sized to fill the rest of the SSD
   - `sfdisk` with a scripted partition table; save the script for diffing.
3. **Filesystems**:
   - `mkfs.vfat -F32 -n bootfs <target>p1`
   - `mkfs.ext4 -L rootfs <target>p2`
   - Record fresh **PARTUUID** for each partition.
4. **Mount target** at a fresh `/mnt/pinas-migrate/{boot,root}`.
5. **rsync clone** (twice, second pass while the system is otherwise quiet):
   - `sudo rsync -aHAX --numeric-ids --info=progress2 --delete \`
     `--exclude={/dev/*,/proc/*,/sys/*,/tmp/*,/run/*,/mnt/*,/media/*,`
     `/lost+found,/var/cache/apt/archives/*.deb,/var/tmp/*,`
     `/mnt/pinas-migrate/*} / /mnt/pinas-migrate/root/`
   - `sudo rsync -aHAX /boot/firmware/ /mnt/pinas-migrate/boot/`
6. **Rewrite bootloader refs** on the *target* (not the running SD):
   - `/mnt/pinas-migrate/boot/cmdline.txt`: replace old root PARTUUID with new
     one via `sed`. Verify by re-parsing.
   - `/mnt/pinas-migrate/root/etc/fstab`: replace the two SD PARTUUIDs (root
     and boot) with the new ones. Verify.
   - Preserve everything else exactly.
7. **Reference-check verification** — before touching the EEPROM, mount the
   target root read-only and confirm:
   - `cmdline.txt` on target references a `root=PARTUUID=…` that exists.
   - Target `fstab` has both new PARTUUIDs.
   - `/boot/firmware/config.txt` on target still resolves.
   - The kernel image is present at the expected paths.
   - The target root contains `/sbin/init` or `/usr/lib/systemd/systemd`.
   - **Fail closed** on any mismatch — do not proceed.
8. **Boot order** (Pi 5 EEPROM):
   - Query current: `rpi-eeprom-config | grep BOOT_ORDER`.
   - For NVMe primary + SD fallback: `BOOT_ORDER=0xf461` (docs).
   - For USB primary + SD fallback: `BOOT_ORDER=0xf14`.
   - Write via `rpi-eeprom-config --apply`.
   - Save the old value to `data/eeprom-pre-migrate.txt` for rollback.
9. **Prompt the user to reboot from the UI**.

## 3. Two-phase commit + rollback

The riskiest step is 8 (writing the EEPROM). Everything before it is safe —
the SD is untouched and the target SSD just has a copy of the OS on it.

- If the migration is aborted before step 8: no state on the SD or EEPROM has
  changed. Unmount, done.
- If step 8 succeeds but the Pi doesn't boot from SSD: the fallback order
  drops it back to SD automatically. On the next successful SD boot, the UI
  shows "Migration reverted — SSD boot failed" and offers to reset the EEPROM
  back to the pre-migration value.
- If the user wants to explicitly revert: a **Rollback** action reads
  `data/eeprom-pre-migrate.txt` and writes it back.

## 4. UI

New "Boot device" section in the **Storage** tab (or a dedicated
"Migration" panel — decide at implementation time):

- Current boot device: `/dev/mmcblk0` (32 GB, SD)
- Detected SSDs: [ dropdown ]
- **Wizard button** → modal with step-by-step live log, progress bar for
  rsync, big red "Apply and switch boot order" gate at the end
- After successful migration:
  - Card shows "Booted from SSD ✓" and offers to disable the SD-image backup
- Rollback link (visible if a pre-migration EEPROM state is saved)

## 5. SSD image backup — replaces SD backup

Once boot lives on the SSD, we snapshot the SSD instead. Implementation is
essentially the current SD-image backup with:

- Source device = whatever `findmnt -n -o SOURCE /` resolves to (the whole
  disk, so `/dev/nvme0n1` not `/dev/nvme0n1p2`).
- Output: `sd-*.img.gz` → `ssd-*.img.gz` on the NAS, same rotation.
- Full SSD is much bigger than an SD; add a quick "used blocks only" mode
  using `partclone.ext4` when the target root is ext4 — much smaller archives
  and much faster than raw `dd`.
- **Retire the SD backup UI** (or hide it once the boot device isn't the SD).

## 6. Testing plan (when hardware is present)

Before shipping:

1. Attach a spare SSD (throwaway data), sacrifice-test.
2. Run migration end-to-end; verify boot from SSD.
3. Simulate cmdline.txt PARTUUID mistake to confirm the pre-EEPROM check
   catches it.
4. Simulate mid-rsync abort; confirm re-run resumes cleanly.
5. Simulate SSD unplug post-migration; confirm SD fallback boots and the UI
   surfaces "Rollback available."
6. Run full-restore from SSD image on a fresh spare SSD.

## 7. What we would drop

- The current SD-image backup UI panel and its endpoint are still useful
  right up to the day the migration ships — cheap insurance for a
  still-SD-booted Pi. Retire them in the *same* release that lands the
  migration + SSD backup, not before.
- The `.pinas-config/` config backup stays valuable regardless — it's tiny,
  survives any boot-device swap, and enables the zero-click restore on a
  fresh install.

## 8. Open decisions

- **Wizard placement**: separate top-level "Migration" panel, or under
  Storage? Storage feels correct (it's about disks) but the wizard is a
  destination in its own right.
- **SSD image backup format**: raw `dd | pigz` (universal, works on any
  device) vs `partclone.ext4` (skips unused blocks, ~10× smaller). Probably
  start with raw and add partclone as an option later.
- **How to disable SD backup automatically post-migration**: hide the panel
  entirely, or leave it as "legacy, not recommended"? Leaning hide.
- **Growing root**: `sfdisk` writes a partition table that fills the target;
  `resize2fs` on the mounted target extends the filesystem. Do this during
  migration (simpler) or leave as a manual step (safer)? Leaning during.

---

## Why this isn't built yet

Every step above needs to run against real hardware to be trusted. There is
no `mmcblk0` → `nvme0n1` translation trick that survives contact with a
mismatched EEPROM or a stale PARTUUID reference. The Pi in front of us has
no SSD (`lsblk` shows only `mmcblk0` + `zram0`), so shipping this now would
be a demo, not a feature.

**Implementation trigger**: as soon as an NVMe or USB SSD is attached to
this Pi (or a sibling Pi we can sacrifice), pull this doc and start on §2.
