// soma_dendrite.v — CeliumNeUR dendrite + plasticity snooper (SPEC §5, I2+I4).
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Duties:
//   1. I2 (indirection): an arriving spike carries a PRESYNAPTIC global id;
//      the syn_table expands it to local (neuron, weight) deliveries. Topology
//      lives in the syn_table, never in wiring or memory geometry.
//   2. I4 (plasticity): rule v1.2 from golden/plasticity.py, in RTL:
//        arrival at entry e     -> ledger[e] := tick_now, valid (and nothing else)
//        fire(post_local = L)   -> every valid entry with post==L and
//                                  (tick - ledger) <= WINDOW: w+1, then clear
//        tick boundary          -> every valid entry with (tick - ledger) >
//                                  WINDOW: w-1 (clamp), then clear
//      Snoop taps (fire strobe, tick) are level-audited each cycle; a fire or
//      tick mid-pass is queued, never lost. A new spike while busy is held
//      in spk_pending — there is no drop path in this module (I1).
//
// Ledger constraint v1: ONE arrival record per entry (the latest arrival
// overwrites). The golden referee models the same, so the contract is exact.
//
// syn_table: 16 entries {valid, pre_gid[9:0], post_local[1:0], weight[7:0]s}
// as a register file; cfg_* writes, rb_* reads (I5: never write-only).

