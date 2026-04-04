"""
Standard test data for E2E tests.

Defines instruments, prices, quantities, and other constants used across tests.
This prevents hardcoded values in test files and ensures consistency.
"""

from decimal import Decimal
from typing import Dict

# ============================================================================
# INSTRUMENTS
# ============================================================================

INSTRUMENTS: Dict[str, str] = {
    # NSE Equity symbols (ticker -> instrument_id)
    "SBIN": "INSTR_NSE_SBIN_EQ",  # State Bank of India
    "INFY": "INSTR_NSE_INFY_EQ",  # Infosys
    "TCS": "INSTR_NSE_TCS_EQ",  # Tata Consultancy Services
    "RELIANCE": "INSTR_NSE_RELIANCE_EQ",  # Reliance Industries
    "HDFC": "INSTR_NSE_HDFC_EQ",  # HDFC Bank
    "ITC": "INSTR_NSE_ITC_EQ",  # ITC Limited
    "WIPRO": "INSTR_NSE_WIPRO_EQ",  # Wipro
    "MARUTI": "INSTR_NSE_MARUTI_EQ",  # Maruti Suzuki
    "SUNPHARMA": "INSTR_NSE_SUNPHARMA_EQ",  # Sun Pharmaceutical
    "BAJAJFINSV": "INSTR_NSE_BAJAJFINSV_EQ",  # Bajaj Finserv
}

# ============================================================================
# PRICES
# ============================================================================

PRICES: Dict[str, Decimal] = {
    # Standard price levels for instruments
    "SBIN": Decimal("550.00"),
    "INFY": Decimal("1950.00"),
    "TCS": Decimal("3850.00"),
    "RELIANCE": Decimal("2950.00"),
    "HDFC": Decimal("2500.00"),
    "ITC": Decimal("450.00"),
    "WIPRO": Decimal("800.00"),
    "MARUTI": Decimal("12500.00"),
    "SUNPHARMA": Decimal("650.00"),
    "BAJAJFINSV": Decimal("18000.00"),
}

# ============================================================================
# QUANTITIES
# ============================================================================

QUANTITIES: Dict[str, int] = {
    "small": 10,  # Small order
    "medium": 50,  # Medium order
    "large": 100,  # Large order
    "very_large": 500,  # Very large order
}

# ============================================================================
# PRICE LEVELS FOR TESTING
# ============================================================================

PRICE_LEVELS = {
    "above": 1.05,  # 5% above current price
    "at": 1.0,  # At current price
    "below": 0.95,  # 5% below current price
    "far_below": 0.85,  # 15% below current price (unlikely to fill)
}

# ============================================================================
# ORDER TYPES
# ============================================================================

ORDER_TYPES = {
    "LIMIT": "limit",
    "MARKET": "market",
    "STOP": "stop",
    "STOP_LIMIT": "stop_limit",
}

# ============================================================================
# ORDER SIDE
# ============================================================================

ORDER_SIDES = {
    "BUY": "BUY",
    "SELL": "SELL",
}

# ============================================================================
# TIME IN FORCE
# ============================================================================

TIME_IN_FORCE = {
    "DAY": "DAY",
    "IOC": "IOC",
    "FOK": "FOK",
}

# ============================================================================
# PORTFOLIO CONSTANTS
# ============================================================================

MARGIN_MULTIPLIER = {
    "intraday": 4,  # 4x intraday margin
    "delivery": 1,  # 1x delivery (full payment)
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_instrument_id(symbol: str) -> str:
    """
    Get instrument ID for a symbol.

    Args:
        symbol: Stock symbol (e.g., "SBIN")

    Returns:
        Instrument ID (e.g., "INSTR_NSE_SBIN_EQ")

    Raises:
        KeyError: If symbol is not in INSTRUMENTS
    """
    return INSTRUMENTS[symbol]


def get_price(symbol: str) -> Decimal:
    """
    Get standard price for a symbol.

    Args:
        symbol: Stock symbol (e.g., "SBIN")

    Returns:
        Price as Decimal

    Raises:
        KeyError: If symbol is not in PRICES
    """
    return PRICES[symbol]


def get_quantity(size: str) -> int:
    """
    Get quantity for a given size.

    Args:
        size: Size identifier (e.g., "small", "medium", "large")

    Returns:
        Quantity in shares

    Raises:
        KeyError: If size is not in QUANTITIES
    """
    return QUANTITIES[size]


def calculate_price_level(base_price: Decimal, level: str) -> Decimal:
    """
    Calculate price at a given level relative to base price.

    Args:
        base_price: Base price
        level: Level identifier (e.g., "above", "at", "below")

    Returns:
        Price at the specified level

    Raises:
        KeyError: If level is not in PRICE_LEVELS
    """
    multiplier = PRICE_LEVELS[level]
    result = base_price * Decimal(str(multiplier))
    # Round to 2 decimal places
    return result.quantize(Decimal("0.01"))
