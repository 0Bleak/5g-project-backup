#!/usr/bin/env python3
from gnuradio import gr, blocks, zeromq

class MultiUEBroker(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "6-UE ZMQ Broker")

        self.gnb_dl_src = zeromq.req_source(gr.sizeof_gr_complex, 1,
            "tcp://127.0.0.1:3000", 100, False, -1)

        dl_ports = [3010, 3100, 3200, 4010, 4100, 4200]
        self.ue_dl_sinks = []
        for port in dl_ports:
            sink = zeromq.rep_sink(gr.sizeof_gr_complex, 1,
                f"tcp://127.0.0.1:{port}", 100, False, -1)
            self.ue_dl_sinks.append(sink)
            self.connect(self.gnb_dl_src, sink)

        ul_ports = [3001, 3101, 3201, 4001, 4101, 4201]
        self.ue_ul_srcs = []
        self.adder = blocks.add_cc(1)
        self.gnb_ul_sink = zeromq.rep_sink(gr.sizeof_gr_complex, 1,
            "tcp://127.0.0.1:3009", 100, False, -1)

        for i, port in enumerate(ul_ports):
            src = zeromq.req_source(gr.sizeof_gr_complex, 1,
                f"tcp://127.0.0.1:{port}", 100, False, -1)
            self.ue_ul_srcs.append(src)
            self.connect(src, (self.adder, i))

        self.connect(self.adder, self.gnb_ul_sink)

if __name__ == "__main__":
    tb = MultiUEBroker()
    print("[BROKER] 6-UE ZMQ broker starting")
    print("[BROKER] DL: gNB:3000 -> UE1:3010, UE2:3100, UE3:3200, UE4:4010, UE5:4100, UE6:4200")
    print("[BROKER] UL: UE1:3001, UE2:3101, UE3:3201, UE4:4001, UE5:4101, UE6:4201 -> gNB:3009")
    try:
        tb.start()
        tb.wait()
    except KeyboardInterrupt:
        tb.stop()
        tb.wait()
