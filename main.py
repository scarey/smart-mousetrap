# OTA:file:main.py
# OTA:reboot:true

# MIT License (MIT)
# Copyright (c) 2024 Stephen Carey
# https://opensource.org/licenses/MIT
import json

import uasyncio as asyncio
from machine import Pin

from mqtt_as import MQTTClient
from mqtt_local import config

VERSION = "1.0"

BASE_TOPIC = 'esp32/mousetrap'
CONFIG_TOPIC = f'{BASE_TOPIC}/config'
AVAILABLE_TOPIC = f'{BASE_TOPIC}/availability'
TRAP_TOPIC = f'{BASE_TOPIC}/trap'
OTA_TOPIC = f'{BASE_TOPIC}/ota'
VERSION_TOPIC = f'{BASE_TOPIC}/version'

updatable_config = {}

client = None
last_sprung_traps = None
active_pins = None
trap_pins = None
pin_to_num = None
configured = False


def handle_incoming_message(topic, msg, retained):
    msg_str = str(msg, 'UTF-8')
    topic_str = str(topic, 'UTF-8')
    global active_pins, updatable_config, trap_pins, pin_to_num, configured
    if topic_str == CONFIG_TOPIC:
        print(f'{topic_str}: {msg_str}')

        # config looks something like:
        # {
        #   "activePins": [25,26,27]
        # }
        updatable_config = json.loads(msg_str)
        active_pins = updatable_config['activePins']
        trap_pins = [Pin(x, Pin.IN, pull=Pin.PULL_UP) for x in active_pins]
        pin_to_num = {}
        for idx, pin_num in enumerate(active_pins):
            pin_to_num[idx] = str(pin_num)
        configured = True
    elif topic_str == OTA_TOPIC:
        try:
            import ota
            ota.process_ota_msg(msg_str)
        except ImportError:
            print("ota module not found, updating isn't available")


async def wifi_han(state):
    print('Wifi is ', 'up' if state else 'down')
    await asyncio.sleep(1)


# If you connect with clean_session True, must re-subscribe (MQTT spec 3.1.2.4)
async def conn_han(client):
    await client.subscribe(CONFIG_TOPIC, 0)
    await client.subscribe(OTA_TOPIC, 0)
    await online()


async def online():
    await client.publish(AVAILABLE_TOPIC, 'online', retain=True, qos=0)


async def main():
    await client.connect()
    await asyncio.sleep(2)  # Give broker time
    await online()
    global last_sprung_traps, active_pins
    while not configured:
        print("Waiting for config...")
        await asyncio.sleep(5)

    await client.publish(VERSION_TOPIC, VERSION, retain=True, qos=0)

    while True:
        sprung_traps = ''
        for idx, pin in enumerate(trap_pins):
            if pin.value():
                print(f'{pin_to_num[idx]} is sprung')
                if len(sprung_traps) > 0:
                    sprung_traps += ','
                sprung_traps += pin_to_num[idx]
        if last_sprung_traps != sprung_traps:
            await client.publish(TRAP_TOPIC, sprung_traps, retain=False)
            last_sprung_traps = sprung_traps
        await asyncio.sleep(30)


config['subs_cb'] = handle_incoming_message
config['connect_coro'] = conn_han
config['wifi_coro'] = wifi_han
config['will'] = [AVAILABLE_TOPIC, 'offline', True, 0]

MQTTClient.DEBUG = False
client = MQTTClient(config)

try:
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
finally:
    client.close()
    asyncio.new_event_loop()
