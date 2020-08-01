#!/usr/bin/env python3

import io
import struct
import queue
import threading
import pyserial
import asyncio

#K-Line PHY driver for PyVCDS. this implements the transport and connection
#parts of KWP2000, allowing the session layer and up to be shared with the VWTP
#stack. Unfortunately, due to the 07 passat being *one year too new*, I can't test
#this on real hardware (unless someone makes a sim that emulates a serial port
#K-line adapter...)

RUN=True

def bufloop(stack):
  global RUN
  buffer = bytearray()
  while RUN:
    stack.ser.read() #FIXME: K-line frame decoding.


class KLineStack:
  def __init__(self, port):
    self.port = port
    self.inbuf = queue.Queue()
    raise NotImplementedError("K-Line phy not yet implemented")
    self.socket = open(port,"rwb")

  def recv(self,timeout=None):
    self.inbuf.get(timeout=timeout)
  def _recv(self, buf):
    #FIXME: strip KWP transport headers from frame!
    self.inbuf.put(buf)

  def send(self, buf):
    
