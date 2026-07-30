# Kindle PW4 Firmware Downgrade: 5.16.x to 5.16.2.1.1

Jailbreak survives downgrade (JB payload in /mnt/us). KUAL survives. Extensions need ABI-matched reinstalls - Amazon switched to hard-float ABI at 5.16.3.

## ABI Break

Firmware <= 5.16.2.1.1: soft-float (arm-linux-gnueabi). Firmware >= 5.16.3: hard-float (arm-linux-gnueabihf). Binaries from one ABI crash on the other.

## Procedure

1. Confirm JB functional: ;log mrpi responds
2. Download firmware: https://s3.amazonaws.com/firmwaredownloads/update_kindle_all_new_paperwhite_v2_5.16.2.1.1.bin (NOT update_kindle_10th)
3. Download AllowDowngrade.sh: https://kindlemodding.org/firmware-and-flashing/downgrading/AllowDowngrade.sh
4. Back up /mnt/us/ to PC
5. Airplane Mode ON
6. KUAL -> Rename OTA Binaries -> Restore
7. Copy AllowDowngrade.sh to /mnt/us/documents/
8. Eject, unplug, open "Allow Downgrade" booklet
9. Plug in, copy .bin to root
10. Hold power until restart. Wait for install.

Post: If white screen, DO_FACTORY_RESTORE empty file + force reboot. Verify FW 5.16.2.1.1. Re-block OTA. Reinstall soft-float extensions. Recompile touch_tap with arm-linux-gnueabi-gcc -static.

## Sources

- https://kindlemodding.org/firmware-and-flashing/downgrading/
- https://github.com/notmarek/LanguageBreak
- https://www.mobileread.com/forums/showthread.php?t=357058
- https://github.com/koreader/koreader/discussions/11298
