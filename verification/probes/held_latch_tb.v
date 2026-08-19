// held_latch_tb.v — packet-assembly regression: one stim -> one fire -> one
// SPDX-License-Identifier: Apache-2.0
// well-formed egress packet (christened after the concat-width scar hunt).
`timescale 1ns/1ps
`default_nettype none

module held_latch_tb;
    reg clk = 0, rst_n = 0;
    always #5 clk = ~clk;

    reg        tick = 0;
    reg        integrate_open = 0;
    reg        stim_valid = 0;
    reg  [7:0] stim_neuron = 0, stim_weight = 0;
    reg        cfg_en = 0;
    reg  [3:0] cfg_addr = 0;
    reg  [26:0] cfg_wdata = 0;
    reg        cfg_soma_en = 0;
    reg  [7:0] cfg_soma_addr = 0;
    reg  [63:0] cfg_soma_wdata = 0;

    neuro_tile #(.GID_BASE(0), .DEFAULT_AXON_MASK(4'h4)) dut (
        .clk(clk), .rst_n(rst_n),
        .spk_valid(1'b0), .spk_gid(10'd0), .spk_parity(1'b0), .spk_ready(),
        .dend_busy(),
        .integrate_open(integrate_open),
        .stim_valid(stim_valid), .stim_neuron(stim_neuron), .stim_weight(stim_weight),
        .stim_ready(), .tick(tick), .tick_ready(),
        .cfg_en(cfg_en), .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata),
        .cfg_ready(),
        .cfg_soma_en(cfg_soma_en), .cfg_soma_addr(cfg_soma_addr),
        .cfg_soma_wdata(cfg_soma_wdata), .cfg_soma_ready(),
        .cfg_axon_en(1'b0), .cfg_axon_addr(2'd0),
        .cfg_axon_wdata(4'd0), .cfg_axon_ready(),
        .rb_dend_addr(4'd0), .rb_dend_rdata(),
        .rb_soma_addr(8'd0), .rb_soma_req(1'b0), .rb_soma_data(),
        .rb_soma_ready(), .rb_soma_valid(),
        .out_spk_valid(), .out_spk_pkt(), .out_spk_ready(1'b1),
        .out_stall_wit(), .fire_overflow_wit(), .tile_busy()
    );

    // program neuron 0: theta=10, leak=0, refr=0
    task cfg_soma(input [7:0] neuron, input [63:0] word);
        begin
            @(negedge clk);
            cfg_soma_addr = neuron;
            cfg_soma_wdata = word;
            cfg_soma_en = 1;
            @(posedge clk); @(negedge clk); cfg_soma_en = 0;
            @(negedge clk);
        end
    endtask

    task stim(input [7:0] w);
        begin
            @(negedge clk);
            stim_neuron = 8'd0; stim_weight = w;
            stim_valid = 1;
            @(posedge clk); @(negedge clk); stim_valid = 0;
            @(negedge clk);
        end
    endtask

    // the court-tester check written after the concat-width scar: one fire
    // must produce exactly one egress packet with header nibble 1, route
    // mask 4, gid 0. A silent width inflation truncates the mask to zero.
    integer outs = 0;
    reg     bad  = 0;

    initial begin
        repeat (4) @(negedge clk);
        rst_n = 1'b1;
        repeat (20) @(negedge clk);   // wipe sweep
        cfg_soma(8'd0, {16'd10, 1'b1, 4'd15, 8'd0, 8'd0,
                        8'd0, 3'b0, 16'd0});
        stim(8'd60);
        repeat (40) @(negedge clk);
        if (outs == 1 && !bad) begin
            $display("HELD-LATCH-PASS pkt well-formed");
            $finish;
        end
        // $fatal rc is 0 with this vvp build; use finish_and_return(1).
        $display("HELD-LATCH BAD: outs=%0d", outs);
        $finish_and_return(1);
    end

    always @(negedge clk) begin
        if (dut.out_spk_valid) begin
            outs = outs + 1;
            if (dut.out_spk_pkt[31:28] !== 4'h1 ||
                dut.out_spk_pkt[23:20] !== 4'h4 ||
                dut.out_spk_pkt[9:0]   !== 10'd0) begin
                bad = 1;
                $display("BAD pkt=%h (want hdr=1 mask=4 gid=0)", dut.out_spk_pkt);
            end
        end
    end
endmodule

`default_nettype wire
