"""Curated investment universes for diversification.

All tickers are in Trading 212 format ({SYMBOL}_{EXCHANGE}_{TYPE}).
Lists are static — verify membership against the live instrument cache before
trading, since ETFs occasionally get delisted or renamed.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


# ── ETF universes ─────────────────────────────────────────────────────────────

SECTOR_ETFS: dict[str, str] = {
    "Technology": "XLK_US_EQ",
    "Financials": "XLF_US_EQ",
    "Healthcare": "XLV_US_EQ",
    "Energy": "XLE_US_EQ",
    "Industrials": "XLI_US_EQ",
    "Consumer Discretionary": "XLY_US_EQ",
    "Consumer Staples": "XLP_US_EQ",
    "Utilities": "XLU_US_EQ",
    "Materials": "XLB_US_EQ",
    "Real Estate": "XLRE_US_EQ",
    "Communication Services": "XLC_US_EQ",
}

INDEX_ETFS: dict[str, str] = {
    "S&P 500 (SPY)": "SPY_US_EQ",
    "Nasdaq 100 (QQQ)": "QQQ_US_EQ",
    "Dow Jones (DIA)": "DIA_US_EQ",
    "Russell 2000 (IWM)": "IWM_US_EQ",
    "Total US Market (VTI)": "VTI_US_EQ",
    "S&P 500 low-cost (VOO)": "VOO_US_EQ",
}

GEOGRAPHIC_ETFS: dict[str, str] = {
    "Developed ex-US (VEA)": "VEA_US_EQ",
    "Emerging Markets (VWO)": "VWO_US_EQ",
    "EAFE (EFA)": "EFA_US_EQ",
    "Emerging Markets (EEM)": "EEM_US_EQ",
}

BOND_ETFS: dict[str, str] = {
    "US Aggregate (AGG)": "AGG_US_EQ",
    "Total Bond (BND)": "BND_US_EQ",
    "Long Treasury (TLT)": "TLT_US_EQ",
    "Investment Grade Corp (LQD)": "LQD_US_EQ",
    "High Yield (HYG)": "HYG_US_EQ",
}

COMMODITY_ETFS: dict[str, str] = {
    "Gold (GLD)": "GLD_US_EQ",
    "Silver (SLV)": "SLV_US_EQ",
    "Oil (USO)": "USO_US_EQ",
    "Broad Commodities (DBC)": "DBC_US_EQ",
}

ETF_UNIVERSES: dict[str, dict[str, str]] = {
    "sectors": SECTOR_ETFS,
    "indexes": INDEX_ETFS,
    "geographic": GEOGRAPHIC_ETFS,
    "bonds": BOND_ETFS,
    "commodities": COMMODITY_ETFS,
}


# ── S&P 500 by GICS sector (large-cap seed, ~10 per sector) ───────────────────
# Static snapshot. Membership shifts quarterly; treat as a starting universe,
# not gospel. Run instrument-info on a candidate before trading to confirm
# it's still listed and check current sector classification.

SP500_BY_SECTOR: dict[str, list[str]] = {
    "Technology": [
        "AAPL_US_EQ", "MSFT_US_EQ", "NVDA_US_EQ", "AVGO_US_EQ", "ORCL_US_EQ",
        "CRM_US_EQ", "ADBE_US_EQ", "AMD_US_EQ", "CSCO_US_EQ", "ACN_US_EQ",
    ],
    "Financials": [
        "JPM_US_EQ", "BAC_US_EQ", "WFC_US_EQ", "GS_US_EQ", "MS_US_EQ",
        "BLK_US_EQ", "C_US_EQ", "AXP_US_EQ", "SCHW_US_EQ", "SPGI_US_EQ",
    ],
    "Healthcare": [
        "LLY_US_EQ", "JNJ_US_EQ", "UNH_US_EQ", "ABBV_US_EQ", "MRK_US_EQ",
        "PFE_US_EQ", "TMO_US_EQ", "ABT_US_EQ", "DHR_US_EQ", "AMGN_US_EQ",
    ],
    "Energy": [
        "XOM_US_EQ", "CVX_US_EQ", "COP_US_EQ", "EOG_US_EQ", "SLB_US_EQ",
        "PSX_US_EQ", "MPC_US_EQ", "VLO_US_EQ", "OXY_US_EQ", "PXD_US_EQ",
    ],
    "Industrials": [
        "GE_US_EQ", "CAT_US_EQ", "RTX_US_EQ", "HON_US_EQ", "UNP_US_EQ",
        "BA_US_EQ", "LMT_US_EQ", "DE_US_EQ", "UPS_US_EQ", "ETN_US_EQ",
    ],
    "Consumer Discretionary": [
        "AMZN_US_EQ", "TSLA_US_EQ", "HD_US_EQ", "MCD_US_EQ", "NKE_US_EQ",
        "LOW_US_EQ", "SBUX_US_EQ", "TJX_US_EQ", "BKNG_US_EQ", "ABNB_US_EQ",
    ],
    "Consumer Staples": [
        "WMT_US_EQ", "PG_US_EQ", "KO_US_EQ", "PEP_US_EQ", "COST_US_EQ",
        "PM_US_EQ", "MO_US_EQ", "MDLZ_US_EQ", "CL_US_EQ", "TGT_US_EQ",
    ],
    "Utilities": [
        "NEE_US_EQ", "SO_US_EQ", "DUK_US_EQ", "SRE_US_EQ", "AEP_US_EQ",
        "D_US_EQ", "PCG_US_EQ", "EXC_US_EQ", "XEL_US_EQ", "PEG_US_EQ",
    ],
    "Materials": [
        "LIN_US_EQ", "SHW_US_EQ", "APD_US_EQ", "ECL_US_EQ", "FCX_US_EQ",
        "NEM_US_EQ", "DOW_US_EQ", "DD_US_EQ", "PPG_US_EQ", "NUE_US_EQ",
    ],
    "Real Estate": [
        "PLD_US_EQ", "AMT_US_EQ", "EQIX_US_EQ", "CCI_US_EQ", "PSA_US_EQ",
        "O_US_EQ", "WELL_US_EQ", "SPG_US_EQ", "DLR_US_EQ", "AVB_US_EQ",
    ],
    "Communication Services": [
        "GOOGL_US_EQ", "META_US_EQ", "NFLX_US_EQ", "DIS_US_EQ", "TMUS_US_EQ",
        "VZ_US_EQ", "T_US_EQ", "CMCSA_US_EQ", "CHTR_US_EQ", "EA_US_EQ",
    ],
}


# ── Diversified basket suggestion ─────────────────────────────────────────────

@dataclass(frozen=True)
class DiversifiedBasket:
    """A suggested diversified basket. Picks one ticker from each category."""
    tickers: list[str]
    sources: dict[str, str]  # category → ticker
    seed: int | None = None


def diversify(
    categories: list[str] | None = None,
    seed: int | None = None,
) -> DiversifiedBasket:
    """Build a diversified ETF basket — one ticker per requested category.

    Default categories: sectors-broad (XLK proxy), indexes, geographic, bonds, commodities.
    A 5-name basket gives meaningful cross-asset diversification with one click.
    """
    if categories is None:
        categories = ["indexes", "geographic", "bonds", "commodities"]

    rng = random.Random(seed)
    sources: dict[str, str] = {}
    tickers: list[str] = []

    for cat in categories:
        if cat == "sectors":
            label, ticker = rng.choice(list(SECTOR_ETFS.items()))
            sources[f"sectors:{label}"] = ticker
            tickers.append(ticker)
            continue
        universe = ETF_UNIVERSES.get(cat)
        if not universe:
            continue
        label, ticker = rng.choice(list(universe.items()))
        sources[f"{cat}:{label}"] = ticker
        tickers.append(ticker)

    return DiversifiedBasket(tickers=tickers, sources=sources, seed=seed)


def sector_sample(sector: str, count: int = 3, seed: int | None = None) -> list[str]:
    """Pick `count` random tickers from one S&P 500 sector."""
    pool = SP500_BY_SECTOR.get(sector)
    if not pool:
        raise KeyError(
            f"Unknown sector '{sector}'. Available: {sorted(SP500_BY_SECTOR.keys())}"
        )
    rng = random.Random(seed)
    n = min(count, len(pool))
    return rng.sample(pool, n)


def all_universes() -> dict[str, dict[str, str] | dict[str, list[str]]]:
    """Return every curated universe in one dict — useful for listing."""
    return {**ETF_UNIVERSES, "sp500_sectors": SP500_BY_SECTOR}
