import logging
import sqlite3
import time
import tkinter as tk
from tkinter import ttk, messagebox
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_name="undervalued_assets.db"):
        """Initialize database connection and create required tables."""
        self.db_name = db_name
        self.conn = None
        self.setup_database()

    def setup_database(self):
        """Set up the SQLite database and create tables if they don't exist."""
        try:
            self.conn = sqlite3.connect(self.db_name)
            c = self.conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS assets (
                            id INTEGER PRIMARY KEY,
                            title TEXT NOT NULL,
                            price REAL NOT NULL,
                            link TEXT NOT NULL,
                            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )''')
            self.conn.commit()
            logging.info("Database setup completed successfully")
        except sqlite3.Error as e:
            logging.error(f"Database setup failed: {e}")
            raise

    def insert_assets(self, assets):
        """Insert multiple assets into the database."""
        try:
            c = self.conn.cursor()
            c.executemany(
                "INSERT INTO assets (title, price, link) VALUES (?, ?, ?)",
                assets
            )
            self.conn.commit()
            logging.info(f"Successfully inserted {len(assets)} assets")
            return True
        except sqlite3.Error as e:
            logging.error(f"Failed to insert assets: {e}")
            self.conn.rollback()
            return False

    def get_all_assets(self):
        """Retrieve all assets from the database."""
        return pd.read_sql_query("SELECT * FROM assets", self.conn)

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()

class MarketplaceScraper:
    def __init__(self, base_url="https://example-marketplace.com"):
        """Initialize the marketplace scraper with configuration."""
        self.base_url = base_url
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    def scrape_page(self, url):
        """Scrape a single page and return list of items."""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, "html.parser")
            items = []

            for listing in soup.find_all("div", class_="item-class"):
                try:
                    title = listing.find("h2").get_text(strip=True) if listing.find("h2") else "N/A"
                    price_text = listing.find("span", class_="price-class").get_text(strip=True)
                    price = float(price_text.replace("$", "").replace(",", ""))
                    link = listing.find("a")["href"]
                    
                    if all([title != "N/A", price > 0, link]):
                        items.append((title, price, link))
                except (AttributeError, ValueError) as e:
                    logging.warning(f"Failed to parse listing: {e}")
                    continue

            logging.info(f"Successfully scraped {len(items)} items from {url}")
            return items

        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch {url}: {e}")
            return []

    def scrape_multiple_pages(self, start_page=1, end_page=3):
        """Scrape multiple pages and return combined results."""
        all_items = []
        for page_num in range(start_page, end_page + 1):
            url = f"{self.base_url}/page/{page_num}"
            items = self.scrape_page(url)
            all_items.extend(items)
            time.sleep(1)  # Respect rate limits
        return all_items

class AuctionManager:
    def __init__(self, api_url="https://your-auction-site.com/api"):
        """Initialize the auction manager with API configuration."""
        self.api_url = api_url
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def post_to_auction(self, item):
        """Post a single item to the auction site."""
        try:
            payload = {
                "title": item["title"],
                "price": item["price"],
                "link": item["link"],
                "timestamp": datetime.now().isoformat()
            }
            
            response = requests.post(
                f"{self.api_url}/create-auction",
                json=payload,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            logging.info(f"Successfully posted auction for: {item['title']}")
            return True

        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to post auction for {item['title']}: {e}")
            return False

class AssetAnalyzer:
    @staticmethod
    def identify_undervalued_assets(df, threshold_percentile=25):
        """Identify undervalued assets based on price distribution."""
        if df.empty:
            return pd.DataFrame()

        price_threshold = df["price"].quantile(threshold_percentile / 100)
        undervalued = df[df["price"] < price_threshold].copy()
        undervalued["discount_percent"] = (
            (df["price"].mean() - undervalued["price"]) / df["price"].mean() * 100
        )
        
        logging.info(f"Identified {len(undervalued)} undervalued assets")
        return undervalued.sort_values("discount_percent", ascending=False)

class ApplicationGUI:
    def __init__(self, root):
        """Initialize the GUI application."""
        self.root = root
        self.root.title("Asset Scraper and Auction Manager")
        self.root.geometry("1000x600")
        
        self.db = DatabaseManager()
        self.scraper = MarketplaceScraper()
        self.auction_manager = AuctionManager()
        
        self.setup_gui()

    def setup_gui(self):
        """Set up the GUI components."""
        # Control buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=10)

        buttons = [
            ("Scrape Marketplace", self.handle_scrape),
            ("Display Undervalued Assets", self.handle_display),
            ("Post to Auction", self.handle_post_auction)
        ]

        for idx, (text, command) in enumerate(buttons):
            tk.Button(btn_frame, text=text, command=command).grid(
                row=0, column=idx, padx=5
            )

        # Treeview for displaying assets
        columns = ("Title", "Price", "Discount %", "Link")
        self.tree = ttk.Treeview(self.root, columns=columns, show="headings")
        
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="center", width=200)

        # Scrollbar
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Pack everything
        self.tree.pack(side="left", pady=20, fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def handle_scrape(self):
        """Handle the scrape button click."""
        try:
            items = self.scraper.scrape_multiple_pages()
            if items and self.db.insert_assets(items):
                messagebox.showinfo(
                    "Success",
                    f"Successfully scraped and stored {len(items)} items"
                )
            else:
                messagebox.showerror(
                    "Error",
                    "Failed to scrape items or store them in the database"
                )
        except Exception as e:
            logging.error(f"Scraping failed: {e}")
            messagebox.showerror("Error", f"Scraping failed: {str(e)}")

    def handle_display(self):
        """Handle the display button click."""
        df = self.db.get_all_assets()
        undervalued = AssetAnalyzer.identify_undervalued_assets(df)
        
        self.tree.delete(*self.tree.get_children())
        
        if undervalued.empty:
            messagebox.showinfo("No Data", "No undervalued assets found")
            return

        for _, row in undervalued.iterrows():
            self.tree.insert("", "end", values=(
                row["title"],
                f"${row['price']:.2f}",
                f"{row['discount_percent']:.1f}%",
                row["link"]
            ))

    def handle_post_auction(self):
        """Handle the post to auction button click."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Selection Required", "Please select items to post")
            return

        posted = 0
        for item_id in selection:
            values = self.tree.item(item_id)["values"]
            item = {
                "title": values[0],
                "price": float(values[1].replace("$", "")),
                "link": values[3]
            }
            
            if self.auction_manager.post_to_auction(item):
                posted += 1

        messagebox.showinfo(
            "Posting Complete",
            f"Successfully posted {posted} out of {len(selection)} items"
        )

def main():
    """Main entry point for the application."""
    # Configure logging
    logging.basicConfig(
        filename="asset_scraper.log",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    # Start the application
    root = tk.Tk()
    app = ApplicationGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()