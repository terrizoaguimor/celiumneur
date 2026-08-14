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
    integer events = 0;
    integer fires = 0;
    integer packets = 0;

    reg        cfg_en = 0;
    reg  [3:0] cfg_addr = 0;
    reg  [26:0] cfg_wdata = 0;

    neuro_tile #(.GID_BASE(0), .NEURONS(4), .ID_BITS(2),
                 .DEFAULT_AXON_MASK(4'hf)) dut (
        .clk(clk), .rst_n(rst_n),
        .spk_valid(spk_valid), .spk_gid(spk_gid), .spk_parity(spk_parity),
        .spk_ready(), .spk_overflow_wit(),
        .stim_valid(1'b0), .stim_neuron(8'd0), .stim_weight(8'd0), .stim_ready(),
        .tick(1'b0), .tick_ready(), .integrate_open(1'b1),
        .cfg_en(cfg_en), .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata),
        .cfg_ready(),
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
    initial begin
        repeat (4) @(negedge clk);
        rst_n = 1'b1;
        repeat (3) @(negedge clk);

        // neuron 0: theta=200, subtractive, leak=15, refractory=0
        dut.soma.nram[0] = {16'd200, 1'b1, 4'd15, 8'd0, 8'd0,
                            8'd0, 3'b0, 16'd0};
        // entry 0: gid1 -> post0, w=150
        cfg_addr = 4'd0;
        cfg_wdata = (1'b1 << 26) | (10'd1 << 16) | (8'd0 << 8) | 8'd120;
        cfg_en = 1'b1;
        @(posedge clk); @(negedge clk); cfg_en = 1'b0;

        // two arrivals
        @(negedge clk); spk_valid = 1'b1; spk_gid = 10'd1;
        @(posedge clk); @(negedge clk); spk_valid = 1'b0;
        repeat (120) @(negedge clk);

        @(negedge clk); spk_valid = 1'b1; spk_gid = 10'd1;
        @(posedge clk); @(negedge clk); spk_valid = 1'b0;
        repeat (120) @(negedge clk);

        if (events != 2 || fires != 1 || packets != 1
                || dut.soma.nram[0][15:0] != 16'd40) begin
            $display("DUAL-PROBE-FAIL events=%0d fires=%0d packets=%0d v=%0d",
                     events, fires, packets, dut.soma.nram[0][15:0]);
            $finish_and_return(1);
        end
        $display("DUAL-PROBE-PASS events=2 fires=1 packets=1 v=40");
        $finish;
    end

    always @(negedge clk) begin
        if (dut.soma.fire_valid && dut.soma.fire_ready) fires = fires + 1;
        if (dut.dendrite.ev_valid && dut.ev_ready) events = events + 1;
        if (dut.out_spk_valid) packets = packets + 1;
    end
endmodule

`default_nettype wire
