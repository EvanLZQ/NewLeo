"""Lens pricing v2: the price table (price_v2.xlsx and later files) drives
everything — prices, limitations, labels, colour groups and product lines.

Modules:
    config    the single place for every business parameter that may change
              (defaults in code, overridable per row in LensPricingSettings)
    sheet     reads the Excel file into ParsedBlock objects (no database)
    engine    pure pricing rules on parsed blocks (no database)
    store     loads the active PriceTableVersion from the database
    importer  dry run / import as draft / diff report / activate / roll back
    api       REST endpoints used by the storefront
    cart      CompleteSet (cart item / order line) pricing and snapshot
"""
