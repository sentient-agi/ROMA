@echo off
echo ================================================================================
echo           SaaS AUTOMATION BUILDER - Build Project
echo ================================================================================
echo.
echo This will build a SaaS project from an intake form.
echo.
set /p FORM_PATH="Enter the path to your intake form (e.g., intake-form.json): "
echo.
echo Building project from: %FORM_PATH%
echo.
npm run dev -- build %FORM_PATH%
echo.
echo.
echo ================================================================================
echo Build complete! Check the output folder for your generated project.
echo ================================================================================
pause
