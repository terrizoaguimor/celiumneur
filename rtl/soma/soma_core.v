// soma_core.v — CeliumNeUR SomaCore v1 (SPEC.md §3).
// SPDX-License-Identifier: Apache-2.0
//
// Time-multiplexed neuron update engine: ONE physical datapath serves all
// neurons, sweeping SRAM state (the "network is an illusion created by
// memory" pattern — same structural lineage as the audited ODIN, but with
// the audit fixes baked in):
//   - saturating accumulator, never wraps                (I6; lif-tt-asic)
//   - ceiling leak toward zero, no sticky residues       (lif-tt-asic >>>)
//   - refractory counted in real time ticks              (ed-snn-fpga sweeps)
//   - all parameters independent per neuron              (I7; ReckOn pairs)
//   - subtractive reset option keeps post-spike residue  (ODIN reset-to-zero)
//
// Neuron word (64-bit), params and state interleaved:
//   [63:48] theta (16, 1..32767)
//   [47]    reset_mode: 1 = subtractive (v-theta), 0 = to zero
//   [46:43] leak_shift k (4b): tick leak = ceil(|v| / 2**k)
//   [42:35] refractory_ticks (8b)
//   [34:27] reserved (8b, write-zero)
//   [26:19] refractory_countdown (8b, state)
//   [18:16] reserved_flags (3b, write-zero)
//   [15:0]  v (16b signed, state)
//
// Update semantics mirror golden/soma.py ONE-TO-ONE (see cocotb soma_test).
// Tick = explicit strobe; v1 sweep is phase-mode: events are accepted only
// when no sweep is in progress (the bench and the host share this rule).

