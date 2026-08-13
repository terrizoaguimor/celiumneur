// celiumneur_soc.v — CeliumNeUR SoC v1: 4 neuro_tiles on the Hyphae 2x2 mesh.
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Wiring contract per core (SPEC §2 + tile seam):
//   tile.out_spk_*  -> mesh PE ingress      (fire packets into the fabric)
//   mesh PE egress  -> tile.spk_*           (arriving spikes into the dendrite)
//   mesh feeder_ret -> SoC PE credit counter (tile sends only against room)
//
// Explicit flat wiring (no generate gymnastics — 4 tiles is small enough to
// read, and any wiring error should be visible at a glance).

`default_nettype none

module celiumneur_soc (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        tick,

    // stimulus (electrode injection), tile-selected
    // Integration gate: tile deliveries integrate only while open. Packets
    // stamped with the CURRENT tick parity wait — they are this-phase
    // cascades and belong to the next phase (the sandbox semantic, in metal).
    input  wire        integrate_open,

    input  wire [1:0]  stim_tile,
    input  wire        stim_valid,
    input  wire [7:0]  stim_neuron,
    input  wire [7:0]  stim_weight,

    // dendrite config, tile-selected
    input  wire [1:0]  cfg_tile,
    input  wire        cfg_en,
    input  wire [4:0]  cfg_addr,
    input  wire [20:0] cfg_wdata,
    // autonomous soma config (reviewed hole closed): cfg_which = 1 writes
    // the soma word; cfg_which = 0 wires it to the dendrite table.
    // vehicle format: cfg_wdata = the full 64-bit neuron word.
    input  wire        cfg_which,
    input  wire [63:0] cfg_soma_data,

    // readback, tile-selected (I5)
    input  wire [1:0]  rb_tile,
    input  wire [4:0]  rb_addr,
    input  wire        rb_req,
    output wire [20:0] rb_dend_rdata,
    output wire [63:0] rb_soma_data,

    output wire [3:0]  mesh_overflow_any
);

    // ---------------- axon maps (static for the v1 demo; §7 will host-load)
    // core0/1 electrodes -> core2; core2 detector -> core3; core3 sinks none
    localparam [63:0] AXON_ALL = {16'h0000, 16'h0008, 16'h0004, 16'h0004};

    // ---------------- mesh-side wires
    wire [127:0] pe_in_data;
    wire [3:0]   pe_in_valid;
    wire [127:0] pe_out_data;
    wire [3:0]   pe_out_valid;
    wire [3:0]   pe_feeder_ret;

    // ---------------- tile-side wires
    wire [3:0]  t_out_spk_valid;
    wire [3:0]  t_spk_ready;
    wire [31:0] t_pk0, t_pk1, t_pk2, t_pk3;
    wire [3:0]  t_busy;
    // stall witnesses read hierarchically from the bench when needed
    wire [20:0] t_rd0, t_rd1, t_rd2, t_rd3;
    wire [63:0] t_rs0, t_rs1, t_rs2, t_rs3;

    // ---------------- per-core PE credit counters (room tracking)
    reg [3:0] pe_credit [3:0];
    wire pc_ok0 = (pe_credit[0] != 0);
    wire pc_ok1 = (pe_credit[1] != 0);
    wire pc_ok2 = (pe_credit[2] != 0);
    wire pc_ok3 = (pe_credit[3] != 0);
    integer cc;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (cc = 0; cc < 4; cc = cc + 1) pe_credit[cc] <= 4'd4;
        end else begin
            for (cc = 0; cc < 4; cc = cc + 1) begin
                case ({ pe_feeder_ret[cc],
                        t_out_spk_valid[cc] && pe_credit[cc] })
                    2'b10: pe_credit[cc] <= pe_credit[cc] + 4'd1;
                    2'b01: pe_credit[cc] <= pe_credit[cc] - 4'd1;
                    default: ;
                endcase
            end
        end
    end

    // ---------------- tiles
    neuro_tile #(.GID_BASE(0)) t0 (
        .clk(clk), .rst_n(rst_n),
        .spk_valid(pe_out_valid[0]), .spk_gid(pe_out_data[9:0]),
        .spk_parity(pe_out_data[19]), .spk_ready(t_spk_ready[0]), .dend_busy(),
        .integrate_open(integrate_open),
        .stim_valid(stim_valid && (stim_tile == 2'd0)),
        .stim_neuron(stim_neuron), .stim_weight(stim_weight),
        .tick(tick),
        .cfg_en(!cfg_which && cfg_en && (cfg_tile == 2'd0)), .cfg_addr(cfg_addr),
        .cfg_soma_en(cfg_which && cfg_en && (cfg_tile == 2'd0)), .cfg_soma_addr({3'b0, cfg_addr}),
        .cfg_soma_wdata(cfg_soma_data),
        .cfg_wdata(cfg_wdata), .rb_dend_addr(rb_addr), .rb_dend_rdata(t_rd0),
        .rb_soma_addr({6'b0, rb_addr[1:0]}), .rb_soma_req(rb_req && (rb_tile == 2'd0)),
        .rb_soma_data(t_rs0), .rb_soma_ready(),
        .axon_masks(AXON_ALL[0*16 +: 16]),
        .out_spk_valid(t_out_spk_valid[0]), .out_spk_pkt(t_pk0),
        .out_spk_ready(pc_ok0), .out_stall_wit(), .tile_busy(t_busy[0])
    );
    neuro_tile #(.GID_BASE(4)) t1 (
        .clk(clk), .rst_n(rst_n),
        .spk_valid(pe_out_valid[1]), .spk_gid(pe_out_data[32*1 +: 10]), .spk_parity(pe_out_data[32*1 + 19]),
        .spk_ready(t_spk_ready[1]), .dend_busy(),
        .integrate_open(integrate_open),
        .stim_valid(stim_valid && (stim_tile == 2'd1)),
        .stim_neuron(stim_neuron), .stim_weight(stim_weight),
        .tick(tick),
        .cfg_en(!cfg_which && cfg_en && (cfg_tile == 2'd1)),
        .cfg_addr(cfg_addr),
        .cfg_soma_en(cfg_which && cfg_en && (cfg_tile == 2'd1)),
        .cfg_soma_addr({3'b0, cfg_addr}),
        .cfg_soma_wdata(cfg_soma_data),
        .cfg_wdata(cfg_wdata), .rb_dend_addr(rb_addr), .rb_dend_rdata(t_rd1),
        .rb_soma_addr({6'b0, rb_addr[1:0]}), .rb_soma_req(rb_req && (rb_tile == 2'd1)),
        .rb_soma_data(t_rs1), .rb_soma_ready(),
        .axon_masks(AXON_ALL[1*16 +: 16]),
        .out_spk_valid(t_out_spk_valid[1]), .out_spk_pkt(t_pk1),
        .out_spk_ready(pc_ok1), .out_stall_wit(), .tile_busy(t_busy[1])
    );
    neuro_tile #(.GID_BASE(8)) t2 (
        .clk(clk), .rst_n(rst_n),
        .spk_valid(pe_out_valid[2]), .spk_gid(pe_out_data[32*2 +: 10]), .spk_parity(pe_out_data[32*2 + 19]),
        .spk_ready(t_spk_ready[2]), .dend_busy(),
        .integrate_open(integrate_open),
        .stim_valid(stim_valid && (stim_tile == 2'd2)),
        .stim_neuron(stim_neuron), .stim_weight(stim_weight),
        .tick(tick),
        .cfg_en(!cfg_which && cfg_en && (cfg_tile == 2'd2)),
        .cfg_addr(cfg_addr),
        .cfg_soma_en(cfg_which && cfg_en && (cfg_tile == 2'd2)),
        .cfg_soma_addr({3'b0, cfg_addr}),
        .cfg_soma_wdata(cfg_soma_data),
        .cfg_wdata(cfg_wdata), .rb_dend_addr(rb_addr), .rb_dend_rdata(t_rd2),
        .rb_soma_addr({6'b0, rb_addr[1:0]}), .rb_soma_req(rb_req && (rb_tile == 2'd2)),
        .rb_soma_data(t_rs2), .rb_soma_ready(),
        .axon_masks(AXON_ALL[2*16 +: 16]),
        .out_spk_valid(t_out_spk_valid[2]), .out_spk_pkt(t_pk2),
        .out_spk_ready(pc_ok2), .out_stall_wit(), .tile_busy(t_busy[2])
    );
    neuro_tile #(.GID_BASE(12)) t3 (
        .clk(clk), .rst_n(rst_n),
        .spk_valid(pe_out_valid[3]), .spk_gid(pe_out_data[32*3 +: 10]), .spk_parity(pe_out_data[32*3 + 19]),
        .spk_ready(t_spk_ready[3]), .dend_busy(),
        .integrate_open(integrate_open),
        .stim_valid(stim_valid && (stim_tile == 2'd3)),
        .stim_neuron(stim_neuron), .stim_weight(stim_weight),
        .tick(tick),
        .cfg_en(!cfg_which && cfg_en && (cfg_tile == 2'd3)),
        .cfg_addr(cfg_addr),
        .cfg_soma_en(cfg_which && cfg_en && (cfg_tile == 2'd3)),
        .cfg_soma_addr({3'b0, cfg_addr}),
        .cfg_soma_wdata(cfg_soma_data),
        .cfg_wdata(cfg_wdata), .rb_dend_addr(rb_addr), .rb_dend_rdata(t_rd3),
        .rb_soma_addr({6'b0, rb_addr[1:0]}), .rb_soma_req(rb_req && (rb_tile == 2'd3)),
        .rb_soma_data(t_rs3), .rb_soma_ready(),
        .axon_masks(AXON_ALL[3*16 +: 16]),
        .out_spk_valid(t_out_spk_valid[3]), .out_spk_pkt(t_pk3),
        .out_spk_ready(pc_ok3), .out_stall_wit(), .tile_busy(t_busy[3])
    );

    // mesh ingress gating by room
    assign pe_in_valid = { t_out_spk_valid[3] && pc_ok3,
                           t_out_spk_valid[2] && pc_ok2,
                           t_out_spk_valid[1] && pc_ok1,
                           t_out_spk_valid[0] && pc_ok0 };
    assign pe_in_data = { t_pk3, t_pk2, t_pk1, t_pk0 };

    hyphae_mesh_2x2 mesh (
        .clk(clk), .rst_n(rst_n),
        .pe_in_data(pe_in_data), .pe_in_valid(pe_in_valid),
        .pe_feeder_ret(pe_feeder_ret),
        .pe_out_ready(t_spk_ready),
        .pe_out_data(pe_out_data), .pe_out_valid(pe_out_valid),
        .overflow_any(mesh_overflow_any)
    );

    assign rb_dend_rdata = (rb_tile == 2'd3) ? t_rd3 :
                           (rb_tile == 2'd2) ? t_rd2 :
                           (rb_tile == 2'd1) ? t_rd1 : t_rd0;
    assign rb_soma_data  = (rb_tile == 2'd3) ? t_rs3 :
                           (rb_tile == 2'd2) ? t_rs2 :
                           (rb_tile == 2'd1) ? t_rs1 : t_rs0;

endmodule

`default_nettype wire
