import queue
import struct
import threading
import time

import can

import util

# Volkswagen Transport Protocol

# FIXME:

DEBUG = False

_sleep = time.sleep


def sleep(sl):
    #  print("Sleeping for {} seconds...".format(sl))
    _sleep(sl)


if DEBUG:
    time.sleep = sleep  # crude debug hook for debugging timeouts

_threadrun = True


# VWTP was architectured for an asynchronous socket, but python sockets are synchronous,
# so we need a thread to do that for us.
def recvthread(stack):
    sock = stack.socket
    while stack.open:
        msg = sock.recv(.05)
        if msg:
            stack._recv(msg)


def pingthread(conn):
    try:
        while conn._open or conn.reopen:  # keep the thread spinning while reconnecting
            time.sleep(.5)
            if conn._open:
                util.log(6, "Ping!")
                conn._send([0xa3])  # but don't actually *send* anything.
    except VWTPException:  # just die cleanly.
        pass


class VWTPException(Exception):
    pass


class ETIME(VWTPException):
    pass


class ERETRY(VWTPException):
    pass


# note: the VWTP stack itself handles the sockets.
# connections should *never* be instantiated directly!
# thread-safety: partial. used to terminate connection cleanly from other thread.
# only one sending thread permitted at a time, and `_send` can *never* be called
# with a running instance of `send`, unless it's a disconnect or a ping. (opcode-distinct from data frames)
class VWTPConnection:
    def __init__(self, stack, chan_id, callback=None, reopen=True):
        self.mod_id = 0  # not set; is set externally.
        self.keepalive = 1  # number of seconds between pings.
        self.framebuf = None
        self.buffer = queue.Queue()
        self.acks = {}  # an ack buffer; separate from the queue to allow for introspection.
        self.params = None
        self.callback = callback
        self.stack = stack
        self.tx = chan_id
        self._tx = chan_id
        self.blksize = None  # the number of packets that can be recieved at once before an ACK
        self.seq = 0  # the sequence we're expecting to see
        self.tseq = 0  # the sequence the ECU is expecting to see
        self._open = False
        self.q = queue.Queue()  # used for "await" by the channel setup.
        self.pinger = threading.Thread(target=pingthread, args=(self,))
        self.reopen = reopen  # attempt to automatically re-open a connection (to avoid the car saying "fuck off" while brute-forcing block IDs...)
        self.lock = threading.Lock()  # used to suspend sending through disconnects
        self.connected = True
        self.sending = False
        self.fin = queue.Queue()
        self.fault = False
        self.proto = None

    def open(self):
        self._open = True
        util.log(5, "Beginning channel parameter setup")
        # called when the channel is set up to recieve frames at the designated ID, to start channel setup.
        buf = [None] * 6
        buf[0] = 0xA0
        buf[1] = 15  # block size.
        buf[
            2] = 0x8a  # these four bytes are timing parameters; this one being ack timeout. upper 2 bits are scale, lower 6 are int. (this is 100ms)
        buf[3] = 0xff
        buf[4] = 0x0A  # interval between packets 5ms? seems high. (50x 0.1ms scale)
        buf[5] = 0xff
        self._send(buf)
        util.log(5, "Setup message sent, awaiting response.")
        for i in range(6):
            try:
                self.q.get(timeout=.1)  # 100ms per setup
                break
            except queue.Empty:
                util.log(6, "Retransmit setup...")
                self._send(buf)
        if not self.blksize:
            raise ETIME("Channel setup timeout")
        if self.connected:  # use this to determine "new" open vs "old" open; this is set to True by the constructor, which is not re-called on reconnect.
            self.pinger.start()  # only start the thread if it's not already running.
        self.connected = True
        self.tx = self._tx

    def reconnect(self):
        util.log(5, "Re-opening connection to:", hex(self.mod_id))
        self.stack.reconnect(self)
        self.open()  # outermost lock doesn't affect this, since it uses primitives directly
        self.connected = True

    def _recv(self, msg):
        global DEBUG
        # msg is a can data frame.
        buf = msg  # the raw buffer contents of a CAN frame.
        op = buf[0]
        buf = buf[1:]
        if op == 0xA8:  # disconnect
            if not self._open:  # waiting on a finalizer.
                self.fin.put(None)
            if self.reopen:
                self.connected = False  # asyncronously signal this to main thread.
            with self.lock:  # finish the current outgoing block, then cut it short.
                if self._open:
                    self._send([0xa8])  # respond if this was remote-initiated.
                self.sending = False
                self.close(True)  # tell the closure thread to check reopen state
        elif op == 0xA3:  # "ping"
            pass  # FIXME: send parameter response method
        elif op == 0xA1:  # params response
            if self.blksize:
                util.log(6, "Pong!")
                # util.log(3,"Potential connection fault: recieved 'parameter response' when already configured!\nDropping it and hoping nothing breaks...")
                return
            self.params = buf
            self.blksize = buf[0] + 1  # 0 is "1 frame"
            scale = [.1, 1, 10, 100]
            acktime = buf[1] >> 6  # scale is 100ms, 10ms, 1ms, .1ms
            self.acktime = (scale[acktime] * (buf[1] & 0x3F)) * 0.001  # go from ms to s.
            self.packival = (scale[buf[3] >> 6] * (buf[3] & 0x3F)) * 0.001
            util.log(5, "Parameter response received.")
            util.log(6, "channel parameters:",
                     "\nTimeout in ms:", self.acktime * 1000, "\nMinimum Interval between frames in ms:",
                     self.packival * 1000, "\nBlock Size:", self.blksize)
            self.q.put(None)  # just stuff *something* in there to break the retry loop
        elif op & 0xf0 == 0xB0 or op & 0xf0 == 0x90:
            if op & 0xf0 == 0x90:
                util.log(3, "ACK but not ready. this is unhandled, spray and pray!")
            self.acks[op & 0xf] = True  # mark the ack in the sequence table
        else:  # assume it's a data packet.
            seq = op & 0x0f
            if op & 0x20 == 0 and seq == self.seq:  # expecting ACK
                try:
                    self._ack(seq + 1)  # expecting seq + 1 response
                except VWTPException:
                    pass  # connection closed; just drop it so we don't crash the thread.
            self.seq += 1
            if self.seq == 0x10:
                self.seq = 0
            if not self.framebuf:  # first frame of a transaction
                try:
                    self.framelen = struct.unpack(">H", buf[0:2])[0]
                    self.framebuf = bytearray()
                    self.framebuf += buf[2:]  # because bytearray.
                except struct.error:  # usually means fatal connection error.
                    util.log(2, "Short Frame Fault! opcode:", hex(op))
                    util.log(2, "Frame:", buf)
                    self.fault = VWTPException("Short Frame Fault.")
                    return
            else:
                self.framebuf += buf
            if op & 0x10 == 0x10:
                if self.proto == 1 and self.framelen != len(
                        self.framebuf):  # "harmless" fault, but only "valid" on KWP.
                    util.log(3, "Frame length mismatch! expected {}, got {}. Attempting to continue...".format(
                        self.framelen, len(self.framebuf)))
                    util.log(4, "Problematic Frame data:", struct.pack("<H", self.framelen) + self.framebuf)
                self.recv(bytes(self.framebuf))
                self.framebuf = None

    def recv(self, frame):
        util.log(5, "Assembled VWTP message:", frame)
        if self.callback:  # if we have a callback, call it
            self.callback(frame)
        else:  # else buffer the frames until the reader swings around
            self.buffer.put(frame)

    def _ack(self, seq):
        buf = bytearray(1)
        buf[0] = 0xB0 + seq
        self._send(bytes(buf))

    def _brk(self):
        util.log(6, "BRK!")
        self._send([0xa4])

    def _send(self, blob):
        #    if self.fault:
        #      raise ValueError("Connection Fault:",self.fault)
        if not self._open and not blob[0] == 0xA8:  # ignore this for "disconnect" messages
            raise VWTPException("Attempted to write to closed connection")
        if self.tx:
            frame = can.Message(arbitration_id=self.tx, data=blob, extended_id=False)
        else:
            frame = can.Message(arbitration_id=0x200, data=blob, extended_id=False)
        self.stack.send(frame)

    def _sendblk(self, blk):
        seq = self.tseq
        wait = False
        for i in range(len(blk)):
            f = blk[i]
            if len(f) < 7:  # last CAN frame
                op = 0x10 + seq
                wait = True
            elif i == self.blksize:  # last frame in block, want an ACK
                wait = True
                op = seq
            else:  # normal data frame
                blk = 0
                op = 0x20 + seq
            seq += 1
            if seq == 0x10:  # clamp to nibble.
                seq = 0
            self._send(bytes([op]) + f)
            if wait:
                self.tseq = seq
                return self._await(seq)

    def _await(self, seq):  # a short little helper stub to await acks.
        if not seq in self.acks:
            time.sleep(self.acktime)  # the actual tomeout value in ms.
        if not seq in self.acks:  # not recieved in time.
            return False
        del self.acks[seq]
        return True

    # note: these send *VWTP frames*! they are *arbitrary bytes-like buffers*
    def send(self, msg):  # this is the *only* code that should be called by user programs.
        if self.fault:
            raise self.fault
        if not self.connected and self.reopen:  # blocking reconnect triggered in recv thread is a *bad* idea. deadlocks abound. do it here.
            self.reconnect()
        self.sending = True
        mv = msg
        if self.proto == 1:  # for KWP only, prepend the length field to the buffer before splitting it apart.
            mv = struct.pack(">H", len(mv)) + mv
        buf = []
        for i in range(0, (len(mv) + 6) // 7, 7):  # round up
            buf.append(mv[i:i + 7])
        blocks = []
        for i in range(0, (len(buf) + self.blksize - 1) // self.blksize, self.blksize):  # round up
            blocks.append(buf[i:i + self.blksize])
        for blk in blocks:
            retry = 10
            sent = False
            while not sent and self.sending:  # repeat blocks that time out
                with self.lock:  # avoid "sliced" blocks if a reconnect occurs in the middle. finish flushing the block and bail first.
                    sent = self._sendblk(blk)
                    retry -= 1
                    if not sent:  # missed an ACK, send a BRK to flush the buffers.
                        self._brk()
                    if retry == 0:  # not an assert, otherwise "optimized" use would spinlock by infinitely trying to send.
                        raise ERETRY("Retry limit exceeded, aborting!")
            if not self.sending:
                util.log(5, "Send cut short by reconnect.")
                raise VWTPException("Send cut short by reconnect.")
        self.sending = False

    def read(self, timeout=None):  # note: this is *ONLY VALID* if there's no callback registered.
        return self.buffer.get(timeout=timeout)

    def close(self, check=False):
        if self._open:  # don't close the socket twice.
            self._open = False
            if not check or not self.reopen:
                self.stack.disconnect(self)  # call back to our stack manager for cleanup
                self.pinger.join()  # and wait for our pinger to die (if it should...)
                self.finalize()

    def finalize(self):  # wait for ECU to ack disconnect
        try:
            self.fin.get(timeout=.1)
        except queue.Empty:
            pass

    def __exit__(self, type, value, traceback):
        self.reopen = False  # clean disconnect, don't reconnect.
        self.close()
        if value:
            return False  # our sole purpose here is to close the connection on the ECU side.
        else:
            return True

    def __enter__(self):  # we only use the context manager for auto-cleanup.
        return self

    def __del__(self):
        if self._open:
            print("WARN: VWTP connection garbage-collected before being closed!")
            self.reopen = False
            self.pinger.join()  # if we're being GCed, the stack object's already gone.


class VWTPStack:
    def __init__(self, socket, sync=True):
        self.socket = socket
        # a sparse list of connections based on recv address.
        self.connections = {}
        self.framebuf = {}  # a sparse frame buffer based on recieved address. *must* register a dest before messages will be buffered!
        self.sync = sync
        self.open = True
        # frame buffers and connection table modifications are behind this lock.
        self.buflock = threading.Lock()
        self.next = 0x300

        if sync:
            # socket is synchronous, start the listener thread.
            self.recvthread = threading.Thread(target=recvthread, args=(self,))
            self.recvthread.start()
        else:
            self.recvthread = None

    def stop(self):
        pass

    def enum(self):
        raise NotImplementedError("VWTP over CAN bus contains no usable enumeration primitives.")

    def _register(self, dest):
        global DEBUG
        with self.buflock:
            if dest in self.framebuf:
                return
            else:
                util.log(6, "Registering simple-frame handler for dest:", dest)
                self.framebuf[dest] = queue.Queue()

    def _unregister(self, dest):  # note: only one user of an address can exist at a time!
        global DEBUG
        with self.buflock:
            if dest in self.framebuf:
                del self.framebuf[dest]
                util.log(6, "Unregistering simple-frame handler for dest:", dest)

    def _recv(self, msg):
        global DEBUG
        with self.buflock:  # fix a race condition when frames are duplicated, a time-of-check race.
            if msg.arbitration_id in self.connections:
                util.log(6, "Got VWTP subframe:", msg)
                self.connections[msg.arbitration_id]._recv(
                    msg.data)  # note: _recv is for CAN frame data, recv is called when a *VWTP* frame is constructed.
            elif msg.arbitration_id in self.framebuf:
                util.log(5, "Got link control frame:", msg)
                self.framebuf[msg.arbitration_id].put(msg.data)

    def send(self, msg):
        util.log(6, "Sending frame:", msg)
        self.socket.send(msg)

    def connect(self, dest, callback=None,
                proto=1):  # note: the *logical* destination, also known as the unit identifier
        util.log(5, "Connecting to ECU:", dest)
        # connect frame format:
        # 0x0: component ID
        # 0x1: opcode (0xC0: setup request, 0xD0: positive respose, 0xD6..D8: negative response)
        # 0x2: RX ID low
        # 0x3: RX ID high #note: both high bytes contain an additional flag bit at 0x10(?) that denotes
        # 0x4: TX ID low  #ID validity; with '0' being valid.
        # 0x5: TX ID high
        # 0x6: Application type, 0x01 for KWP(?)
        rx = None
        self._register(0x200 + dest)  # this needs to be outside the lock, because it uses it itself.
        with self.buflock:  # yes, the whole connection is inside the lock; mostly for concurrency issues.
            addr = self.next
            idx = 0
            while addr in self.connections:  # if the chosen address is in-use, cycle it.
                addr += 1
                if addr == 0x310:
                    addr = 0x300
                idx += 1
                if idx == 11:
                    raise VWTPException("No free RX channels")
            self.next = addr + 1 if addr != 0x30f else 0x300
            rx = addr
            # self._register(0x200 + dest) #register the response address so we don't drop frames...
            frame = [None] * 7
            frame[0] = dest
            frame[1] = 0xC0  # setup request
            frame[2] = 0
            frame[3] = 0x10  # high nibble of high byte set to invalid
            frame[4] = rx & 255  # low byte of address
            frame[5] = (rx / 256) & 255  # high nibble, 0x300-310 are the usually seen ones
            frame[6] = proto  # default is KWP transport
            msg = can.Message(arbitration_id=0x200, data=frame, is_extended_id=False)
            self.send(msg)
            try:
                msg = self.framebuf[0x200 + dest].get(timeout=.3)  # 300ms timeout for connect interrogation.
            except queue.Empty:
                raise ETIME("Channel Connect timeout")
            self._unregister(0x200 + dest)
            blob = msg
            assert blob[0] == dest, "Recieved connect response for different module? {}".format(
                blob[0])  # how would this even be *possible*? should still catch it though.
            assert blob[1] == 0xd0, "Negative or invalid response to connect: {}".format(
                blob[1])  # invalid or negative connect response.
            assert blob[
                       5] & 0x10 == 0, "ECU gave us an invalid TX address?"  # shouldn't happen, but trap it if it does.
            tx = (blob[5] * 256) + blob[4]
            conn = VWTPConnection(self, tx, callback)  # tx is usually 0x740.
            conn.rx = rx
            conn.mod_id = dest
            self.connections[rx] = conn  # pin the connection to the RX address we picked.
            util.log(5, "Connected")
            conn.proto = proto  # inform the connection object what "quirks" it needs to apply.
            conn.open()
            return conn

    def _connect(self, rx, tx, proto=None, callback=None):
        util.log(5, "Opening pre-established communication channel...")
        VWTPConnection(self, tx, callback)
        conn.rx = rx  # FIXME: What's conn?
        conn.proto = proto  # inform connection structure which quirks to apply.
        with self.buflock:
            self.connections[rx] = conn
        conn.open()
        util.log(5, "Opened.")
        return conn

    def reconnect(self, conn, proto=1):
        dest = conn.mod_id  # locking is unnecessary here, since we aren't peering into connection structures.
        util.log(5, "Re-connecting to ECU:", hex(dest))
        frame = [None] * 7
        frame[0] = dest
        frame[1] = 0xC0  # setup request
        frame[2] = 0
        frame[3] = 0x10  # high nibble of high byte set to invalid
        frame[4] = conn.rx
        frame[5] = (conn.rx / 256) & 0x0F  # re-use the RX address we already allocated.
        frame[6] = proto  # default is KWP transport
        with self.buflock:  # only need to hold this until we unregister link-control, since we're not modifying or using the connection table (RX address already allocated)
            self._register(0x200 + dest)  # register the response address so we don't drop frames...
            msg = can.Message(arbitration_id=0x200, data=frame, is_extended_id=False)
            self.send(msg)
            try:
                msg = self.framebuf[0x200 + dest].get(timeout=.2)  # 200ms timeout for connect interrogation.
            except queue.Empty:
                raise ETIME("Reconnect Timeout")
            self._unregister(0x200 + dest)
        blob = msg
        assert blob[5] & 0x10 == 0, "ECU gave us an invalid TX address?"  # shouldn't happen, but trap it if it does.
        tx = (blob[5] * 256) + blob[4]
        conn.tx = tx  # give it the new TX address.
        util.log(5, "Reconnected")

    def disconnect(self, con):
        con._send([0xA8])
        for k, v in self.connections.items():
            if v is con:
                util.log(5, "Disconnected from ECU channel:", k)
                try:
                    del self.connections[k]
                except KeyError:
                    pass  # this just means we've already disconnected.
                break

    def __enter__(self):
        return self

    def __exit__(self, a, b, c):
        self.open = False
        if self.recvthread:
            self.recvthread.join()
            self.recvthread = None
