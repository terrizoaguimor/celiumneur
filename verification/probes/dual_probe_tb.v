// dual_probe_tb.v — the smallest reproducer of "deliveries happen, no fire".
// SPDX-License-Identifier: AGPL-3.0-or-later
// One synapse: gid1 -> post0, weight 150. Two arrivals. Post must fire.
`timescale 1ns/1ps
`default_nettype none

module dual_probe_tb;
    reg clk = 0, rst_n = 0;
    always #50 clk = ~clk;

    reg        spk_valid = 0;
    reg  [9:0] spk_gid = 0;
    reg        spk_parity = 1;

    reg        cfg_en = 0;
    reg  [4:0] cfg_addr = 0;
    reg  [20:0] cfg_wdata = 0;

    neuro_tile #(.GID_BASE(0), .NEURONS(4), .ID_BITS(2)) dut (
        .clk(clk), .rst_n(rst_n),
        .spk_valid(spk_valid), .spk_gid(spk_gid), .spk_parity(spk_parity),
        .spk_ready(), .spk_overflow_wit(),
        .stim_valid(1'b0), .stim_neuron(8'd0), .stim_weight(8'd0),
        .tick(1'b0), .integrate_open(1'b1),
        .cfg_en(cfg_en), .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata),
        .rb_dend_addr(5'd0), .rb_dend_rdata(),
        .rb_soma_addr(8'd0), .rb_soma_req(1'b0),
        .rb_soma_data(), .rb_soma_ready(),
        .axon_masks(16'hffff),
        .out_spk_valid(), .out_spk_pkt(), .out_spk_ready(1'b1),
        .out_stall_wit(),
        .dend_busy(), .tile_busy()
    );
    initial begin
        repeat (4) @(negedge clk);
        rst_n = 1'b1;
        repeat (3) @(negedge clk);

        // neuron 0: theta=200, subtractive, leak=15, refractory=0
        dut.soma.nram[0] = { 16'd200, 1'b1, 4'd15, 8'd0, 8'd0, 3'b0, 16'd0 };
        // entry 0: gid1 -> post0, w=150
        cfg_addr = 5'd0;
        cfg_wdata = (1'b1 << 20) | (10'd1 << 10) | (2'd0 << 8) | 8'd120;
        cfg_en = 1'b1;
        @(posedge clk); @(negedge clk); cfg_en = 1'b0;

        // two arrivals
        @(negedge clk); spk_valid = 1'b1; spk_gid = 10'd1;
        @(posedge clk); @(negedge clk); spk_valid = 1'b0;
        repeat (120) @(negedge clk);

        @(negedge clk); spk_valid = 1'b1; spk_gid = 10'd1;
        @(posedge clk); @(negedge clk); spk_valid = 1'b0;
        repeat (120) @(negedge clk);

        $display("PROBE v0_word=%h", dut.soma.nram[0]);
        $finish;
    end

    always @(negedge clk) begin
        if (dut.soma.fire_valid)
            $display("FIRE t=%0t neuron=%0d", $time, dut.soma.fire_neuron);
        if (dut.dendrite.ev_valid)
            $display("EV t=%0t neuron=%0d w=%0d", $time,
                     dut.dendrite.ev_neuron, $signed(dut.dendrite.ev_weight));
    end
endmodule

`default_nettype wire
