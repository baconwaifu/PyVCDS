import struct
import io
import threading
import queue
import time
import util

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
"readDiagnosticTroubleCodes": KWPRequest(0x13), #this reads *all* DTCs the module supports!
"clearDiagnosticInformation": KWPRequest(0x14),
"readStatusOfDiagnosticTroubleCodes": KWPRequest(0x17),
"readDiagnosticTroubleCodesByStatus": KWPRequest(0x18, "s"), #this can be used to read only "tripped" DTCs
"UDSreadDiagnosticTroubleCodes": KWPRequest(0x19), #UDS "read DTCs"
"readEcuIdentification": KWPRequest(0x1A, "B"), #0x91, 9A, 9B params for VWs?
"stopDiagnosticSession": KWPRequest(0x20),
"readDataByLocalIdentifier": KWPRequest(0x21, "B"),
"readDataByCommonIdentifier": KWPRequest(0x22, "<H"),
"readMemoryByAddress": KWPRequest(0x23),
"UDSReadScalingDataByIdentifier": KWPRequest(0x24),
"setDataRates": KWPRequest(0x26),
"securityAccess": KWPRequest(0x27),
"UDSauthentication": KWPRequest(0x29), #Is UDS, or control flow "on" in DaimerChrysler stuff.
"UDSReadDataByIdentifierPeriodic": KWPRequest(0x2A), #Note: DO NOT USE. architecture does not support asynchronous responses!
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
"startRoutineByAddress": KWPRequest(0x38), #UDS: RequestFileTransfer
"stopRoutineByAddress": KWPRequest(0x39),
"requestRoutineResultsByAddress": KWPRequest(0x3A),
"writeDataByLocalIdentifier": KWPRequest(0x3B),
"writeMemoryByAddress": KWPRequest(0x3D),
"testerPresent": KWPRequest(0x3E), #keepalive message.
"escCode": KWPRequest(0x80), #not part of diagnostic services specification; KWP 2000 spec says it's for manufacturer-specific services.
"UDSAccessTimingParameters": KWPRequest(0x83), #UDS is "transport-compatible" with KWP, meaning we can see *what* command is run.
"UDSSecureTransmission": KWPRequest(0x84), #which means the tracer can see it too.
"UDSControlDTCs": KWPRequest(0x85),
"UDSResponseOnEvent": KWPRequest(0x86),
"UDSLinkControl": KWPRequest(0x87),
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


class KWPException(Exception):
  pass

#repeat the question.
class EAGAIN(KWPException):
  pass

#please wait.
class EWAIT(KWPException): #should be EBUSY. TODO: change that.
  pass

#Timeout.
class ETIME(KWPException):
  pass

class EPERM(KWPException): #permission denied
  pass

class ENEEDAUTH(KWPException): #needs authentication (ie: SecurityAccessDenied but before authentication)
  pass

class ENOENT(KWPException):
  pass

class E2BIG(KWPException):
  pass

class EFAULT(KWPException):
  pass

class EINVAL(KWPException):
  pass

class EAUTH(KWPException):
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
    self.mfrsrv = {}
    self.mfrresp = {}
  def mfr(self,service,resp):
    self.mfrsrv = service
    self.mfrresp = resp

  def begin(self, *params): #manufacturer defined; VW 0x89: "DIAG"
    resp = self.request("startDiagnosticSession", *params)
    assert resp[0] == 0x50 #this is checked elsewhere, but make sure.
    self.timethread.start()

  def request(self, req, *params):
    global framelock, DEBUG
    if len(params) == 0:
      util.log(5,"Performing request:",req)
    else:
      util.log(5,"Performing request '{}' with params: {}".format(req,params))
    if not req in requests: #if we don't have a generic, try the OEM.
      req = self.mfrsrv[req]
      util.log(5,"Is OEM Request")
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
              util.log(6,"EWAIT")
              #recv is blocking, so just immediately keep waiting.
            except queue.Empty:
              raise ETIME("KWP Timeout")
      except EAGAIN: #repeat the request after a short delay (50ms)
        util.log(6,"EAGAIN")
        time.sleep(self.transport.packival)
  def recv(self,timeout=None):
    return self.transport.read(timeout) #the queue-based implementation is a blocking call if the queue is empty.

  def check(self, resp, val): #format: 0x7F, [service], [code]; or [service + 0x40]
    global responses
    if resp[0] == 0x7F:
      util.log(5,"Got Negative response:",resp)
      if resp[2] == 0x21 or resp[2] == 0x23: #repeat the request; either busy or "not done yet"
        raise EAGAIN
      elif resp[2] == 0x78: #"Response Pending"
        raise EWAIT
      elif resp[2] == 0x33:
        raise EPERM #TODO: add authentication support, and check that.
      elif resp[2] == 0x31:
        raise ENOENT
      elif resp[2] == 0x35:
        raise EAUTH
      elif resp[2] == 0x12:
        raise EINVAL
      msg = "<Unknown response {}>".format(hex(resp[2]))
      if resp[2] in responses:
        msg = responses[resp[2]] #give us the error's name.
      elif resp[2] in self.mfrresp:
        msg = self.mfrresp[resp[2]] #manufacturer-specific error
      raise KWPException(msg)

    elif resp[0] == val:
      return True
    raise ValueError("Checked frame not for us? (Not a negative response *or* the desired response!)")

  def close(self):
    pass
  def __enter__(self):
    return self
  def __exit__(self,a,b,c):
    self.close()
