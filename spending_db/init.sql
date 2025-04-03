-- Create transactions table
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    category VARCHAR(50) NOT NULL,
    description VARCHAR(255) NOT NULL,
    amount DECIMAL(10,2) NOT NULL
);

-- Create temporary table for importing CSV
CREATE TEMPORARY TABLE temp_transactions (
    date DATE,
    category VARCHAR(50),
    description VARCHAR(255),
    amount DECIMAL(10,2)
);

-- Copy data from CSV file
COPY temp_transactions(date, category, description, amount)
FROM '/transactions.csv'
DELIMITER ','
CSV HEADER;

-- Insert data from temp table to main table
INSERT INTO transactions(date, category, description, amount)
SELECT date, category, description, amount FROM temp_transactions;

-- Create views for analysis
CREATE VIEW category_totals AS
SELECT category, SUM(amount) as total_amount
FROM transactions
GROUP BY category
ORDER BY total_amount DESC;

CREATE VIEW monthly_spending AS
SELECT 
    EXTRACT(YEAR FROM date) AS year,
    EXTRACT(MONTH FROM date) AS month,
    SUM(amount) as total_amount
FROM transactions
GROUP BY year, month
ORDER BY year, month;

-- Print message when initialization completes
\echo 'Database initialization completed!'
\echo 'The transactions table has been created and populated with data.'
\echo 'Run SQL queries to analyze the spending data.' 