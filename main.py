from fastmcp import FastMCP, Context
import os
import aiosqlite
import sqlite3
import yfinance as yf
import tempfile

# --- CONFIGURATION ---
mcp = FastMCP("Stock Trader")

# Use temp directory for write permissions
TEMP_DIR = tempfile.gettempdir()
DB_FILE = os.path.join(TEMP_DIR, "portfolio.db")
print(f"Database path: {DB_FILE}")

# --- HELPER FUNCTIONS ---

def get_user_id(ctx: Context) -> str:
    """Identify the user. Defaults to 'local_user' if running locally."""
    if ctx.request_context and ctx.request_context.lifecycle_context:
        return ctx.request_context.lifecycle_context.get("user_id", "local_user")
    return "local_user"

def init_db():
    """Initialize database with multi-user support and migration logic."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            
            # Check if table exists to decide on migration
            c.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='portfolio'")
            table_exists = c.fetchone()[0] > 0

            if not table_exists:
                # Create new schema with user_id and composite primary key
                c.execute('''
                    CREATE TABLE portfolio (
                        user_id TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        quantity INTEGER,
                        avg_price REAL,
                        PRIMARY KEY (user_id, symbol)
                    )
                ''')
                print("Database initialized.")
            else:
                # --- MIGRATION BLOCK for existing users ---
                c.execute("PRAGMA table_info(portfolio)")
                columns = [info[1] for info in c.fetchall()]
                
                if "user_id" not in columns:
                    print("Migrating database: Upgrading to multi-user schema...")
                    # We need to recreate the table to change the Primary Key
                    c.execute("ALTER TABLE portfolio RENAME TO old_portfolio")
                    c.execute('''
                        CREATE TABLE portfolio (
                            user_id TEXT NOT NULL,
                            symbol TEXT NOT NULL,
                            quantity INTEGER,
                            avg_price REAL,
                            PRIMARY KEY (user_id, symbol)
                        )
                    ''')
                    # Copy old data to 'local_user'
                    c.execute('''
                        INSERT INTO portfolio (user_id, symbol, quantity, avg_price)
                        SELECT 'local_user', symbol, quantity, avg_price FROM old_portfolio
                    ''')
                    c.execute("DROP TABLE old_portfolio")
                    print("Migration complete.")
                # ------------------------------------------
            
            conn.commit()
    except Exception as e:
        print(f"Database initialization error: {e}")
        raise

# Initialize immediately
init_db()

# --- REAL-WORLD DATA TOOLS ---

@mcp.tool()
def get_stock_price(symbol: str) -> str:
    """Get the real-time price of a stock (e.g., RELIANCE.NS, AAPL)."""
    try:
        stock = yf.Ticker(symbol)
        price = stock.fast_info['last_price']
        currency = stock.fast_info['currency']
        return f"The current price of {symbol} is {price:.2f} {currency}."
    except Exception as e:
        return f"Error fetching price for {symbol}: {str(e)}"

# --- ASYNC DATABASE TOOLS ---

@mcp.tool()
async def buy_stock(ctx: Context, symbol: str, quantity: int) -> str:
    """Simulate buying a stock at current market price."""
    user_id = get_user_id(ctx)
    
    # 1. Get live price (synchronous call wrapped in try/except)
    try:
        stock = yf.Ticker(symbol)
        price = stock.fast_info['last_price']
    except:
        return f"Could not find stock {symbol} to buy."

    # 2. Update Database asynchronously
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            # Check if we already own it
            async with conn.execute(
                "SELECT quantity, avg_price FROM portfolio WHERE user_id=? AND symbol=?", 
                (user_id, symbol)
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                # Calculate new average price (Weighted Average)
                old_qty, old_avg = row
                new_qty = old_qty + quantity
                total_cost = (old_qty * old_avg) + (quantity * price)
                new_avg = total_cost / new_qty
                
                await conn.execute(
                    "UPDATE portfolio SET quantity=?, avg_price=? WHERE user_id=? AND symbol=?",
                    (new_qty, new_avg, user_id, symbol)
                )
            else:
                # New entry
                await conn.execute(
                    "INSERT INTO portfolio (user_id, symbol, quantity, avg_price) VALUES (?, ?, ?, ?)",
                    (user_id, symbol, quantity, price)
                )
            
            await conn.commit()
            return f"Bought {quantity} shares of {symbol} at {price:.2f}. Added to portfolio for user {user_id}."
            
    except Exception as e:
        return f"Database error: {str(e)}"

@mcp.tool()
async def get_portfolio_status(ctx: Context) -> str:
    """Check your current portfolio value and profit/loss."""
    user_id = get_user_id(ctx)
    
    try:
        async with aiosqlite.connect(DB_FILE) as conn:
            async with conn.execute(
                "SELECT symbol, quantity, avg_price FROM portfolio WHERE user_id=?", 
                (user_id,)
            ) as cursor:
                rows = await cursor.fetchall()

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

    except Exception as e:
        return f"Error retrieving portfolio: {str(e)}"

if __name__ == "__main__":
    # Uses SSE transport to fix the 404 error
    mcp.run(transport="http", host="0.0.0.0", port=8000)