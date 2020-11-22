#!/usr/bin/env python3

import kwp
import vw
import struct

def parse_basic(buf):
  return repr(buf)

def parse_dtc(buf):
  return repr(buf) #FIXME: DTC labels.

ecu_identifiers = {
  0x86: "Extended Ident",
  0x92: "System Supplier Hardware ID",
  0x91: "Unknown (0x91)",
  0x94: "System Supplier Software ID",
  0x9A: "Unknown (0x9A)",
  0x9B: "ECU Ident",
  0x9C: "Flash Status"
}

def recv_readDiagnosticTroubleCodes(buf):
  dtcs = []
  count = buf[1]
  for i in range(0, count*2, 2):
    dtcs.append(parse_dtc(buf[i+2,i+4]))
  return "\n".join(dtcs)

def xmit_readDiagnosticTroubleCodes(buf):
  return "DTC Groups requested: " + repr(buf[1:])

def xmit_readDiagnosticTroubleCodesByStatus(buf):
  return "DTC status flags: " + repr(buf[1:3]) + "\nDTC Groups: " + buf[3:]

def recv_readDiagnosticTroubleCodesByStatus(buf):
  return recv_readDiagnosticTroubleCodes(buf) #same format, re-use code.

def xmit_readEcuIdentification(buf):
  if buf[1] in ecu_identifiers:
    return ecu_identifers[buf[1]]
  return "Unknown ({})".format(hex(buf[1]))
  #return parse_basic(buf) #FIXME. parameters.

def recv_readEcuIdentification(buf):
  if buf[1] in ecu_identifiers:
    return "{}: {}".format(ecu_identifers[buf[1]], parse_basic(buf[2:])
  return "Unknown ({}): {}".format(hex(buf[1]), parse_basic(buf[2:])
  #return parse_basic(buf) #FIXME: IDs?

def xmit_readDataByLocalIdentifier(buf):
  return "ID: " + buf[1]

def recv_readDataByLocalIdentifier(buf):
  return parse_basic(buf) #FIXME: parse out measuring blocks.

def xmit_readDataByCommonIdentifier(buf):
  return "ID: " + buf[1]

def recv_readDataByCommonIdentifier(buf):
  return parse_basic(buf)

def xmit_readMemoryByAddress(buf):
  return NotImplemented #FIXME: get parameters.

def recv_readMemoryByAddress(buf):
  return "Memory Contents: " + repr(buf[1:])

def xmit_writeDataByCommonIdentifier(buf):
  return "ID: " + buf[1] + "\nWritten Data: " + repr(buf[2])

def xmit_startRoutineByLocalIdentifier(buf):
  return "Routine: " + parse_routine(buf[1]) + ("\nArguments: " + repr(buf[2:])) if len(buf) > 2 else ""

def xmit_stopRoutineByLocalIdentifier(buf):
  return "Routine: " + parse_routine(buf[1])

def xmit_writeMemoryByAddress(buf):
  return NotImplemented #FIXME: get address sizing.

recv = {}
xmit = {}

#use reflection to register all decoders we have defined.
for k,w in kwp.requests.items():
  global recv,xmit
  if "recv_" + k in __dict__:
    recv[w.num + 0x40] = __dict__["recv_"+k] #ACK frames have bit 0x40 set
  if "xmit_" + k in __dict__:
    recv[w.num] = __dict__["xmit_"+k]


