# SPDX-License-Identifier: AGPL-3.0-or-later
"""Protocol tests for the routed Hyphae configuration assembler."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge


def bodies(space: int, addr: int, data: int) -> list[int]:
    result = [((space & 0x3) << 15) | ((addr & 0xFF) << 7)]
    result.extend(
        ((fragment + 1) << 17)
        | (((data >> (16 * fragment)) & 0xFFFF) << 1)
        for fragment in range(4)
    )
    return result


async def reset(dut) -> None:
    dut.rst_n.value = 0
    dut.pkt_valid.value = 0
    dut.pkt_body.value = 0
    dut.cfg_ready.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


async def send_body(dut, body: int) -> None:
    dut.pkt_body.value = body
    dut.pkt_valid.value = 1
    while not int(dut.pkt_ready.value):
        await FallingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.pkt_valid.value = 0


@cocotb.test()
async def ordered_transaction_holds_complete_commit_until_ready(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    expected = 0xFEDCBA9876543210
    for body in bodies(space=1, addr=203, data=expected):
        await send_body(dut, body)

    assert int(dut.cfg_en.value) == 1
    assert int(dut.pkt_ready.value) == 0
    assert int(dut.cfg_space.value) == 1
    assert int(dut.cfg_addr.value) == 203
    assert int(dut.cfg_data.value) == expected

    for _ in range(12):
        await FallingEdge(dut.clk)
        assert int(dut.cfg_en.value) == 1
        assert int(dut.cfg_data.value) == expected

    dut.cfg_ready.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    assert int(dut.cfg_en.value) == 0
    assert int(dut.protocol_error_wit.value) == 0


@cocotb.test()
async def malformed_sequence_is_rejected_without_a_write(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    # A data fragment without a header may not create a configuration commit.
    await send_body(dut, (2 << 17) | (0x1234 << 1))
    assert int(dut.protocol_error_wit.value) == 1
    assert int(dut.cfg_en.value) == 0


@cocotb.test()
async def out_of_order_fragment_cannot_commit(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    await send_body(dut, bodies(2, 19, 0)[0])
    await send_body(dut, (2 << 17) | (0xCAFE << 1))
    assert int(dut.protocol_error_wit.value) == 1
    assert int(dut.cfg_en.value) == 0



@cocotb.test()
async def nested_header_is_rejected(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    await send_body(dut, bodies(0, 7, 0)[0])
    await send_body(dut, bodies(1, 8, 0)[0])
    assert int(dut.protocol_error_wit.value) == 1
    assert int(dut.cfg_en.value) == 0
