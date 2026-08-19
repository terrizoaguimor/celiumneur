// hypha_config_endpoint.v — ordered CONFIG packet assembler for one tile.
// SPDX-License-Identifier: Apache-2.0
//
// A 64-bit write is five routed single-flit packets with the same destination
// mask. The mesh preserves order along a path, and every destination owns an
// independent endpoint, so the same transaction may be multicast atomically:
//
//   header: kind=0 | space[1:0] | address[7:0] | reserved[6:0]=0
//   data  : kind=1..4 | data16 | reserved[0]=0
//
// The final fragment raises cfg_en and holds the complete write stable until
// the selected tile space accepts it. Malformed or out-of-order packets set a
// sticky witness and never mutate configuration state.

`default_nettype none

module hypha_config_endpoint (
    input  wire        clk,
    input  wire        rst_n,

    input  wire        pkt_valid,
    input  wire [19:0] pkt_body,
    output wire        pkt_ready,

    output wire        cfg_en,
    output wire [1:0]  cfg_space,
    output wire [7:0]  cfg_addr,
    output wire [63:0] cfg_data,
    input  wire        cfg_ready,

    output reg         protocol_error_wit
);

    reg        transaction_active;
    reg [2:0]  expected_kind;
    reg [1:0]  cfg_space_r;
    reg [7:0]  cfg_addr_r;
    reg [63:0] cfg_data_r;
    reg        commit_pending;

    wire [2:0] packet_kind = pkt_body[19:17];
    wire [1:0] header_space = pkt_body[16:15];
    wire [7:0] header_addr = pkt_body[14:7];

    assign pkt_ready = !commit_pending;
    assign cfg_en = commit_pending;
    assign cfg_space = cfg_space_r;
    assign cfg_addr = cfg_addr_r;
    assign cfg_data = cfg_data_r;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            transaction_active <= 1'b0;
            expected_kind       <= 3'd0;
            cfg_space_r         <= 2'd0;
            cfg_addr_r          <= 8'd0;
            cfg_data_r          <= 64'd0;
            commit_pending      <= 1'b0;
            protocol_error_wit  <= 1'b0;
        end else begin
            if (commit_pending && cfg_ready)
                commit_pending <= 1'b0;

            if (pkt_valid && pkt_ready) begin
                if (packet_kind == 3'd0) begin
                    if (transaction_active || pkt_body[6:0] != 7'd0
                            || header_space == 2'd3) begin
                        protocol_error_wit <= 1'b1;
                        transaction_active <= 1'b0;
                        expected_kind <= 3'd0;
                    end else begin
                        transaction_active <= 1'b1;
                        expected_kind <= 3'd1;
                        cfg_space_r <= header_space;
                        cfg_addr_r <= header_addr;
                        cfg_data_r <= 64'd0;
                    end
                end else if (!transaction_active
                             || packet_kind != expected_kind
                             || pkt_body[0] != 1'b0) begin
                    protocol_error_wit <= 1'b1;
                    transaction_active <= 1'b0;
                    expected_kind <= 3'd0;
                end else begin
                    case (packet_kind)
                        3'd1: cfg_data_r[15:0]  <= pkt_body[16:1];
                        3'd2: cfg_data_r[31:16] <= pkt_body[16:1];
                        3'd3: cfg_data_r[47:32] <= pkt_body[16:1];
                        3'd4: cfg_data_r[63:48] <= pkt_body[16:1];
                        default: ;
                    endcase
                    if (packet_kind == 3'd4) begin
                        transaction_active <= 1'b0;
                        expected_kind <= 3'd0;
                        commit_pending <= 1'b1;
                    end else begin
                        expected_kind <= expected_kind + 3'd1;
                    end
                end
            end
        end
    end

endmodule

`default_nettype wire
