import queue
import struct
import threading
import time

import util
import vwtp


# methods are stateless; used for metadata storage only.
class KWPRequest:
    def __init__(self, num, fmt="s"):
        self.num = num
        self.fmt = fmt
        self.b = bytes([num])  # performance improvement; only need to do this once.

    def unpack(self, buf):
        return struct.unpack(self.fmt, buf)

    def pack(self, *val):
        if len(val) > 0:
            return struct.pack(self.fmt, *val)
        return b''  # no parameters, don't call struct.pack for an empty argument.


# NOTE: this is for the KWP *APPLICATION LAYER*.
# transport and link layers are handled by kwp_phy.
# VW cars as of 2008 (and some prior; depends on model) use the KWP application layer
# on top of the proprietary (yet rather simple...) VWTP 2.0 over CAN bus.

# KWP addressing-modes are not relevant to VW vehicles using VWTP, as all
# ECU addressing is handled by VWTP.

# UDS session types (may be applicable to KWP as well):
# 1: default session. the base session everything runs in. can access some diag bits
# 2: PROG session. used to update/verify firmware on an ECU
# 3: Extended session. probably security-related or something?
# 4: Safety extended session. almost *certainly* airbag related.
# 0x40: EOL session? setting off airbags by hand?

# a lookup table of all standard KWP2000 request codes by name as per ISO 14230-3:1996
# (if someone could get me the :1999 edition that would be great...)
# an additional set of tables is used for manufacturer-specific services between 0xA0->0xBF.
# the response is the same number with bit 0x40 ("bit 6" in the standard) set.
# all UDS-specific services have the prefix "UDS" while UDS *compatible* services
# are marked with a comment.

# gathered from a translated chinese blog post; some fields are quite badly translated...
# the first 9 services on a real K-line (0x1 -> 0x9) are OBD2 defined as follows:
# 0x1: Powertrain Diagnostics
# 0x2: Powertrain freeze-frame
# 0x3: Emissions Diagnostics
# 0x4: Clear Emissions DTCs
# 0x9: Vehicle Information (VIN number, mainly...)
# Optional services:
# 0x5: Oxygen sensor test results
# 0x6: Other monitor test results (parameters? only have a bad translation)
# 0x7: Emissions DTCs during most recent driving cycle
# 0x8: Control onboard component (what?)
requests = {
    "startDiagnosticSession": KWPRequest(0x10, "B"),  # UDS supported. 0x86 is a "test mode" for VW?
    "ecuReset": KWPRequest(0x11),  # UDS supported
    "readFreezeFrameData": KWPRequest(0x12),
    "readDiagnosticTroubleCodes": KWPRequest(0x13),  # this reads *all* DTCs the module supports?
    "clearDiagnosticInformation": KWPRequest(0x14),  # UDS supported.
    "readStatusOfDiagnosticTroubleCodes": KWPRequest(0x17),
    "readDiagnosticTroubleCodesByStatus": KWPRequest(0x18, "s"),  # this can be used to read only "tripped" DTCs
    "UDSreadDiagnosticTroubleCodes": KWPRequest(0x19),  # UDS "read DTCs"
    "readEcuIdentification": KWPRequest(0x1A, "B"),
    # Parameter is which identifier to read (documented in kwp_trace.py)
    "stopDiagnosticSession": KWPRequest(0x20),
    "readDataByLocalIdentifier": KWPRequest(0x21, "B"),
    "readDataByCommonIdentifier": KWPRequest(0x22, ">H"),  # UDS supported (readDataByIdentifier, same arg format)
    "readMemoryByAddress": KWPRequest(0x23),  # UDS Supported
    "UDSReadScalingDataByIdentifier": KWPRequest(0x24),
    "setDataRates": KWPRequest(0x26),
    "securityAccess": KWPRequest(0x27, "Bs"),  # UDS supported, param 0x1 is "request seed"
    "UDSauthentication": KWPRequest(0x29),  # Is UDS, or control flow "on" in DaimerChrysler KWP2000 stuff.
    "UDSReadDataByIdentifierPeriodic": KWPRequest(0x2A),
    "DynamicallyDefineLocalIdentifier": KWPRequest(0x2C),  # UDS supported
    "writeDataByCommonIdentifier": KWPRequest(0x2E),  # UDS supported
    "inputOutputControlByCommonIdentifier": KWPRequest(0x2F),  # UDS supported.
    "inputOutputControlByLocalIdentifier": KWPRequest(0x30),
    "startRoutineByLocalIdentifier": KWPRequest(0x31, "B"),
    # UDS supported, UDS variant includes stop and result sub-functions.
    "stopRoutineByLocalIdentifier": KWPRequest(0x32, "B"),
    "requestRoutineResultsByLocalIdentifier": KWPRequest(0x33, "B"),
    "requestDownload": KWPRequest(0x34),  # UDS supported
    "requestUpload": KWPRequest(0x35, 's'),
    # UDS supported. takes an odd little struct involving 3-byte addresses in KWP2000.
    "transferData": KWPRequest(0x36, 's'),  # UDS supported
    "requestTransferExit": KWPRequest(0x37),  # UDS supported
    "startRoutineByAddress": KWPRequest(0x38),  # UDS: RequestFileTransfer
    "stopRoutineByAddress": KWPRequest(0x39),
    "requestRoutineResultsByAddress": KWPRequest(0x3A),
    "writeDataByLocalIdentifier": KWPRequest(0x3B),
    "writeMemoryByAddress": KWPRequest(0x3D),  # UDS supported.
    "testerPresent": KWPRequest(0x3E),  # UDS supported, keepalive message.
    "escCode": KWPRequest(0x80),
    # not part of diagnostic services specification; KWP 2000 spec says it's for manufacturer-specific services.
    "UDSAccessTimingParameters": KWPRequest(0x83),
    # UDS is "transport-compatible" with KWP, meaning we can see *what* command is run.
    "UDSSecureTransmission": KWPRequest(0x84),  # which means the tracer can see it too.
    "UDSControlDTCs": KWPRequest(0x85),
    "UDSResponseOnEvent": KWPRequest(0x86),
    "UDSLinkControl": KWPRequest(0x87),
}

