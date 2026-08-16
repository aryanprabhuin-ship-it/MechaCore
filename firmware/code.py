import board
import keypad
import time
import usb_hid

ROWS = (board.GP0, board.GP1, board.GP2, board.GP3, board.GP4)
COLS = (
    board.GP5,
    board.GP6,
    board.GP7,
    board.GP8,
    board.GP9,
    board.GP10,
    board.GP11,
    board.GP12,
    board.GP13,
    board.GP14,
    board.GP15,
    board.GP16,
    board.GP17,
    board.GP18,
)

CONSUMER = 0x10000
PREVIOUS_TRACK = CONSUMER + 0xB6
NEXT_TRACK = CONSUMER + 0xB5
PLAY_PAUSE = CONSUMER + 0xCD
MUTE = CONSUMER + 0xE2
VOLUME_UP = CONSUMER + 0xE9
VOLUME_DOWN = CONSUMER + 0xEA

BASE = (
    (0x35, 0x1E, 0x1F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x2D, 0x2E, 0x2A),
    (0x2B, 0x14, 0x1A, 0x08, 0x15, 0x17, 0x1C, 0x18, 0x0C, 0x12, 0x13, 0x2F, 0x30, 0x31),
    (0x39, 0x04, 0x16, 0x07, 0x09, 0x0A, 0x0B, 0x0D, 0x0E, 0x0F, 0x33, 0x34, 0x28, 0),
    (0xE1, 0x1D, 0x1B, 0x06, 0x19, 0x05, 0x11, 0x10, 0x36, 0x37, 0x38, 0xE5, 0, 0),
    (0xE0, 0xE3, 0xE2, 0x2C, 0xE6, 0xE7, 0, 0xE4, 0, 0, 0, 0, 0, 0),
)

FN_LAYER = (
    (0x29, 0x3A, 0x3B, 0x3C, 0x3D, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x4C),
    (None, PREVIOUS_TRACK, PLAY_PAUSE, NEXT_TRACK, None, None, None, 0x4A, 0x52, 0x4D, 0x4B, None, None, None),
    (None, None, None, None, None, None, None, 0x50, 0x51, 0x4F, 0x4E, None, None, None),
    (None, None, None, None, None, None, None, MUTE, VOLUME_DOWN, VOLUME_UP, PLAY_PAUSE, None, None, None),
    (None, None, None, None, None, None, None, None, None, None, None, None, None, None),
)

FN_POSITION = 62
MENU_KEY = 0x65
FN_DELAY = 0.18


def key_for(position, fn_active):
    row, column = divmod(position, len(COLS))
    if fn_active:
        value = FN_LAYER[row][column]
        if value is not None:
            return value
    return BASE[row][column]


class Hid:
    def __init__(self):
        self.keyboard = None
        self.consumer = None
        self.last_keyboard = None
        self.last_consumer = None

        for device in usb_hid.devices:
            if device.usage_page == 0x01 and device.usage == 0x06:
                self.keyboard = device
            elif device.usage_page == 0x0C:
                self.consumer = device

        if self.keyboard is None or self.consumer is None:
            raise RuntimeError("USB HID devices are missing")

    def send(self, device, report, previous):
        if report == previous:
            return previous, True
        try:
            device.send_report(report)
        except OSError:
            return previous, False
        return report, True

    def update(self, positions, fn_active, extra=()):
        usages = []
        for position in sorted(positions):
            if position != FN_POSITION:
                usage = key_for(position, fn_active)
                if usage:
                    usages.append(usage)
        usages.extend(extra)

        modifiers = 0
        regular = []
        consumer = 0

        for usage in usages:
            if usage >= CONSUMER:
                if consumer == 0:
                    consumer = usage - CONSUMER
            elif 0xE0 <= usage <= 0xE7:
                modifiers |= 1 << (usage - 0xE0)
            elif usage not in regular:
                regular.append(usage)

        keyboard_report = bytearray(8)
        keyboard_report[0] = modifiers
        if len(regular) > 6:
            for index in range(2, 8):
                keyboard_report[index] = 0x01
        else:
            for index, usage in enumerate(regular):
                keyboard_report[index + 2] = usage

        consumer_report = bytes((consumer & 0xFF, consumer >> 8))
        self.last_keyboard, keyboard_ok = self.send(
            self.keyboard,
            bytes(keyboard_report),
            self.last_keyboard,
        )
        self.last_consumer, consumer_ok = self.send(
            self.consumer,
            consumer_report,
            self.last_consumer,
        )
        return keyboard_ok and consumer_ok

    def tap(self, positions, fn_active, usage):
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            if self.update(positions, fn_active, (usage,)):
                break
            time.sleep(0.005)
        time.sleep(0.012)
        self.update(positions, fn_active)


def run():
    matrix = keypad.KeyMatrix(
        row_pins=ROWS,
        column_pins=COLS,
        columns_to_anodes=True,
        interval=0.002,
        max_events=64,
        debounce_threshold=3,
    )
    hid = Hid()
    pressed = set()
    fn_started = None
    fn_active = False
    fn_used = False

    while True:
        now = time.monotonic()
        if fn_started is not None and not fn_active and now - fn_started >= FN_DELAY:
            fn_active = True
            fn_used = True

        event = matrix.events.get()
        while event is not None:
            position = event.key_number

            if position == FN_POSITION:
                if event.pressed:
                    pressed.add(position)
                    fn_started = time.monotonic()
                    fn_active = False
                    fn_used = False
                else:
                    pressed.discard(position)
                    tapped = fn_started is not None and not fn_used
                    fn_started = None
                    fn_active = False
                    hid.update(pressed, fn_active)
                    if tapped:
                        hid.tap(pressed, fn_active, MENU_KEY)
            elif event.pressed:
                pressed.add(position)
                if fn_started is not None:
                    fn_active = True
                    fn_used = True
            else:
                pressed.discard(position)

            event = matrix.events.get()

        hid.update(pressed, fn_active)
        time.sleep(0.001)


if __name__ == "__main__":
    run()
