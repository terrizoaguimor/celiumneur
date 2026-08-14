// hyphae_mesh_2x2.v — Hyphae fabric integration: 4 routers as a 2x2 mesh
// SPDX-License-Identifier: AGPL-3.0-or-later
// (SPEC.md §2, v1 scale). Pure structural wiring, explicit per-link wires —
// 2x2 is small, and any wiring mistake should be visible at a glance instead
// of hiding inside generate arithmetic.
//
// Core ids follow golden/hyphae.py: id = y*2 + x.
//   core0 = (0,0)  core1 = (1,0)
//   core2 = (0,1)  core3 = (1,1)
//
// Every link is a two-party credit contract: the sender transmits only
// against credits, the receiver returns one credit when its input FIFO pops
// (receiver feeder_ret_o bit -> sender credit_ret_i bit of the facing port).
// Port bits in hypha_router: {S,N,W,E,PE} = {4,3,2,1,0}.
//
// PE endpoints per core are exported flat: {core3, core2, core1, core0}.

`default_nettype none

module hyphae_mesh_2x2 (
    input  wire         clk,
    input  wire         rst_n,
    // PE ingress per core (host/core injection), flat {core3..core0}
    input  wire [127:0] pe_in_data,
    input  wire [3:0]   pe_in_valid,
    // PE credit-return toward each local core
    output wire [3:0]   pe_feeder_ret,
    // PE egress per core (deliveries): packet held valid until the consumer
    // acknowledges (I1). pe_out_ready comes from each tile's input budget.
    input  wire [3:0]   pe_out_ready,
    output wire [127:0] pe_out_data,
    output wire [3:0]   pe_out_valid,
    // I1 witness per router: a bit set means a link FIFO saw a push while
    // full — a credit-contract breach. Must never fire.
    output wire [3:0]   overflow_any
);

    // -------------------- inter-router link wires --------------------
    // names: lk_<src><out_port>_to_<dst><in_port>_*
    wire [31:0] lk_0e_to_1w_data;  wire lk_0e_to_1w_valid;
    wire [31:0] lk_1w_to_0e_data;  wire lk_1w_to_0e_valid;
    wire [31:0] lk_0n_to_2s_data;  wire lk_0n_to_2s_valid;
    wire [31:0] lk_2s_to_0n_data;  wire lk_2s_to_0n_valid;
    wire [31:0] lk_2e_to_3w_data;  wire lk_2e_to_3w_valid;
    wire [31:0] lk_3w_to_2e_data;  wire lk_3w_to_2e_valid;
    wire [31:0] lk_1n_to_3s_data;  wire lk_1n_to_3s_valid;
    wire [31:0] lk_3s_to_1n_data;  wire lk_3s_to_1n_valid;

    wire [3:0]  r0_credit_ret, r1_credit_ret, r2_credit_ret, r3_credit_ret;
    // Boundary-facing return bits have no physical consumer in a 2x2 mesh.
    /* verilator lint_off UNUSEDSIGNAL */
    wire [4:0]  r0_feeder_ret, r1_feeder_ret, r2_feeder_ret, r3_feeder_ret;
    /* verilator lint_on UNUSEDSIGNAL */
    wire [31:0] r0_pe_out_data, r1_pe_out_data, r2_pe_out_data, r3_pe_out_data;
    wire        r0_pe_out_valid, r1_pe_out_valid, r2_pe_out_valid, r3_pe_out_valid;

    // Outputs facing beyond the fixed 2x2 boundary are intentionally open.
    /* verilator lint_off PINCONNECTEMPTY */
    // -------------------- core0 (0,0): E<->1, N<->2 --------------------
    hypha_router #(.CORE_X(0), .CORE_Y(0)) r0 (
        .clk(clk), .rst_n(rst_n),
        .in_pe_data (pe_in_data[31:0]),   .in_pe_valid(pe_in_valid[0]),
        .in_e_data  (lk_1w_to_0e_data),   .in_e_valid (lk_1w_to_0e_valid),
        .in_w_data  (32'b0),              .in_w_valid (1'b0),
        .in_n_data  (lk_2s_to_0n_data),   .in_n_valid (lk_2s_to_0n_valid),
        .in_s_data  (32'b0),              .in_s_valid (1'b0),
        .credit_ret_i(r0_credit_ret),
        .feeder_ret_o(r0_feeder_ret),
        .out_pe_data(r0_pe_out_data),     .out_pe_valid(r0_pe_out_valid),
        .pe_out_ready(pe_out_ready[0]),
        .out_e_data (lk_0e_to_1w_data),   .out_e_valid (lk_0e_to_1w_valid),
        .out_w_data (),                   .out_w_valid (),
        .out_n_data (lk_0n_to_2s_data),   .out_n_valid (lk_0n_to_2s_valid),
        .out_s_data (),                   .out_s_valid (),
        .overflow_any(overflow_any[0])
    );

    // -------------------- core1 (1,0): W<->0, N<->3 --------------------
    hypha_router #(.CORE_X(1), .CORE_Y(0)) r1 (
        .clk(clk), .rst_n(rst_n),
        .in_pe_data (pe_in_data[63:32]),  .in_pe_valid(pe_in_valid[1]),
        .in_e_data  (32'b0),              .in_e_valid (1'b0),
        .in_w_data  (lk_0e_to_1w_data),   .in_w_valid (lk_0e_to_1w_valid),
        .in_n_data  (lk_3s_to_1n_data),   .in_n_valid (lk_3s_to_1n_valid),
        .in_s_data  (32'b0),              .in_s_valid (1'b0),
        .credit_ret_i(r1_credit_ret),
        .feeder_ret_o(r1_feeder_ret),
        .out_pe_data(r1_pe_out_data),     .out_pe_valid(r1_pe_out_valid),
        .pe_out_ready(pe_out_ready[1]),
        .out_e_data (),                   .out_e_valid (),
        .out_w_data (lk_1w_to_0e_data),   .out_w_valid (lk_1w_to_0e_valid),
        .out_n_data (lk_1n_to_3s_data),   .out_n_valid (lk_1n_to_3s_valid),
        .out_s_data (),                   .out_s_valid (),
        .overflow_any(overflow_any[1])
    );

    // -------------------- core2 (0,1): E<->3, S<->0 --------------------
    hypha_router #(.CORE_X(0), .CORE_Y(1)) r2 (
        .clk(clk), .rst_n(rst_n),
        .in_pe_data (pe_in_data[95:64]),  .in_pe_valid(pe_in_valid[2]),
        .in_e_data  (lk_3w_to_2e_data),   .in_e_valid (lk_3w_to_2e_valid),
        .in_w_data  (32'b0),              .in_w_valid (1'b0),
        .in_n_data  (32'b0),              .in_n_valid (1'b0),
        .in_s_data  (lk_0n_to_2s_data),   .in_s_valid (lk_0n_to_2s_valid),
        .credit_ret_i(r2_credit_ret),
        .feeder_ret_o(r2_feeder_ret),
        .out_pe_data(r2_pe_out_data),     .out_pe_valid(r2_pe_out_valid),
        .pe_out_ready(pe_out_ready[2]),
        .out_e_data (lk_2e_to_3w_data),   .out_e_valid (lk_2e_to_3w_valid),
        .out_w_data (),                   .out_w_valid (),
        .out_n_data (),                   .out_n_valid (),
        .out_s_data (lk_2s_to_0n_data),   .out_s_valid (lk_2s_to_0n_valid),
        .overflow_any(overflow_any[2])
    );

    // -------------------- core3 (1,1): W<->2, S<->1 --------------------
    hypha_router #(.CORE_X(1), .CORE_Y(1)) r3 (
        .clk(clk), .rst_n(rst_n),
        .in_pe_data (pe_in_data[127:96]), .in_pe_valid(pe_in_valid[3]),
        .in_e_data  (32'b0),              .in_e_valid (1'b0),
        .in_w_data  (lk_2e_to_3w_data),   .in_w_valid (lk_2e_to_3w_valid),
        .in_n_data  (32'b0),              .in_n_valid (1'b0),
        .in_s_data  (lk_1n_to_3s_data),   .in_s_valid (lk_1n_to_3s_valid),
        .credit_ret_i(r3_credit_ret),
        .feeder_ret_o(r3_feeder_ret),
        .out_pe_data(r3_pe_out_data),     .out_pe_valid(r3_pe_out_valid),
        .pe_out_ready(pe_out_ready[3]),
        .out_e_data (),                   .out_e_valid (),
        .out_w_data (lk_3w_to_2e_data),   .out_w_valid (lk_3w_to_2e_valid),
        .out_n_data (),                   .out_n_valid (),
        .out_s_data (lk_3s_to_1n_data),   .out_s_valid (lk_3s_to_1n_valid),
        .overflow_any(overflow_any[3])
    );
    /* verilator lint_on PINCONNECTEMPTY */

    // -------------------- credit returns across each link --------------------
    // {S,N,W,E} order per router's credit_ret_i.
    assign r0_credit_ret = { 1'b0,            // S: no south link
                             r2_feeder_ret[4],// N link: core2 popped its S-fifo
                             1'b0,            // W: no west link
                             r1_feeder_ret[2] // E link: core1 popped its W-fifo
                           };
    assign r1_credit_ret = { 1'b0,
                             r3_feeder_ret[4], // N link: core3 popped its S-fifo
                             r0_feeder_ret[1], // W link: core0 popped its E-fifo
                             1'b0
                           };
    assign r2_credit_ret = { r0_feeder_ret[3], // S link: core0 popped its N-fifo
                             1'b0,
                             1'b0,
                             r3_feeder_ret[2]  // E link: core3 popped its W-fifo
                           };
    assign r3_credit_ret = { r1_feeder_ret[3], // S link: core1 popped its N-fifo
                             1'b0,
                             r2_feeder_ret[1], // W link: core2 popped its E-fifo
                             1'b0
                           };

    // -------------------- PE endpoints --------------------
    assign pe_feeder_ret = { r3_feeder_ret[0], r2_feeder_ret[0],
                             r1_feeder_ret[0], r0_feeder_ret[0] };
    assign pe_out_data   = { r3_pe_out_data, r2_pe_out_data,
                             r1_pe_out_data, r0_pe_out_data };
    assign pe_out_valid  = { r3_pe_out_valid, r2_pe_out_valid,
                             r1_pe_out_valid, r0_pe_out_valid };

endmodule

`default_nettype wire
