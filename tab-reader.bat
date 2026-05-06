@echo off REM Double-click to launch the Tab Reader app. REM First run: installs dependencies into the user's Python.
 
where python >nul 2>nul if errorlevel 1 (     echo Python is not on PATH. Install Python 3 from python.org and tick "Add to PATH".     pause     exit /b 1 )
 
python -c "import fitz, PIL, pygame" 2>nul if errorlevel 1 (     echo Installing dependencies...     python -m pip install --user -r "%~dp0requirements.txt" )
 
python "%~dp0tab_reader.py"