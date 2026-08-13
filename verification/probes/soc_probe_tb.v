// soc_probe_tb.v — vvp probe of the whole SoC v1 demo scenario in one place.
// SPDX-License-Identifier: AGPL-3.0-or-later
// This is the reviewer's instrument: no cocotb environment between us and
// the fabric. If this writes the golden fire multiset, the chain is VIVA.
`timescale 1ns/1ps
`default_nettype none

module soc_probe_tb;
    reg clk = 0, rst_n = 0;
    always #5 clk = ~clk;

    reg        tick = 0;
    reg        integrate_open = 0;
    reg  [1:0] stim_tile = 0;
    reg        stim_valid = 0;
    reg  [7:0] stim_neuron = 0;
    reg  [7:0] stim_weight = 0;
    reg  [1:0] cfg_tile = 0;
    reg        cfg_en = 0;
    reg  [4:0] cfg_addr = 0;
    reg  [20:0] cfg_wdata = 0;
    reg        cfg_which = 0;
    reg  [63:0] cfg_soma_data = 0;
    reg  [1:0] rb_tile = 0;
    reg  [4:0] rb_addr = 0;
    reg        rb_req = 0;

    celiumneur_soc dut (
        .clk(clk), .rst_n(rst_n), .tick(tick), .integrate_open(integrate_open),
        .stim_tile(stim_tile), .stim_valid(stim_valid),
        .stim_neuron(stim_neuron), .stim_weight(stim_weight),
        .cfg_tile(cfg_tile), .cfg_en(cfg_en), .cfg_addr(cfg_addr),
        .cfg_wdata(cfg_wdata),
        .cfg_which(cfg_which), .cfg_soma_data(cfg_soma_data),
        .rb_tile(rb_tile), .rb_addr(rb_addr), .rb_req(rb_req),
        .rb_dend_rdata(), .rb_soma_data(),
        .mesh_overflow_any()
    );

    integer fire_count [0:15];
    integer t;

    initial for (t = 0; t < 16; t = t + 1) fire_count[t] = 0;

    // cfg helper: write a dendrite entry into a tile
    task cfg_entry(input [1:0] tile_sel, input [4:0] addr,
                   input [9:0] pre_gid, input [1:0] post, input [7:0] w);
        begin
            cfg_tile = tile_sel;
            cfg_addr = addr;
            cfg_wdata = (1'b1 << 20) | (pre_gid << 10) | (post << 8) | w;
            cfg_which = 0;                 // lane: dendrite table
            cfg_en = 1;
            @(posedge clk); @(negedge clk); cfg_en = 0;
            @(negedge clk);
        end
    endtask

    // cfg helper: write neuron params into a tile's soma word
    task cfg_soma(input [1:0] tile_sel, input neuron, input [63:0] word);
        begin
            cfg_tile = tile_sel;
            cfg_which = 1;                 // lane: soma autonomous word
            cfg_soma_data = word;
            cfg_addr = neuron;
            cfg_en = 1;
            @(posedge clk); @(negedge clk); cfg_en = 0;
            @(negedge clk);
        end
    endtask

    // bench tick then integration window
    task phase(input integer open_cycles);
        begin
            @(posedge clk); tick = 1;
            @(negedge clk); tick = 0;
            integrate_open = 1;
            repeat (open_cycles) @(negedge clk);
            integrate_open = 0;
        end
    endtask

    task stim(input [1:0] tile_sel, input [7:0] w);
        begin
            stim_tile = tile_sel;
            stim_neuron = 8'd0;
            stim_weight = w;
            @(posedge clk); stim_valid = 1;
            @(negedge clk); stim_valid = 0;
        end
    endtask

    initial begin
        repeat (4) @(negedge clk);
        rst_n = 1'b1;

        // wait for the post-reset wipe sweep to complete on tile0 as proxy
        repeat (10) @(negedge clk);

        // ---- program tile 0/1 electrodes: neuron 0: theta=100 ----
        cfg_soma(2'd0, 8'd0, {16'd100, 1'b1, 4'd15, 8'd0, 8'd0, 3'b0, 16'd0});
        cfg_soma(2'd1, 8'd0, {16'd100, 1'b1, 4'd15, 8'd0, 8'd0, 3'b0, 16'd0});
        // detector tile2: theta=200 (fires on pair only)
        cfg_soma(2'd2, 8'd0, {16'd200, 1'b1, 4'd15, 8'd0, 8'd0, 3'b0, 16'd0});
        // output tile3: theta=100, refractory 4
        cfg_soma(2'd3, 8'd0, {16'd100, 1'b1, 4'd15, 8'd4, 8'd0, 3'b0, 16'd0});

        // ---- dendrite tables: gid0/4 -> tile2 | gid8 -> tile3 ----
        cfg_entry(2'd2, 5'd0, 10'd0, 2'd0, 8'd120);   // gid0 -> post0
        cfg_entry(2'd2, 5'd1, 10'd4, 2'd0, 8'd120);   // gid4 -> post0
        cfg_entry(2'd3, 5'd0, 10'd8, 2'd0, 8'd120);   // gid8 -> post0

        // ---- the demo: same phases as demo_net.run_demo_script ----
        stim(2'd0, 8'd120); phase(60);
        phase(60);
        stim(2'd1, 8'd120); phase(60);
        phase(60);
        stim(2'd0, 8'd120); stim(2'd1, 8'd120); phase(60);  // pair
        phase(60);
        stim(2'd0, 8'd120); stim(2'd1, 8'd120); phase(60);  // re-pair
        phase(60);
        repeat (10) phase(60);                             // settle

        $display("SOC-PROBE firecounts: n0=%0d n4=%0d n8=%0d n12=%0d",
                 fire_count[0], fire_count[4], fire_count[8], fire_count[12]);
        $finish;
    end

    // catch every fire packet on the fabric egress plane
    always @(negedge clk) begin
        for (t = 0; t < 4; t = t + 1)
            if (dut.pe_out_valid[t]) begin
                fire_count[((dut.pe_out_data >> (t*32)) & 10'h3FF)] =
                    fire_count[((dut.pe_out_data >> (t*32)) & 10'h3FF)] + 1;
            end
        // physical truth at tile level first
        if (dut.t0.soma.fire_valid) begin
            $display("[t=%0t] tile0 fires n=%0d (state=%0d busy=%0d)",
                     $time, dut.t0.soma.fire_neuron, dut.t0.soma.state,
                     dut.t0.tile_busy);
        end
        if (dut.t1.soma.fire_valid) begin
            $display("[t=%0t] tile1 fires n=%0d (state=%0d)",
                     $time, dut.t1.soma.fire_neuron, dut.t1.soma.state);
        end
        if (dut.t0.out_spk_valid)
            $display("[t=%0t] t0 out pkt mask=%b gid=%0d axon_masks=%h",
                     $time, dut.t0.out_spk_pkt[23:20], dut.t0.out_spk_pkt[9:0],
                     dut.t0.axon_masks);
        if (dut.t0.soma.fire_valid)
            $display("[t=%0t] t0 FIRE n=%0d", $time, dut.t0.soma.fire_neuron);
        if (dut.t0.fire_taken)
            $display("[t=%0t] t0 TAKE pkt=%h", $time, dut.t0.pktq_dout);
        if (dut.t2.out_spk_valid)
            $display("[t=%0t] t2 out pkt mask=%b gid=%0d",
                     $time, dut.t2.out_spk_pkt[23:20], dut.t2.out_spk_pkt[9:0]);
    end
endmodule

`default_nettype wire
