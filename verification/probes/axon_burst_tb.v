// axon_burst_tb.v — three rapid electrode stimuli; three axon packets out.
// SPDX-License-Identifier: AGPL-3.0-or-later
`timescale 1ns/1ps
`default_nettype none
module axon_burst_tb;
    reg clk = 0, rst_n = 0;
    always #5 clk = ~clk;

    reg        cfg_en = 0;
    reg  [4:0] cfg_addr = 0;
    reg  [20:0] cfg_wdata = 0;
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
        .cfg_en(cfg_en), .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata),
        .rb_dend_addr(5'd0), .rb_dend_rdata(),
        .rb_soma_addr(8'd0), .rb_soma_req(1'b0),
        .rb_soma_data(), .rb_soma_ready(),
        .axon_masks(16'hffff),
        .out_spk_valid(), .out_spk_pkt(), .out_spk_ready(1'b1),
        .out_stall_wit(),
        .dend_busy(), .tile_busy()
    );

    // neuron n: theta=10, subtractive
    task stim(input [2:0] n, input [7:0] w);
        begin
            @(negedge clk); stim_neuron = {5'b0, n}; stim_weight = w;
            stim_valid = 1'b1;
            @(posedge clk); @(negedge clk); stim_valid = 1'b0;
            @(negedge clk);
        end
    endtask

    integer fires [0:3];
    integer outs  [0:3];
    integer fi;
    initial for (fi = 0; fi < 4; fi = fi + 1) begin
        fires[fi] = 0; outs[fi] = 0;
    end

    initial begin
        repeat (4) @(negedge clk);
        rst_n = 1'b1;
        // sweep-then-program ORDER: S_INIT wipes nram[0..3] one entry per
        // cycle after reset; poking before it ends is silently overwritten
        // (the "only n=1 fires" scar). Wait for the sweep to finish.
        wait (dut.soma.sweep_active == 1'b0);
        repeat (4) @(negedge clk);
        dut.soma.nram[0] = { 16'd10, 1'b1, 4'd15, 8'd0, 8'd0, 3'b0, 16'd0 };
        dut.soma.nram[1] = { 16'd10, 1'b1, 4'd15, 8'd0, 8'd0, 3'b0, 16'd0 };
        dut.soma.nram[2] = { 16'd10, 1'b1, 4'd15, 8'd0, 8'd0, 3'b0, 16'd0 };
        dut.soma.nram[3] = { 16'd10, 1'b1, 4'd15, 8'd0, 8'd0, 3'b0, 16'd0 };

        // a soma event costs ~3 fabric cycles (S_IDLE->EV_RD->EV_AP); a
        // strobe arriving mid-event is silently dropped. Space the burst.
        stim(3'd0, 8'd60); repeat (2) @(negedge clk);
        stim(3'd1, 8'd60); repeat (2) @(negedge clk);
        stim(3'd2, 8'd60);
        repeat (400) @(negedge clk);
        if (fires[0] == 1 && fires[1] == 1 && fires[2] == 1 &&
            outs[0] == 1 && outs[1] == 1 && outs[2] == 1)
            $display("AXON-PROBE-END fires+packets complete");
        else
            $display("AXON-PROBE incomplete: fires=%0d,%0d,%0d outs=%0d,%0d,%0d",
                     fires[0], fires[1], fires[2], outs[0], outs[1], outs[2]);
        // $fatal rc is 0 with this vvp build; use finish_and_return(1) so the
        // runner sees the regression.
        if (!(fires[0] == 1 && fires[1] == 1 && fires[2] == 1 &&
              outs[0] == 1 && outs[1] == 1 && outs[2] == 1))
            $finish_and_return(1);
        $finish;
    end

    always @(negedge clk) begin
        if (dut.soma.fire_valid) begin
            fires[dut.soma.fire_neuron[1:0]] = fires[dut.soma.fire_neuron[1:0]] + 1;
            $display("[t=%0t] soma fire n=%0d", $time, dut.soma.fire_neuron);
        end
        if (dut.out_spk_valid) begin
            outs[dut.out_spk_pkt[9:0]] = outs[dut.out_spk_pkt[9:0]] + 1;
            $display("[t=%0t] out pkt gid=%0d", $time, dut.out_spk_pkt[9:0]);
        end
    end
endmodule

`default_nettype wire
