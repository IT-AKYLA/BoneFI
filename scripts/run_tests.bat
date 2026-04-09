@echo off
echo ========================================
echo Running all tests
echo ========================================

echo.
echo [1/3] Testing data-analysis...
cd data-analysis
pytest tests/ -v --tb=short
cd ..

echo.
echo [2/3] Testing data-management...
cd data-management
pytest tests/ -v --tb=short
cd ..

echo.
echo [3/3] Running integration tests...
pytest tests/ -v --tb=short

echo.
echo All tests completed!