@echo off
echo ================================================================================
echo           SaaS AUTOMATION BUILDER - Stop All Projects
echo ================================================================================
echo.
echo This will stop all Docker containers from generated SaaS projects.
echo.
echo Searching for running containers...
echo.

docker ps --filter "name=taskflow" --filter "name=feedback" --filter "name=python-test" -q > temp_containers.txt

set /p CONTAINERS=<temp_containers.txt
del temp_containers.txt

if "%CONTAINERS%"=="" (
    echo No running SaaS project containers found.
    echo.
    pause
    exit /b
)

echo Found running containers. Stopping them now...
echo.

docker stop %CONTAINERS%

echo.
echo ================================================================================
echo All SaaS project containers have been stopped.
echo ================================================================================
echo.
pause
