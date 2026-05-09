"""Test instrument data for E2E tests.

Instruments are pre-seeded into consumer service databases (BAS, PBS)
during test setup. This follows the event-driven architecture where:
1. Instruments are synced from external source (Fyers) to MDS
2. MDS emits instrument events to consumers
3. Consumers (BAS, PBS) store instruments in their own databases
4. Tests load instruments from consumer databases, not MDS

For E2E tests, we seed instruments directly into consumer databases
to simulate this event-driven flow without requiring actual instrument
sync events.
"""

from typing import Any


def get_test_instruments() -> list[dict[str, Any]]:
    """
    Get a set of test instruments to seed into consumer service databases.

    These represent equity instruments that would normally be synced
    from an external broker (Fyers) via instrument.created events.

    Returns:
        List of instrument dictionaries ready to insert into databases
    """
    return [
        # Blue-chip equities (segment=CASH for NSE equity cash market)
        {
            "id": "NSE:SBIN:EQ",
            "symbol": "SBIN",
            "name": "State Bank of India",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE062A01020",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:INFY:EQ",
            "symbol": "INFY",
            "name": "Infosys Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE009A01021",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:TCS:EQ",
            "symbol": "TCS",
            "name": "Tata Consultancy Services",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE467B01029",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:HDFC:EQ",
            "symbol": "HDFC",
            "name": "Housing Development Finance Corporation",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE001A01015",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:ICICIBANK:EQ",
            "symbol": "ICICIBANK",
            "name": "ICICI Bank Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE090A01021",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        # Mid-cap equities
        {
            "id": "NSE:MARUTI:EQ",
            "symbol": "MARUTI",
            "name": "Maruti Suzuki India Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE585B01010",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:BAJAJFINSV:EQ",
            "symbol": "BAJAJFINSV",
            "name": "Bajaj Finserv Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE918I01018",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:RELIANCE:EQ",
            "symbol": "RELIANCE",
            "name": "Reliance Industries Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE002A01015",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        # Small-cap equities for testing
        {
            "id": "NSE:TESTEQUITY1:EQ",
            "symbol": "TESTEQUITY1",
            "name": "Test Equity 1",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE999A01001",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:TESTEQUITY2:EQ",
            "symbol": "TESTEQUITY2",
            "name": "Test Equity 2",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE999A01002",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        # Additional equities referenced by individual tests. Symbols are
        # opaque keys for catalog lookup; the id is independent and never
        # derived from the symbol at runtime.
        {
            "id": "NSE:ASIAN:EQ",
            "symbol": "ASIAN",
            "name": "Asian Paints Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE021A01026",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:AXIS:EQ",
            "symbol": "AXIS",
            "name": "Axis Bank Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE238A01034",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:BHARTIARTL:EQ",
            "symbol": "BHARTIARTL",
            "name": "Bharti Airtel Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE397D01024",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:HEROMOTOCO:EQ",
            "symbol": "HEROMOTOCO",
            "name": "Hero MotoCorp Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE158A01026",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:ITC:EQ",
            "symbol": "ITC",
            "name": "ITC Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE154A01025",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:KOTAK:EQ",
            "symbol": "KOTAK",
            "name": "Kotak Mahindra Bank Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE237A01028",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:KOTAKBANK:EQ",
            "symbol": "KOTAKBANK",
            "name": "Kotak Mahindra Bank Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE237A01028",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:LT:EQ",
            "symbol": "LT",
            "name": "Larsen & Toubro Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE018A01030",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:POWERGRID:EQ",
            "symbol": "POWERGRID",
            "name": "Power Grid Corporation of India Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE752E01010",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:SUNPHARMA:EQ",
            "symbol": "SUNPHARMA",
            "name": "Sun Pharmaceutical Industries Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE044A01036",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:TITAN:EQ",
            "symbol": "TITAN",
            "name": "Titan Company Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE280A01028",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:ULTRACEMCO:EQ",
            "symbol": "ULTRACEMCO",
            "name": "UltraTech Cement Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE481G01011",
            "lot_size": 1,
            "tick_size": 0.05,
        },
        {
            "id": "NSE:WIPRO:EQ",
            "symbol": "WIPRO",
            "name": "Wipro Limited",
            "exchange": "NSE",
            "segment": "CASH",
            "type": "EQUITY",
            "isin": "INE075A01022",
            "lot_size": 1,
            "tick_size": 0.05,
        },
    ]
