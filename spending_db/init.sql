-- This script dynamically creates tables and imports data from a CSV file
-- regardless of the column structure

-- Start with a basic attempt to detect CSV structure
DO $$
DECLARE
    column_list text := '';
    csv_exists boolean;
BEGIN
    -- Check if the CSV file exists and is readable
    BEGIN
        CREATE TEMP TABLE test_csv (line text);
        COPY test_csv FROM '/transactions.csv' CSV;
        csv_exists := true;
        DROP TABLE test_csv;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'Error accessing CSV file: %', SQLERRM;
        csv_exists := false;
    END;

    IF NOT csv_exists THEN
        RAISE EXCEPTION 'Cannot access transactions.csv file';
    END IF;
END $$;

-- Create tables and import data
DO $$
DECLARE
    sample_line text;
    column_names text;
    column_list text;
    header_line text;
    possible_columns text[];
    column_count integer;
BEGIN
    -- Create a table to read the first few lines
    CREATE TEMP TABLE csv_sample (line text);
    
    -- Import just a few lines to analyze
    EXECUTE 'COPY csv_sample FROM ''/transactions.csv'' CSV';
    
    -- Get the first line (likely the header)
    SELECT line INTO header_line FROM csv_sample LIMIT 1;
    
    -- Count columns by counting commas + 1
    SELECT array_length(string_to_array(header_line, ','), 1) INTO column_count;
    
    -- Generate possible column names
    possible_columns := ARRAY['col1', 'col2', 'col3', 'col4', 'col5', 'col6', 'col7', 'col8', 'col9', 'col10',
                             'col11', 'col12', 'col13', 'col14', 'col15', 'col16', 'col17', 'col18', 'col19', 'col20'];
    
    -- Check if first line looks like a header (has text in it)
    IF header_line ~ '[a-zA-Z]' THEN
        -- Use the header line to generate column names
        SELECT string_agg(quote_ident(trim(column_name)), ', ')
        INTO column_names
        FROM (
            SELECT unnest(string_to_array(header_line, ',')) as column_name
        ) subq;
        
        -- Generate column definitions (all text initially)
        SELECT string_agg(quote_ident(trim(column_name)) || ' TEXT', ', ')
        INTO column_list
        FROM (
            SELECT unnest(string_to_array(header_line, ',')) as column_name
        ) subq;
    ELSE
        -- Use generic column names
        SELECT string_agg(possible_columns[i], ', ')
        INTO column_names
        FROM generate_series(1, column_count) as i;
        
        -- Generate column definitions
        SELECT string_agg(possible_columns[i] || ' TEXT', ', ')
        INTO column_list
        FROM generate_series(1, column_count) as i;
    END IF;
    
    -- Clean up the temp table
    DROP TABLE csv_sample;
    
    -- Make sure we have column definitions
    IF column_list IS NULL OR column_list = '' THEN
        RAISE EXCEPTION 'Could not determine CSV structure';
    END IF;
    
    -- Drop existing tables
    DROP TABLE IF EXISTS transactions;
    DROP TABLE IF EXISTS temp_transactions;
    
    -- Create a temporary table for data import
    EXECUTE 'CREATE TEMP TABLE temp_transactions (' || column_list || ')';
    
    -- Import the CSV data
    BEGIN
        IF header_line ~ '[a-zA-Z]' THEN
            -- Skip the header if it exists
            EXECUTE 'COPY temp_transactions FROM ''/transactions.csv'' CSV HEADER';
        ELSE
            -- No header to skip
            EXECUTE 'COPY temp_transactions FROM ''/transactions.csv'' CSV';
        END IF;
    EXCEPTION
        WHEN OTHERS THEN
            RAISE EXCEPTION 'Error importing CSV: %', SQLERRM;
    END;
    
    -- Create the final table with a primary key
    EXECUTE 'CREATE TABLE transactions (id SERIAL PRIMARY KEY, ' || column_list || ')';
    
    -- Copy data from temp table to final table
    EXECUTE 'INSERT INTO transactions (' || column_names || ') SELECT ' || column_names || ' FROM temp_transactions';
    
    -- Clean up
    DROP TABLE temp_transactions;
    
    RAISE NOTICE 'Successfully created transactions table with columns: %', column_names;
END $$;

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
                        SUM(CASE WHEN ' || quote_ident(amount_column) || ' ~ ''^[0-9,.]+$'' 
                             THEN CAST(' || quote_ident(amount_column) || ' AS DECIMAL) 
                             ELSE 0 END) as total_amount
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
                         EXTRACT(YEAR FROM TO_DATE(' || quote_ident(date_column) || ', ''YYYY-MM-DD'')) AS year,
                         EXTRACT(MONTH FROM TO_DATE(' || quote_ident(date_column) || ', ''YYYY-MM-DD'')) AS month,
                         SUM(CASE WHEN ' || quote_ident(amount_column) || ' ~ ''^[0-9,.]+$'' 
                              THEN CAST(' || quote_ident(amount_column) || ' AS DECIMAL) 
                              ELSE 0 END) as total_amount
                     FROM transactions
                     WHERE ' || quote_ident(date_column) || ' ~ ''^[0-9]{4}-[0-9]{2}-[0-9]{2}''
                     GROUP BY year, month
                     ORDER BY year, month';
            
            RAISE NOTICE 'Created monthly_spending view using % and % columns', date_column, amount_column;
        EXCEPTION
            WHEN OTHERS THEN
                RAISE NOTICE 'Could not create monthly_spending view - date casting failed: %', SQLERRM;
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
\echo '- SELECT * FROM transactions WHERE description ILIKE ''%keyword%'';  -- Search for transactions' 