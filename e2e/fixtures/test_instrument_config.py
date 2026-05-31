"""
Fixed instrument IDs for E2E testing.

Using specific, well-known equity instruments instead of dynamic selection
makes tests deterministic and eliminates the need for test file scanning.

These are common Indian stocks that should be available in the Fyers instrument master.
Format: {exchange}:{segment}:{instrument_type}:{symbol}
"""

# Well-known Indian equity instruments (NSE CM - Cash Market)
# Note: These are placeholder IDs - need to match actual Fyers format
TEST_INSTRUMENTS = [
    "NSE:CM:EQUITY:RELIANCE",   # Reliance Industries
    "NSE:CM:EQUITY:TCS",        # Tata Consultancy Services  
    "NSE:CM:EQUITY:HDFCBANK",   # HDFC Bank
    "NSE:CM:EQUITY:INFY",       # Infosys
    "NSE:CM:EQUITY:ICICIBANK",  # ICICI Bank
    "NSE:CM:EQUITY:SBIN",       # State Bank of India
    "NSE:CM:EQUITY:BHARTIARTL", # Bharti Airtel
    "NSE:CM:EQUITY:ITC",        # ITC Limited
    "NSE:CM:EQUITY:KOTAKBANK",  # Kotak Mahindra Bank
    "NSE:CM:EQUITY:LICI",       # LIC of India
]

def discover_actual_instrument_ids(instrument_catalog) -> list[str]:
    """
    Discover actual instrument IDs from the catalog by symbol.
    
    This function looks up the test instruments by symbol in the actual
    instrument catalog to get the real IDs used by Fyers.
    
    Args:
        instrument_catalog: InstrumentCatalog instance
        
    Returns:
        List of actual instrument IDs from the catalog
    """
    # Target symbols we want to use for testing
    target_symbols = [
        "RELIANCE",
        "TCS", 
        "HDFCBANK",
        "INFY",
        "ICICIBANK",
        "SBIN",
        "BHARTIARTL",
        "ITC",
        "KOTAKBANK",
        "LICI",
    ]
    
    symbol_to_id = {symbol: None for symbol in target_symbols}
    
    # Try to find these symbols in the catalog
    all_instruments = instrument_catalog.list_all()
    for instrument in all_instruments:
        symbol = instrument.get("symbol")
        if symbol in symbol_to_id and symbol_to_id[symbol] is None:
            symbol_to_id[symbol] = instrument.get("id")
    
    # Filter out symbols not found and return the IDs
    found_ids = [id for id in symbol_to_id.values() if id is not None]
    
    if len(found_ids) < len(target_symbols):
        missing = [sym for sym, id in symbol_to_id.items() if id is None]
        print(f"Warning: Could not find instruments for symbols: {missing}")
        print(f"Found {len(found_ids)} out of {len(target_symbols)} target instruments")
    
    return found_ids

def get_test_instrument_ids(count: int = 1) -> list[str]:
    """
    Get the first N test instrument IDs.
    
    Args:
        count: Number of instrument IDs to return
        
    Returns:
        List of instrument IDs
    """
    return TEST_INSTRUMENTS[:count]

def get_test_instrument_id(index: int = 0) -> str:
    """
    Get a specific test instrument ID by index.
    
    Args:
        index: Index in the TEST_INSTRUMENTS list
        
    Returns:
        Instrument ID string
    """
    if index >= len(TEST_INSTRUMENTS):
        raise ValueError(f"Index {index} out of range (only {len(TEST_INSTRUMENTS)} test instruments)")
    return TEST_INSTRUMENTS[index]