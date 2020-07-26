import can
import vwtp
import threading

#VWTP was architectured for an asynchronous socket
#so we need a thread to do that for us.
def recvthread(stack):
  sock = stack.socket
  while True:
    msg = sock.recv()
    if hasattr(msg,"data"):
      stack._recv(msg)
    else:
      print(msg)
      raise AttributeError("Not like a can.Message?")

sock = can.interface.Bus(channel='vcan0', bustype='socketcan')

stack = vwtp.VWTPStack(sock)

recv = threading.Thread(target=recvthread, args=(stack,))
recv.start()

conn = stack.connect(1) #"ECU"

with conn:
  conn.send(b'\x10\x89')
  assert conn.read() == b'\x50\x89' #positive response, same value.
  conn.send(b'\x21\x01') #readDataByLocalIdentifier ID 1.
  print(conn.read())