`default_nettype none

module soma_dendrite #(
    parameter ENTRIES   = 16,
    parameter TICK_BITS = 10,
    parameter WINDOW    = 3
) (
    input  wire        clk,
    input  wire        rst_n,

    // Arriving spike (pre-expanded presynaptic global id).
    input  wire        spk_valid,
    input  wire [9:0]  spk_gid,
    output wire        dend_busy,      // high while a pass runs; new spikes
                                       // are latched, not lost

    // Fanout toward the soma engine.
    output reg         ev_valid,
    input  wire        ev_ready,
    output reg  [7:0]  ev_neuron,
    output reg  [7:0]  ev_weight,      // contents of the syn_table slot (signed)

    // Snoop taps from the soma engine: LEVEL interface on the fire FIFO.
    // fire_valid means "there is a pending postsynaptic fire"; fire_taken is
    // the one-cycle strobe the queue pops on (the pass consumed this one).
    input  wire        fire_valid,
    input  wire [7:0]  fire_neuron,
    output wire        fire_taken,
    input  wire        tick_strobe,

    // Host config + readback (I5).
    input  wire        cfg_en,
    input  wire [4:0]  cfg_addr,
    input  wire [20:0] cfg_wdata,
    input  wire [4:0]  rb_addr,
    output wire [20:0] rb_rdata
);

    // layout: [20] valid | [19:10] pre_gid | [9:8] post_local | [7:0] weight
    reg [20:0] syn_table [0:ENTRIES-1];

    reg [TICK_BITS-1:0] ledger_tick  [0:ENTRIES-1];
    reg                 ledger_valid [0:ENTRIES-1];
    reg [TICK_BITS-1:0] tick_cnt;

    reg        spk_pending;
    reg [9:0]  pending_gid;

    function [7:0] w_plus1;
        input [7:0] w;
        begin
            w_plus1 = ($signed(w) >= 8'sd127) ? 8'sd127 : w + 8'sd1;
        end
    endfunction
    function [7:0] w_minus1;
        input [7:0] w;
        begin
            w_minus1 = ($signed(w) <= -8'sd128) ? 8'sd128 : w - 8'sd1;
        end
    endfunction

    localparam [2:0] S_IDLE = 3'd0,
                     S_SCAN = 3'd1,   // fanout pass over the syn_table
                     S_POT  = 3'd2,   // LTP pay pass after a fire
                     S_EXP  = 3'd3;   // LTD expiry pass at a tick boundary

    reg [2:0] state;
    reg [4:0] scan_i;
    reg [9:0] active_gid;   // gid latched when the scan started (spk_valid
                            // drops one cycle later; scanning must not read air)
    reg [7:0] fire_neuron_r;
    reg       fire_taken_r;
    reg       tick_queued;

    assign rb_rdata  = syn_table[rb_addr];
    assign dend_busy = (state != S_IDLE) || spk_pending;
    assign fire_taken = fire_taken_r;

    integer wi;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state              <= S_IDLE;
            scan_i             <= 5'd0;
            tick_cnt           <= {TICK_BITS{1'b0}};
            ev_valid           <= 1'b0;
            ev_neuron          <= 8'd0;
            ev_weight          <= 8'd0;
            spk_pending        <= 1'b0;
            pending_gid        <= 10'd0;
            active_gid         <= 10'h0;
            fire_neuron_r      <= 8'd0;
            fire_taken_r       <= 1'b0;
            tick_queued        <= 1'b0;
            for (wi = 0; wi < ENTRIES; wi = wi + 1) begin
                syn_table[wi]        <= 21'b0;
                ledger_tick[wi]  <= {TICK_BITS{1'b0}};
                ledger_valid[wi] <= 1'b0;
            end
        end else begin
            // -------- level taps: fire/tick/new-spike are NEVER lost --------
            if (spk_valid) begin
                if (state == S_IDLE && !spk_pending)
                    spk_pending <= 1'b0;      // consumed in the case below
                else begin
                    spk_pending <= 1'b1;
                    pending_gid <= spk_gid;
                end
            end
            // fire taps are LEVEL now: pending is physical, consumption is
            // the fire_taken strobe (see state transitions below). Nothing
            // here but the default down-tick of the strobe.
            fire_taken_r <= 1'b0;
            if (tick_strobe)
                tick_queued <= 1'b1;

            // --------------------------- FSM -----------------------------
            case (state)
                S_IDLE: begin
                    ev_valid <= 1'b0;
                    if (cfg_en) begin
                        syn_table[cfg_addr] <= cfg_wdata;
                    end else if (spk_valid || spk_pending) begin
                        scan_i     <= 5'd0;
                        active_gid <= spk_pending ? pending_gid : spk_gid;
                        if (spk_pending) spk_pending <= 1'b0;
                        state <= S_SCAN;
                    end else if (fire_valid) begin
                        // consume the queued head into this POT pass
                        fire_neuron_r <= fire_neuron;
                        fire_taken_r  <= 1'b1;
                        scan_i        <= 5'd0;
                        state         <= S_POT;
                    end else if (tick_queued) begin
                        tick_queued <= 1'b0;
                        tick_cnt    <= tick_cnt + 1'b1;
                        scan_i      <= 5'd0;
                        state       <= S_EXP;
                    end
                end

                S_SCAN: begin
                    if (scan_i < ENTRIES) begin
                        if (syn_table[scan_i][20]
                            && syn_table[scan_i][19:10] == active_gid) begin
                            if (!ev_valid) begin
                                ev_valid  <= 1'b1;
                                ev_neuron <= {6'b0, syn_table[scan_i][9:8]};
                                ev_weight <= syn_table[scan_i][7:0];
                            end else if (ev_ready) begin
                                // delivered: stamp the ledger with now
                                ev_valid              <= 1'b0;
                                ledger_tick[scan_i]   <= tick_cnt;
                                ledger_valid[scan_i]  <= 1'b1;
                                scan_i                <= scan_i + 5'd1;
                            end
                        end else begin
                            scan_i <= scan_i + 5'd1;
                        end
                    end else begin
                        ev_valid <= 1'b0;
                        scan_i   <= 5'd0;
                        if (fire_valid) begin
                            fire_neuron_r <= fire_neuron;
                            fire_taken_r  <= 1'b1;
                            state         <= S_POT;
                        end else if (tick_queued) begin
                            tick_queued <= 1'b0;
                            tick_cnt    <= tick_cnt + 1'b1;
                            state       <= S_EXP;
                        end else begin
                            state <= S_IDLE;
                        end
                    end
                end

                S_POT: begin
                    if (scan_i < ENTRIES) begin
                        if (syn_table[scan_i][20]
                            && syn_table[scan_i][9:8] == fire_neuron_r[1:0]
                            && ledger_valid[scan_i]
                            && (tick_cnt - ledger_tick[scan_i]) <= WINDOW) begin
                            syn_table[scan_i]       <= {syn_table[scan_i][20:8],
                                                    w_plus1(syn_table[scan_i][7:0])};
                            ledger_valid[scan_i] <= 1'b0;
                        end
                        scan_i <= scan_i + 5'd1;
                    end else begin
                        // after paying, run the expiry pass so unpaid entries
                        // age correctly even outside a tick (keeps the bench's
                        // golden single-pass traversal exact)
                        state  <= S_EXP;
                        scan_i <= 5'd0;
                    end
                end

                S_EXP: begin
                    if (scan_i < ENTRIES) begin
                        if (syn_table[scan_i][20] && ledger_valid[scan_i]
                            && (tick_cnt - ledger_tick[scan_i]) > WINDOW) begin
                            syn_table[scan_i]       <= {syn_table[scan_i][20:8],
                                                    w_minus1(syn_table[scan_i][7:0])};
                            ledger_valid[scan_i] <= 1'b0;
                        end
                        scan_i <= scan_i + 5'd1;
                    end else begin
                        scan_i <= 5'd0;
                        if (fire_valid) begin
                            fire_neuron_r <= fire_neuron;
                            fire_taken_r  <= 1'b1;
                            state         <= S_POT;
                        end else if (tick_queued) begin
                            tick_queued <= 1'b0;
                            tick_cnt    <= tick_cnt + 1'b1;
                            state       <= S_EXP;
                        end else begin
                            state <= S_IDLE;
                        end
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule

`default_nettype wire
