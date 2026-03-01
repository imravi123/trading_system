"""Shared tool registry — used by both the MCP server and the internal chat service.

Tools are registered here and shared between:
  - The MCP server (stdio/SSE transport for Claude Desktop / Claude Code)
  - The internal chat service (WebSocket /ws/chat used by the React UI)

To add more tools:
  1. Define the implementation (or import from backend.tools.*)
  2. Append a Tool entry to TOOLS
  3. Add a dispatch case to call_tool()

Current tools
─────────────
  get_stock_price    — current price + basic stats for an NSE symbol
  get_stock_analysis — full fundamentals, analyst targets, and recent news
  scrape_url         — fetch any web page and return clean LLM-friendly text
"""
from __future__ import annotations

from mcp.types import Tool

from backend.services.scraper.market_scraper import MarketScraper
from backend.services.scraper.web_scraper import scrape_url as _scrape_url

_market = MarketScraper()


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOLS: list[Tool] = [
    Tool(
        name="get_stock_price",
        description=(
            "Get the current market price and basic trading stats for an NSE-listed stock. "
            "Returns price, day high/low, 52-week range, volume, and moving averages. "
            "Use this for quick price checks."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "NSE stock symbol (e.g. 'TCS', 'RELIANCE', 'HDFCBANK'). "
                                   "Do NOT add .NS — it is added automatically.",
                },
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="get_stock_analysis",
        description=(
            "Get a comprehensive stock analysis for an NSE-listed company. "
            "Includes price data, fundamentals (P/E, EPS, market cap, ROE, D/E, margins), "
            "analyst consensus (rating + price targets), and the 5 most recent news headlines. "
            "Use this when the user asks for a full stock overview or research."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "NSE stock symbol (e.g. 'TCS', 'RELIANCE', 'HDFCBANK').",
                },
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="scrape_url",
        description=(
            "Fetch any public web URL and return clean plain-text content, "
            "with all HTML tags, scripts, ads, and navigation stripped out. "
            "Useful for reading financial news articles, analyst reports, "
            "NSE/BSE announcements, or any web page the user provides."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Fully-qualified URL to fetch, e.g. 'https://www.moneycontrol.com/...'",
                },
            },
            "required": ["url"],
        },
    ),
]


# ── LLM-friendly formatters ───────────────────────────────────────────────────

def _fmt_price(r) -> str:
    """Format a ScrapeResponse as a concise price summary."""
    lines: list[str] = []
    name = r.company_name or r.symbol
    lines.append(f"{r.symbol} ({name}) | NSE")

    if r.price is not None:
        change_str = ""
        if r.change is not None and r.change_pct is not None:
            sign = "+" if r.change >= 0 else ""
            change_str = f"  |  Change: {sign}₹{r.change:.2f} ({sign}{r.change_pct:.2f}%)"
        lines.append(f"Price: ₹{r.price:,.2f}{change_str}")

    if r.day_low is not None and r.day_high is not None:
        prev = f"  |  Prev Close: ₹{r.prev_close:,.2f}" if r.prev_close else ""
        lines.append(f"Day Range: ₹{r.day_low:,.2f} – ₹{r.day_high:,.2f}{prev}")

    if r.week_52_low is not None and r.week_52_high is not None:
        lines.append(f"52W Range: ₹{r.week_52_low:,.2f} – ₹{r.week_52_high:,.2f}")

    parts: list[str] = []
    if r.volume:
        parts.append(f"Volume: {r.volume:,}")
    if r.ma_50:
        parts.append(f"MA50: ₹{r.ma_50:,.2f}")
    if r.ma_200:
        parts.append(f"MA200: ₹{r.ma_200:,.2f}")
    if parts:
        lines.append("  |  ".join(parts))

    lines.append(f"[Source: Yahoo Finance  |  As of: {r.timestamp[:19]}]")
    return "\n".join(lines)


