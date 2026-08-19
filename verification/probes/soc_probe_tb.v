// soc_probe_tb.v — raw-vvp proof of packet config, multicast and GID 1023.
// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
`default_nettype none

module soc_probe_tb;
    reg clk = 0, rst_n = 0;
    always #5 clk = ~clk;

    reg tick = 0;
    reg host_valid = 0;
    reg [31:0] host_packet = 0;
    wire host_ready;
    reg [1:0] stim_tile = 0;
    reg stim_valid = 0;
    reg [7:0] stim_neuron = 0;
    reg [7:0] stim_weight = 0;
    wire stim_ready;
    wire [3:0] config_protocol_error;
    wire [3:0] mesh_overflow_any;

    celiumneur_soc dut (
        .clk(clk), .rst_n(rst_n),
        .tick(tick), .tick_ready(), .tick_backpressure(),
        .tick_overflow_wit(),
        .host_valid(host_valid), .host_packet(host_packet),
        .host_ready(host_ready),
        .integrate_open(1'b1),
        .stim_tile(stim_tile), .stim_valid(stim_valid),
        .stim_neuron(stim_neuron), .stim_weight(stim_weight),
        .stim_ready(stim_ready),
        .rb_tile(2'd0), .rb_addr(8'd0), .rb_req(1'b0),
        .rb_dend_rdata(), .rb_soma_data(), .rb_ready(), .rb_valid(),
        .mesh_overflow_any(mesh_overflow_any), .tile_overflow_any(),
        .tile_backpressure(), .tile_busy(), .tile_dend_busy(),
        .spike_backpressure_count(),
        .config_protocol_error(config_protocol_error),
        .unsupported_packet_wit()
    );

    task send_packet;
        input [31:0] packet;
        begin
            @(negedge clk);
            host_packet = packet;
            host_valid = 1'b1;
            while (!host_ready) @(negedge clk);
            @(posedge clk);
            @(negedge clk);
            host_valid = 1'b0;
        end
    endtask

    integer fragment;
    reg [19:0] body;
    task config_write;
        input [3:0] mask;
        input [1:0] space;
        input [7:0] addr;
        input [63:0] data;
        begin
            body = {3'd0, space, addr, 7'd0};
            send_packet({4'h2, 4'd0, mask, body});
            for (fragment = 0; fragment < 4; fragment = fragment + 1) begin
                body = 20'd0;
                body[19:17] = fragment + 1;
                body[16:1] = data[fragment*16 +: 16];
                send_packet({4'h2, 4'd0, mask, body});
            end
        end
    endtask

    integer timeout;
    integer packet_count = 0;
    reg [9:0] observed_gid = 0;
    reg [3:0] observed_mask = 0;
    reg [63:0] multicast_word;

    initial begin
        repeat (4) @(negedge clk);
        rst_n = 1'b1;
        timeout = 0;
        while ((dut.t0.tile_busy || dut.t1.tile_busy
                || dut.t2.tile_busy || dut.t3.tile_busy) && timeout < 400) begin
            timeout = timeout + 1;
            @(negedge clk);
        end
        if (timeout == 400) begin
            $display("SOC-PROBE-FAIL reset sweep timeout");
            $finish_and_return(1);
        end

        // A single branch-replicated transaction writes the same state word
        // into local neuron 200 on all four physical tiles.
        multicast_word = {16'd1234, 1'b0, 4'd7, 8'd9, 8'd0,
                          8'd0, 3'b0, 16'hfebf};
        config_write(4'hf, 2'd1, 8'd200, multicast_word);
        timeout = 0;
        while ((dut.t0.soma.nram[200] !== multicast_word
                || dut.t1.soma.nram[200] !== multicast_word
                || dut.t2.soma.nram[200] !== multicast_word
                || dut.t3.soma.nram[200] !== multicast_word)
               && timeout < 1000) begin
            timeout = timeout + 1;
            @(negedge clk);
        end

        // Program the last neuron and its per-neuron axon route by packets.
        config_write(4'h8, 2'd1, 8'd255,
                     {16'd10, 1'b1, 4'd15, 8'd0, 8'd0,
                      8'd0, 3'b0, 16'd0});
        config_write(4'h8, 2'd2, 8'd255, 64'h1);
        timeout = 0;
        while (dut.t3.axon_table[255] !== 4'h1 && timeout < 1000) begin
            timeout = timeout + 1;
            @(negedge clk);
        end

        @(negedge clk);
        stim_tile = 2'd3;
        stim_neuron = 8'd255;
        stim_weight = 8'd60;
        stim_valid = 1'b1;
        while (!stim_ready) @(negedge clk);
        @(posedge clk);
        @(negedge clk);
        stim_valid = 1'b0;

        repeat (600) @(negedge clk);
        if (timeout == 1000 || packet_count != 1 || observed_gid != 10'd1023
                || observed_mask != 4'h1
                || config_protocol_error != 4'd0
                || mesh_overflow_any != 4'd0) begin
            $display("SOC-PROBE-FAIL multicast_timeout=%0d packets=%0d gid=%0d mask=%b cfgerr=%b mesh=%b",
                     timeout == 1000, packet_count, observed_gid, observed_mask,
                     config_protocol_error, mesh_overflow_any);
            $finish_and_return(1);
        end
        $display("SOC-PROBE-PASS multicast=4 gid=1023 packets=1");
        $finish;
    end

    always @(negedge clk) begin
        if (dut.t3.out_spk_valid) begin
            packet_count = packet_count + 1;
            observed_gid = dut.t3.out_spk_pkt[9:0];
            observed_mask = dut.t3.out_spk_pkt[23:20];
        end
    end
endmodule

`default_nettype wire
