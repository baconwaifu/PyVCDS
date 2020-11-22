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
  global sock
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
    with obd2.OBD2Interface(sock) as obd:
      status = obd.readPID(1, 1) #Current Data: Monitor Status
    #byte 0 is MIL and DTC count
    mil = status[0] & 0x80 != 0 #check engine flag
    dtcs = status[0] & 0xef #rest of bits are DTC count
    #byte 1 low nibble is self-tests available, and high nibble is test *incomplete*
    print("Check Engine state:", "ON" if mil else "OFF")
    print("Number of DTCs:", dtcs)
    if status[1] & 1 != 0 and status[1] & 0x10 != 0:
      print("Misfire self-test: INCOMPLETE")
    if status[1] & 2 != 0 and status[1] & 0x20 != 0:
      print("Fuel system self-test: INCOMPLETE")
    if status[1] & 4 != 0 and status[1] & 0x40 != 0:
      print("Components self-test: INCOMPLETE")
    if status[1] & 0x8 == 0: #spark engine, otto/wankel
      avail = status[2]
      incom = status[3]
      for i in range(8):
        if avail & 1 != 0:
          print("{} self-test:".format(obd2.spark_tests[i]),"INCOMPLETE" if incom & 1 != 0 else "COMPLETE")
        avail = avail >> 1
        incom = incom >> 1
    else: #compression, diesel
      avail = status[2]
      incom = status[3]
      for i in range(8):
        if avail & 1 != 0: #don't print anything for tests that aren't available.
          print("{} self-test:".format(obd2.comp_tests[i]),"INCOMPLETE" if incom & 1 != 0 else "COMPLETE")
        avail = avail >> 1
        incom = incom >> 1
  elif op == 3: #somehow, nobody wrote down that the VIN transfer protocol was actually ISO-TP. so this was fairly painless to implement.
    with obd2.OBD2Interface(sock) as obd:
      status = obd.readPID(1, 1) #check DTC count first.
      for k in status:
        if k[0] & 0xef == 0:
          print("{}: No DTCs to display".format(hex(k)))
        else:
          l = k[0] & 0xef
          dtcs = obd.readPID(3, 0, k)[k] #PID is spurrious, just to make python happy.
          assert len(dtcs) >= 2 * l, "Not enough DTC data?" #each DTC is 2 bytes. TODO: check pending DTCs?
          for i in range(0, l*2, 2):
            dtc = obd2.OBD2DTC.getDTCFromBytes(dtcs[i:i+2])
            print("{}: DTC Set:".format(hex(k)), dtc)
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
