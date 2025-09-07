import sqlite3
import pandas as pd
import logging
from ingestion_db import ingest_db

# Set up logging
logging.basicConfig(
    filename="logs/get_vendor_summary.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filemode="a",
    force = True
)

def create_vendor_summary(conn):
    """
    Merge different tables to get the overall vendor summary
    """
    vendor_sales_summary = pd.read_sql_query("""
    WITH FreightSummary AS (
        SELECT
            VendorNumber,
            SUM(Freight) AS FreightCost
        FROM InvoicePurchases12312016
        GROUP BY VendorNumber
    ), 

    PurchaseSummary AS (
        SELECT
            p.VendorNumber,
            p.VendorName,
            p.Brand,
            p.Description,
            p.PurchasePrice,
            pp.Price AS ActualPrice,
            pp.Volume,
            SUM(p.Quantity) AS TotalPurchaseQuantity,
            SUM(p.Dollars) AS TotalPurchaseDollars
        FROM PurchasesFINAL12312016 p
        JOIN PurchasePricesDec pp
            ON p.Brand = pp.Brand
        WHERE p.PurchasePrice > 0
        GROUP BY 
            p.VendorNumber,
            p.VendorName,
            p.Brand,
            p.Description,
            p.PurchasePrice,
            pp.Price,
            pp.Volume
    ),

    SalesSummary AS (
        SELECT
            VendorNo,
            Brand,
            SUM(SalesQuantity) AS TotalSalesQuantity,
            SUM(SalesDollars) AS TotalSalesDollars,
            SUM(SalesPrice) AS TotalSalesPrice,
            SUM(ExciseTax) AS TotalExciseTax
        FROM SalesFINAL12312016
        GROUP BY VendorNo, Brand
    )

    SELECT
        ps.VendorNumber,
        ps.VendorName,
        ps.Brand,
        ps.Description,
        ps.PurchasePrice,
        ps.ActualPrice,
        ps.Volume,
        ps.TotalPurchaseQuantity,
        ps.TotalPurchaseDollars,
        ss.TotalSalesQuantity,
        ss.TotalSalesDollars,
        ss.TotalSalesPrice,
        ss.TotalExciseTax,
        fs.FreightCost
    FROM PurchaseSummary ps
    LEFT JOIN SalesSummary ss
        ON ps.VendorNumber = ss.VendorNo
        AND ps.Brand = ss.Brand
    LEFT JOIN FreightSummary fs
        ON ps.VendorNumber = fs.VendorNumber
    ORDER BY ps.TotalPurchaseDollars DESC
    """, conn)

    return vendor_sales_summary


def clean_data(df):
    """
    Clean and enhance vendor data for analysis
    """
    df['Volume'] = df['Volume'].astype(float)

    df.fillna(0, inplace=True)

    df['VendorName'] = df['VendorName'].str.strip()
    df['Description'] = df['Description'].str.strip()

    # Calculated columns
    df['GrossProfit'] = df['TotalSalesDollars'] - df['TotalPurchaseDollars']
    df['ProfitMargin'] = (df['GrossProfit'] / df['TotalSalesDollars']) * 100
    df['StockTurnover'] = df['TotalSalesQuantity'] / df['TotalPurchaseQuantity']
    df['SalesToPurchaseRatio'] = df['TotalSalesDollars'] / df['TotalPurchaseDollars']

    total_sales = df['TotalSalesDollars'].sum()
    df['SalesContributionPercent'] = (df['TotalSalesDollars'] / total_sales) * 100

    # Ranking
    rank_sales = df['TotalSalesDollars'].rank(method='dense', ascending=False)
    rank_profit = df['GrossProfit'].rank(method='dense', ascending=False)
    rank_margin = df['ProfitMargin'].rank(method='dense', ascending=False)
    rank_stock = df['StockTurnover'].rank(method='dense', ascending=False)

    overall_score = rank_sales + rank_profit + rank_margin + rank_stock
    df['VendorRanking'] = overall_score.rank(method='dense', ascending=True)

    return df


if __name__ == '__main__':
    # Create DB connection
    conn = sqlite3.connect('inventory.db')

    logging.info('Creating Vendor summary table...')
    summary_df = create_vendor_summary(conn)
    logging.info("\n" + str(summary_df.head()))

    logging.info('Cleaning Data...')
    clean_df = clean_data(summary_df)
    logging.info("\n" + str(clean_df.head()))

    logging.info('Ingesting data...')
    ingest_db(clean_df, 'vendor_sales_summary', conn)
    logging.info('Completed')


    