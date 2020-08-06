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
  if vin.startswith("WVW"): 
    import menu_vw
    menu_vw.main(sock)
  else:
    print("Un-implemented OEM for VIN '{}'".format(vin))
    return    

def main():
  global obd
  global vin
  opt = [ "Display VIN", "OEM Extended Diagnostics", "Inspection Readyness", "Display DTCs", "Advanced/Debugging", "Exit" ]
  print("PyVCDS")
  op = menu.selector(opt)
  if op == 0:
    print(vin)
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
  sys.exit(0)

while True:
  main()