def _fmt_analysis(r) -> str:
    """Format a ScrapeResponse as a detailed multi-section analysis."""
    sections: list[str] = []
    name = r.company_name or r.symbol
    sections.append(f"{'='*60}")
    sections.append(f"{r.symbol}  —  {name}")
    sections.append(f"{'='*60}")

    if r.sector or r.industry:
        sections.append(f"Sector: {r.sector or 'N/A'}  |  Industry: {r.industry or 'N/A'}")

    if r.description:
        sections.append(f"\nBusiness: {r.description.strip()}")

    # Price block
    sections.append("\n── PRICE ──")
    sections.append(_fmt_price(r))

    # Fundamentals block
    fund: list[str] = []
    if r.market_cap:
        cr = r.market_cap / 1e7
        fund.append(f"Market Cap: ₹{cr:,.0f} Cr")
    if r.pe_ratio:
        fund.append(f"P/E (TTM): {r.pe_ratio:.1f}")
    if r.forward_pe:
        fund.append(f"Forward P/E: {r.forward_pe:.1f}")
    if r.eps:
        fund.append(f"EPS (TTM): ₹{r.eps:.2f}")
    if r.book_value:
        fund.append(f"Book Value: ₹{r.book_value:.2f}")
    if r.price_to_book:
        fund.append(f"P/B Ratio: {r.price_to_book:.2f}x")
    if r.dividend_yield:
        fund.append(f"Dividend Yield: {r.dividend_yield * 100:.2f}%")
    if r.beta:
        fund.append(f"Beta: {r.beta:.2f}")
    if r.roe:
        fund.append(f"ROE: {r.roe * 100:.1f}%")
    if r.profit_margin:
        fund.append(f"Net Margin: {r.profit_margin * 100:.1f}%")
    if r.debt_to_equity:
        fund.append(f"D/E Ratio: {r.debt_to_equity:.2f}")
    if r.current_ratio:
        fund.append(f"Current Ratio: {r.current_ratio:.2f}")
    if fund:
        sections.append("\n── FUNDAMENTALS ──")
        sections.extend(fund)

    # Analyst view
    analyst: list[str] = []
    if r.recommendation:
        count = f" ({r.analyst_count} analysts)" if r.analyst_count else ""
        analyst.append(f"Consensus: {r.recommendation.upper()}{count}")
    if r.target_mean_price:
        analyst.append(
            f"Price Targets:  Mean ₹{r.target_mean_price:,.2f}"
            f"  |  High ₹{r.target_high_price:,.2f}"
            f"  |  Low ₹{r.target_low_price:,.2f}"
        )
    if analyst:
        sections.append("\n── ANALYST VIEW ──")
        sections.extend(analyst)

    # News
    if r.news:
        sections.append("\n── RECENT NEWS ──")
        for i, item in enumerate(r.news[:5], 1):
            pub_date = item.published_at[:10] if item.published_at else "N/A"
            sections.append(f"{i}. {item.title}")
            sections.append(f"   {item.publisher}  |  {pub_date}  |  {item.link}")

    sections.append(f"\n[Source: Yahoo Finance  |  As of: {r.timestamp[:19]}]")
    return "\n".join(sections)


# ── Dispatcher ────────────────────────────────────────────────────────────────

async def call_tool(name: str, arguments: dict) -> str:
    """Route a tool call to its implementation. Returns a plain-text result."""

    if name == "get_stock_price":
        symbol = (arguments.get("symbol") or "").strip().upper()
        if not symbol:
            return "Error: 'symbol' parameter is required."
        result = await _market.scrape_one(symbol, include_news=False, include_fundamentals=False)
        if not result.scraped_ok:
            return f"Could not fetch price for {symbol}: {result.error}"
        return _fmt_price(result)

    elif name == "get_stock_analysis":
        symbol = (arguments.get("symbol") or "").strip().upper()
        if not symbol:
            return "Error: 'symbol' parameter is required."
        result = await _market.scrape_one(symbol, include_news=True, include_fundamentals=True)
        if not result.scraped_ok:
            return f"Could not fetch analysis for {symbol}: {result.error}"
        return _fmt_analysis(result)

    elif name == "scrape_url":
        url = (arguments.get("url") or "").strip()
        if not url:
            return "Error: 'url' parameter is required."
        return await _scrape_url(url)

    else:
        available = [t.name for t in TOOLS]
        raise ValueError(f"Unknown tool: '{name}'. Available tools: {available}")
