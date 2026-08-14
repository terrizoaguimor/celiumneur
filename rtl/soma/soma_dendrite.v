// soma_dendrite.v — concurrent dendrite expansion + CWR learning engine.
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Two independent walkers share the explicit synapse table:
//   - integration scans one accepted presynaptic GID and emits soma events;
//   - learning applies CWR potentiation/expiry passes in the background.
//
// The walkers may inspect the same entry in one cycle. If a new arrival and
// a learning clear target that entry together, the new arrival wins: it
// occurred after the fire/tick snapshot owned by the learning pass and must
// remain available for the next causal window.

`default_nettype none

module soma_dendrite #(
    parameter ENTRIES   = 16,
    parameter ENTRY_ADDR_BITS = 4,
    parameter TICK_BITS = 10,
    parameter WINDOW    = 3
) (
    input  wire        clk,
    input  wire        rst_n,

    // Presynaptic input transaction.
    input  wire        spk_valid,
    input  wire [9:0]  spk_gid,
    output wire        spk_ready,
    output wire        dend_busy,
    output wire        scan_busy,
    output wire        learn_busy,

    // Expanded event transaction toward SomaCore.
    output reg         ev_valid,
    input  wire        ev_ready,
    output reg  [7:0]  ev_neuron,
    output reg  [7:0]  ev_weight,

    // Pending postsynaptic fire. fire_tick is captured at the physical fire,
    // not when this walker eventually reaches the record.
    input  wire                 fire_valid,
    input  wire [7:0]           fire_neuron,
    input  wire [TICK_BITS-1:0] fire_tick,
    output wire                 fire_taken,

    // Accepted global tick. One later tick may queue behind an active pass.
    input  wire        tick_strobe,
    output wire        tick_ready,

    // Host configuration and asynchronous table readback.
    input  wire        cfg_en,
    input  wire [ENTRY_ADDR_BITS-1:0] cfg_addr,
    input  wire [26:0] cfg_wdata,
    output wire        cfg_ready,
    input  wire [ENTRY_ADDR_BITS-1:0] rb_addr,
    output wire [26:0] rb_rdata
);

    // layout: valid | pre_gid[9:0] | post_local[7:0] | signed weight[7:0]
    reg [26:0] syn_table [0:ENTRIES-1];
    reg [TICK_BITS-1:0] ledger_tick [0:ENTRIES-1];
    reg                 ledger_valid [0:ENTRIES-1];
    reg [TICK_BITS-1:0] tick_cnt;

    function [7:0] w_plus1;
        input [7:0] w;
        begin
            w_plus1 = (w == 8'h7f) ? 8'h7f : w + 8'd1;
        end
    endfunction

    function [7:0] w_minus1;
        input [7:0] w;
        begin
            w_minus1 = (w == 8'h80) ? 8'h80 : w - 8'd1;
        end
    endfunction

    // Integration walker.
    reg       scan_active;
    reg [ENTRY_ADDR_BITS:0] scan_i;
    reg [9:0] active_gid;

    // Learning walker.
    localparam [1:0] L_IDLE = 2'd0,
                     L_POT  = 2'd1,
                     L_EXP  = 2'd2;
    reg [1:0] learn_state;
    reg [ENTRY_ADDR_BITS:0] learn_i;
    reg [7:0] learn_post_neuron;
    reg [TICK_BITS-1:0] learn_fire_tick;
    reg [TICK_BITS-1:0] learn_expiry_tick;
    reg tick_pending;
    reg fire_taken_r;

    // Diagnostic compatibility for raw probes: 0 idle, 1 scan, 2 POT, 3 EXP.
    /* verilator lint_off UNUSEDSIGNAL */
    wire [2:0] state = scan_active ? 3'd1
                     : (learn_state == L_POT) ? 3'd2
                     : (learn_state == L_EXP) ? 3'd3 : 3'd0;
    /* verilator lint_on UNUSEDSIGNAL */

    assign rb_rdata = syn_table[rb_addr];
    assign scan_busy = scan_active;
    assign learn_busy = (learn_state != L_IDLE);
    assign dend_busy = scan_active || learn_busy || tick_pending;
    assign fire_taken = fire_taken_r;

    // Configuration owns a quiescent table boundary. Integration remains
    // available during learning; that independence is the I4 contract.
    assign cfg_ready = !scan_active && (learn_state == L_IDLE)
                     && !tick_pending && !fire_valid;
    assign spk_ready = !scan_active && !(cfg_en && cfg_ready);
    assign tick_ready = !tick_pending;

    integer wi;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            scan_active       <= 1'b0;
            scan_i            <= {(ENTRY_ADDR_BITS+1){1'b0}};
            active_gid        <= 10'd0;
            ev_valid          <= 1'b0;
            ev_neuron         <= 8'd0;
            ev_weight         <= 8'd0;
            learn_state       <= L_IDLE;
            learn_i           <= {(ENTRY_ADDR_BITS+1){1'b0}};
            learn_post_neuron <= 8'd0;
            learn_fire_tick   <= {TICK_BITS{1'b0}};
            learn_expiry_tick <= {TICK_BITS{1'b0}};
            tick_pending      <= 1'b0;
            tick_cnt          <= {TICK_BITS{1'b0}};
            fire_taken_r      <= 1'b0;
            for (wi = 0; wi < ENTRIES; wi = wi + 1) begin
                syn_table[wi]    <= 27'd0;
                ledger_tick[wi]  <= {TICK_BITS{1'b0}};
                ledger_valid[wi] <= 1'b0;
            end
        end else begin
            fire_taken_r <= 1'b0;

            if (tick_strobe && tick_ready) begin
                tick_cnt     <= tick_cnt + {{(TICK_BITS-1){1'b0}}, 1'b1};
                tick_pending <= 1'b1;
            end

            if (cfg_en && cfg_ready)
                syn_table[cfg_addr] <= cfg_wdata;

            // ---------------- learning walker --------------------------
            case (learn_state)
                L_IDLE: begin
                    learn_i <= {(ENTRY_ADDR_BITS+1){1'b0}};
                    if (fire_valid) begin
                        learn_post_neuron <= fire_neuron;
                        learn_fire_tick   <= fire_tick;
                        fire_taken_r      <= 1'b1;
                        learn_state       <= L_POT;
                    end else if (tick_pending) begin
                        tick_pending      <= 1'b0;
                        learn_expiry_tick <= tick_cnt;
                        learn_state       <= L_EXP;
                    end
                end

                L_POT: begin
                    if (learn_i < ENTRIES) begin
                        if (syn_table[learn_i[ENTRY_ADDR_BITS-1:0]][26]
                            && syn_table[learn_i[ENTRY_ADDR_BITS-1:0]][15:8]
                               == learn_post_neuron
                            && ledger_valid[learn_i[ENTRY_ADDR_BITS-1:0]]
                            && (learn_fire_tick
                                - ledger_tick[learn_i[ENTRY_ADDR_BITS-1:0]])
                               <= WINDOW) begin
                            syn_table[learn_i[ENTRY_ADDR_BITS-1:0]] <= {
                                syn_table[learn_i[ENTRY_ADDR_BITS-1:0]][26:8],
                                w_plus1(syn_table[learn_i[ENTRY_ADDR_BITS-1:0]][7:0])
                            };
                            ledger_valid[learn_i[ENTRY_ADDR_BITS-1:0]] <= 1'b0;
                        end
                        learn_i <= learn_i + {{ENTRY_ADDR_BITS{1'b0}}, 1'b1};
                    end else begin
                        learn_i <= {(ENTRY_ADDR_BITS+1){1'b0}};
                        if (tick_pending) begin
                            tick_pending      <= 1'b0;
                            learn_expiry_tick <= tick_cnt;
                            learn_state       <= L_EXP;
                        end else begin
                            learn_state <= L_IDLE;
                        end
                    end
                end

                L_EXP: begin
                    if (learn_i < ENTRIES) begin
                        if (syn_table[learn_i[ENTRY_ADDR_BITS-1:0]][26]
                            && ledger_valid[learn_i[ENTRY_ADDR_BITS-1:0]]
                            && (learn_expiry_tick
                                - ledger_tick[learn_i[ENTRY_ADDR_BITS-1:0]])
                               > WINDOW) begin
                            syn_table[learn_i[ENTRY_ADDR_BITS-1:0]] <= {
                                syn_table[learn_i[ENTRY_ADDR_BITS-1:0]][26:8],
                                w_minus1(syn_table[learn_i[ENTRY_ADDR_BITS-1:0]][7:0])
                            };
                            ledger_valid[learn_i[ENTRY_ADDR_BITS-1:0]] <= 1'b0;
                        end
                        learn_i <= learn_i + {{ENTRY_ADDR_BITS{1'b0}}, 1'b1};
                    end else begin
                        learn_i <= {(ENTRY_ADDR_BITS+1){1'b0}};
                        if (fire_valid) begin
                            learn_post_neuron <= fire_neuron;
                            learn_fire_tick   <= fire_tick;
                            fire_taken_r      <= 1'b1;
                            learn_state       <= L_POT;
                        end else if (tick_pending) begin
                            tick_pending      <= 1'b0;
                            learn_expiry_tick <= tick_cnt;
                            learn_state       <= L_EXP;
                        end else begin
                            learn_state <= L_IDLE;
                        end
                    end
                end

                default: learn_state <= L_IDLE;
            endcase

            // ---------------- integration walker -----------------------
            // This block intentionally follows the learning block. A new
            // arrival therefore wins a same-entry ledger clear.
            if (!scan_active) begin
                ev_valid <= 1'b0;
                if (spk_valid && spk_ready) begin
                    active_gid  <= spk_gid;
                    scan_i      <= {(ENTRY_ADDR_BITS+1){1'b0}};
                    scan_active <= 1'b1;
                end
            end else if (scan_i < ENTRIES) begin
                if (syn_table[scan_i[ENTRY_ADDR_BITS-1:0]][26]
                    && syn_table[scan_i[ENTRY_ADDR_BITS-1:0]][25:16]
                       == active_gid) begin
                    if (!ev_valid) begin
                        ev_valid  <= 1'b1;
                        ev_neuron <= syn_table[scan_i[ENTRY_ADDR_BITS-1:0]][15:8];
                        ev_weight <= syn_table[scan_i[ENTRY_ADDR_BITS-1:0]][7:0];
                    end else if (ev_ready) begin
                        ev_valid             <= 1'b0;
                        ledger_tick[scan_i[ENTRY_ADDR_BITS-1:0]]  <= tick_cnt;
                        ledger_valid[scan_i[ENTRY_ADDR_BITS-1:0]] <= 1'b1;
                        scan_i <= scan_i + {{ENTRY_ADDR_BITS{1'b0}}, 1'b1};
                    end
                end else begin
                    scan_i <= scan_i + {{ENTRY_ADDR_BITS{1'b0}}, 1'b1};
                end
            end else begin
                scan_active <= 1'b0;
                scan_i      <= {(ENTRY_ADDR_BITS+1){1'b0}};
                ev_valid    <= 1'b0;
            end
        end
    end

endmodule

`default_nettype wire
