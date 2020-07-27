import struct
import io
import threading
import queue
import time

DEBUG=True

#methods are stateless; used for metadata storage only.
class KWPRequest:
  def __init__(self, num, fmt=""):
    self.num = num
    self.fmt = fmt
    self.b = bytes([num]) #performance improvement; only need to do this once.
  def unpack(self, buf):
    return struct.unpack(self.fmt, buf)

  def pack(self, *val):
    return struct.pack(self.fmt, *val)

#NOTE: this is for the KWP *APPLICATION LAYER*.
#transport and link layers are handled by kwp_phy.
#VW cars as of 2008 (and some prior; depends on model) use the KWP application layer
#on top of the proprietary (yet rather simple...) VWTP 2.0 over CAN bus.

#KWP addressing-modes are not relevant to VW vehicles using VWTP, as all
#ECU addressing is handled by VWTP.

#a lookup table of all standard KWP2000 request codes by name as per ISO 14230-3:1996
#(if someone could get me the :1999 edition that would be great...)
#an additional set of tables is used for manufacturer-specific services between 0xA0->0xBF.
#the response is the same number with bit 0x40 ("bit 6" in the standard) set.
requests = {
"startDiagnosticSession": KWPRequest(0x10, "B"),
"ecuReset": KWPRequest(0x11),
"readFreezeFrameData": KWPRequest(0x12),
"readDiagnosticTroubleCodes": KWPRequest(0x13),
"clearDiagnosticInformation": KWPRequest(0x14),
"readStatusOfDiagnosticTroubleCodes": KWPRequest(0x17),
"readDiagnosticTroubleCodesByStatus": KWPRequest(0x18),
"UDSreadDiagnosticTroubleCodes": KWPRequest(0x19), #UDS "read DTCs"
"readEcuIdentification": KWPRequest(0x1A, "B"), #0x91, 9A, 9B params for VWs.
"stopDiagnosticSession": KWPRequest(0x20),
"readDataByLocalIdentifier": KWPRequest(0x21, "B"),
"readDataByCommonIdentifier": KWPRequest(0x22, "B"),
"readMemoryByAddress": KWPRequest(0x23),
"setDataRates": KWPRequest(0x26),
"securityAccess": KWPRequest(0x27),
"UDSauthentication": KWPRequest(0x29), #Is actually UDS; used for more advanced authentication such as PKI
"DynamicallyDefineLocalIdentifier": KWPRequest(0x2C),
"writeDataByCommonIdentifier": KWPRequest(0x2E),
"inputOutputControlByCommonIdentifier": KWPRequest(0x2F),
"inputOutputControlByLocalIdentifier": KWPRequest(0x30),
"startRoutineByLocalIdentifier": KWPRequest(0x31, "B"),
"stopRoutineByLocalIdentifier": KWPRequest(0x32, "B"),
"requestRoutineResultsByLocalIdentifier": KWPRequest(0x33),
"requestDownload": KWPRequest(0x34),
"requestUpload": KWPRequest(0x35),
"transferData": KWPRequest(0x36),
"requestTransferExit": KWPRequest(0x37),
"startRoutineByAddress": KWPRequest(0x38),
"stopRoutineByAddress": KWPRequest(0x39),
"requestRoutineResultsByAddress": KWPRequest(0x3A),
"writeDataByLocalIdentifier": KWPRequest(0x3B),
"writeMemoryByAddress": KWPRequest(0x3D),
"testerPresent": KWPRequest(0x3E), #keepalive message.
"escCode": KWPRequest(0x80) #not part of diagnostic services specification; KWP 2000 only (not even sure what this *is*...)
}

