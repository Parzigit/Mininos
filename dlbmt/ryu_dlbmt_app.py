"""
DLBMT Ryu Controller Application
---------------------------------
Each Ryu instance identifies itself via the DLBMT_CONTROLLER_ID env var.
It collects per-switch packet-in counts and process-level CPU/memory metrics,
then POSTs them to the Flask backend every second.

Launch example:
    DLBMT_CONTROLLER_ID=c1 ryu-manager ryu_dlbmt_app.py \
        --ofp-tcp-listen-port 6633
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet
from ryu.lib import hub

import requests
import psutil
import os
import logging

LOG = logging.getLogger(__name__)

# Flask endpoint where metrics are sent
FLASK_ENDPOINT = os.environ.get(
    "DLBMT_FLASK_ENDPOINT", "http://127.0.0.1:5000/api/ryu/update"
)


def _get_controller_id():
    """Read controller ID from DLBMT_CONTROLLER_ID environment variable."""
    return os.environ.get("DLBMT_CONTROLLER_ID", "unknown")


class DLBMTRyuApp(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.controller_id = _get_controller_id()
        self.mac_to_port = {}          # dpid -> {mac: port}
        self.switch_packet_counts = {} # dpid -> count (reset each interval)

        self._process = psutil.Process()
        # Prime cpu_percent so first real call returns meaningful value
        self._process.cpu_percent(interval=None)

        self.monitor_thread = hub.spawn(self._monitor)
        LOG.info("DLBMT Ryu app started — controller_id=%s", self.controller_id)

    # ------------------------------------------------------------------
    #  Monitor thread — POSTs metrics to Flask every 1 second
    # ------------------------------------------------------------------

    def _monitor(self):
        while True:
            hub.sleep(1)
            try:
                # Snapshot and reset packet counts atomically-ish
                counts = {}
                for dpid in list(self.switch_packet_counts.keys()):
                    counts[str(dpid)] = self.switch_packet_counts.get(dpid, 0)
                    self.switch_packet_counts[dpid] = 0

                # Process-level metrics (no artificial multipliers)
                cpu = self._process.cpu_percent(interval=None)
                mem = self._process.memory_percent()

                payload = {
                    "controller_id": self.controller_id,
                    "cpu": cpu,
                    "memory": mem,
                    "switches": counts,
                }

                requests.post(FLASK_ENDPOINT, json=payload, timeout=2)

            except Exception as e:
                LOG.debug("Monitor send failed: %s", e)

    # ------------------------------------------------------------------
    #  Switch connected — install table-miss flow
    # ------------------------------------------------------------------

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        self.switch_packet_counts.setdefault(datapath.id, 0)

        # Table-miss: send to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(
            ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER
        )]
        self._add_flow(datapath, 0, match, actions, idle_timeout=0)

        LOG.info("Switch %s connected to %s", datapath.id, self.controller_id)

    # ------------------------------------------------------------------
    #  Flow install helper
    # ------------------------------------------------------------------

    def _add_flow(self, datapath, priority, match, actions,
                  idle_timeout=30, hard_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(
            ofproto.OFPIT_APPLY_ACTIONS, actions
        )]

        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
        )
        datapath.send_msg(mod)

    # ------------------------------------------------------------------
    #  Packet-In handler — L2 learning switch with short-lived flows
    # ------------------------------------------------------------------

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        dpid = datapath.id
        self.switch_packet_counts.setdefault(dpid, 0)
        self.switch_packet_counts[dpid] += 1

        self.mac_to_port.setdefault(dpid, {})

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return

        # Ignore LLDP
        if eth.ethertype == 0x88cc:
            return

        dst = eth.dst
        src = eth.src
        in_port = msg.match["in_port"]

        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # DEMO MODE: Do NOT install flow rules.
        # Every packet must go to the controller as a packet-in so that
        # the DLBMT engine can observe sustained load. If flows were
        # installed, traffic would bypass the controller after the first
        # packet and load would drop to zero — defeating the demo.
        # The MAC learning table above still ensures correct forwarding
        # via PacketOut (no loops).

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)
