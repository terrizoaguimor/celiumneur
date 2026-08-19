// celiumneur_soc.v — CeliumNeUR SoC v1: 4 neuro_tiles on the Hyphae 2x2 mesh.
// SPDX-License-Identifier: Apache-2.0
//
// Wiring contract per core (SPEC §2 + tile seam):
//   tile.out_spk_*  -> mesh PE ingress      (fire packets into the fabric)
//   mesh PE egress  -> tile.spk_*           (arriving spikes into the dendrite)
//   mesh feeder_ret -> SoC PE credit counter (tile sends only against room)
//
// Explicit flat wiring (no generate gymnastics — 4 tiles is small enough to
// read, and any wiring error should be visible at a glance).

`default_nettype none

module celiumneur_soc #(
    parameter NEURONS_PER_TILE    = 256,
    parameter ID_BITS            = 8,
    parameter SYNAPSES_PER_TILE  = 256,
    parameter SYNAPSE_ADDR_BITS  = 8
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        tick,
    output wire        tick_ready,
    output wire        tick_backpressure,
    output wire        tick_overflow_wit,

    // Hyphae host ingress. Configuration is carried by routed packets; there
    // is no host-visible register-write sideband in this SoC.
    input  wire        host_valid,
    input  wire [31:0] host_packet,
    output wire        host_ready,

    // stimulus (electrode injection), tile-selected
    // Integration gate: tile deliveries integrate only while open. Packets
    // stamped with the CURRENT tick parity wait — they are this-phase
    // cascades and belong to the next phase (the sandbox semantic, in metal).
    input  wire        integrate_open,

    input  wire [1:0]  stim_tile,
    input  wire        stim_valid,
    input  wire [7:0]  stim_neuron,
    input  wire [7:0]  stim_weight,
    output wire        stim_ready,

    // readback, tile-selected (I5)
    input  wire [1:0]  rb_tile,
    input  wire [7:0]  rb_addr,
    input  wire        rb_req,
    output wire [26:0] rb_dend_rdata,
    output wire [63:0] rb_soma_data,
    output wire        rb_ready,
    output wire        rb_valid,

    output wire [3:0]  mesh_overflow_any,
    output wire [3:0]  tile_overflow_any,
    output wire [3:0]  tile_backpressure,
    output wire [3:0]  tile_busy,
    output wire [3:0]  tile_dend_busy,
    output wire [31:0] spike_backpressure_count,
    output wire [3:0]  config_protocol_error,
    output wire [3:0]  unsupported_packet_wit
);

    // ---------------- mesh-side wires
    wire [127:0] pe_in_data;
    wire [3:0]   pe_in_valid;
    wire [127:0] pe_out_data;
    wire [3:0]   pe_out_valid;
    wire [3:0]   pe_feeder_ret;
    wire [3:0]   pe_delivery_ready;
    wire [3:0]   pe_local_mask_ok;
    wire [3:0]   pe_reserved_ok;

    // ---------------- tile-side wires
    wire [3:0]  t_out_spk_valid;
    wire [3:0]  t_spk_ready;
    wire [3:0]  t_tick_ready;
    wire [3:0]  t_stim_ready;
    wire [3:0]  t_cfg_ready;
    wire [3:0]  t_cfg_soma_ready;
    wire [3:0]  t_cfg_axon_ready;
    wire [31:0] t_pk0, t_pk1, t_pk2, t_pk3;
    // stall witnesses read hierarchically from the bench when needed
    wire [26:0] t_rd0, t_rd1, t_rd2, t_rd3;
    wire [63:0] t_rs0, t_rs1, t_rs2, t_rs3;
    wire [3:0]  t_rb_ready;
    wire [3:0]  t_rb_valid;

    // ---------------- routed configuration endpoints ------------------
    localparam [3:0] TYPE_SPIKE  = 4'h1;
    localparam [3:0] TYPE_CONFIG = 4'h2;
    wire [3:0]   c_pkt_ready;
    wire [3:0]   c_cfg_en;
    wire [7:0]   c_cfg_space;
    wire [31:0]  c_cfg_addr;
    wire [255:0] c_cfg_data;

    assign pe_local_mask_ok[0] = pe_out_data[23:20] == 4'b0001;
    assign pe_local_mask_ok[1] = pe_out_data[55:52] == 4'b0010;
    assign pe_local_mask_ok[2] = pe_out_data[87:84] == 4'b0100;
    assign pe_local_mask_ok[3] = pe_out_data[119:116] == 4'b1000;
    assign pe_reserved_ok[0] = pe_out_data[27:24] == 4'd0;
    assign pe_reserved_ok[1] = pe_out_data[59:56] == 4'd0;
    assign pe_reserved_ok[2] = pe_out_data[91:88] == 4'd0;
    assign pe_reserved_ok[3] = pe_out_data[123:120] == 4'd0;

    // ---------------- global tick queue --------------------------------
    // A tick is accepted once and dispatched atomically to all four tiles.
    // Backpressure is public; a producer holds tick while !tick_ready.
    wire tickq_empty, tickq_full, tickq_overflow;
    wire all_tiles_tick_ready = &t_tick_ready;
    wire tick_dispatch = !tickq_empty && all_tiles_tick_ready;

    // Tick tokens carry no payload beyond their presence.
    /* verilator lint_off PINCONNECTEMPTY */
    hypha_link_fifo #(
        .WIDTH(1), .DEPTH(8), .ADDR_BITS(3), .COUNT_BITS(4)
    ) tickq (
        .clk(clk), .rst_n(rst_n),
        .push(tick && tick_ready), .din(1'b1),
        .pop(tick_dispatch), .dout(), .empty(tickq_empty),
        .full(tickq_full), .overflow(tickq_overflow)
    );
    /* verilator lint_on PINCONNECTEMPTY */

    assign tick_ready = !tickq_full;
    assign tick_backpressure = tick && !tick_ready;
    assign tick_overflow_wit = tickq_overflow;
    assign stim_ready = t_stim_ready[stim_tile];

    // ---------------- per-core PE credit counters (room tracking)
    reg [3:0] pe_credit [3:0];
    wire pc_ok0 = (pe_credit[0] != 0);
    wire pc_ok1 = (pe_credit[1] != 0);
    wire pc_ok2 = (pe_credit[2] != 0);
    wire pc_ok3 = (pe_credit[3] != 0);
    wire host_select = host_valid;
    assign host_ready = pc_ok0;
    integer cc;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (cc = 0; cc < 4; cc = cc + 1) pe_credit[cc] <= 4'd4;
        end else begin
            for (cc = 0; cc < 4; cc = cc + 1) begin
                case ({pe_feeder_ret[cc], pe_in_valid[cc]})
                    2'b10: pe_credit[cc] <= pe_credit[cc] + 4'd1;
                    2'b01: pe_credit[cc] <= pe_credit[cc] - 4'd1;
                    default: ;
                endcase
            end
        end
    end

    wire c_commit_ready0 = (c_cfg_space[1:0] == 2'd0) ? t_cfg_ready[0] :
                           (c_cfg_space[1:0] == 2'd1) ? t_cfg_soma_ready[0] :
                           (c_cfg_space[1:0] == 2'd2) ? t_cfg_axon_ready[0] : 1'b0;
    wire c_commit_ready1 = (c_cfg_space[3:2] == 2'd0) ? t_cfg_ready[1] :
                           (c_cfg_space[3:2] == 2'd1) ? t_cfg_soma_ready[1] :
                           (c_cfg_space[3:2] == 2'd2) ? t_cfg_axon_ready[1] : 1'b0;
    wire c_commit_ready2 = (c_cfg_space[5:4] == 2'd0) ? t_cfg_ready[2] :
                           (c_cfg_space[5:4] == 2'd1) ? t_cfg_soma_ready[2] :
                           (c_cfg_space[5:4] == 2'd2) ? t_cfg_axon_ready[2] : 1'b0;
    wire c_commit_ready3 = (c_cfg_space[7:6] == 2'd0) ? t_cfg_ready[3] :
                           (c_cfg_space[7:6] == 2'd1) ? t_cfg_soma_ready[3] :
                           (c_cfg_space[7:6] == 2'd2) ? t_cfg_axon_ready[3] : 1'b0;

    hypha_config_endpoint ce0 (
        .clk(clk), .rst_n(rst_n),
        .pkt_valid(pe_out_valid[0] && pe_local_mask_ok[0] && pe_reserved_ok[0]
                   && pe_out_data[31:28] == TYPE_CONFIG),
        .pkt_body(pe_out_data[19:0]), .pkt_ready(c_pkt_ready[0]),
        .cfg_en(c_cfg_en[0]), .cfg_space(c_cfg_space[1:0]),
        .cfg_addr(c_cfg_addr[7:0]), .cfg_data(c_cfg_data[63:0]),
        .cfg_ready(c_commit_ready0),
        .protocol_error_wit(config_protocol_error[0])
    );
    hypha_config_endpoint ce1 (
        .clk(clk), .rst_n(rst_n),
        .pkt_valid(pe_out_valid[1] && pe_local_mask_ok[1] && pe_reserved_ok[1]
                   && pe_out_data[63:60] == TYPE_CONFIG),
        .pkt_body(pe_out_data[51:32]), .pkt_ready(c_pkt_ready[1]),
        .cfg_en(c_cfg_en[1]), .cfg_space(c_cfg_space[3:2]),
        .cfg_addr(c_cfg_addr[15:8]), .cfg_data(c_cfg_data[127:64]),
        .cfg_ready(c_commit_ready1),
        .protocol_error_wit(config_protocol_error[1])
    );
    hypha_config_endpoint ce2 (
        .clk(clk), .rst_n(rst_n),
        .pkt_valid(pe_out_valid[2] && pe_local_mask_ok[2] && pe_reserved_ok[2]
                   && pe_out_data[95:92] == TYPE_CONFIG),
        .pkt_body(pe_out_data[83:64]), .pkt_ready(c_pkt_ready[2]),
        .cfg_en(c_cfg_en[2]), .cfg_space(c_cfg_space[5:4]),
        .cfg_addr(c_cfg_addr[23:16]), .cfg_data(c_cfg_data[191:128]),
        .cfg_ready(c_commit_ready2),
        .protocol_error_wit(config_protocol_error[2])
    );
    hypha_config_endpoint ce3 (
        .clk(clk), .rst_n(rst_n),
        .pkt_valid(pe_out_valid[3] && pe_local_mask_ok[3] && pe_reserved_ok[3]
                   && pe_out_data[127:124] == TYPE_CONFIG),
        .pkt_body(pe_out_data[115:96]), .pkt_ready(c_pkt_ready[3]),
        .cfg_en(c_cfg_en[3]), .cfg_space(c_cfg_space[7:6]),
        .cfg_addr(c_cfg_addr[31:24]), .cfg_data(c_cfg_data[255:192]),
        .cfg_ready(c_commit_ready3),
        .protocol_error_wit(config_protocol_error[3])
    );

    assign pe_delivery_ready[0] = (!pe_local_mask_ok[0] || !pe_reserved_ok[0]) ? 1'b0 :
                                  (pe_out_data[31:28] == TYPE_SPIKE)
                                ? t_spk_ready[0]
                                : (pe_out_data[31:28] == TYPE_CONFIG)
                                ? c_pkt_ready[0] : 1'b0;
    assign pe_delivery_ready[1] = (!pe_local_mask_ok[1] || !pe_reserved_ok[1]) ? 1'b0 :
                                  (pe_out_data[63:60] == TYPE_SPIKE)
                                ? t_spk_ready[1]
                                : (pe_out_data[63:60] == TYPE_CONFIG)
                                ? c_pkt_ready[1] : 1'b0;
    assign pe_delivery_ready[2] = (!pe_local_mask_ok[2] || !pe_reserved_ok[2]) ? 1'b0 :
                                  (pe_out_data[95:92] == TYPE_SPIKE)
                                ? t_spk_ready[2]
                                : (pe_out_data[95:92] == TYPE_CONFIG)
                                ? c_pkt_ready[2] : 1'b0;
    assign pe_delivery_ready[3] = (!pe_local_mask_ok[3] || !pe_reserved_ok[3]) ? 1'b0 :
                                  (pe_out_data[127:124] == TYPE_SPIKE)
                                ? t_spk_ready[3]
                                : (pe_out_data[127:124] == TYPE_CONFIG)
                                ? c_pkt_ready[3] : 1'b0;

    assign unsupported_packet_wit[0] = pe_out_valid[0]
        && (!pe_local_mask_ok[0] || !pe_reserved_ok[0]
            || (pe_out_data[31:28] != TYPE_SPIKE
                && pe_out_data[31:28] != TYPE_CONFIG));
    assign unsupported_packet_wit[1] = pe_out_valid[1]
        && (!pe_local_mask_ok[1] || !pe_reserved_ok[1]
            || (pe_out_data[63:60] != TYPE_SPIKE
                && pe_out_data[63:60] != TYPE_CONFIG));
    assign unsupported_packet_wit[2] = pe_out_valid[2]
        && (!pe_local_mask_ok[2] || !pe_reserved_ok[2]
            || (pe_out_data[95:92] != TYPE_SPIKE
                && pe_out_data[95:92] != TYPE_CONFIG));
    assign unsupported_packet_wit[3] = pe_out_valid[3]
        && (!pe_local_mask_ok[3] || !pe_reserved_ok[3]
            || (pe_out_data[127:124] != TYPE_SPIKE
                && pe_out_data[127:124] != TYPE_CONFIG));

    // ---------------- tiles
    // Defaults preserve the reference network while each per-neuron axon mask
    // remains host-configurable through cfg_space=2.
    neuro_tile #(
        .ENTRIES(SYNAPSES_PER_TILE), .ENTRY_ADDR_BITS(SYNAPSE_ADDR_BITS),
        .NEURONS(NEURONS_PER_TILE), .ID_BITS(ID_BITS),
        .GID_BASE(0 * NEURONS_PER_TILE), .DEFAULT_AXON_MASK(4'h4)
    ) t0 (
        .clk(clk), .rst_n(rst_n),
        .spk_valid(pe_out_valid[0] && pe_local_mask_ok[0] && pe_reserved_ok[0]
                   && pe_out_data[31:28] == TYPE_SPIKE),
        .spk_gid(pe_out_data[9:0]),
        .spk_parity(pe_out_data[19]), .spk_ready(t_spk_ready[0]),
        .spk_overflow_wit(spike_backpressure_count[7:0]),
        .dend_busy(tile_dend_busy[0]), .integrate_open(integrate_open),
        .stim_valid(stim_valid && (stim_tile == 2'd0)),
        .stim_neuron(stim_neuron), .stim_weight(stim_weight),
        .stim_ready(t_stim_ready[0]),
        .tick(tick_dispatch), .tick_ready(t_tick_ready[0]),
        .cfg_en(c_cfg_en[0] && c_cfg_space[1:0] == 2'd0),
        .cfg_addr(c_cfg_addr[SYNAPSE_ADDR_BITS-1:0]),
        .cfg_wdata(c_cfg_data[26:0]), .cfg_ready(t_cfg_ready[0]),
        .cfg_soma_en(c_cfg_en[0] && c_cfg_space[1:0] == 2'd1),
        .cfg_soma_addr(c_cfg_addr[7:0]), .cfg_soma_wdata(c_cfg_data[63:0]),
        .cfg_soma_ready(t_cfg_soma_ready[0]),
        .cfg_axon_en(c_cfg_en[0] && c_cfg_space[1:0] == 2'd2),
        .cfg_axon_addr(c_cfg_addr[ID_BITS-1:0]),
        .cfg_axon_wdata(c_cfg_data[3:0]),
        .cfg_axon_ready(t_cfg_axon_ready[0]),
        .rb_dend_addr(rb_addr[SYNAPSE_ADDR_BITS-1:0]), .rb_dend_rdata(t_rd0),
        .rb_soma_addr(rb_addr), .rb_soma_req(rb_req && (rb_tile == 2'd0)),
        .rb_soma_data(t_rs0), .rb_soma_ready(t_rb_ready[0]),
        .rb_soma_valid(t_rb_valid[0]),
        .out_spk_valid(t_out_spk_valid[0]), .out_spk_pkt(t_pk0),
        .out_spk_ready(pc_ok0 && !host_select),
        .out_stall_wit(tile_backpressure[0]),
        .fire_overflow_wit(tile_overflow_any[0]), .tile_busy(tile_busy[0])
    );

    neuro_tile #(
        .ENTRIES(SYNAPSES_PER_TILE), .ENTRY_ADDR_BITS(SYNAPSE_ADDR_BITS),
        .NEURONS(NEURONS_PER_TILE), .ID_BITS(ID_BITS),
        .GID_BASE(1 * NEURONS_PER_TILE), .DEFAULT_AXON_MASK(4'h4)
    ) t1 (
        .clk(clk), .rst_n(rst_n),
        .spk_valid(pe_out_valid[1] && pe_local_mask_ok[1] && pe_reserved_ok[1]
                   && pe_out_data[63:60] == TYPE_SPIKE),
        .spk_gid(pe_out_data[32*1 +: 10]),
        .spk_parity(pe_out_data[32*1 + 19]), .spk_ready(t_spk_ready[1]),
        .spk_overflow_wit(spike_backpressure_count[15:8]),
        .dend_busy(tile_dend_busy[1]), .integrate_open(integrate_open),
        .stim_valid(stim_valid && (stim_tile == 2'd1)),
        .stim_neuron(stim_neuron), .stim_weight(stim_weight),
        .stim_ready(t_stim_ready[1]),
        .tick(tick_dispatch), .tick_ready(t_tick_ready[1]),
        .cfg_en(c_cfg_en[1] && c_cfg_space[3:2] == 2'd0),
        .cfg_addr(c_cfg_addr[8 +: SYNAPSE_ADDR_BITS]),
        .cfg_wdata(c_cfg_data[64 +: 27]), .cfg_ready(t_cfg_ready[1]),
        .cfg_soma_en(c_cfg_en[1] && c_cfg_space[3:2] == 2'd1),
        .cfg_soma_addr(c_cfg_addr[15:8]), .cfg_soma_wdata(c_cfg_data[127:64]),
        .cfg_soma_ready(t_cfg_soma_ready[1]),
        .cfg_axon_en(c_cfg_en[1] && c_cfg_space[3:2] == 2'd2),
        .cfg_axon_addr(c_cfg_addr[8 +: ID_BITS]),
        .cfg_axon_wdata(c_cfg_data[64 +: 4]),
        .cfg_axon_ready(t_cfg_axon_ready[1]),
        .rb_dend_addr(rb_addr[SYNAPSE_ADDR_BITS-1:0]), .rb_dend_rdata(t_rd1),
        .rb_soma_addr(rb_addr), .rb_soma_req(rb_req && (rb_tile == 2'd1)),
        .rb_soma_data(t_rs1), .rb_soma_ready(t_rb_ready[1]),
        .rb_soma_valid(t_rb_valid[1]),
        .out_spk_valid(t_out_spk_valid[1]), .out_spk_pkt(t_pk1),
        .out_spk_ready(pc_ok1), .out_stall_wit(tile_backpressure[1]),
        .fire_overflow_wit(tile_overflow_any[1]), .tile_busy(tile_busy[1])
    );

    neuro_tile #(
        .ENTRIES(SYNAPSES_PER_TILE), .ENTRY_ADDR_BITS(SYNAPSE_ADDR_BITS),
        .NEURONS(NEURONS_PER_TILE), .ID_BITS(ID_BITS),
        .GID_BASE(2 * NEURONS_PER_TILE), .DEFAULT_AXON_MASK(4'h8)
    ) t2 (
        .clk(clk), .rst_n(rst_n),
        .spk_valid(pe_out_valid[2] && pe_local_mask_ok[2] && pe_reserved_ok[2]
                   && pe_out_data[95:92] == TYPE_SPIKE),
        .spk_gid(pe_out_data[32*2 +: 10]),
        .spk_parity(pe_out_data[32*2 + 19]), .spk_ready(t_spk_ready[2]),
        .spk_overflow_wit(spike_backpressure_count[23:16]),
        .dend_busy(tile_dend_busy[2]), .integrate_open(integrate_open),
        .stim_valid(stim_valid && (stim_tile == 2'd2)),
        .stim_neuron(stim_neuron), .stim_weight(stim_weight),
        .stim_ready(t_stim_ready[2]),
        .tick(tick_dispatch), .tick_ready(t_tick_ready[2]),
        .cfg_en(c_cfg_en[2] && c_cfg_space[5:4] == 2'd0),
        .cfg_addr(c_cfg_addr[16 +: SYNAPSE_ADDR_BITS]),
        .cfg_wdata(c_cfg_data[128 +: 27]), .cfg_ready(t_cfg_ready[2]),
        .cfg_soma_en(c_cfg_en[2] && c_cfg_space[5:4] == 2'd1),
        .cfg_soma_addr(c_cfg_addr[23:16]), .cfg_soma_wdata(c_cfg_data[191:128]),
        .cfg_soma_ready(t_cfg_soma_ready[2]),
        .cfg_axon_en(c_cfg_en[2] && c_cfg_space[5:4] == 2'd2),
        .cfg_axon_addr(c_cfg_addr[16 +: ID_BITS]),
        .cfg_axon_wdata(c_cfg_data[128 +: 4]),
        .cfg_axon_ready(t_cfg_axon_ready[2]),
        .rb_dend_addr(rb_addr[SYNAPSE_ADDR_BITS-1:0]), .rb_dend_rdata(t_rd2),
        .rb_soma_addr(rb_addr), .rb_soma_req(rb_req && (rb_tile == 2'd2)),
        .rb_soma_data(t_rs2), .rb_soma_ready(t_rb_ready[2]),
        .rb_soma_valid(t_rb_valid[2]),
        .out_spk_valid(t_out_spk_valid[2]), .out_spk_pkt(t_pk2),
        .out_spk_ready(pc_ok2), .out_stall_wit(tile_backpressure[2]),
        .fire_overflow_wit(tile_overflow_any[2]), .tile_busy(tile_busy[2])
    );

    neuro_tile #(
        .ENTRIES(SYNAPSES_PER_TILE), .ENTRY_ADDR_BITS(SYNAPSE_ADDR_BITS),
        .NEURONS(NEURONS_PER_TILE), .ID_BITS(ID_BITS),
        .GID_BASE(3 * NEURONS_PER_TILE), .DEFAULT_AXON_MASK(4'h0)
    ) t3 (
        .clk(clk), .rst_n(rst_n),
        .spk_valid(pe_out_valid[3] && pe_local_mask_ok[3] && pe_reserved_ok[3]
                   && pe_out_data[127:124] == TYPE_SPIKE),
        .spk_gid(pe_out_data[32*3 +: 10]),
        .spk_parity(pe_out_data[32*3 + 19]), .spk_ready(t_spk_ready[3]),
        .spk_overflow_wit(spike_backpressure_count[31:24]),
        .dend_busy(tile_dend_busy[3]), .integrate_open(integrate_open),
        .stim_valid(stim_valid && (stim_tile == 2'd3)),
        .stim_neuron(stim_neuron), .stim_weight(stim_weight),
        .stim_ready(t_stim_ready[3]),
        .tick(tick_dispatch), .tick_ready(t_tick_ready[3]),
        .cfg_en(c_cfg_en[3] && c_cfg_space[7:6] == 2'd0),
        .cfg_addr(c_cfg_addr[24 +: SYNAPSE_ADDR_BITS]),
        .cfg_wdata(c_cfg_data[192 +: 27]), .cfg_ready(t_cfg_ready[3]),
        .cfg_soma_en(c_cfg_en[3] && c_cfg_space[7:6] == 2'd1),
        .cfg_soma_addr(c_cfg_addr[31:24]), .cfg_soma_wdata(c_cfg_data[255:192]),
        .cfg_soma_ready(t_cfg_soma_ready[3]),
        .cfg_axon_en(c_cfg_en[3] && c_cfg_space[7:6] == 2'd2),
        .cfg_axon_addr(c_cfg_addr[24 +: ID_BITS]),
        .cfg_axon_wdata(c_cfg_data[192 +: 4]),
        .cfg_axon_ready(t_cfg_axon_ready[3]),
        .rb_dend_addr(rb_addr[SYNAPSE_ADDR_BITS-1:0]), .rb_dend_rdata(t_rd3),
        .rb_soma_addr(rb_addr), .rb_soma_req(rb_req && (rb_tile == 2'd3)),
        .rb_soma_data(t_rs3), .rb_soma_ready(t_rb_ready[3]),
        .rb_soma_valid(t_rb_valid[3]),
        .out_spk_valid(t_out_spk_valid[3]), .out_spk_pkt(t_pk3),
        .out_spk_ready(pc_ok3), .out_stall_wit(tile_backpressure[3]),
        .fire_overflow_wit(tile_overflow_any[3]), .tile_busy(tile_busy[3])
    );

    // mesh ingress gating by room
    assign pe_in_valid = {t_out_spk_valid[3] && pc_ok3,
                          t_out_spk_valid[2] && pc_ok2,
                          t_out_spk_valid[1] && pc_ok1,
                          pc_ok0 && (host_select || t_out_spk_valid[0])};
    assign pe_in_data = {t_pk3, t_pk2, t_pk1,
                         host_select ? host_packet : t_pk0};

    hyphae_mesh_2x2 mesh (
        .clk(clk), .rst_n(rst_n),
        .pe_in_data(pe_in_data), .pe_in_valid(pe_in_valid),
        .pe_feeder_ret(pe_feeder_ret),
        .pe_out_ready(pe_delivery_ready),
        .pe_out_data(pe_out_data), .pe_out_valid(pe_out_valid),
        .overflow_any(mesh_overflow_any)
    );

    assign rb_dend_rdata = (rb_tile == 2'd3) ? t_rd3 :
                           (rb_tile == 2'd2) ? t_rd2 :
                           (rb_tile == 2'd1) ? t_rd1 : t_rd0;
    assign rb_soma_data  = (rb_tile == 2'd3) ? t_rs3 :
                           (rb_tile == 2'd2) ? t_rs2 :
                           (rb_tile == 2'd1) ? t_rs1 : t_rs0;
    assign rb_ready = t_rb_ready[rb_tile];
    assign rb_valid = t_rb_valid[rb_tile];

endmodule

`default_nettype wire
