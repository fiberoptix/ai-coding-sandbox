# Spending Database Project

A PostgreSQL database in a Docker container for analyzing spending transactions.

## Features

- **Dynamic CSV Import**: Automatically adapts to your CSV structure
- **Intelligent View Creation**: Creates analysis views based on detected columns
- **Interactive PostgreSQL CLI**: Run custom queries directly against your data
- **Containerized**: Everything runs in a Docker container for easy setup and cleanup

## Setup & Usage

1. Make sure Docker is running on your system
2. Place your `transactions.csv` file in the `spending_db` directory
3. Run the start script: `./start-db.sh`
4. The script will:
   - Build the Docker image
   - Start the PostgreSQL container
   - Connect to the database with the PostgreSQL CLI

## How It Works

The system:
1. Reads your CSV file header to determine column structure
2. Creates a database table that matches your CSV columns
3. Imports all data from your CSV file
4. Attempts to create helpful analysis views by intelligently detecting:
   - Amount/cost/price columns
   - Category/type columns
   - Date columns

## Example Queries

```sql
-- View first 10 transactions
SELECT * FROM transactions LIMIT 10;

-- View table structure
\d transactions

-- List all columns
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'transactions';

-- View category totals (if available)
SELECT * FROM category_totals;

-- View monthly spending (if available)
SELECT * FROM monthly_spending;
```

## Updating Your Data

When you need to update your transactions:

1. Replace the `transactions.csv` file with your new data
2. Rebuild and restart the container:
   ```bash
   docker stop spending-postgres
   docker rm spending-postgres
   ./start-db.sh
   ```

## Stopping the Container

When you're done, you can stop and remove the container:

```bash
docker stop spending-postgres
docker rm spending-postgres
``` 