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

    neuro_tile #(.GID_BASE(0), .NEURONS(4), .ID_BITS(2)) dut (
        .clk(clk), .rst_n(rst_n),
        .spk_valid(1'b0), .spk_gid(10'b0), .spk_parity(1'b1),
        .spk_ready(), .spk_overflow_wit(),
        .stim_valid(stim_valid), .stim_neuron(stim_neuron),
        .stim_weight(stim_weight),
        .tick(1'b0), .integrate_open(1'b1),
        .cfg_en(1'b0), .cfg_addr(5'd0), .cfg_wdata(21'd0),
        .rb_dend_addr(5'd0), .rb_dend_rdata(),
        .rb_soma_addr(8'd0), .rb_soma_req(1'b0),
        .rb_soma_data(), .rb_soma_ready(),
        .axon_masks(16'hffff),
        .out_spk_valid(), .out_spk_pkt(), .out_spk_ready(1'b1),
        .out_stall_wit(),
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
        repeat (2) @(negedge clk);
        dut.soma.nram[0] = { 16'd10, 1'b1, 4'd15, 8'd0, 8'd0, 3'b0, 16'd0 };
        dut.soma.nram[1] = { 16'd10, 1'b1, 4'd15, 8'd0, 8'd0, 3'b0, 16'd0 };
        dut.soma.nram[2] = { 16'd10, 1'b1, 4'd15, 8'd0, 8'd0, 3'b0, 16'd0 };
        dut.soma.nram[3] = { 16'd10, 1'b1, 4'd15, 8'd0, 8'd0, 3'b0, 16'd0 };
        drive(3'd0, 8'd60);
        drive(3'd1, 8'd60);
        drive(3'd2, 8'd60);
        repeat (300) @(negedge clk);
        $display("diag done: fireq_empty=%b outq_empty=%b",
                 dut.fireq_empty, dut.outq_empty);
        $finish;
    end

    always @(negedge clk) begin
        $display("[%0t] tick yawn state=%0d spkQ=%0d fireq=%0d outq=%0d firev=%0d firn=%0d outv=%0d g=%0d",
                 $time, dut.dendrite.state, !dut.inq_empty, !dut.fireq_empty,
                 !dut.outq_empty, dut.soma_fire_valid, dut.soma_fire_neuron,
                 dut.out_spk_valid, dut.out_spk_pkt[9:0]);
    end
endmodule

`default_nettype wire