#and a lookup of the response codes. the upper half is manufacturer-specific.
responses = {
0x10: "generalReject",
0x11: "serviceNotSupported",
0x12: "subFunctionNotSupported-invalidFormat",
0x21: "busy-RepeatRequest",
0x22: "conditionsNotCorrect or requestSequenceError", #(conditional on service being used)
0x23: "routineNotComplete",
0x31: "requestOutOfRange",
0x33: "securityAccessDenied",
0x35: "invalidKey",
0x36: "exceedNumberOfAttempts",
0x37: "requiredTimeDelayNotExpired", #presumably the response if you make a request after getting an exceedNumberOfAttempts...
0x40: "downloadNotAccepted",
0x41: "improperDownloadType",
0x42: "can'tDownloadToSpecifiedAddress",
0x43: "can'tDownloadNumberOfBytesRequested",
0x50: "uploadNotAccepted",
0x51: "improperUploadType",
0x52: "can'tUploadFromSpecifiedAddress",
0x53: "can'tUploadNumberOfBytesRequested",
0x71: "transferSuspended",
0x72: "transferAborted",
0x74: "illegalAddressInBlockTransfer",
0x75: "illegalByteCountInBlockTransfer",
0x76: "illegalBlockTransferType",
0x77: "blockTransferDataChecksumError",
0x78: "reqCorrectlyRcvd-RspPending", #requestCorrectlyRecieved-ResponsePending ("Could not respond within required timing, please wait")
0x79: "incorrectByteCountDuringBlockTransfer"
}

params = {

}


#repeat the question.
class EAGAIN(Exception):
  pass

#please wait.
class EWAIT(Exception):
  pass

#Timeout.
class ETIME(Exception):
  pass

def timeout(sess, timeout):
  sl = timeout/2 #play it safe, ping in half the timeout
  while True:
    time.sleep(sl)
    if sess.transport._open: #implemenation detail; TODO: change that.
      try:
        sess.request("testerPresent")
      except (ValueError, ETIME):
        return #catch the "tried to send to closed connection" message and kill the thread cleanly.
    else:
      return

#to allow a heartbeat thread, we need to be sure
#KWP frames are sent thread-atomically, so use this lock.
framelock = threading.Lock() 


class KWPSession:
  def __init__(self, transport):
    self.transport = transport
    self.timethread = threading.Thread(target=timeout, args=(self,2))
    self.mfrsrv = []
    self.mfrresp = []
  def mfr(self,service,resp):
    self.mfrsrv = service
    self.mfrresp = resp

  def begin(self, *params):
    resp = self.request("startDiagnosticSession", *params)
    assert resp[0] == 0x50 #this is checked elsewhere, but make sure.
    self.timethread.start()

  def request(self, req, *params):
    global framelock, DEBUG
    if DEBUG:
      if len(params) == 0:
        print("Performing request:",req)
      else:
        print("Performing request '{}' with params: {}".format(req,params))
    if not req in requests: #if we don't have a generic, try the OEM.
      req = self.mfrsrv[req]
      if DEBUG:
        print("Is OEM Request")
    else:
      req = requests[req]
    while True: #this is for request repetition due to "EAGAIN" response.
      try:
        with framelock:
          if params:
            p = req.pack(*params)
            self.transport.send(req.b + p)
          else:
            self.transport.send(req.b)
          while True: #since we don't demux response buffers, this is also thread-locked.
            try:
              resp = self.recv(1)
              self.check(resp, req.num + 0x40)
              return resp
            except EWAIT:
              if DEBUG:
                print("EWAIT")
              #recv is blocking, so just immediately keep waiting.
            except queue.Empty:
              raise ETIME("KWP Timeout")
      except EAGAIN: #repeat the request after a short delay (50ms)
        if DEBUG:
          print("EAGAIN")
        time.sleep(self.transport.packival)
  def recv(self,timeout=None):
    return self.transport.read(timeout) #the queue-based implementation is a blocking call if the queue is empty.

  def check(self, resp, val):
    if resp[0] == 0x7F:
      if DEBUG:
        print("Got Negative response:",resp)
      if resp[1] == 0x21 or resp[1] == 0x23: #repeat the request; either busy or "not done yet"
        raise EAGAIN
      elif resp[1] == 0x78: #"Response Pending"
        raise EWAIT
      msg = "Unknown response"
      if resp[1] in responses:
        msg = reponses[resp[1]] #give us the error's name.
      elif resp[1] in self.mfrresp:
        msg = self.mfrresp[resp[1]] #manufacturer-specific error
      raise NotImplementedError(msg) #this is mostly just a matter of *which* error to throw.

    elif resp[0] == val:
      return True
    raise ValueError("Checked frame not for us? (Not a negative response *or* the desired response!)")

  def close(self):
    pass
  def __enter__(self):
    return self
  def __exit__(self,a,b,c):
    self.close()
