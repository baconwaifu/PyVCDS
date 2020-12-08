#!/usr/bin/env python3

# import tracer
import json

# import tracer
import can

import sniff.vw
import sniff.vw
import util


# NOTE: this is designed for tracing *RAW VWTP SESSIONS*.
# there is *NO* higher-level protocol decoding implemented here.
# since VWTP borrows the CAN concept of "Message ID" for addressing,
# there is no easy way to associate multiple connections without seeing the start-up procedures
# or manual correllation with candump or wireshark.
# fortunately, VWTP includes explicit end-of-packet opcodes, so synchonizing recv buffers with the transmitter
# is relatively painless

class VWTPConnection:
    def __init__(self, num):
        self.num = hex(num)  # we don't do any math on it, so we can stringify it here.
        self.framebuf = None
        self.framelen = 0
        self.start = True
        self.blksize = None
        self.seq = 0

    def _recv(self, msg):
        buf = msg.data  # the raw buffer contents of a CAN frame.
        op = buf[0]
        buf = buf[1:]  # drop the opcode from the frame.
        if op == 0xA8:  # disconnect
            self.close()
        elif op == 0xA3:  # "ping"
            util.log(5, "[{}] Ping!".format(self.num))
        elif op == 0xA1:  # params response, also sent as a "Pong!"
            if self.blksize:
                util.log(6, "[{}] Pong!".format(self.num))  # already configured, so it's a pong.
                # util.log(3,"[{}] Potential connection fault: recieved 'parameter response' when already configured!".format(self.num))
                return
            self.blksize = buf[0] + 1  # 0 is "1 frame" #we don't actually *use* this, other than "config or pong?"
            scale = [.1, 1, 10, 100]
            acktime = buf[1] >> 6  # scale is 100ms, 10ms, 1ms, .1ms
            acktime = (scale[acktime] * (buf[1] & 0x3F)) * 0.001  # go from ms to s.
            packival = (scale[buf[3] >> 6] * (buf[3] & 0x3F)) * 0.001
            util.log(5, "[{}] Parameter response received.".format(self.num))
            util.log(6, "channel parameters:",
                     "\nTimeout in ms:", acktime * 1000, "\nMinimum Interval between frames in ms:", packival * 1000,
                     "\nBlock Size:", self.blksize)
        elif op & 0xf0 == 0xB0 or op & 0xf0 == 0x90:
            util.log(5, "[{}] Acked block".format(self.num))
        else:  # assume it's a data packet.
            seq = op & 0x0f
            if op & 0x20 == 0 and seq == self.seq:  # expecting ACK
                util.log(5, "[{}] Expecting Ack".format(self.num))
            self.seq += 1
            if self.seq == 0x10:
                self.seq = 0
            if not self.framebuf:  # first frame of a transaction
                util.log(5, "[{}] Frame start".format(self.num))
                if op & 0x10 == 0x10:
                    util.log(5, "[{}] Short frame".format(self.num))
                    self.recv(bytes(buf))  # single-frame short-circuit
                    self.framebuf = None
                    return
                self.framebuf = bytearray()
                self.framebuf += buf  # the length is only a feature of VWTP/KWP, and is not part of VWTP itself.
            else:
                util.log(6, "[{}] Subframe recieved".format(self.num))
                self.framebuf += buf
            if op & 0x10 == 0x10:  # final subframe
                util.log(5, "[{}] Received frame finalizer".format(self.num))
                #        if self.framelen != len(self.framebuf) and not self.start: #already synchronized
                #          util.log(3,"[{}] Frame length mismatch! expected {}, got {}. Attempting to continue...".format(self.num,self.framelen, len(self.framebuf)))
                #        elif self.framelen != len(self.framebuf) and self.start: #not synced, may have started in middle of frame
                #          util.log(4,"[{}] First frame is partial, now fully synchronized".format(self.num))
                self.start = False
                self.recv(bytes(self.framebuf))
                self.framebuf = None

    def close(self):
        self.blksize = None
        util.log(5, "[{}] Disconnect".format(self.num))

    def recv(self, frame):
        util.log(4, "[{}] Received VWTP Message:".format(self.num), repr(frame))


if __name__ == "__main__":
    sessions = {}

    try:
        with open("config.json", "r") as fd:
            opts = json.loads(fd.read())
    except FileNotFoundError:  # write default config.
        opts = {"channel": "can0", "bustype": "socketcan"}
        with open("config.json", 'w') as fd:
            fd.write(json.dumps(opts))
    sock = can.interface.Bus(**opts)
    while True:
        msg = sock.recv()
        if not msg.arbitration_id in sessions:
            if msg.arbitration_id > 0x660:
                sessions[msg.arbitration_id] = VWTPConnection(msg.arbitration_id)
        if msg.arbitration_id > 0x660:
            sessions[msg.arbitration_id]._recv(msg)
        else:
            if msg.arbitration_id in sniff.vw.models["3C"]:
                util.log(5, sniff.vw.models["3C"].repr(msg))
            else:
                util.log(6, "Untracked frame from address '{}'".format(msg.arbitration_id))
