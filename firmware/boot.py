import supervisor
import usb_hid

supervisor.set_usb_identification(
    manufacturer="aryanprabhuin-ship-it",
    product="MechaCore",
)
usb_hid.enable((usb_hid.Device.KEYBOARD, usb_hid.Device.CONSUMER_CONTROL))
