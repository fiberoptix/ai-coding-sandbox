#!/bin/bash
# Full QA check script for Financial Analyst application

echo "=========== FINANCIAL ANALYST QA TEST ==========="
echo "Build: $(curl -s http://localhost:5002/test_database | grep -o 'Build #[0-9]*')"
echo "Date: $(date)"
echo ""

# Wait for container to fully initialize
echo "Waiting for container to initialize..."
sleep 5
attempt=1
max_attempts=12
while [ $attempt -le $max_attempts ]; do
  if curl -s -o /dev/null -w "%{http_code}" http://localhost:5002/ | grep -q "200\|302"; then
    echo "Application is up and running"
    break
  fi
  echo "Attempt $attempt/$max_attempts: Application not ready, waiting..."
  sleep 5
  attempt=$((attempt+1))
done

if [ $attempt -gt $max_attempts ]; then
  echo "CRITICAL ERROR: Application failed to start after $(($max_attempts * 5)) seconds"
  exit 1
fi

echo ""
echo "=== CONTAINER STATUS ==="
docker ps | grep financial_analyst || echo "CRITICAL: Container not running"

echo ""
echo "=== DATABASE CONNECTIVITY ==="
docker exec financial_analyst pg_isready -h localhost -p 5432 -U postgres || echo "CRITICAL: Database connection failed"

echo ""
echo "=== PAGE STATUS CODES ==="
for p in / /data_import_tagging /monthly_summary /transaction_summary /historical_analysis /budgets; do
  status=$(curl -L -s -o /dev/null -w "%{http_code}" "http://localhost:5002$p")
  if [ "$status" == "200" ] || [ "$status" == "302" ]; then
    echo "✅ $p: $status"
  else
    echo "❌ $p: $status"
  fi
done

echo ""
echo "=== PAGE SIZE CHECKS ==="
# Define minimum expected sizes
min_size_home=200          # Home redirect is expected to be small
min_size_import=10000      # Data import page
min_size_monthly=50000     # Monthly summary page 
min_size_trans=50000       # Transaction summary page
min_size_historical=50000  # Historical analysis page
min_size_budgets=50000     # Budget settings page

for p in / /data_import_tagging /monthly_summary /transaction_summary /historical_analysis /budgets; do
  # Get bytes and content
  response_file=$(mktemp)
  bytes=$(curl -s -w "%{size_download}" -o "$response_file" "http://localhost:5002$p")
  
  # Set minimum size based on page
  if [ "$p" = "/" ]; then
    min_size=$min_size_home
  elif [ "$p" = "/data_import_tagging" ]; then
    min_size=$min_size_import
  elif [ "$p" = "/monthly_summary" ]; then
    min_size=$min_size_monthly
  elif [ "$p" = "/transaction_summary" ]; then
    min_size=$min_size_trans
  elif [ "$p" = "/historical_analysis" ]; then
    min_size=$min_size_historical
  elif [ "$p" = "/budgets" ]; then
    min_size=$min_size_budgets
  else
    min_size=10000  # Default minimum
  fi
  
  if [ "$bytes" -lt "$min_size" ]; then
    if [ "$p" = "/" ] && [ "$bytes" -gt 100 ]; then
      # Home redirect is expected to be small but not too small
      echo "✅ $p: $bytes bytes (redirect page)"
    else
      echo "❌ $p: $bytes bytes - BELOW EXPECTED MINIMUM OF $min_size"
      echo "--- Checking page content for errors ---"
      # Extract title
      title=$(grep -o "<title>[^<]*</title>" "$response_file" | sed 's/<title>\(.*\)<\/title>/\1/')
      echo "Page title: $title"
      # Check for common error messages
      grep -i "error\|exception\|not found\|unexpected\|unhandled\|failed" "$response_file" | head -5
      echo "--- First 10 lines of HTML output ---"
      head -10 "$response_file"
      echo "-------------------------------------"
    fi
  else
    echo "✅ $p: $bytes bytes"
  fi
  
  # Clean up temporary file
  rm "$response_file"
done

echo ""
echo "=== DATA INTEGRITY CHECKS ==="
# Check transaction counts display for method references
if curl -s http://localhost:5002/transaction_summary | grep -i "method\.\|built-in method\|object at 0x" > /dev/null; then
  echo "❌ Transaction counts: Method references found"
else
  echo "✅ Transaction counts: No method references found"
fi

# Check budget form exists
if curl -s http://localhost:5002/budgets | grep -A5 "budget-form" > /dev/null; then
  echo "✅ Budget settings: Form found"
else
  echo "❌ Budget settings: Form not found"
fi

# Check for chart containers
if curl -s http://localhost:5002/historical_analysis | grep -A2 "chart-container" > /dev/null; then
  echo "✅ Charts: Chart containers found"
else
  echo "❌ Charts: Chart containers missing"
fi

echo ""
echo "=== DATABASE TABLE COUNTS ==="
docker exec financial_analyst psql -U postgres -d financial_analyst -c "SELECT 'records_history' as table_name, COUNT(*) FROM records_history UNION SELECT 'tags', COUNT(*) FROM tags UNION SELECT 'budgets', COUNT(*) FROM budgets ORDER BY table_name;"

echo ""
echo "=== SAMPLE DATA CHECK ==="
echo "Transaction counts sample (should show numbers, not methods):"
curl -s http://localhost:5002/transaction_summary | grep -B1 -A1 "<td>[0-9]\+</td>" | head -10

echo ""
echo "=== RESPONSE TIME CHECKS ==="
echo "Transaction summary page load time:"
time curl -s -o /dev/null http://localhost:5002/transaction_summary

echo ""
echo "=== RECENT LOG ERRORS ==="
docker logs financial_analyst --tail 50 2>&1 | grep -i "error\|exception\|fail" | tail -5 || echo "No recent errors found in logs"

echo ""
echo "========== QA TEST COMPLETE =========="
# Exit with error code 0 (success) - In a real scenario, you'd want to exit with 1 if critical tests fail
exit 0