`default_nettype none

module soma_core #(
    parameter NEURONS = 4,
    parameter ID_BITS = 2,              // clog2(NEURONS)
    parameter TICK_BITS = 10
) (
    input  wire        clk,
    input  wire        rst_n,

    // Synaptic event input (weight arrives, one per cycle max).
    input  wire        ev_valid,
    input  wire [7:0]  ev_neuron,
    input  wire signed [7:0] ev_weight,
    output wire        ev_ready,        // high iff the engine may accept now

    // Time tick: sweeps every neuron once (I7: per-neuron params/rule).
    input  wire        tick_req,
    output wire        tick_ready,
    output wire        sweep_active,
    output wire        busy,

    // Autonomous configuration (the reviewer hole, closed): the host writes
    // the full neuron word when the engine is idle. Parameters land atomically
    // — no indeterminate state after reset, no simulator hierarchy climbing.
    input  wire        cfg_en,
    input  wire [7:0]  cfg_addr,
    input  wire [63:0] cfg_wdata,
    output wire        cfg_ready,

    // Fire channel. Payload remains stable while valid && !ready.
    output reg         fire_valid,
    output reg  [7:0]  fire_neuron,
    output reg         fire_parity,
    output reg  [TICK_BITS-1:0] fire_tick,
    input  wire        fire_ready,
    input  wire        phase_parity,
    input  wire [TICK_BITS-1:0] phase_tick,

    // Independent asynchronous observation port. The request never enters
    // the update arbiter and therefore cannot halt events or tick sweeps.
    input  wire [7:0]  rb_addr,
    input  wire        rb_req,
    output wire [63:0] rb_data,
    output wire        rb_ready,
    output wire        rb_valid
);

    // ------------------------------------------------------------------
    // State memory (behavioral 64-bit RAM; v1: single bank, structural
    // split even/odd deferred to the 2-updates/cycle upgrade — SPEC §3).
    // ------------------------------------------------------------------
    reg [63:0] nram [0:NEURONS-1];

    // ------------------------------------------------------------------
    // Golden-mirrored arithmetic (translate soma.py bit by bit).
    // ------------------------------------------------------------------
    function signed [15:0] sat16;
        input signed [16:0] wide;
        begin
            if (wide > 17'sd32767)      sat16 = 16'sd32767;
            else if (wide < -17'sd32768) sat16 = -16'sd32768;
            else                          sat16 = wide[15:0];
        end
    endfunction

    function [15:0] leak_mag;  // ceil(|v| / 2**k)
        input signed [15:0] v;
        input [3:0]         k;
        reg   [15:0]        magnitude, biased;
        begin
            magnitude = v[15] ? -v : v;
            biased    = magnitude + ((16'd1 << k) - 16'd1);
            leak_mag  = (v == 16'sd0) ? 16'd0 : (biased >> k);
        end
    endfunction

    // ------------------------------------------------------------------
    // Engine FSM: per neuron update = RD (sync read issued) -> AP (apply).
    // ------------------------------------------------------------------
    localparam [2:0] S_IDLE    = 3'd0,
                     S_EV_RD   = 3'd1,
                     S_EV_AP   = 3'd2,
                     S_SW_RD   = 3'd3,
                     S_SW_AP   = 3'd4,
                     S_INIT    = 3'd5,   // post-reset deterministic zero-sweep
                     S_FIRE    = 3'd6;   // hold fire until downstream accepts

    reg [2:0]  state;
    reg [7:0]  op_neuron;        // neuron being serviced
    reg        op_is_tick;       // 1 = tick update, 0 = synaptic event
    reg signed [7:0] op_weight;
    reg [7:0]  sweep_idx;
    reg [63:0] word_q;           // captured RAM word for the in-flight op
    reg        fire_from_sweep;
    reg        fire_last_in_sweep;

    assign sweep_active = (state == S_SW_RD) || (state == S_SW_AP)
                       || (state == S_INIT)
                       || ((state == S_FIRE) && fire_from_sweep);
    assign busy = (state != S_IDLE);
    assign cfg_ready = (state == S_IDLE);
    assign ev_ready = (state == S_IDLE) && !cfg_en;
    assign tick_ready = (state == S_IDLE) && !cfg_en && !ev_valid;
    assign rb_ready = 1'b1;
    assign rb_valid = rb_req;
    assign rb_data = nram[rb_addr[ID_BITS-1:0]];

    wire signed [15:0] v_mem   = word_q[15:0];
    wire [7:0]  refr_cnt       = word_q[26:19];
    wire [7:0]  refr_ticks     = word_q[42:35];
    wire [3:0]  leak_k         = word_q[46:43];
    wire        subtract_mode  = word_q[47];
    wire signed [15:0] theta   = word_q[63:48];

    // Computation for the in-flight op, mirroring Soma.advance_time /
    // Soma.apply_synaptic_input including the fire-then-decrement order.
    reg signed [15:0] v_next;
    reg [7:0]  refr_next;
    reg        fire_next;
    reg signed [16:0] acc_wide;   // integration accumulator (module scope:
                                  // Verilog-2005 forbids block-scope decls)
    reg [15:0] lmag;
    reg [7:0]  init_i;            // post-reset wipe walk (deterministic init)
    always @(*) begin
        v_next    = v_mem;
        refr_next = refr_cnt;
        fire_next = 1'b0;
        lmag       = 16'd0;
        acc_wide   = {v_mem[15], v_mem};
        // integrate path
        if (op_is_tick) begin
            lmag = leak_mag(v_mem, leak_k);
            acc_wide = {v_mem[15], v_mem} + (v_mem[15] ? {1'b0, lmag} : -{1'b0, lmag});
            v_next = sat16(acc_wide);
        end else begin
            acc_wide = {v_mem[15], v_mem} + {{9{op_weight[7]}}, op_weight};
            v_next = sat16(acc_wide);
        end
        // evaluate (spike masked by refractory), then decrement: a counter
        // loaded by a fire on this very op loses one tick immediately, which
        // is exactly the golden's advance_time order (evaluate-then-decrement).
        if (refr_cnt == 8'd0 && v_next >= theta) begin
            fire_next = 1'b1;
            if (subtract_mode) v_next = sat16({v_next[15], v_next} - {1'b0, theta});
            else               v_next = 16'sd0;
            refr_next = refr_ticks;
        end
        // Golden parity: only the TICK path decrements the counter; a fire
        // during a tick loads and immediately loses one tick (evaluate-then-
        // decrement). Events never age the refractory countdown.
        if (op_is_tick && refr_next != 8'd0) refr_next = refr_next - 8'd1;
    end

    wire [63:0] word_next = { theta, subtract_mode, leak_k, refr_ticks,
                              word_q[34:27], refr_next, word_q[18:16], v_next };

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_INIT;    // deterministic post-reset wipe
            init_i      <= 8'd0;
            op_neuron   <= 8'd0;
            op_is_tick  <= 1'b0;
            op_weight   <= 8'sd0;
            sweep_idx   <= 8'd0;
            word_q      <= 64'd0;
            fire_valid  <= 1'b0;
            fire_neuron <= 8'd0;
            fire_parity <= 1'b0;
            fire_tick   <= {TICK_BITS{1'b0}};
            fire_from_sweep <= 1'b0;
            fire_last_in_sweep <= 1'b0;
        end else begin
            case (state)
                S_INIT: begin
                    // inert-by-default neuron: theta max, all else zero —
                    // a wiped neuron must never fire on its own (a theta=0
                    // wipe would misfire spontaneously; that is the kind of
                    // bug an unreviewed default wins you).
                    nram[init_i] <= 64'h7FFF_0000_0000_0000;
                    if ({1'b0, init_i} == NEURONS - 1) state <= S_IDLE;
                    else init_i <= init_i + 8'd1;
                end
                S_IDLE: begin
                    fire_valid <= 1'b0;
                    if (cfg_en && cfg_ready) begin
                        // stand-alone configuration write (no touch of datapath)
                        nram[cfg_addr] <= cfg_wdata;
                    end else if (ev_valid && ev_ready) begin
                        op_neuron  <= ev_neuron;
                        op_is_tick <= 1'b0;
                        op_weight  <= ev_weight;
                        state      <= S_EV_RD;
                    end else if (tick_req && tick_ready) begin
                        sweep_idx <= 8'd0;
                        state     <= S_SW_RD;
                    end
                end
                S_EV_RD: begin
                    word_q <= nram[op_neuron[ID_BITS-1:0]];
                    state  <= S_EV_AP;
                end
                S_EV_AP: begin
                    nram[op_neuron[ID_BITS-1:0]] <= word_next;
                    if (fire_next) begin
                        fire_valid  <= 1'b1;
                        fire_neuron <= op_neuron;
                        fire_parity <= phase_parity;
                        fire_tick   <= phase_tick;
                        fire_from_sweep <= 1'b0;
                        fire_last_in_sweep <= 1'b0;
                        state <= S_FIRE;
                    end else begin
                        state <= S_IDLE;
                    end
                end
                S_SW_RD: begin
                    word_q <= nram[sweep_idx[ID_BITS-1:0]];
                    state  <= S_SW_AP;
                end
                S_SW_AP: begin
                    nram[sweep_idx[ID_BITS-1:0]] <= word_next;
                    if (fire_next) begin
                        fire_valid  <= 1'b1;
                        fire_neuron <= sweep_idx;
                        fire_parity <= phase_parity;
                        fire_tick   <= phase_tick;
                        fire_from_sweep <= 1'b1;
                        fire_last_in_sweep <= ({1'b0, sweep_idx} == NEURONS - 1);
                        if ({1'b0, sweep_idx} != NEURONS - 1)
                            sweep_idx <= sweep_idx + 8'd1;
                        state <= S_FIRE;
                    end else if ({1'b0, sweep_idx} == NEURONS - 1) begin
                        state <= S_IDLE;
                    end else begin
                        sweep_idx <= sweep_idx + 8'd1;
                        state     <= S_SW_RD;
                    end
                end
                S_FIRE: begin
                    if (fire_ready) begin
                        fire_valid <= 1'b0;
                        if (fire_from_sweep && !fire_last_in_sweep)
                            state <= S_SW_RD;
                        else
                            state <= S_IDLE;
                    end
                end
                default: begin
                    fire_valid <= 1'b0;
                    state <= S_IDLE;
                end
            endcase
            // sweep sequencing state for the in-flight tick op
            if (state == S_SW_RD) begin op_neuron <= sweep_idx; op_is_tick <= 1'b1; end
        end
    end

endmodule

`default_nettype wire
