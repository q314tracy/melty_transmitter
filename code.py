import board
import time
import busio as bus
import digitalio as io
import json
import asyncio
import displayio
import terminalio
from i2cdisplaybus import I2CDisplayBus
import adafruit_rfm69 as rfm69
import adafruit_nunchuk as nc
from adafruit_display_text import label
import adafruit_displayio_ssd1306 as ssd1306

print(f"Starting code at {time.monotonic()} seconds")

#release display between code boots
displayio.release_displays()

#node ids for keying messages
robot_node_ID = 69
transmitter_node_ID = 42

#vars for inputs to robot
trans_x = 0.0
trans_y = 0.0
enable = False
vel_sp = False

#vars for telemetry from robot
bat_volts = 0.0
angular_vel = 0.0
angular_dir = 0.0

#status LED for debug
status_led = io.DigitalInOut(board.LED)
status_led.direction = status_led.direction.OUTPUT

#SPI bus
spi = bus.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
cs = io.DigitalInOut(board.D9)
rst = io.DigitalInOut(board.D10)
print(f"SPI bus boot successful at {time.monotonic()} seconds")

#start radio
try:
    radio_rfm69 = rfm69.RFM69(spi, cs, rst, 915)
    radio_rfm69.tx_power = 5
    #radio_rfm69.timeout = 0.050
    print(f"SPI device RFM69HCW radio present at {time.monotonic()} seconds")
except RuntimeError as e:
    while True:
        for n in range(0, 6):
            status_led.value = not status_led.value
            time.sleep(0.5)
        time.sleep(3)

#I2C bus
i2c = bus.I2C(board.SCL, board.SDA, frequency=400_000)
print(f"I2C bus boot successful at {time.monotonic()} seconds")

#I2C devices
nunchuk = nc.Nunchuk(i2c)
print(f"I2C device nunchuk present at {time.monotonic()} seconds")
display_bus = I2CDisplayBus(i2c, device_address=0x3D)
display = ssd1306.SSD1306(display_bus, width=128, height=64)
text_group = displayio.Group()
display.root_group = text_group
print(f"I2C device OLED present at {time.monotonic()} seconds")

#display labels
tx_text = label.Label(terminalio.FONT, text="tx: ***", x=0, y=5)
text_group.append(tx_text)
ty_text = label.Label(terminalio.FONT, text="ty: ***", x=0, y=15)
text_group.append(ty_text)
en_text = label.Label(terminalio.FONT, text="en: ***", x=0, y=25)
text_group.append(en_text)
sp_text = label.Label(terminalio.FONT, text="sp: ***", x=0, y=35)
text_group.append(sp_text)
lt_text = label.Label(terminalio.FONT, text="lt: ***", x=0, y=55)
text_group.append(lt_text)
av_text = label.Label(terminalio.FONT, text="av: ***", x=64, y=5)
text_group.append(av_text)
ad_text = label.Label(terminalio.FONT, text="ad: ***", x=64, y=15)
text_group.append(ad_text)
bv_text = label.Label(terminalio.FONT, text="bv: ***", x=64, y=25)
text_group.append(bv_text)

#used to transform raw joystick to [-1, 1] interval
def normalize(value):
    normalized_value = round((value / 128) - 1, 2)
    if abs(normalized_value) > 0.05:
        return normalized_value
    else:
        return 0.0

#used to update io data
async def run_io():

    #globals
    global trans_x, trans_y, enable, vel_sp

    #update data
    trans_x = normalize(nunchuk.joystick.x)
    trans_y = normalize(nunchuk.joystick.y)
    enable = nunchuk.buttons.Z
    vel_sp = nunchuk.buttons.C
    
    #break
    await asyncio.sleep(0)

#use to receive data
async def receive():

    #globals
    global trans_x, trans_y, enable, vel_sp, angular_vel, bat_volts, angular_dir

    #receive packet, check node id, write data if good
    packet = radio_rfm69.receive()
    if packet is not None:
        data = json.loads(packet.decode("utf-8"))
        if data["id"] == robot_node_ID:
            angular_vel = data["av"]
            angular_dir = data["ad"]
            bat_volts = data["bv"]
    else:
        #print("no packet")
        pass

    #break
    await asyncio.sleep(0)


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
    time.sleep(0.01)
    status_led.value = False

    #break
    await asyncio.sleep(0)

#update that shizzle yo
async def oled_update():
    tx_text.text = f"tx: {trans_x}"
    ty_text.text = f"ty: {trans_y}"
    av_text.text = f"av: {angular_vel}"
    ad_text.text = f"ad: {angular_dir}"
    bv_text.text = f"bv: {bat_volts}"

    if enable: en_text.text = f"en: YES"
    else: en_text.text = f"en: NO"
    if vel_sp: sp_text.text = f"sp: FAST"
    else: sp_text.text = f"sp: SLOW"

    await asyncio.sleep(0)

#do i really need to explain?
async def main():
    print(f"Main loop start at {time.monotonic()} seconds")
    blink_time_last = time.monotonic()
    oled_time_last = time.monotonic()
    main_loop_time_last = time.monotonic()
    while True:

        #clear task list, check time
        tasks = []
        time_now = time.monotonic()

        #only run 1 time per second
        if time_now - blink_time_last >= 1:
            blink_time_last = time.monotonic()
            tasks.append(blink())

        #schedule most tasks on 100ms interval to speed up loop time
        if time_now - oled_time_last >= 0.1:
            oled_time_last = time.monotonic()
            tasks.append(run_io())
            tasks.append(oled_update())
            #tasks.append(transmit())
            lt_text.text = f"lt: {round(time_now - main_loop_time_last, 5)}"
        
        
        tasks.append(receive())
        #reset loop time timer
        main_loop_time_last = time.monotonic()

        #gather tasks and run
        await asyncio.gather(*tasks)

#use your brain, dude
asyncio.run(main())