# and a lookup of the response codes. the upper half is manufacturer-specific.
responses = {
    0x10: "generalReject",
    0x11: "serviceNotSupported",
    0x12: "subFunctionNotSupported-invalidFormat",
    0x13: "UDSInvalidFormat",  # UDS, incorrect message length or invalid format.
    0x14: "UDSResponseTooLong",
    0x21: "busy-RepeatRequest",
    0x22: "conditionsNotCorrect or requestSequenceError",  # (conditional on service being used)
    0x23: "routineNotComplete",
    0x24: "UDSRequestSequenceError",
    0x25: "UDSSubcomponentTimeout",  # Subcomponent request timed out
    0x31: "requestOutOfRange",
    0x33: "securityAccessDenied",
    0x35: "invalidKey",
    0x36: "exceedNumberOfAttempts",
    0x37: "requiredTimeDelayNotExpired",
    # presumably the response if you make a request after getting an exceedNumberOfAttempts...
    0x40: "downloadNotAccepted",
    0x41: "improperDownloadType",
    0x42: "can'tDownloadToSpecifiedAddress",
    0x43: "can'tDownloadNumberOfBytesRequested",
    0x50: "uploadNotAccepted",
    0x51: "improperUploadType",
    0x52: "can'tUploadFromSpecifiedAddress",
    0x53: "can'tUploadNumberOfBytesRequested",
    0x70: "UDStransferNotSupported",
    0x71: "transferSuspended",
    0x72: "transferAborted",  # UDS: General Programming Failure
    0x73: "UDSWrongBlockSequenceCounter",
    0x74: "illegalAddressInBlockTransfer",
    0x75: "illegalByteCountInBlockTransfer",
    0x76: "illegalBlockTransferType",
    0x77: "blockTransferDataChecksumError",
    0x78: "reqCorrectlyRcvd-RspPending",
    # requestCorrectlyRecieved-ResponsePending ("Could not respond within required timing, please wait") NOTE: should never be seen by user; is caught early on as EWAIT.
    0x79: "incorrectByteCountDuringBlockTransfer",
    0x7e: "UDSwrongSession",  # SubFunction not supported in current session mode.
    0x7f: "UDSwrongSession",  # Service Not supported in current session mode. effectively equivalent to above.
    0x80: "serviceNotSupportedInActiveDiagnosticMode"  # Service *supported*, but not in the current mode.
}

params = {

}


class KWPException(Exception):
    pass


# Service Not Supported; invalid request type.
class serviceNotSupportedException(KWPException):
    pass


# repeat the question.
class EAGAIN(KWPException):
    pass


# please wait.
class EWAIT(KWPException):  # should be EBUSY. TODO: change that.
    pass


# Timeout.
class ETIME(KWPException):
    pass


class EPERM(KWPException):  # permission denied
    pass


class ENEEDAUTH(EPERM):  # needs authentication (ie: SecurityAccessDenied but before authentication)
    pass


class ENOENT(KWPException):
    pass


class E2BIG(KWPException):
    pass


class EFAULT(KWPException):
    pass


class EINVAL(KWPException):
    pass


class EAUTH(EPERM):
    pass


def timeout(sess, timeout):
    sl = timeout / 2  # play it safe, ping in half the timeout
    while True:
        time.sleep(sl)
        if sess.transport._open:  # implemenation detail; TODO: change that.
            try:
                sess.request("testerPresent")
            except (
                    ETIME, serviceNotSupportedException,
                    vwtp.VWTPException):  # also catch "Service Not Supported" and bail.
                return  # catch the "tried to send to closed connection" message and kill the thread cleanly.
        else:
            return


# no longer a global, to support higher performance from multiple KWP sessions to different parts.
# to allow a heartbeat thread, we need to be sure
# KWP frames are sent thread-atomically, so use this lock.
# framelock = threading.Lock()


