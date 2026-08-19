// hypha_router.v — Hyphae fabric router (SPEC.md §2.1).
// SPDX-License-Identifier: Apache-2.0
//
// - X-Y dimension-ordered routing with multicast branch replication: a packet
//   waits in line once and leaves on every output port that still carries
//   destinations, each copy bearing the sub-mask for that branch.
// - Atomic replication: an input head pops only when ALL needed output ports
//   hold a credit, so a replication can never leave a torn copy behind.
// - Credit-based links (Invariant I1): egress only against a credit; credits
//   return on downstream pops. There is no drop path in this module.
// - One arbitration winner per cycle, combinational pop (the served head
//   leaves its FIFO at the same edge that registers its copies — registered
//   pop would serve the same packet twice). Matches golden RouterModel 1:1.
//
// Packet: type[31:28] | dst_mask[23:20] | body[19:0].

`default_nettype none

module hypha_router #(
    parameter CORE_X = 0,
    parameter CORE_Y = 0,
    parameter MESH_W = 2,
    parameter MESH_H = 2
) (
    input  wire        clk,
    input  wire        rst_n,

    // Ingress (PE = local core injection; E/W/N/S = from that-side neighbor).
    input  wire [31:0] in_pe_data,  input wire in_pe_valid,
    input  wire [31:0] in_e_data,   input wire in_e_valid,
    input  wire [31:0] in_w_data,   input wire in_w_valid,
    input  wire [31:0] in_n_data,   input wire in_n_valid,
    input  wire [31:0] in_s_data,   input wire in_s_valid,

    // Credit-return pulses for my output links (downstream popped: +1 credit).
    input  wire [3:0]  credit_ret_i,          // {S,N,W,E}

    // PE delivery handshake: the consumer (tile) asserts it can accept.
    // I1: the PE copy must persist until accepted — the pulse shaped v1
    // silently drops anything the sink did not catch in one cycle.
    input  wire        pe_out_ready,

    // Credit-return pulses toward my feeders (I popped their queue copy).
    output wire [4:0]  feeder_ret_o,          // {S,N,W,E,PE}

    // Egress {PE,E,W,N,S}; each copy carries only that branch's sub-mask.
    output wire [31:0] out_pe_data, output wire out_pe_valid,
    output wire [31:0] out_e_data,  output wire out_e_valid,
    output wire [31:0] out_w_data,  output wire out_w_valid,
    output wire [31:0] out_n_data,  output wire out_n_valid,
    output wire [31:0] out_s_data,  output wire out_s_valid,

    output wire        overflow_any  // OR of all input FIFO witnesses
);

    localparam integer LINK_DEPTH = 4;
    localparam [2:0]   LINK_DEPTH_INIT = 4;

    // Output-port indices in need/spend vectors. Credit slot for a mesh
    // output is its port index minus one (PE holds slot 0 logically and is
    // always-ready per SPEC §2.1, so no credit exists for it).
    localparam integer P_PE = 0;

    // ------------------------------------------------------------------
    // X-Y branch function: sub-mask of `mask` that exits via `port`.
    // X leg first; vertical only once x is aligned (turn model, Glass & Ni
    // 1992: routes never turn back into X, so dependencies stay acyclic).
    // ------------------------------------------------------------------
    function [MESH_W*MESH_H-1:0] branch_mask;
        input [MESH_W*MESH_H-1:0] mask;
        input integer             port;
        integer                   d, dx, dy;
        begin
            branch_mask = {MESH_W*MESH_H{1'b0}};
            for (d = 0; d < MESH_W*MESH_H; d = d + 1) begin
                if (mask[d]) begin
                    dx = d % MESH_W;
                    dy = d / MESH_W;
                    if (port == P_PE) begin
                        if (dx == CORE_X && dy == CORE_Y) branch_mask[d] = 1'b1;
                    end else if (port == 1) begin  // E
                        if (dx > CORE_X) branch_mask[d] = 1'b1;
                    end else if (port == 2) begin  // W
                        if (dx < CORE_X) branch_mask[d] = 1'b1;
                    end else if (port == 3) begin  // N
                        if (dx == CORE_X && dy > CORE_Y) branch_mask[d] = 1'b1;
                    end else begin                 // S
                        if (dx == CORE_X && dy < CORE_Y) branch_mask[d] = 1'b1;
                    end
                end
            end
        end
    endfunction

    // ------------------------------------------------------------------
    // Input FIFOs (fall-through heads drive arbitration combinationally).
    // ------------------------------------------------------------------
    wire [31:0] in_data_w  [4:0];
    wire        in_valid_w [4:0];
    assign in_valid_w[0] = in_pe_valid; assign in_data_w[0] = in_pe_data;
    assign in_valid_w[1] = in_e_valid;  assign in_data_w[1] = in_e_data;
    assign in_valid_w[2] = in_w_valid;  assign in_data_w[2] = in_w_data;
    assign in_valid_w[3] = in_n_valid;  assign in_data_w[3] = in_n_data;
    assign in_valid_w[4] = in_s_valid;  assign in_data_w[4] = in_s_data;

    wire [31:0] head_i   [4:0];
    wire [4:0]  empty_i, ov_i;
    wire [4:0]  pop_i;

    genvar gi;
    // Full is implicit in the credit contract; overflow is the public breach
    // witness. The FIFO's full pin is intentionally not duplicated here.
    /* verilator lint_off PINCONNECTEMPTY */
    generate
        for (gi = 0; gi < 5; gi = gi + 1) begin : g_in_fifos
            hypha_link_fifo #(
                .WIDTH(32), .DEPTH(LINK_DEPTH), .ADDR_BITS(2), .COUNT_BITS(3)
            ) fifo (
                .clk(clk), .rst_n(rst_n),
                .push(in_valid_w[gi]), .din(in_data_w[gi]),
                .pop(pop_i[gi]),
                .dout(head_i[gi]),
                .empty(empty_i[gi]), .full(), .overflow(ov_i[gi])
            );
        end
    endgenerate
    /* verilator lint_on PINCONNECTEMPTY */

    assign overflow_any = |ov_i;

    // ------------------------------------------------------------------
    // Need vectors: bit per output port {S,N,W,E,PE}.
    // ------------------------------------------------------------------
    wire [3:0] dst_i [4:0];
    wire [4:0] need_i [4:0];
    genvar gm;
    generate
        for (gm = 0; gm < 5; gm = gm + 1) begin : g_need
            assign dst_i[gm]  = head_i[gm][23:20];
            assign need_i[gm] = {
                (branch_mask(dst_i[gm], 4) != 0),   // S
                (branch_mask(dst_i[gm], 3) != 0),   // N
                (branch_mask(dst_i[gm], 2) != 0),   // W
                (branch_mask(dst_i[gm], 1) != 0),   // E
                (branch_mask(dst_i[gm], 0) != 0)    // PE
            };
        end
    endgenerate

    // ------------------------------------------------------------------
    // Credits: next-state computed once (returns and spends combined), so a
    // return landing on a spend cycle is never lost.
    // ------------------------------------------------------------------
    reg  [2:0] credits [3:0];          // {S,N,W,E} slots 3..0
    wire [3:0] credit_ok = { credits[3] != 0, credits[2] != 0,
                             credits[1] != 0, credits[0] != 0 };

    // PE lane handshake: a head that needs PE is serviceable only when the
    // PE channel is free (nothing unacked) or being consumed this cycle —
    // otherwise the copy would overwrite the copy still in flight. That is
    // the I1 seam, made physical.
    wire pe_lane_free;

    wire [4:0] serviceable;
    genvar gk;
    generate
        for (gk = 0; gk < 5; gk = gk + 1) begin : g_svc
            assign serviceable[gk] = ~empty_i[gk] &
                                     ((need_i[gk][4:1] & ~credit_ok) == 4'b0) &
                                     (~need_i[gk][0] | pe_lane_free);
        end
    endgenerate

    // Round-robin: first serviceable input from rr_ptr wins.
    reg  [2:0] rr_ptr;
    integer    k;
    reg  [2:0] candidate_idx;
    reg  [2:0] sel_idx;
    reg        sel_valid;
    always @(*) begin
        sel_valid = 1'b0;
        sel_idx   = 3'd0;
        candidate_idx = rr_ptr;
        for (k = 0; k < 5; k = k + 1) begin
            case (k)
                0: candidate_idx = rr_ptr;
                1: candidate_idx = (rr_ptr >= 3'd4) ? rr_ptr - 3'd4
                                                     : rr_ptr + 3'd1;
                2: candidate_idx = (rr_ptr >= 3'd3) ? rr_ptr - 3'd3
                                                     : rr_ptr + 3'd2;
                3: candidate_idx = (rr_ptr >= 3'd2) ? rr_ptr - 3'd2
                                                     : rr_ptr + 3'd3;
                default: candidate_idx = (rr_ptr >= 3'd1) ? rr_ptr - 3'd1
                                                           : rr_ptr + 3'd4;
            endcase
            if (!sel_valid && serviceable[candidate_idx]) begin
                sel_valid = 1'b1;
                sel_idx   = candidate_idx;
            end
        end
    end

    assign pop_i = sel_valid ? (5'b00001 << sel_idx) : 5'b00000;
    assign feeder_ret_o = pop_i;

    wire [4:0] need_sel = need_i[sel_idx];

    // ------------------------------------------------------------------
    // Registered egress (copies) + single credit next-state update.
    // ------------------------------------------------------------------
    reg [31:0] out_data_r [4:0];
    reg [4:0]  out_valid_r;
    integer    oj;

    // out_valid_r[0] is now declared (registers must lead references).
    assign pe_lane_free = (out_valid_r[0] == 1'b0) | pe_out_ready;

    assign out_pe_data = out_data_r[0]; assign out_pe_valid = out_valid_r[0];
    assign out_e_data  = out_data_r[1]; assign out_e_valid  = out_valid_r[1];
    assign out_w_data  = out_data_r[2]; assign out_w_valid  = out_valid_r[2];
    assign out_n_data  = out_data_r[3]; assign out_n_valid  = out_valid_r[3];
    assign out_s_data  = out_data_r[4]; assign out_s_valid  = out_valid_r[4];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rr_ptr      <= 3'd0;
            out_valid_r <= 5'b0;
            for (oj = 0; oj < 5; oj = oj + 1) out_data_r[oj] <= 32'b0;
            for (oj = 0; oj < 4; oj = oj + 1) credits[oj] <= LINK_DEPTH_INIT;
        end else begin
            // mesh outputs E/W/N/S pulse exactly one cycle (fiber links have
            // buffered input FIFOs downstream). The PE channel instead uses
            // valid-until-ready: the copy persists until the tile accepts it.
            if (out_valid_r[0] && pe_out_ready)
                out_valid_r[0] <= 1'b0;           // PE copy consumed
            out_valid_r[4:1] <= 4'b0;             // E/W/N/S one-cycle pulses
            for (oj = 0; oj < 4; oj = oj + 1) begin
                credits[oj] <= credits[oj]
                               + (credit_ret_i[oj] ? 3'd1 : 3'd0)
                               - ((sel_valid && need_sel[oj+1]) ? 3'd1 : 3'd0);
            end
            if (sel_valid) begin
                rr_ptr <= (sel_idx == 3'd4) ? 3'd0 : sel_idx + 3'd1;
                for (oj = 0; oj < 5; oj = oj + 1) begin
                    if (need_sel[oj]) begin
                        out_valid_r[oj] <= 1'b1;
                        // type + reserved[27:24] passthrough; mask narrowed
                        out_data_r[oj]  <= { head_i[sel_idx][31:24],
                                             branch_mask(dst_i[sel_idx], oj),
                                             head_i[sel_idx][19:0] };
                    end
                end
            end
        end
    end

endmodule

`default_nettype wire
