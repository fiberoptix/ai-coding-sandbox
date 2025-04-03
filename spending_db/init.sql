-- This script dynamically creates tables and imports data from a CSV file
-- regardless of the column structure

-- Create a function to create the transactions table based on CSV structure
CREATE OR REPLACE FUNCTION setup_transactions_table() RETURNS void AS $$
DECLARE
    column_names text;
    column_list text;
    create_stmt text;
BEGIN
    -- Create temporary table with a single column to read the header
    CREATE TEMP TABLE csv_headers (header text);
    
    -- Import just the first line (header) from the CSV
    EXECUTE 'COPY csv_headers FROM ''/transactions.csv'' CSV HEADER LIMIT 0';
    
    -- Get column names from the temporary import
    SELECT string_agg(column_name, ', ')
    INTO column_names
    FROM information_schema.columns
    WHERE table_name = 'csv_headers' AND table_schema = 'pg_temp';
    
    -- Drop the temporary table
    DROP TABLE csv_headers;
    
    -- Generate column definition for each column in the CSV
    SELECT string_agg(quote_ident(column_name) || ' TEXT', ', ')
    INTO column_list
    FROM (
        SELECT trim(unnest(string_to_array(column_names, ','))) as column_name
    ) subq;
    
    -- Drop existing tables if they exist
    DROP TABLE IF EXISTS transactions;
    DROP TABLE IF EXISTS temp_transactions;
    
    -- Create temporary table matching CSV structure
    EXECUTE 'CREATE TEMP TABLE temp_transactions (' || column_list || ')';
    
    -- Import data from CSV into temp table
    EXECUTE 'COPY temp_transactions FROM ''/transactions.csv'' CSV HEADER';
    
    -- Create final transactions table with appropriate column types
    -- We'll use TEXT initially for all columns, and can refine data types later
    EXECUTE 'CREATE TABLE transactions (id SERIAL PRIMARY KEY, ' || column_list || ')';
    
    -- Insert data from temp to main table
    EXECUTE 'INSERT INTO transactions (' || column_names || ') SELECT ' || column_names || ' FROM temp_transactions';
    
    -- Drop the temporary table
    DROP TABLE temp_transactions;
    
    RAISE NOTICE 'Transactions table created and populated successfully';
END;
$$ LANGUAGE plpgsql;

-- Execute the function to set up the transactions table
SELECT setup_transactions_table();

-- Create or update analysis views
DO $$
DECLARE
    amount_column text;
    category_column text;
    date_column text;
    column_exists boolean;
BEGIN
    -- Try to find common column names for analysis views
    -- Amount column
    SELECT column_name INTO amount_column
    FROM information_schema.columns
    WHERE table_name = 'transactions'
      AND table_schema = 'public'
      AND lower(column_name) IN ('amount', 'price', 'cost', 'value', 'total', 'payment', 'paid', 'spend', 'spending')
    LIMIT 1;

    -- Category column
    SELECT column_name INTO category_column
    FROM information_schema.columns
    WHERE table_name = 'transactions'
      AND table_schema = 'public'
      AND lower(column_name) IN ('category', 'type', 'expense_type', 'expense_category', 'spending_category', 'transaction_type')
    LIMIT 1;

    -- Date column
    SELECT column_name INTO date_column
    FROM information_schema.columns
    WHERE table_name = 'transactions'
      AND table_schema = 'public'
      AND lower(column_name) IN ('date', 'transaction_date', 'time', 'datetime', 'timestamp')
    LIMIT 1;

    -- Create category totals view if we have both category and amount columns
    IF category_column IS NOT NULL AND amount_column IS NOT NULL THEN
        EXECUTE 'DROP VIEW IF EXISTS category_totals';
        EXECUTE 'CREATE VIEW category_totals AS
                 SELECT ' || quote_ident(category_column) || ' as category, 
                        SUM(CAST(' || quote_ident(amount_column) || ' AS DECIMAL)) as total_amount
                 FROM transactions
                 GROUP BY ' || quote_ident(category_column) || '
                 ORDER BY total_amount DESC';
        
        RAISE NOTICE 'Created category_totals view using % and % columns', category_column, amount_column;
    ELSE
        RAISE NOTICE 'Skipped category_totals view - required columns not found';
    END IF;

    -- Create monthly spending view if we have both date and amount columns
    IF date_column IS NOT NULL AND amount_column IS NOT NULL THEN
        EXECUTE 'DROP VIEW IF EXISTS monthly_spending';
        -- Try to cast the date column to date type
        BEGIN
            EXECUTE 'CREATE VIEW monthly_spending AS
                     SELECT 
                         EXTRACT(YEAR FROM CAST(' || quote_ident(date_column) || ' AS DATE)) AS year,
                         EXTRACT(MONTH FROM CAST(' || quote_ident(date_column) || ' AS DATE)) AS month,
                         SUM(CAST(' || quote_ident(amount_column) || ' AS DECIMAL)) as total_amount
                     FROM transactions
                     GROUP BY year, month
                     ORDER BY year, month';
            
            RAISE NOTICE 'Created monthly_spending view using % and % columns', date_column, amount_column;
        EXCEPTION
            WHEN OTHERS THEN
                RAISE NOTICE 'Could not create monthly_spending view - date casting failed';
        END;
    ELSE
        RAISE NOTICE 'Skipped monthly_spending view - required columns not found';
    END IF;
END $$;

-- Display discovered table structure
\echo 'Database initialization completed!'
\echo 'Table structure:'
\d transactions

-- Display available views
\echo 'Available views:'
\dv

-- Help message for the user
\echo ''
\echo 'Use these commands to analyze your data:'
\echo '- SELECT * FROM transactions LIMIT 10;                 -- View first 10 transactions'
\echo '- \d transactions                                      -- View table structure'
\echo '- SELECT column_name FROM information_schema.columns WHERE table_name = ''transactions'';  -- List all columns'
\echo '- SELECT * FROM category_totals;                       -- View spending by category (if available)'
\echo '- SELECT * FROM monthly_spending;                      -- View monthly spending (if available)' 