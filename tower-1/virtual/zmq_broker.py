#!/usr/bin/env python3
from gnuradio import gr, blocks, zeromq

class MultiUEBroker(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "3-UE ZMQ Broker")
        self.gnb_dl_src = zeromq.req_source(gr.sizeof_gr_complex, 1,
            "tcp://127.0.0.1:3000", 100, False, -1)
        self.ue1_dl_sink = zeromq.rep_sink(gr.sizeof_gr_complex, 1,
            "tcp://127.0.0.1:3010", 100, False, -1)
        self.ue2_dl_sink = zeromq.rep_sink(gr.sizeof_gr_complex, 1,
            "tcp://127.0.0.1:3100", 100, False, -1)
        self.ue3_dl_sink = zeromq.rep_sink(gr.sizeof_gr_complex, 1,
            "tcp://127.0.0.1:3200", 100, False, -1)
        self.connect(self.gnb_dl_src, self.ue1_dl_sink)
        self.connect(self.gnb_dl_src, self.ue2_dl_sink)
        self.connect(self.gnb_dl_src, self.ue3_dl_sink)
        self.ue1_ul_src = zeromq.req_source(gr.sizeof_gr_complex, 1,
            "tcp://127.0.0.1:3001", 100, False, -1)
        self.ue2_ul_src = zeromq.req_source(gr.sizeof_gr_complex, 1,
            "tcp://127.0.0.1:3101", 100, False, -1)
        self.ue3_ul_src = zeromq.req_source(gr.sizeof_gr_complex, 1,
            "tcp://127.0.0.1:3201", 100, False, -1)
        self.gnb_ul_sink = zeromq.rep_sink(gr.sizeof_gr_complex, 1,
            "tcp://127.0.0.1:3009", 100, False, -1)
        self.adder = blocks.add_cc(1)
        self.connect(self.ue1_ul_src, (self.adder, 0))
        self.connect(self.ue2_ul_src, (self.adder, 1))
        self.connect(self.ue3_ul_src, (self.adder, 2))
        self.connect(self.adder, self.gnb_ul_sink)

if __name__ == "__main__":
    tb = MultiUEBroker()
    print("[BROKER] 3-UE ZMQ broker starting")
    print("[BROKER] DL: gNB:3000 -> UE1:3010, UE2:3100, UE3:3200")
    print("[BROKER] UL: UE1:3001, UE2:3101, UE3:3201 -> gNB:3009")
    try:
        tb.start()
        tb.wait()
    except KeyboardInterrupt:
        tb.stop()
        tb.wait()
