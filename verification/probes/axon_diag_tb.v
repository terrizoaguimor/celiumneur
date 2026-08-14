// axon_diag_tb.v — pure-vvp diagnosis replica of the cocotb axon case.
// SPDX-License-Identifier: AGPL-3.0-or-later
`timescale 1ns/1ps
`default_nettype none
module axon_diag_tb;
    reg clk = 0, rst_n = 0;
    always #5 clk = ~clk;

    reg        stim_valid = 0;
    reg  [7:0] stim_neuron = 0;
    reg  [7:0] stim_weight = 0;
    integer packets [0:3];
    integer pi;

    initial for (pi = 0; pi < 4; pi = pi + 1) packets[pi] = 0;

    neuro_tile #(.GID_BASE(0), .NEURONS(4), .ID_BITS(2),
                 .DEFAULT_AXON_MASK(4'hf)) dut (
        .clk(clk), .rst_n(rst_n),
        .spk_valid(1'b0), .spk_gid(10'b0), .spk_parity(1'b1),
        .spk_ready(), .spk_overflow_wit(),
        .stim_valid(stim_valid), .stim_neuron(stim_neuron),
        .stim_weight(stim_weight), .stim_ready(),
        .tick(1'b0), .tick_ready(), .integrate_open(1'b1),
        .cfg_en(1'b0), .cfg_addr(4'd0), .cfg_wdata(27'd0), .cfg_ready(),
        .cfg_soma_en(1'b0), .cfg_soma_addr(8'd0),
        .cfg_soma_wdata(64'd0), .cfg_soma_ready(),
        .cfg_axon_en(1'b0), .cfg_axon_addr(2'd0),
        .cfg_axon_wdata(4'd0), .cfg_axon_ready(),
        .rb_dend_addr(4'd0), .rb_dend_rdata(),
        .rb_soma_addr(8'd0), .rb_soma_req(1'b0),
        .rb_soma_data(), .rb_soma_ready(), .rb_soma_valid(),
        .out_spk_valid(), .out_spk_pkt(), .out_spk_ready(1'b1),
        .out_stall_wit(), .fire_overflow_wit(),
        .dend_busy(), .tile_busy()
    );

    task drive(input [2:0] n, input [7:0] w);
        begin
            @(negedge clk); stim_neuron = {5'b0, n}; stim_weight = w; stim_valid = 1'b1;
            @(posedge clk); @(negedge clk); stim_valid = 1'b0;
            @(negedge clk);
        end
    endtask

    initial begin
        repeat (4) @(negedge clk);
        rst_n = 1'b1;
        wait (dut.soma.sweep_active == 1'b0);
        repeat (2) @(negedge clk);
        dut.soma.nram[0] = {16'd10, 1'b1, 4'd15, 8'd0, 8'd0,
                            8'd0, 3'b0, 16'd0};
        dut.soma.nram[1] = {16'd10, 1'b1, 4'd15, 8'd0, 8'd0,
                            8'd0, 3'b0, 16'd0};
        dut.soma.nram[2] = {16'd10, 1'b1, 4'd15, 8'd0, 8'd0,
                            8'd0, 3'b0, 16'd0};
        dut.soma.nram[3] = {16'd10, 1'b1, 4'd15, 8'd0, 8'd0,
                            8'd0, 3'b0, 16'd0};
        drive(3'd0, 8'd60);
        drive(3'd1, 8'd60);
        drive(3'd2, 8'd60);
        repeat (300) @(negedge clk);
        if (packets[0] != 1 || packets[1] != 1 || packets[2] != 1
                || packets[3] != 0 || !dut.fireq_empty || !dut.outq_empty) begin
            $display("AXON-DIAG-FAIL packets=%0d,%0d,%0d,%0d",
                     packets[0], packets[1], packets[2], packets[3]);
            $finish_and_return(1);
        end
        $display("AXON-DIAG-PASS packets=0,1,2 exact");
        $finish;
    end

    always @(negedge clk) begin
        if (dut.out_spk_valid)
            packets[dut.out_spk_pkt[1:0]] = packets[dut.out_spk_pkt[1:0]] + 1;
    end
endmodule

`default_nettype wire
