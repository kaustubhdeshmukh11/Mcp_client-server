from fastmcp import FastMCP
import sqlite3
import yfinance as yf

# Initialize
mcp = FastMCP("Stock Trader")
DB_FILE = "portfolio.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Table to track what you own
    c.execute('''CREATE TABLE IF NOT EXISTS portfolio
                 (symbol TEXT PRIMARY KEY, 
                  quantity INTEGER, 
                  avg_price REAL)''')
    conn.commit()
    conn.close()

init_db()

# --- REAL-WORLD DATA TOOLS ---

@mcp.tool()
def get_stock_price(symbol: str) -> str:
    """Get the real-time price of a stock (e.g., RELIANCE.NS, AAPL)."""
    try:
        stock = yf.Ticker(symbol)
        # fast_info is often faster than .info
        price = stock.fast_info['last_price']
        currency = stock.fast_info['currency']
        return f"The current price of {symbol} is {price:.2f} {currency}."
    except Exception as e:
        return f"Error fetching price for {symbol}: {str(e)}"

# --- DATABASE TOOLS ---

@mcp.tool()
def buy_stock(symbol: str, quantity: int) -> str:
    """Simulate buying a stock at current market price."""
    # 1. Get live price first
    try:
        stock = yf.Ticker(symbol)
        price = stock.fast_info['last_price']
    except:
        return f"Could not find stock {symbol} to buy."

    # 2. Update Database
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Check if we already own it
    c.execute("SELECT quantity, avg_price FROM portfolio WHERE symbol=?", (symbol,))
    row = c.fetchone()
    
    if row:
        # Calculate new average price (Weighted Average)
        old_qty, old_avg = row
        new_qty = old_qty + quantity
        total_cost = (old_qty * old_avg) + (quantity * price)
        new_avg = total_cost / new_qty
        c.execute("UPDATE portfolio SET quantity=?, avg_price=? WHERE symbol=?", 
                  (new_qty, new_avg, symbol))
    else:
        # New entry
        c.execute("INSERT INTO portfolio (symbol, quantity, avg_price) VALUES (?, ?, ?)", 
                  (symbol, quantity, price))
    
    conn.commit()
    conn.close()
    return f"Bought {quantity} shares of {symbol} at {price:.2f}. Added to portfolio."

@mcp.tool()
def get_portfolio_status() -> str:
    """Check your current portfolio value and profit/loss."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT symbol, quantity, avg_price FROM portfolio")
    rows = c.fetchall()
    conn.close()

    if not rows:
        return "Your portfolio is empty."

    report = "📊 **Portfolio Report**\n"
    total_profit = 0

    for symbol, qty, avg_price in rows:
        # Fetch live price for comparison
        try:
            current_price = yf.Ticker(symbol).fast_info['last_price']
            market_value = current_price * qty
            cost_basis = avg_price * qty
            pnl = market_value - cost_basis
            total_profit += pnl
            
            report += f"- **{symbol}**: {qty} shares @ {avg_price:.2f} (Curr: {current_price:.2f}) | P/L: {pnl:+.2f}\n"
        except:
            report += f"- **{symbol}**: (Could not fetch live price)\n"

    report += f"\n💰 **Total Profit/Loss:** {total_profit:+.2f}"
    return report

if __name__ == "__main__":
    mcp.run()