QA Testing Checklist for Financial Analyst Application

## Main Navigation Pages:
1. Home (/): `curl -L -s -o /dev/null -w "%{http_code}" http://localhost:5002/`
2. Data Import and Tagging (/data_import_tagging): `curl -L -s -o /dev/null -w "%{http_code}" http://localhost:5002/data_import_tagging`
3. Monthly Summary (/monthly_summary): `curl -L -s -o /dev/null -w "%{http_code}" http://localhost:5002/monthly_summary`
4. Transaction Summary (/transaction_summary): `curl -L -s -o /dev/null -w "%{http_code}" http://localhost:5002/transaction_summary`
5. Historical Analysis (/historical_analysis): `curl -L -s -o /dev/null -w "%{http_code}" http://localhost:5002/historical_analysis`
6. Budget Settings (/budgets): `curl -L -s -o /dev/null -w "%{http_code}" http://localhost:5002/budgets`

## Legacy/Redirect Pages:
7. Tag Summary (/tag_summary): `curl -L -s -o /dev/null -w "%{http_code}" http://localhost:5002/tag_summary`

## Utility/API Pages:
8. Test Database (/test_database): `curl -L -s -o /dev/null -w "%{http_code}" http://localhost:5002/test_database`
9. Row Count (/row_count): `curl -L -s -o /dev/null -w "%{http_code}" http://localhost:5002/row_count`
10. Check Duplicates (/check_duplicates): `curl -L -s -o /dev/null -w "%{http_code}" http://localhost:5002/check_duplicates`
11. Most Common (/most_common): `curl -L -s -o /dev/null -w "%{http_code}" http://localhost:5002/most_common`
12. Auto Tag (/auto_tag): `curl -L -s -o /dev/null -w "%{http_code}" http://localhost:5002/auto_tag`
13. Export Tags (/export_tags): `curl -L -s -o /dev/null -w "%{http_code}" http://localhost:5002/export_tags`
14. Export History (/export_history): `curl -L -s -o /dev/null -w "%{http_code}" http://localhost:5002/export_history`

## Error Checking Commands:
- Check for errors on main page: `curl -L -s http://localhost:5002/ | grep -i "error"`
- Check for errors on all main pages: `for p in / /data_import_tagging /monthly_summary /transaction_summary /historical_analysis /budgets; do echo "Checking $p"; curl -L -s "http://localhost:5002$p" | grep -i "error" || echo "No errors found"; echo ""; done`

## Page Size Validation:
- Check byte size of each page: `for p in / /data_import_tagging /monthly_summary /transaction_summary /historical_analysis /budgets; do bytes=$(curl -s -w "%{size_download}" -o /dev/null "http://localhost:5002$p"); echo "[$p: Bytes returned> $bytes]"; done`
- Expected minimum sizes (except home redirect):
  - Home (/): >200 bytes (redirect is small)
  - Data Import (/data_import_tagging): >10000 bytes
  - Monthly Summary (/monthly_summary): >50000 bytes 
  - Transaction Summary (/transaction_summary): >50000 bytes
  - Historical Analysis (/historical_analysis): >50000 bytes
  - Budget Settings (/budgets): >50000 bytes
- If any page is below the expected size, it may indicate missing content or errors: `if [ "$bytes" -lt 10000 ]; then curl -s "http://localhost:5002$p" | grep -i "error\|exception\|not found"; fi`

## Container Health Checks:
- Check if container is running: `docker ps | grep financial_analyst || echo "Container not running"`
- Check container logs for errors: `docker logs financial_analyst 2>&1 | grep -i "error\|exception\|fail" | tail -20`
- Check container resource usage: `docker stats financial_analyst --no-stream`
- Verify build number is correctly set: `curl -s http://localhost:5002/test_database | grep -o "Build #[0-9]*"`

## Database Accessibility Checks:
- Test PostgreSQL connection: `docker exec financial_analyst pg_isready -h localhost -p 5432 -U postgres || echo "Database connection failed"`
- Check database tables exist: `docker exec financial_analyst psql -U postgres -d financial_analyst -c "\dt" | grep -E "records_history|records_imported|tags|budgets" || echo "Missing tables"`
- Check row counts in critical tables: `docker exec financial_analyst psql -U postgres -d financial_analyst -c "SELECT 'records_history' as table_name, COUNT(*) FROM records_history UNION SELECT 'tags', COUNT(*) FROM tags UNION SELECT 'budgets', COUNT(*) FROM budgets;"`

## Data Integrity Checks:
- Check transaction counts display correctly: `curl -s http://localhost:5002/transaction_summary | grep -B1 -A1 "<td>[0-9]\\+</td>" | head -10`
- Verify budget settings page has form elements: `curl -s http://localhost:5002/budgets | grep -A5 "budget-form" || echo "Budget form not found"`
- Check historical data visualization loads: `curl -s http://localhost:5002/historical_analysis | grep -A2 "chart-container" || echo "Chart container not found"`
- Check for display of method references in web UI: `curl -s http://localhost:5002/transaction_summary | grep -i "method.\\|built-in method\\|object at 0x" && echo "ERROR: Method references in UI" || echo "No method references found"`

## Response Time Checks:
- Measure load time for key pages: `time curl -s -o /dev/null http://localhost:5002/historical_analysis`
- Check transaction summary page load time: `time curl -s -o /dev/null http://localhost:5002/transaction_summary`

## Automated Full Check Script:
```bash
#!/bin/bash
# Full QA check script for Financial Analyst application

echo "=========== FINANCIAL ANALYST QA TEST ==========="
echo "Build: $(curl -s http://localhost:5002/test_database | grep -o 'Build #[0-9]*')"
echo "Date: $(date)"
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
echo "=== DATA INTEGRITY CHECKS ==="
# Check transaction counts display for method references
if curl -s http://localhost:5002/transaction_summary | grep -i "method.\\|built-in method\\|object at 0x" > /dev/null; then
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

echo ""
echo "=== DATABASE TABLE COUNTS ==="
docker exec financial_analyst psql -U postgres -d financial_analyst -c "SELECT 'records_history' as table_name, COUNT(*) FROM records_history UNION SELECT 'tags', COUNT(*) FROM tags UNION SELECT 'budgets', COUNT(*) FROM budgets;"

echo ""
echo "=== RECENT LOG ERRORS ==="
docker logs financial_analyst --tail 50 2>&1 | grep -i "error\|exception\|fail" | tail -5

echo ""
echo "========== QA TEST COMPLETE =========="
```

## Periodic Automated Testing:
To set up a cron job for periodic testing (every 6 hours):
```bash
# Add this to crontab -e
0 */6 * * * cd /path/to/financial_analyst && ./run-docker.sh restart && sleep 30 && /path/to/qa_test.sh > /path/to/qa_results.log 2>&1
```
