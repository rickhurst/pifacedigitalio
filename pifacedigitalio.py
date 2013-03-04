#!/usr/bin/env python
"""
pifacedigitalio.py
Provides I/O methods for interfacing with PiFace Digital (on the Raspberry Pi)
Copyright (C) 2013 Thomas Preston <thomasmarkpreston@gmail.com>

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""
import sys
import ctypes
import posix
from fcntl import ioctl
from asm_generic_ioctl import _IOW
from time import sleep
from datetime import datetime


# spi stuff requires Python 3
assert sys.version_info.major >= 3, __name__ + " is only supported on Python 3."


VERBOSE_MODE = False # toggle verbosity
__pfdio_print_PREFIX = "PiFaceDigitalIO: " # prefix for pfdio messages

WRITE_CMD = 0
READ_CMD  = 1

# Port configuration
IODIRA = 0x00 # I/O direction A
IODIRB = 0x01 # I/O direction B
IOCON  = 0x0A # I/O config
GPIOA  = 0x12 # port A
GPIOB  = 0x13 # port B
GPPUA  = 0x0C # port A pullups
GPPUB  = 0x0D # port B pullups
OUTPUT_PORT  = GPIOA
INPUT_PORT   = GPIOB
INPUT_PULLUP = GPPUB

SPI_IOC_MAGIC = 107 # yeah :/


spidev_fd = None


# custom exceptions
class InitError(Exception):
    pass

class InputDeviceError(Exception):
    pass

class PinRangeError(Exception):
    pass

class LEDRangeError(Exception):
    pass

class RelayRangeError(Exception):
    pass

class SwitchRangeError(Exception):
    pass


# classes
class Item(object):
    """An item connected to a pin on PiFace Digital"""
    def __init__(self, pin_num, board_num=0, handler=None):
        self.pin_num = pin_num
        self.board_num = board_num
        if handler:
            self.handler = handler

    @property
    def handler(self):
        return sys.modules[__name__]

class InputItem(Item):
    """An input connected to a pin on PiFace Digital"""
    def __init__(self, pin_num, board_num=0, handler=None):
        Item.__init__(self, pin_num, board_num, handler)

    @property
    def value(self):
        return self.handler.digital_read(self.pin_num, self.board_num)

    @value.setter
    def value(self, data):
        raise InputDeviceError("You cannot set an input's values!")

class OutputItem(Item):
    """An output connected to a pin on PiFace Digital"""
    def __init__(self, pin_num, board_num=0, handler=None):
        self.current = 0
        Item.__init__(self, pin_num, board_num, handler)

    @property
    def value(self):
        return self.current

    @value.setter
    def value(self, data):
        self.current = data
        return self.handler.digital_write(self.pin_num, data, self.board_num)

    def turn_on(self):
        self.value = 1
    
    def turn_off(self):
        self.value = 0

    def toggle(self):
        self.value = not self.value

class LED(OutputItem):
    """An LED on PiFace Digital"""
    def __init__(self, led_number, board_num=0, handler=None):
        if led_number < 0 or led_number > 7:
            raise LEDRangeError(
                    "Specified LED index (%d) out of range." % led_number)
        else:
            OutputItem.__init__(self, led_number, board_num, handler)

class Relay(OutputItem):
    """A relay on PiFace Digital"""
    def __init__(self, relay_number, board_num=0, handler=None):
        if relay_number < 0 or relay_number > 1:
            raise RelayRangeError(
                    "Specified relay index (%d) out of range." % relay_number)
        else:
            OutputItem.__init__(self, relay_number, board_num, handler)

class Switch(InputItem):
    """A switch on PiFace Digital"""
    def __init__(self, switch_number, board_num=0, handler=None):
        if switch_number < 0 or switch_number > 3:
            raise SwitchRangeError(
                  "Specified switch index (%d) out of range." % switch_number)
        else:
            InputItem.__init__(self, switch_number, board_num, handler)

class PiFaceDigital(object):
    """A single PiFace Digital board"""
    def __init__(self, board_num=0):
        self.board_num = board_num

        self.led = list()
        for i in range(8):
            self.led.append(LED(i, board_num))

        self.relay = list()
        for i in range(2):
            self.relay.append(Relay(i, board_num))

        self.switch = list()
        for i in range(4):
            self.switch.append(Switch(i, board_num))

class _spi_ioc_transfer(ctypes.Structure):                                      
    """SPI ioc transfer structure (from linux/spi/spidev.h)"""
    _fields_ = [
        ("tx_buf", ctypes.c_uint64),
        ("rx_buf", ctypes.c_uint64),
        ("len", ctypes.c_uint32),
        ("speed_hz", ctypes.c_uint32),
        ("delay_usecs", ctypes.c_uint16),
        ("bits_per_word", ctypes.c_uint8),
        ("cs_change", ctypes.c_uint8),
        ("pad", ctypes.c_uint32)]


# functions
def init(init_ports=True):
    """Initialises the PiFace Digital board"""
    if VERBOSE_MODE:
         __pfdio_print("initialising SPI")

    global spidev_fd
    spidev_fd = posix.open('/dev/spidev0.0', posix.O_RDWR)

    if init_ports:
        for board_index in range(8):
            # set up the ports
            write(IOCON,  8, board_index)    # enable hardware addressing
            write(GPIOA,  0, board_index)    # set port A on
            write(IODIRA, 0, board_index)    # set port A as outputs
            write(IODIRB, 0xFF, board_index) # set port B as inputs
            #write(GPIOA,  0xFF, board_index) # set port A on
            #write(GPIOB,  0xFF, board_index) # set port B on
            #write(GPPUA,  0xFF, board_index) # set port A pullups on
            write(GPPUB,  0xFF, board_index) # set port B pullups on

            # check the outputs are being set (primitive board detection)
            # AR removed this test as it lead to flashing of outputs which 
            # could surprise users!
            #test_value = 0b10101010
            #write_output(test_value)
            #if read_output() != test_value:
            #    spi_handler = None
            #    raise InitError("The PiFace board could not be detected")

            # initialise outputs to 0
            write_output(0, board_index)

def deinit():
    """Closes the spidev file descriptor"""
    global spidev_fd
    posix.close(spidev_fd)

def __pfdio_print(text):
    """Prints a string with the pfdio print prefix"""
    print("%s %s" % (__pfdio_print_PREFIX, text))

def get_pin_bit_mask(pin_number):
    """Translates a pin number to pin bit mask. First pin is pin0."""
    if pin_number > 7 or pin_number < 0:
        raise PinRangeError("Specified pin number (%d) out of range." % pin_number)
    else:
        return 1 << (pin_number)

def get_pin_number(bit_pattern):
    """Returns the lowest pin number from a given bit pattern"""
    pin_number = 0 # assume pin 0
    while (bit_pattern & 1) == 0:
        bit_pattern = bit_pattern >> 1
        pin_number += 1
        if pin_number > 7:
            pin_number = 0
            break
    
    return pin_number

def digital_write(pin_number, value, board_num=0):
    """Writes the value given to the pin specified"""
    if VERBOSE_MODE:
        __pfdio_print("digital write start")

    pin_bit_mask = get_pin_bit_mask(pin_number)

    if VERBOSE_MODE:
        __pfdio_print("pin bit mask: %s" % bin(pin_bit_mask))

    old_pin_values = read_output(board_num)

    if VERBOSE_MODE:
        __pfdio_print("old pin values: %s" % bin(old_pin_values))

    # generate the 
    if value:
        new_pin_values = old_pin_values | pin_bit_mask
    else:
        new_pin_values = old_pin_values & ~pin_bit_mask

    if VERBOSE_MODE:
        __pfdio_print("new pin values: %s" % bin(new_pin_values))

    write_output(new_pin_values, board_num)

    if VERBOSE_MODE:
        __pfdio_print("digital write end")

def digital_read(pin_number, board_num=0):
    """Returns the value of the pin specified"""
    current_pin_values = read_input(board_num)
    pin_bit_mask = get_pin_bit_mask(pin_number)

    result = current_pin_values & pin_bit_mask

    # works with true/false
    if result:
        return 1
    else:
        return 0

def digital_write_pullup(pin_number, value, board_num=0):
    """Writes the pullup value given to the pin specified"""
    if VERBOSE_MODE:
        __pfdio_print("digital write pullup start")

    pin_bit_mask = get_pin_bit_mask(pin_number)

    if VERBOSE_MODE:
        __pfdio_print("pin bit mask: %s" % bin(pin_bit_mask))

    old_pin_values = read_pullup(board_num)

    if VERBOSE_MODE:
        __pfdio_print("old pin values: %s" % bin(old_pin_values))

    # generate the 
    if value:
        new_pin_values = old_pin_values | pin_bit_mask
    else:
        new_pin_values = old_pin_values & ~pin_bit_mask

    if VERBOSE_MODE:
        __pfdio_print("new pin values: %s" % bin(new_pin_values))

    write_pullup(new_pin_values, board_num)

    if VERBOSE_MODE:
        __pfdio_print("digital write end")

def digital_read_pullup(pin_number, board_num=0):
    """Returns the value of the pullup pin specified"""
    current_pin_values = read_pullup(board_num)
    pin_bit_mask = get_pin_bit_mask(pin_number)

    result = current_pin_values & pin_bit_mask

    # works with true/false
    if result:
        return 1
    else:
        return 0

"""
Some wrapper functions so the user doesn't have to deal with
ugly port variables
"""
def read_output(board_num=0):
    """Returns the values of the output pins"""
    port, data = read(OUTPUT_PORT, board_num)
    return data

def read_input(board_num=0):
    """Returns the values of the input pins"""
    port, data = read(INPUT_PORT, board_num)
    # inputs are active low, but the user doesn't need to know this...
    return data ^ 0xff 

def read_pullup(board_num=0):
    """Reads value of pullup registers"""
    port, data = read(INPUT_PULLUP, board_num)
    return data

def write_pullup(data, board_num=0):
    """Writes value to pullup registers"""
    port, data = write(INPUT_PULLUP, data, board_num)
    return data

def write_output(data, board_num=0):
    """Writed the values of the output pins"""
    port, data = write(OUTPUT_PORT, data, board_num)
    return data

"""
def write_input(data):
    " ""Writes the values of the input pins"" "
    port, data = write(INPUT_PORT, data)
    return data
