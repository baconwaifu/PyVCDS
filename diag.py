#!/usr/bin/env python3

import sys
import io
import argparse
import can
import obd2
import threading
import queue
import menu

def recv(socket, stack):
  while stack.open:
    msg = socket.recv(.05)
    if msg:
      stack._recv(msg)



def advanced():
  pass

def oem(vin):
  global sock
  if vin[1:3] == "VW": #first digit is a country code, so drop that.
    import menu_vw
    menu_vw.main(sock)
  elif vin[1] == "V": #Volvo; here because the condition is a superset of "VW"
    print("Volvo vehicles are not yet supported.")
    print("If you have a Volvo diagnostics adapter and wish to contribute,")
    print("Contact the maintainer with a CAN trace.")
    return
  else:
    print("Un-implemented OEM for VIN '{}'".format(vin))
    return

def main():
  global obd
  global vin
  opt = [ "Display VIN", "OEM Extended Diagnostics", "Inspection Readyness", "Display DTCs", "Advanced/Debugging", "Exit" ]
  print("PyVCDS. VIN: {}".format(vin))
  op = menu.selector(opt)
  if op == 0:
    print(vin)
    print("'Anonymized' VIN:")
    print(vin[:11] + "000000") #drops the serial number
    print("NOTE: this still identifies the exact *model* of car, just not the exact *car*")
  elif op == 1:
    oem(vin)
  elif op == 2:
    raise NotImplementedError("Inspection Readyness PID not implemented")
  elif op == 3:
    raise NotImplementedError("Display DTCs not implemented")
  elif op == 4:
    advanced()
  elif op == 5:
    print ("Goodbye")
    sys.exit(0)

p = argparse.ArgumentParser(description="OBD-2 diagnostic utility for SocketCAN")
p.add_argument("--bus", dest='bus', type=str, default=None, help="The CAN bus interface to use")
p.add_argument("--vin", dest='vin', action='store_const', const=True, default=False, help="Print the VIN and exit")
p.add_argument("--bitrate", dest='bits', type=int, default=None, help="The CAN bus bitrate to use")

args = p.parse_args()

if args.bus:
  bus = args.bus
else:
  print("Enter the CAN bus interface to be used (can0):")
  bus = input(">")
  if bus == "":
    bus = "can0"

if args.bits:
  raise NotImplementedError("Dynamic bitrate selection is not yet supported")

sock = can.interface.Bus(channel=bus, bustype='socketcan')

with obd2.OBD2Interface(sock) as obd: #get the VIN using OBD2.
  vin = obd.readVIN()

if args.vin:
  print(vin)
  print("'Anonymized' VIN:")
  print(vin[:11] + "000000") #drops the serial number
  print("NOTE: this still identifies the exact *model* of car, just not the exact *car*")
  sys.exit(0)

try:
  while True:
    main()
except KeyboardInterrupt:
  pass #squash this so it doesn't clutter the output.
