@echo off
echo Setting up 0rca Swarm Dojo - Smart Contracts...
echo.

REM Create virtual environment
echo Creating virtual environment...
python -m venv venv

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing Python dependencies...
pip install -r requirements.txt

echo.
echo Setup complete!
echo.
echo To activate the virtual environment, run:
echo   venv\Scripts\activate.bat
echo.
echo To build contracts, run:
echo   puyapy
echo.
echo To run tests, run:
echo   pytest
echo.
pause
