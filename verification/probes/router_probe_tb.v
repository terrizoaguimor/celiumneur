// router_probe_tb.v — raw minimal probe: one packet into in_e of the corner
// SPDX-License-Identifier: Apache-2.0
// router (0,0) destined for core 1 (mask {1}). Expected: exactly one pulse
// on out_e_valid with the same mask. Nothing else.
`timescale 1ns/1ps
`default_nettype none
module router_probe_tb;
    reg clk = 0, rst_n = 0;
    always #5 clk = ~clk;
    reg [31:0] in_e_data = 0;
    reg        in_e_valid = 0;
    wire [31:0] out_e_data, out_pe_data, out_n_data;
    wire out_e_valid, out_pe_valid, out_n_valid;

    hypha_router #(.CORE_X(0), .CORE_Y(0), .MESH_W(2), .MESH_H(2)) dut (
        .clk(clk), .rst_n(rst_n),
        .in_pe_data(32'b0), .in_pe_valid(1'b0),
        .in_e_data(in_e_data), .in_e_valid(in_e_valid),
        .in_w_data(32'b0), .in_w_valid(1'b0),
        .in_n_data(32'b0), .in_n_valid(1'b0),
        .in_s_data(32'b0), .in_s_valid(1'b0),
        .credit_ret_i(4'b0),
        .pe_out_ready(1'b1),
        .feeder_ret_o(),
        .out_pe_data(out_pe_data), .out_pe_valid(out_pe_valid),
        .out_e_data(out_e_data), .out_e_valid(out_e_valid),
        .out_w_data(), .out_w_valid(),
        .out_n_data(out_n_data), .out_n_valid(out_n_valid),
        .out_s_data(), .out_s_valid(),
        .overflow_any()
    );

    integer t;
    integer east_count = 0;
    integer illegal_count = 0;
    reg bad_payload = 0;
    initial begin
        repeat (4) @(negedge clk);
        rst_n = 1;
        repeat (2) @(negedge clk);
        // SPIKE type=1, mask 0b0010 (core 1), body 0xBEEF
        in_e_data  = (32'h1 << 28) | (4'b0010 << 20) | 32'hBEEF;
        in_e_valid = 1;
        @(negedge clk);
        in_e_valid = 0;
        for (t = 0; t < 40; t = t + 1) begin
            @(posedge clk);
            #1;
            if (out_e_valid) begin
                east_count = east_count + 1;
                if (out_e_data !== in_e_data) bad_payload = 1;
            end
            if (out_pe_valid || out_n_valid) illegal_count = illegal_count + 1;
        end
        if (east_count != 1 || illegal_count != 0 || bad_payload) begin
            $display("ROUTER-PROBE-FAIL east=%0d illegal=%0d bad=%0d",
                     east_count, illegal_count, bad_payload);
            $finish_and_return(1);
        end
        $display("ROUTER-PROBE-PASS east=1 exact-payload");
        $finish;
    end
endmodule
`default_nettype wire