class KWPSession:
    def __init__(self, transport, exc=False):
        self.transport = transport
        self.timethread = threading.Thread(target=timeout, args=(self, 2))
        self.mfrsrv = {}
        self.mfrresp = {}
        self.exclusive = exc
        self.lock = threading.Lock()  # used for callback frame management
        self.framelock = threading.Lock()  # so we don't send a KWP request while we're still waiting on a response.
        self.periodic = {}
        self.q = queue.Queue()
        self.transport.callback = lambda msg: self._recv(msg)  # this is a lambda to embed a reference to self.

    def registerperiodic(self, req, callback, param):  # supported read types only take a single param
        # not yet implemented; IIRC this is UDS-only?
        raise serviceNotSupportedException("KWP2000 periodic reads are not yet supported, poll it instead")
        global requests
        with self.lock:
            if req in ["readDataByLocalIdentifier", "readDataByCommonIdentifier"]:
                if requests[req] not in self.periodic:
                    self.periodic[requests[req]] = {}
                self.periodic[request[req]][params] = callback
                # FIXME: make request to start periodic update
            else:
                raise EINVAL("Invalid Request for periodic updating")

    def deregisterperiodic(self, req, callback, param):
        global requests
        with self.lock:
            if requests[req] in self.periodic:
                if param in self.periodic[requests[req]]:
                    del self.periodic[requests[req]][param]

    def mfr(self, service, resp):
        self.mfrsrv = service
        self.mfrresp = resp

    def begin(self, *params):  # manufacturer defined; VW 0x89: "DIAG", 0x85: PROG, UDS 0x2: PROG?
        resp = self.request("startDiagnosticSession", *params)
        assert resp[0] == 0x50  # this is checked elsewhere, but make sure.
        self.timethread.start()

    def request(self, req, *params):
        if len(params) == 0:
            util.log(5, "Performing request:", req)
        else:
            util.log(5, "Performing request '{}' with params: {}".format(req, params))
        if not req in requests:  # if we don't have a generic, try the OEM.
            req = self.mfrsrv[req]
            util.log(5, "Is OEM Request")
        else:
            req = requests[req]
        while True:  # this is for request repetition due to "EAGAIN" response.
            try:
                with self.framelock:
                    if params:
                        p = req.pack(*params)
                        self.transport.send(req.b + p)
                    else:
                        self.transport.send(req.b)
                    while True:  # since we don't demux response buffers, this is also thread-locked.
                        try:
                            resp = self.recv(1)
                            self.check(resp, req.num + 0x40)
                            return resp
                        except EWAIT:
                            util.log(6, "EWAIT")
                            # recv is blocking, so just immediately keep waiting.
                        except queue.Empty:
                            raise ETIME("KWP Timeout")
            except EAGAIN:  # repeat the request after a short delay (50ms)
                util.log(6, "EAGAIN")
                time.sleep(self.transport.packival)

    def recv(self, timeout=None):
        # we use a callback-driven architecture for the transport, so we have our own buffering.
        return self.q.read(timeout=timeout)
        # return self.transport.read(timeout) #the queue-based implementation is a blocking call if the queue is empty.

    def _recv(self, msg):
        with self.lock:
            if msg[0] in self.periodic:
                if msg[1] in self.periodic[msg[0]]:
                    self.periodic[msg[0]][msg[1]](msg)
                    return
        self.q.put(msg)

    def check(self, resp, val):  # format: 0x7F, [service], [code]; or [service + 0x40]
        global responses
        if resp[0] == 0x7F:
            util.log(5, "Got Negative response:", resp)
            if resp[2] == 0x21 or resp[2] == 0x23:  # repeat the request; either busy or "not done yet"
                raise EAGAIN("EAGAIN")
            elif resp[2] == 0x78:  # "Response Pending"
                raise EWAIT("EWAIT")
            elif resp[2] == 0x33:
                raise EPERM("EPERM")  # TODO: add authentication support, and check that.
            elif resp[2] == 0x31:
                raise ENOENT("ENOENT")
            elif resp[2] == 0x35:
                raise EAUTH("EAUTH")
            elif resp[2] == 0x12:
                raise EINVAL("EINVAL")
            elif resp[2] == 0x11:
                raise serviceNotSupportedException("serviceNotSupported")
            msg = "<Unknown response {}>".format(hex(resp[2]))
            if resp[2] in responses:
                msg = responses[resp[2]]  # give us the error's name.
            elif resp[2] in self.mfrresp:
                msg = self.mfrresp[resp[2]]  # manufacturer-specific error
            raise KWPException(msg)

        elif resp[0] == val:
            return True
        raise ValueError("Checked frame not for us? (Not a negative response *or* the desired response!)")

    def close(self):
        if self.exclusive:  # if we have an exclusive socket reference, kill it.
            self.transport.close()
        self.timethread.join()
        self.timethread = None  # and leave a flag for the destructor.

    def __enter__(self):
        return self

    def __exit__(self, a, b, c):
        self.close()

    def __del__(self):
        if self.timethread:
            print("WARN: KWP object destroyed before being closed!")
