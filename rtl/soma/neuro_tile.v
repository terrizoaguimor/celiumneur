// neuro_tile.v — one CeliumNeUR tile: soma_dendrite driving soma_core.
// SPDX-License-Identifier: AGPL-3.0-or-later
// Reviewed seams closed end-to-end:
//
//   - spk input: hypha_link_fifo (verified single-clock FIFO) + PE
//     valid-until-ready handshake from hypha_router. Overflow physically
//     impossible; spk_overflow_wit witnesses any attempt.
//   - stim enters behind dendrite events (dendrite right-of-way).
//   - axon out: 4-deep queue — one fire, one packet, never overwritten.
//   - fires in flight: level interface + dendrite fire_taken strobe.

`default_nettype none

module neuro_tile #(
    parameter ENTRIES  = 16,
    parameter NEURONS  = 4,
    parameter ID_BITS  = 2,
    parameter TICK_BITS= 10,
    parameter WINDOW   = 3,
    parameter GID_BASE = 0          // this tile's starting global neuron id
) (
    input  wire        clk,
    input  wire        rst_n,

    // Spike input handshake (presynaptic global id from the fabric).
    input  wire        spk_valid,
    input  wire [9:0]  spk_gid,
    input  wire        spk_parity,
    output wire        spk_ready,
    output reg  [7:0]  spk_overflow_wit,

    // External stimulus (electrode injection).
    input  wire        stim_valid,
    input  wire [7:0]  stim_neuron,
    input  wire [7:0]  stim_weight,

    input  wire        tick,
    input  wire        integrate_open,

    // Dendrite table config + readback (I5).
    input  wire        cfg_en,
    input  wire [4:0]  cfg_addr,
    input  wire [20:0] cfg_wdata,
    input  wire [4:0]  rb_dend_addr,
    output wire [20:0] rb_dend_rdata,

    // Soma autonomous config (the reviewer's hole): a separate lane that
    // writes the neuron word when the engine is idle.
    input  wire        cfg_soma_en,
    input  wire [7:0]  cfg_soma_addr,
    input  wire [63:0] cfg_soma_wdata,

    // Soma state readback (I5).
    input  wire [7:0]  rb_soma_addr,
    input  wire        rb_soma_req,
    output wire [63:0] rb_soma_data,
    output wire        rb_soma_ready,

    input  wire [15:0] axon_masks,

    // Outgoing fire packets into the fabric.
    output wire        out_spk_valid,
    output wire [31:0] out_spk_pkt,
    input  wire        out_spk_ready,
    output wire        out_stall_wit,

    output wire        dend_busy,
    output wire        tile_busy
);

    // Declarations before use (Verilog-2001).
    wire dend_busy_int;
    wire dend_ev_valid;
    wire [7:0] dend_ev_neuron, dend_ev_weight;
    wire ev_ready, soma_fire_valid, soma_sweep_active;
    wire [7:0] soma_fire_neuron;
    wire fire_req;
    wire fire_taken;
    wire fire_pop;
    wire [7:0] fireq_dout;

    // ---------------- tick parity (phase bookkeeping) ------------------
    reg tick_parity;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) tick_parity <= 1'b0;
        else if (tick) tick_parity <= ~tick_parity;
    end

    // ---------------- input link FIFO (verified building block) --------
    wire [10:0] inq_dout;
    wire        inq_empty, inq_full;

    assign spk_ready = ~inq_full;
    wire head_parity = inq_dout[10];
    wire fence_ok    = head_parity != tick_parity;
    wire take_strobe = !inq_empty && integrate_open && fence_ok && !dend_busy_int;

    hypha_link_fifo #(
        .WIDTH(11), .DEPTH(8), .ADDR_BITS(3), .COUNT_BITS(4)
    ) inq (
        .clk(clk), .rst_n(rst_n),
        .push(spk_valid & spk_ready), .din({spk_parity, spk_gid}),
        .pop(take_strobe), .dout(inq_dout), .empty(inq_empty),
        .full(inq_full), .overflow()
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) spk_overflow_wit <= 8'd0;
        else if (spk_valid && !spk_ready) spk_overflow_wit <= spk_overflow_wit + 1;
    end

    soma_dendrite #(
        .ENTRIES(ENTRIES), .TICK_BITS(TICK_BITS), .WINDOW(WINDOW)
    ) dendrite (
        .clk(clk), .rst_n(rst_n),
        .spk_valid(take_strobe), .spk_gid(inq_dout[9:0]), .dend_busy(dend_busy_int),
        .ev_valid(dend_ev_valid), .ev_ready(ev_ready),
        .ev_neuron(dend_ev_neuron), .ev_weight(dend_ev_weight),
        .fire_valid(fire_req), .fire_neuron(fireq_dout), .fire_taken(fire_taken),
        .tick_strobe(tick),
        .cfg_en(cfg_en), .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata),
        .rb_addr(rb_dend_addr), .rb_rdata(rb_dend_rdata)
    );

    // ---------------- stim mux (dendrite right-of-way) ------------------
    wire       soma_ev_valid  = dend_ev_valid | stim_valid;
    wire [7:0] soma_ev_neuron = dend_ev_valid ? dend_ev_neuron : stim_neuron;
    wire [7:0] soma_ev_weight = dend_ev_valid ? dend_ev_weight : stim_weight;

    soma_core #(.NEURONS(NEURONS), .ID_BITS(ID_BITS)) soma (
        .clk(clk), .rst_n(rst_n),
        .ev_valid(soma_ev_valid), .ev_neuron(soma_ev_neuron),
        .ev_weight(soma_ev_weight), .ev_ready(ev_ready),
        .tick_req(tick), .sweep_active(soma_sweep_active),
        .fire_valid(soma_fire_valid), .fire_neuron(soma_fire_neuron),
        .rb_addr(rb_soma_addr), .rb_req(rb_soma_req),
        .rb_data(rb_soma_data), .rb_ready(rb_soma_ready),
        .cfg_en(cfg_soma_en), .cfg_addr(cfg_soma_addr), .cfg_wdata(cfg_soma_wdata)
    );

    // ---------------- fire queue (level interface) ----------------------
    wire fireq_empty, fireq_full;

    hypha_link_fifo #(
        .WIDTH(8), .DEPTH(4), .ADDR_BITS(2), .COUNT_BITS(3)
    ) fireq (
        .clk(clk), .rst_n(rst_n),
        .push(soma_fire_valid && !fireq_full), .din(soma_fire_neuron),
        .pop(fire_taken), .dout(fireq_dout), .empty(fireq_empty),
        .full(fireq_full), .overflow()
    );

    assign fire_req = !fireq_empty;
    assign fire_pop = fire_taken;

    // Pack assembly — AT FIRE TIME, into a packet fifo in lockstep with the
    // neuron ffifo. (court-tester scar #1: a bare `GID_BASE + neuron` is a
    // 32-bit integer expression; inside the concat it silently inflated the
    // packet to 54 bits and truncation deleted the mask+header lanes — the
    // gid operand must be exactly 10 bits. scar #2: a single `held_packet`
    // register latched at fire and pushed on take+1 is clobbered by any
    // mid-flight fire, because the dendrite arbiter's take is scan-latency
    // away — gid 1 vanished and gid 2 was emitted twice. The packet must
    // live in a queue, not in a register.)
    localparam [9:0] GID_LSB = GID_BASE[9:0];
    wire [9:0] fire_gid = GID_LSB + {2'b0, soma_fire_neuron};
    wire [15:0] axon_shl = axon_masks >> (soma_fire_neuron[1:0] * 4);
    wire [3:0]  fire_mask = axon_shl[3:0];
    wire [31:0] fire_packet = { 4'h1, 4'b0000, fire_mask, tick_parity,
                                9'b0, fire_gid };
    wire [31:0] pktq_dout;
    wire        pktq_full;

    hypha_link_fifo #(
        .WIDTH(32), .DEPTH(4), .ADDR_BITS(2), .COUNT_BITS(3)
    ) pktq (
        .clk(clk), .rst_n(rst_n),
        .push(soma_fire_valid && !pktq_full), .din(fire_packet),
        .pop(fire_taken), .dout(pktq_dout), .empty(),
        .full(pktq_full), .overflow()
    );

    wire [31:0] outq_dout;
    wire        outq_empty, outq_full;

    // FWFT: the popped head is valid in the take cycle itself; push then.
    hypha_link_fifo #(
        .WIDTH(32), .DEPTH(4), .ADDR_BITS(2), .COUNT_BITS(3)
    ) outq (
        .clk(clk), .rst_n(rst_n),
        .push(fire_taken), .din(pktq_dout),
        .pop(!outq_empty && out_spk_ready), .dout(outq_dout), .empty(outq_empty),
        .full(outq_full), .overflow()
    );

    assign out_spk_pkt   = outq_dout;
    assign out_spk_valid = !outq_empty;
    assign out_stall_wit = soma_fire_valid && fireq_full;

    assign dend_busy = dend_busy_int;
    assign tile_busy = dend_busy_int | soma_sweep_active | !inq_empty | !outq_empty;

endmodule

`default_nettype wire
