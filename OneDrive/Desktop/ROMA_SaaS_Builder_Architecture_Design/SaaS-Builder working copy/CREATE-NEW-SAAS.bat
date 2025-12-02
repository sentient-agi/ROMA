@echo off
echo ================================================================================
echo           SaaS AUTOMATION BUILDER - Interactive Setup
echo ================================================================================
echo.
echo This will start an interactive questionnaire to create a new SaaS project.
echo You'll be asked about your product, features, tech stack, and more.
echo.
echo The builder will then generate a complete SaaS application for you!
echo.
pause
echo.
npm run dev -- init
echo.
echo.
echo ================================================================================
echo Questionnaire complete!
echo.
echo To build your project, run BUILD-SAAS.bat and provide the intake form path
echo ================================================================================
pause
