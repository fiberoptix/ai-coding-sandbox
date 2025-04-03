# Spending Database Project

A PostgreSQL database in a Docker container for analyzing spending transactions.

## Setup & Usage

1. Make sure Docker is running on your system
2. Run the start script: `./start-db.sh`
3. The script will:
   - Build the Docker image
   - Start the PostgreSQL container
   - Connect to the database with the PostgreSQL CLI

## Database Structure

- **Table**: `transactions`
  - `id`: Serial Primary Key
  - `date`: Date of transaction
  - `category`: Category of spending
  - `description`: Description of transaction
  - `amount`: Amount spent

- **Views**:
  - `category_totals`: Sum of spending by category
  - `monthly_spending`: Sum of spending by month

## Example Queries

```sql
-- View all transactions
SELECT * FROM transactions;

-- View category totals
SELECT * FROM category_totals;

-- View monthly spending
SELECT * FROM monthly_spending;

-- Find highest spending transactions
SELECT * FROM transactions ORDER BY amount DESC LIMIT 5;

-- Find transactions in a specific category
SELECT * FROM transactions WHERE category = 'Groceries';
```

## Stopping the Container

When you're done, you can stop and remove the container:

```bash
docker stop spending-postgres
docker rm spending-postgres
``` 