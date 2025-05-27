import board
import time
import busio as bus
import digitalio as io
import json
import asyncio
import adafruit_rfm69 as rfm69 #not sensed by intellisense
import adafruit_nunchuk as nc

print(f"Starting code at {time.monotonic()} seconds")

#node ids for keying messages
robot_node_ID = 69
transmitter_node_ID = 42

#vars for inputs to robot
trans_x = 0.0
trans_y = 0.0
enable = False
vel_sp = False

#used for toggles on enable and vel_sp
last_enable = False

#SPI bus stuff
spi = bus.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
cs = io.DigitalInOut(board.D9)
rst = io.DigitalInOut(board.D10)

#I2C bus stuff
i2c = bus.I2C(board.SCL, board.SDA)
nunchuck = nc.Nunchuk(i2c)

#status LED for debug
status_led = io.DigitalInOut(board.LED)
status_led.direction = status_led.direction.OUTPUT

#start radio
try:
    radio_rfm69 = rfm69.RFM69(spi, cs, rst, 915)
    radio_rfm69.tx_power = 5
    print(f"Radio boot successful at {time.monotonic()} seconds")
except RuntimeError as e:
    while True:
        for n in range(0, 6):
            status_led.value = not status_led.value
            time.sleep(0.5)
        time.sleep(3)

#pulse debug LED to indicate successful start
for n in range(0, 10):
    status_led.value = not status_led.value
    time.sleep(0.05)

#used to interpolate joystick in correct interval
def interpolate(value, in_min, in_max, out_min, out_max, deadzone):
    center = 127
    if abs(value - center) < deadzone:
        return 0.0
    else:
        return round(out_min + (value - in_min) * (out_max - out_min) / (in_max - in_min), 2)
    
#used to update io data
async def run_io():

    #globals
    global trans_x, trans_y, enable, vel_sp, last_enable, last_vel_sp
    
    #check button and joystick states
    trans_x = interpolate(nunchuck.joystick.x, 0, 255, -1, 1, 0.05)
    trans_y = interpolate(nunchuck.joystick.y, 0, 255, -1, 1, 0.05)
    if nunchuck.buttons.C and not last_enable:
        enable = not enable
    last_enable = nunchuck.buttons.C
    vel_sp = nunchuck.buttons.Z

#use to transmit data
async def transmit():

    #format data into json, keep lengths down to limit assertion errors
    data = {
        "id": transmitter_node_ID, #indicates this node sent the packet
        "tx": trans_x, #translation X
        "ty": trans_y, #translation Y
        "en": int(enable), #enable / disable
        "sp": int(vel_sp) #high or low setpoint
    }

    #dump json data into packet and send in byte array
    #assertion error will occur if payload > 62 bytes
    try:
        radio_rfm69.send(bytes(json.dumps(data), "utf-8"))
    except AssertionError as e:
        print(f"Message send failure, likely byte overflow. {e}")

    #break
    await asyncio.sleep(0)

#use your imagination
async def blink():

    #blink
    status_led.value = True
    time.sleep(0.025)
    status_led.value = False
    
    #break
    await asyncio.sleep(0)

#do i really need to explain?
async def main():
    blink_time_last = time.monotonic()
    while True:

        #clear task list, check time
        tasks = []
        time_now = time.monotonic()

        #always add transmit and io checks to schedule
        tasks.append(run_io())
        tasks.append(transmit())

        #only run 1 time per second
        if time_now - blink_time_last >= 1:
            blink_time_last = time.monotonic()
            tasks.append(blink())

        #gather tasks and run
        await asyncio.gather(*tasks)

#use your brain, dude
asyncio.run(main())

