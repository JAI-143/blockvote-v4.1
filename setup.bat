@echo off
echo Installing BlockVote v4 dependencies...
pip install flask==3.0.0 flask-cors==4.0.0 web3==6.11.3 requests==2.31.0 numpy Pillow
echo.
echo Optional: Install face recognition (requires cmake + Visual C++ Build Tools):
echo   pip install cmake dlib face_recognition
echo.
echo Setup complete. Run: python backend/app.py
pause