"""

def __get_device_opcode(board_num, read_write_cmd):
    """Returns the device opcode (as a byte)"""
    board_addr_pattern = (board_num << 1) & 0xE # 1 -> 0b0010, 3 -> 0b0110
    rw_cmd_pattern = read_write_cmd & 1 # make sure it's just 1 bit long
    return 0x40 | board_addr_pattern | rw_cmd_pattern

def read(port, board_num=0):
    """Reads from the port specified"""
    devopcode = __get_device_opcode(board_num, READ_CMD)
    operation, port, data = spisend((devopcode, port, 0)) # data byte is not used
    return (port, data)

def write(port, data, board_num=0):
    """Writes data to the port specified"""
    devopcode = __get_device_opcode(board_num, WRITE_CMD)
    operation, port, data = spisend((devopcode, port, data))
    return (port, data)

def spisend(bytes_to_send):
    """Sends bytes via the SPI bus"""
    global spidev_fd
    if spidev_fd == None:
        raise InitError("Before spisend(), call init().")

    # make some buffer space to store reading/writing
    write_bytes = bytes(bytes_to_send)
    wbuffer = ctypes.create_string_buffer(write_bytes, len(write_bytes))
    rbuffer = ctypes.create_string_buffer(len(bytes_to_send))

    # create the spi transfer struct
    transfer = _spi_ioc_transfer(
        tx_buf=ctypes.addressof(wbuffer),
        rx_buf=ctypes.addressof(rbuffer),
        len=ctypes.sizeof(wbuffer))

    # send the spi command (with a little help from asm-generic
    iomsg = _IOW(SPI_IOC_MAGIC, 0, ctypes.c_char*ctypes.sizeof(transfer))
    ioctl(spidev_fd, iomsg, ctypes.addressof(transfer))
    return ctypes.string_at(rbuffer, ctypes.sizeof(rbuffer))
