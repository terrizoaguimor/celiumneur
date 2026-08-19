// neuro_tile.v — one CeliumNeUR tile: soma_dendrite driving soma_core.
// SPDX-License-Identifier: Apache-2.0
// Reviewed seams closed end-to-end:
//
//   - spk input: hypha_link_fifo (verified single-clock FIFO) + PE
//     valid-until-ready handshake from hypha_router. Overflow physically
//     impossible; spk_overflow_wit witnesses any attempt.
//   - stim enters behind dendrite events (dendrite right-of-way).
//   - axon out: valid/ready from soma through the fabric; one fire record owns
//     both its learning event and packet, so the two cannot desynchronize.

`default_nettype none

module neuro_tile #(
    parameter ENTRIES  = 16,
    parameter ENTRY_ADDR_BITS = 4,
    parameter NEURONS  = 4,
    parameter ID_BITS  = 2,
    parameter TICK_BITS= 10,
    parameter WINDOW   = 3,
    parameter GID_BASE = 0,         // this tile's starting global neuron id
    parameter [3:0] DEFAULT_AXON_MASK = 4'hf
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
    output wire        stim_ready,

    input  wire        tick,
    output wire        tick_ready,
    input  wire        integrate_open,

    // Dendrite table config + readback (I5).
    input  wire        cfg_en,
    input  wire [ENTRY_ADDR_BITS-1:0] cfg_addr,
    input  wire [26:0] cfg_wdata,
    output wire        cfg_ready,
    input  wire [ENTRY_ADDR_BITS-1:0] rb_dend_addr,
    output wire [26:0] rb_dend_rdata,

    // Soma autonomous config (the reviewer's hole): a separate lane that
    // writes the neuron word when the engine is idle.
    input  wire        cfg_soma_en,
    input  wire [7:0]  cfg_soma_addr,
    input  wire [63:0] cfg_soma_wdata,
    output wire        cfg_soma_ready,

    // Per-neuron axon destination table.
    input  wire        cfg_axon_en,
    input  wire [ID_BITS-1:0] cfg_axon_addr,
    input  wire [3:0]  cfg_axon_wdata,
    output wire        cfg_axon_ready,

    // Soma state readback (I5).
    input  wire [7:0]  rb_soma_addr,
    input  wire        rb_soma_req,
    output wire [63:0] rb_soma_data,
    output wire        rb_soma_ready,
    output wire        rb_soma_valid,

    // Outgoing fire packets into the fabric.
    output wire        out_spk_valid,
    output wire [31:0] out_spk_pkt,
    input  wire        out_spk_ready,
    output wire        out_stall_wit,
    output wire        fire_overflow_wit,

    output wire        dend_busy,
    output wire        tile_busy
);

    // Declarations before use (Verilog-2001).
    wire dend_busy_int;
    wire dend_ev_valid;
    wire [7:0] dend_ev_neuron, dend_ev_weight;
    wire ev_ready, soma_fire_valid, soma_fire_ready, soma_sweep_active;
    wire soma_busy;
    wire soma_tick_ready, dend_tick_ready;
    wire dend_cfg_ready, soma_cfg_ready;
    wire [7:0] soma_fire_neuron;
    wire soma_fire_parity;
    wire [TICK_BITS-1:0] soma_fire_tick;
    wire fire_req;
    wire fire_taken;
    wire [TICK_BITS+39:0] fireq_dout;
    wire fireq_empty, fireq_full, fireq_overflow;
    wire [31:0] outq_dout;
    wire outq_empty, outq_full, outq_overflow;
    wire [15:0] stimq_dout;
    wire stimq_empty, stimq_full, stimq_overflow;
    wire stim_pop;

    // ---------------- tick parity (phase bookkeeping) ------------------
    reg tick_parity;
    reg [TICK_BITS-1:0] tick_epoch;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            tick_parity <= 1'b0;
            tick_epoch  <= {TICK_BITS{1'b0}};
        end else if (tick && tick_ready) begin
            tick_parity <= ~tick_parity;
            tick_epoch  <= tick_epoch + {{(TICK_BITS-1){1'b0}}, 1'b1};
        end
    end

    // ---------------- input link FIFO (verified building block) --------
    wire [10:0] inq_dout;
    wire        inq_empty, inq_full, inq_overflow;

    assign spk_ready = ~inq_full;
    wire head_parity = inq_dout[10];
    wire fence_ok    = head_parity != tick_parity;
    wire dend_spk_ready;
    wire take_strobe = !inq_empty && integrate_open && fence_ok && dend_spk_ready;

    hypha_link_fifo #(
        .WIDTH(11), .DEPTH(8), .ADDR_BITS(3), .COUNT_BITS(4)
    ) inq (
        .clk(clk), .rst_n(rst_n),
        .push(spk_valid & spk_ready), .din({spk_parity, spk_gid}),
        .pop(take_strobe), .dout(inq_dout), .empty(inq_empty),
        .full(inq_full), .overflow(inq_overflow)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) spk_overflow_wit <= 8'd0;
        else if (spk_valid && !spk_ready) spk_overflow_wit <= spk_overflow_wit + 1;
    end

    // Aggregate dend_busy is public; component busy pins would be redundant.
    /* verilator lint_off PINCONNECTEMPTY */
    soma_dendrite #(
        .ENTRIES(ENTRIES), .ENTRY_ADDR_BITS(ENTRY_ADDR_BITS),
        .TICK_BITS(TICK_BITS), .WINDOW(WINDOW)
    ) dendrite (
        .clk(clk), .rst_n(rst_n),
        .spk_valid(take_strobe), .spk_gid(inq_dout[9:0]),
        .spk_ready(dend_spk_ready), .dend_busy(dend_busy_int),
        .scan_busy(), .learn_busy(),
        .ev_valid(dend_ev_valid), .ev_ready(ev_ready),
        .ev_neuron(dend_ev_neuron), .ev_weight(dend_ev_weight),
        .fire_valid(fire_req),
        .fire_neuron(fireq_dout[TICK_BITS+39:TICK_BITS+32]),
        .fire_tick(fireq_dout[TICK_BITS+31:32]),
        .fire_taken(fire_taken),
        .tick_strobe(tick && tick_ready), .tick_ready(dend_tick_ready),
        .cfg_en(cfg_en), .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata),
        .cfg_ready(dend_cfg_ready),
        .rb_addr(rb_dend_addr), .rb_rdata(rb_dend_rdata)
    );
    /* verilator lint_on PINCONNECTEMPTY */

    // ---------------- stimulus queue + dendrite-priority mux ------------
    assign stim_ready = !stimq_full;
    assign stim_pop = !dend_ev_valid && !stimq_empty && ev_ready;

    hypha_link_fifo #(
        .WIDTH(16), .DEPTH(4), .ADDR_BITS(2), .COUNT_BITS(3)
    ) stimq (
        .clk(clk), .rst_n(rst_n),
        .push(stim_valid && stim_ready), .din({stim_neuron, stim_weight}),
        .pop(stim_pop), .dout(stimq_dout), .empty(stimq_empty),
        .full(stimq_full), .overflow(stimq_overflow)
    );

    wire       soma_ev_valid  = dend_ev_valid | !stimq_empty;
    wire [7:0] soma_ev_neuron = dend_ev_valid ? dend_ev_neuron : stimq_dout[15:8];
    wire [7:0] soma_ev_weight = dend_ev_valid ? dend_ev_weight : stimq_dout[7:0];

    assign tick_ready = soma_tick_ready && dend_tick_ready;
    assign cfg_ready = dend_cfg_ready;
    assign cfg_soma_ready = soma_cfg_ready;

    soma_core #(
        .NEURONS(NEURONS), .ID_BITS(ID_BITS), .TICK_BITS(TICK_BITS)
    ) soma (
        .clk(clk), .rst_n(rst_n),
        .ev_valid(soma_ev_valid), .ev_neuron(soma_ev_neuron),
        .ev_weight(soma_ev_weight), .ev_ready(ev_ready),
        .tick_req(tick && tick_ready), .tick_ready(soma_tick_ready),
        .sweep_active(soma_sweep_active), .busy(soma_busy),
        .fire_valid(soma_fire_valid), .fire_neuron(soma_fire_neuron),
        .fire_parity(soma_fire_parity), .fire_tick(soma_fire_tick),
        .fire_ready(soma_fire_ready), .phase_parity(tick_parity),
        .phase_tick(tick_epoch),
        .rb_addr(rb_soma_addr), .rb_req(rb_soma_req),
        .rb_data(rb_soma_data), .rb_ready(rb_soma_ready),
        .rb_valid(rb_soma_valid),
        .cfg_en(cfg_soma_en), .cfg_addr(cfg_soma_addr),
        .cfg_wdata(cfg_soma_wdata), .cfg_ready(soma_cfg_ready)
    );

    // Pack assembly happens while the soma fire payload is stable. A bare
    // `GID_BASE + neuron` is a
    // 32-bit integer expression; inside the concat it silently inflated the
    // packet to 54 bits and truncation deletes the mask+header lanes, so the
    // gid operand is explicitly 10 bits.
    localparam [9:0] GID_LSB = GID_BASE[9:0];
    wire [9:0] fire_gid = GID_LSB + {2'b0, soma_fire_neuron};
    reg [3:0] axon_table [0:NEURONS-1];
    integer axon_i;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (axon_i = 0; axon_i < NEURONS; axon_i = axon_i + 1)
                axon_table[axon_i] <= DEFAULT_AXON_MASK;
        end else if (cfg_axon_en && cfg_axon_ready) begin
            axon_table[cfg_axon_addr] <= cfg_axon_wdata;
        end
    end

    assign cfg_axon_ready = !soma_fire_valid;
    wire [3:0] fire_mask = axon_table[soma_fire_neuron[ID_BITS-1:0]];
    wire [31:0] fire_packet = { 4'h1, 4'b0000, fire_mask, soma_fire_parity,
                                9'b0, fire_gid };

    // One queue record owns both consumers of a fire. The soma holds valid
    // until this queue accepts, so saturation propagates upstream instead of
    // dropping a pulse. Packet parity was captured by soma at fire time.
    assign soma_fire_ready = !fireq_full;

    hypha_link_fifo #(
        .WIDTH(40 + TICK_BITS), .DEPTH(4), .ADDR_BITS(2), .COUNT_BITS(3)
    ) fireq (
        .clk(clk), .rst_n(rst_n),
        .push(soma_fire_valid && soma_fire_ready),
        .din({soma_fire_neuron, soma_fire_tick, fire_packet}),
        .pop(fire_taken), .dout(fireq_dout), .empty(fireq_empty),
        .full(fireq_full), .overflow(fireq_overflow)
    );

    // Do not let the learning consumer pop unless the packet consumer has
    // room. This deliberately permits a one-cycle bubble at full capacity;
    // correctness is preferred over a FIFO-specific full+pop shortcut.
    assign fire_req = !fireq_empty && !outq_full;

    hypha_link_fifo #(
        .WIDTH(32), .DEPTH(4), .ADDR_BITS(2), .COUNT_BITS(3)
    ) outq (
        .clk(clk), .rst_n(rst_n),
        .push(fire_taken), .din(fireq_dout[31:0]),
        .pop(!outq_empty && out_spk_ready), .dout(outq_dout), .empty(outq_empty),
        .full(outq_full), .overflow(outq_overflow)
    );

    assign out_spk_pkt   = outq_dout;
    assign out_spk_valid = !outq_empty;
    assign out_stall_wit = (soma_fire_valid && !soma_fire_ready)
                         || (!fireq_empty && outq_full);
    assign fire_overflow_wit = inq_overflow | stimq_overflow
                             | fireq_overflow | outq_overflow;

    assign dend_busy = dend_busy_int;
    assign tile_busy = dend_busy_int | soma_busy | soma_sweep_active
                     | !inq_empty | !stimq_empty | !fireq_empty | !outq_empty;

endmodule

`default_nettype wire
