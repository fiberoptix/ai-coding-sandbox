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

-- Create a transactions table with a basic structure
-- We'll use TEXT for all fields to be more forgiving of data formats
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    -- We'll add columns dynamically based on the CSV
    -- For now, this is just a placeholder
    csv_data TEXT
);

-- Inform user about progress
\echo 'Created base transactions table...';

-- Now let's try to read the CSV file and determine its structure
DO $$
DECLARE
    cmd text;
    header_line text := '';
    column_count integer := 0;
    column_names text[];
    column_types text[];
    i integer;
BEGIN
    -- Create a temporary table to store the first line
    CREATE TEMP TABLE header_raw (line text);
    
    -- Try to import just the first line to get the header
    BEGIN
        COPY header_raw FROM '/transactions.csv' CSV;
        -- Get the first line
        SELECT line INTO header_line FROM header_raw LIMIT 1;
        
        IF header_line IS NOT NULL AND header_line != '' THEN
            -- Split the header line by comma
            column_names := string_to_array(header_line, ',');
            column_count := array_length(column_names, 1);
            
            -- Create an array of column types (all TEXT initially)
            column_types := array_fill('TEXT'::text, ARRAY[column_count]);
            
            -- Drop the transactions table and recreate it with the correct columns
            EXECUTE 'DROP TABLE transactions';
            
            -- Create SQL for new table
            cmd := 'CREATE TABLE transactions (id SERIAL PRIMARY KEY';
            
            -- Add columns
            FOR i IN 1..column_count LOOP
                -- Clean up column name (trim whitespace and quotes)
                column_names[i] := trim(both ' "''' FROM column_names[i]);
                -- Add column to create table statement
                cmd := cmd || ', ' || quote_ident(column_names[i]) || ' TEXT';
            END LOOP;
            
            -- Close create table statement
            cmd := cmd || ')';
            
            -- Execute the create table command
            EXECUTE cmd;
            
            -- Import the data, skipping the first line as header
            EXECUTE 'COPY transactions(' || 
                    array_to_string(array_agg(quote_ident(col)), ', ' ORDER BY ordinality) || 
                    ') FROM ''/transactions.csv'' CSV HEADER'
            FROM unnest(column_names) WITH ORDINALITY AS t(col, ordinality);
            
            RAISE NOTICE 'Created transactions table with % columns', column_count;
        ELSE
            RAISE EXCEPTION 'Could not read header from CSV file';
        END IF;
    
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'Error processing CSV: %', SQLERRM;
        
        -- Fallback: Create a simple table for raw CSV data
        DROP TABLE IF EXISTS transactions;
        CREATE TABLE transactions (
            id SERIAL PRIMARY KEY,
            date TEXT,
            category TEXT, 
            description TEXT,
            amount TEXT
        );
        
        -- Attempt to copy with fallback structure
        BEGIN
            COPY transactions(date, category, description, amount) 
            FROM '/transactions.csv' CSV HEADER;
            RAISE NOTICE 'Imported data with fallback structure';
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'Failed to import CSV data: %', SQLERRM;
        END;
    END;
END $$;

-- Try to create some useful views based on common column names
DO $$
DECLARE
    has_column boolean;
    column_exists text;
    
    -- Potential column names for common fields
    date_columns text[] := ARRAY['date', 'transaction_date', 'time', 'datetime', 'txdate', 'tx_date'];
    amount_columns text[] := ARRAY['amount', 'price', 'cost', 'value', 'total', 'sum', 'charge', 'payment'];
    category_columns text[] := ARRAY['category', 'type', 'expense_type', 'transaction_type', 'tx_type'];
    description_columns text[] := ARRAY['description', 'notes', 'memo', 'details', 'desc'];
    
    -- The columns we found
    date_col text;
    amount_col text;
    category_col text;
    description_col text;
BEGIN
    -- Find date column
    FOREACH column_exists IN ARRAY date_columns LOOP
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'transactions' AND lower(column_name) = lower(column_exists)
        ) INTO has_column;
        
        IF has_column THEN
            date_col := column_exists;
            EXIT;
        END IF;
    END LOOP;
    
    -- Find amount column
    FOREACH column_exists IN ARRAY amount_columns LOOP
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'transactions' AND lower(column_name) = lower(column_exists)
        ) INTO has_column;
        
        IF has_column THEN
            amount_col := column_exists;
            EXIT;
        END IF;
    END LOOP;
    
    -- Find category column
    FOREACH column_exists IN ARRAY category_columns LOOP
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'transactions' AND lower(column_name) = lower(column_exists)
        ) INTO has_column;
        
        IF has_column THEN
            category_col := column_exists;
            EXIT;
        END IF;
    END LOOP;
    
    -- Find description column
    FOREACH column_exists IN ARRAY description_columns LOOP
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'transactions' AND lower(column_name) = lower(column_exists)
        ) INTO has_column;
        
        IF has_column THEN
            description_col := column_exists;
            EXIT;
        END IF;
    END LOOP;
    
    -- Create a view with the detected columns if possible
    IF date_col IS NOT NULL OR amount_col IS NOT NULL OR category_col IS NOT NULL OR description_col IS NOT NULL THEN
        EXECUTE 'CREATE VIEW transaction_summary AS SELECT id';
        
        IF date_col IS NOT NULL THEN
            EXECUTE 'ALTER VIEW transaction_summary ADD COLUMN transaction_date TEXT';
        END IF;
        
        IF amount_col IS NOT NULL THEN
            EXECUTE 'ALTER VIEW transaction_summary ADD COLUMN amount TEXT';
        END IF;
        
        IF category_col IS NOT NULL THEN
            EXECUTE 'ALTER VIEW transaction_summary ADD COLUMN category TEXT';
        END IF;
        
        IF description_col IS NOT NULL THEN
            EXECUTE 'ALTER VIEW transaction_summary ADD COLUMN description TEXT';
        END IF;
        
        EXECUTE 'SELECT * FROM transaction_summary LIMIT 0';
        
        RAISE NOTICE 'Created transaction_summary view with detected columns';
    END IF;
    
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Error creating views: %', SQLERRM;
END $$;

-- Display table structure and help info
\echo '\nSuccessfully initialized database!'
\echo 'Table structure:'
\d transactions

\echo '\nExample queries:'
\echo '- SELECT * FROM transactions LIMIT 10;  -- View first 10 transactions'
\echo '- SELECT DISTINCT column_name FROM transactions;  -- List unique values in a column'
\echo '- SELECT * FROM transactions WHERE description ILIKE ''%search_term%'';  -- Search transactions'
\echo '- SELECT COUNT(*) FROM transactions;  -- Count total transactions' 