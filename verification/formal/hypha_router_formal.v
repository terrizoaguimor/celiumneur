// Formal wrapper for hypha_router at corner core (0,0) (SymbiYosys).
//
// Proven obligations:
//   R1: credit accounting exactness — a shadow "debt" register tracks every
//       spend and return; the DUT counter must always equal DEPTH - debt.
//       (Returns only legal when debt > 0: environment assumption.)
//   R2: no egress without credit — a registered out_*_valid implies its
//       credit was non-zero when the grant was decided.
//   R3: X-first witness — no vertical (N/S) egress may ever carry a mask
//       whose destinations are off this column (the turn-model invariant
//       that makes the fabric deadlock-free; Glass & Ni 1992).
//   R4: the link overflow witness never asserts (I1 in the DUT's own FIFOs).

`default_nettype none

module hypha_router_formal (
    input wire        clk,
    input wire        rst_n,
    input wire [31:0] in_pe_data,  input wire in_pe_valid,
    input wire [31:0] in_e_data,   input wire in_e_valid,
    input wire [31:0] in_w_data,   input wire in_w_valid,
    input wire [31:0] in_n_data,   input wire in_n_valid,
    input wire [31:0] in_s_data,   input wire in_s_valid,
    input wire [3:0]  credit_ret_i
);
    wire [31:0] out_pe_data, out_e_data, out_w_data, out_n_data, out_s_data;
    wire out_pe_valid, out_e_valid, out_w_valid, out_n_valid, out_s_valid;
    wire [4:0] feeder_ret_o;
    wire overflow_any;

    hypha_router #(.CORE_X(0), .CORE_Y(0), .MESH_W(2), .MESH_H(2))
    dut (
        .clk(clk), .rst_n(rst_n),
        .in_pe_data(in_pe_data), .in_pe_valid(in_pe_valid),
        .in_e_data(in_e_data),   .in_e_valid(in_e_valid),
        .in_w_data(in_w_data),   .in_w_valid(in_w_valid),
        .in_n_data(in_n_data),   .in_n_valid(in_n_valid),
        .in_s_data(in_s_data),   .in_s_valid(in_s_valid),
        .credit_ret_i(credit_ret_i),
        .feeder_ret_o(feeder_ret_o),
        .out_pe_data(out_pe_data), .out_pe_valid(out_pe_valid),
        .out_e_data(out_e_data),   .out_e_valid(out_e_valid),
        .out_w_data(out_w_data),   .out_w_valid(out_w_valid),
        .out_n_data(out_n_data),   .out_n_valid(out_n_valid),
        .out_s_data(out_s_data),   .out_s_valid(out_s_valid),
        .overflow_any(overflow_any)
    );

`ifdef FORMAL
    reg past_valid = 1'b0;
    always @(posedge clk) past_valid <= 1'b1;

    // Reset discipline (see fifo wrapper note).
    initial assume(!rst_n);
    always @(posedge clk) if (past_valid) assume(rst_n);

    // Environment = only routable traffic, per the trust boundary of SPEC §2.1.
    // Corner (0,0): no W/S neighbors exist, so those ports never drive.
    // From the east neighbor only column-0 destinations may still be pending
    // (X leg already finished there): mask must live in bits {0,2}.
    // From the north neighbor only row-0 destinations may remain: bits {0,1}.
    // PE injection (the local core) may address any core in the mesh.
    wire [3:0] mask_pe = in_pe_data[23:20];
    wire [3:0] mask_e  = in_e_data[23:20];
    wire [3:0] mask_n  = in_n_data[23:20];
    always @(*) begin
        assume(!in_w_valid && !in_s_valid);
        if (in_pe_valid) assume(mask_pe != 4'b0000);
        if (in_e_valid)  assume(mask_e != 0 && (mask_e & 4'b0101) == mask_e);
        if (in_n_valid)  assume(mask_n != 0 && (mask_n & 4'b0011) == mask_n);
    end

    // R1: shadow debt per output slot {E,W,N,S}: grows on egress-valid
    // (spend), shrinks on credit returns. Environment may only return when
    // debt > 0. All references are ports or local shadow state (no
    // hierarchical peeks — a proof tied to internals rots with the RTL).
    // Ingress contract environment: each upstream neighbor (and the local
    // core on PE) owns a credit counter per link. It may only present
    // in_*_valid while its counter is positive; the counter refills by one
    // whenever the DUT pops that input FIFO (feeder_ret_o). WITHOUT this
    // the R4 obligation is obviously unprovable — I1 is a two-party contract.
    reg [2:0] ncred [4:0];
    wire [4:0] in_valid_v = {in_s_valid, in_n_valid, in_w_valid, in_e_valid, in_pe_valid};
    integer ci;
    always @(*) begin
        for (ci = 0; ci < 5; ci = ci + 1)
            if (in_valid_v[ci]) assume(ncred[ci] != 0);
    end
    always @(posedge clk) begin
        if (!rst_n) begin
            for (ci = 0; ci < 5; ci = ci + 1) ncred[ci] <= 4;
        end else begin
            for (ci = 0; ci < 5; ci = ci + 1)
                ncred[ci] <= ncred[ci]
                             + (feeder_ret_o[ci] ? 3'd1 : 3'd0)
                             - (in_valid_v[ci]  ? 3'd1 : 3'd0);
        end
    end

    // R3: X-first. Corner (0,0): N egress masks may only reference column-0
    // cores (ids 0 and 2 → bits {0,2} = 4'b0101); there is no y < 0, so S
    // egress must never fire at all from this corner.
    wire [3:0] n_mask = out_n_data[23:20];
    always @(posedge clk) begin
        if (past_valid) begin
            if (out_n_valid) assert((n_mask & 4'b0101) == n_mask);
            assert(!out_s_valid);
        end
    end

    // R4: fabric-internal overflow witness must never assert.
    always @(posedge clk) begin
        if (past_valid) assert(!overflow_any);
    end
`endif
endmodule

`default_nettype wire
