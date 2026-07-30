/*
 * touch_tap.c — Minimal evdev touch reader for Kindle
 *
 * Reads /dev/input/event* for ABS touch events,
 * scales coordinates to screen pixels, debounces,
 * and prints "x y\n" on tap release.
 *
 * Compile (cross-compile for Kindle ARM):
 *   zig cc -target arm-linux-musleabi -O2 -static -o touch_tap touch_tap.c
 *
 * Output: "x y\n" on each tap release (stdout, line-buffered)
 *         Errors go to stderr
 *
 * The only C code needed in the hybrid shell architecture.
 * Compiled once, never modified for new views.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <time.h>
#include <sys/ioctl.h>
#include <linux/input.h>

#define MAX_DEVICES 16
#define DEBOUNCE_MS 700
#define SCREEN_W 1072
#define SCREEN_H 1448

static int devices[MAX_DEVICES];
static int dev_count = 0;

struct abs_range {
    int min, max;
    int has_range;
};

static struct abs_range dev_x[MAX_DEVICES];
static struct abs_range dev_y[MAX_DEVICES];

static int scale(int value, int min, int max, int screen_size) {
    /* On PW4, EVIOCGABS returns x:0-0 y:0-0 — the device reports raw
     * pixel coordinates, not a hardware range like 0-4095. When
     * min>=max, skip scaling and just clamp to screen bounds. */
    if (max <= min) {
        if (value < 0) return 0;
        if (value >= screen_size) return screen_size - 1;
        return value;
    }
    long scaled = (long)(value - min) * (long)(screen_size - 1) / (long)(max - min);
    if (scaled < 0) scaled = 0;
    if (scaled >= screen_size) scaled = screen_size - 1;
    return (int)scaled;
}

/* Use CLOCK_MONOTONIC — immune to NTP clock jumps after wake.
 * gettimeofday breaks when NTP syncs (clock jumps forward/backward),
 * causing debounce to either drop all taps or fire them all at once. */
static long long now_ms() {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

int main() {
    int i;
    struct input_absinfo absinfo;

    /* Scan /dev/input/event0..15 for touch devices */
    for (i = 0; i < 16; i++) {
        char path[48];
        snprintf(path, sizeof(path), "/dev/input/event%d", i);
        int fd = open(path, O_RDONLY | O_NONBLOCK);
        if (fd < 0) continue;

        int has_x = 0, has_y = 0;
        if (ioctl(fd, EVIOCGABS(ABS_X), &absinfo) == 0) {
            dev_x[dev_count].min = absinfo.minimum;
            dev_x[dev_count].max = absinfo.maximum;
            dev_x[dev_count].has_range = 1;
            has_x = 1;
        } else if (ioctl(fd, EVIOCGABS(ABS_MT_POSITION_X), &absinfo) == 0) {
            dev_x[dev_count].min = absinfo.minimum;
            dev_x[dev_count].max = absinfo.maximum;
            dev_x[dev_count].has_range = 1;
            has_x = 1;
        }

        if (ioctl(fd, EVIOCGABS(ABS_Y), &absinfo) == 0) {
            dev_y[dev_count].min = absinfo.minimum;
            dev_y[dev_count].max = absinfo.maximum;
            dev_y[dev_count].has_range = 1;
            has_y = 1;
        } else if (ioctl(fd, EVIOCGABS(ABS_MT_POSITION_Y), &absinfo) == 0) {
            dev_y[dev_count].min = absinfo.minimum;
            dev_y[dev_count].max = absinfo.maximum;
            dev_y[dev_count].has_range = 1;
            has_y = 1;
        }

        if (!has_x || !has_y) { close(fd); continue; }

        /* Grab the device exclusively — check for failure.
         * If EVIOCGRAB fails, events go to both us and the framework,
         * causing double-handling. */
        if (ioctl(fd, EVIOCGRAB, 1) < 0) {
            fprintf(stderr, "touch_tap: WARNING: EVIOCGRAB failed on %s: %s\n",
                    path, strerror(errno));
        }
        devices[dev_count] = fd;
        fprintf(stderr, "touch_tap: found touch device at %s (x:%d-%d y:%d-%d)\n",
                path, dev_x[dev_count].min, dev_x[dev_count].max,
                dev_y[dev_count].min, dev_y[dev_count].max);
        dev_count++;
        if (dev_count >= MAX_DEVICES) break;
    }

    if (dev_count == 0) {
        fprintf(stderr, "touch_tap: no touch device found\n");
        return 1;
    }

    int touch_x = -1, touch_y = -1, has_x = 0, has_y = 0, was_down = 0;
    long long last_tap_ms = 0;

    setvbuf(stdout, NULL, _IOLBF, 0);

    while (1) {
        for (i = 0; i < dev_count; i++) {
            struct input_event ev;
            ssize_t n;

            while ((n = read(devices[i], &ev, sizeof(ev))) == sizeof(ev)) {
                if (ev.type == EV_ABS) {
                    if (ev.code == ABS_X || ev.code == ABS_MT_POSITION_X) {
                        touch_x = scale(ev.value, dev_x[i].min, dev_x[i].max, SCREEN_W);
                        has_x = 1; was_down = 1;
                    } else if (ev.code == ABS_Y || ev.code == ABS_MT_POSITION_Y) {
                        touch_y = scale(ev.value, dev_y[i].min, dev_y[i].max, SCREEN_H);
                        has_y = 1; was_down = 1;
                    } else if (ev.code == ABS_MT_TRACKING_ID) {
                        if (ev.value < 0) {
                            /* MT protocol: TRACKING_ID -1 = finger lifted.
                             * This is a reliable release signal, unlike SYN_REPORT
                             * which can fire with stale coordinates. */
                            if (was_down && has_x && has_y) {
                                long long now = now_ms();
                                if (now - last_tap_ms >= DEBOUNCE_MS) {
                                    printf("%d %d\n", touch_x, touch_y);
                                    fflush(stdout);
                                    last_tap_ms = now;
                                }
                            }
                            was_down = 0; has_x = 0; has_y = 0;
                        } else {
                            was_down = 1;
                        }
                    }
                } else if (ev.type == EV_KEY && (ev.code == BTN_TOUCH || ev.code == BTN_LEFT)) {
                    if (ev.value > 0) { was_down = 1; }
                    else if (ev.value == 0 && was_down && has_x && has_y) {
                        long long now = now_ms();
                        if (now - last_tap_ms >= DEBOUNCE_MS) {
                            printf("%d %d\n", touch_x, touch_y);
                            fflush(stdout);
                            last_tap_ms = now;
                        }
                        was_down = 0; has_x = 0; has_y = 0;
                    }
                }
                /* NOTE: No SYN_REPORT tap emission. SYN_REPORT can fire with
                 * stale coordinates if the touch sequence doesn't use BTN_TOUCH.
                 * Only BTN_TOUCH release and MT TRACKING_ID=-1 are reliable. */
            }

            /* Log read errors (device removed, etc.) */
            if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
                fprintf(stderr, "touch_tap: read error on device %d: %s\n",
                        i, strerror(errno));
            }
        }
        usleep(100000);
    }

    for (i = 0; i < dev_count; i++) { ioctl(devices[i], EVIOCGRAB, 0); close(devices[i]); }
    return 0;
}
