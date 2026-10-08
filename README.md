SheShield

Real-time AI safety monitoring that helps people respond faster, with a human always making the final call.

SheShield watches live camera video, tracks people, scores how risky a situation looks, and alerts a human operator. Alerts are only sent after a person confirms them, so the system supports human judgment and does not replace it.

Live demo: https://sheshield-rho.vercel.app

Final year project, BS Information Technology, Government College University Faisalabad (GCUF), 2026.

Show Image

<!-- [CHECK: add a real screenshot at docs/dashboard.png, or delete this line] -->
What it does
Tracks people in live video using YOLOv8 for detection and ByteTrack to keep each person's identity across frames.
Combines several signals into one threat score. Each signal has its own meter, and the scores are smoothed over time (exponential moving average) so one noisy frame does not trigger an alarm.
Shows everything on a live dashboard. The React dashboard streams live camera tiles (MJPEG) with a threat meter for each signal.
Sends alerts through a human-confirm gate. SMS (Twilio) and email alerts go out only after an operator confirms the event.
Records evidence with privacy in mind. Evidence recording is designed to keep stored footage to a minimum.
How it works
Camera -> YOLOv8 detection -> ByteTrack tracking -> signal analysis
       -> threat fusion (EMA smoothing) -> dashboard
       -> operator confirms -> SMS / email alert
Tech stack
Part	Tools
Detection and tracking	YOLOv8, ByteTrack
Backend	Python, FastAPI, SQLite (default)
Dashboard	React, MJPEG streaming
Alerts	Twilio (SMS), email
Other libraries used in the project	MediaPipe, DeepFace
Repository layout
sheshield-guard/ : [CHECK: one line on what this folder contains]
[CHECK: add the backend folder here, or remove this line if it is in a different repository]
Getting started

Tested on Windows (PowerShell). [CHECK: confirm every command below against your project before publishing.]

powershell
git clone https://github.com/Noorulhuda-12/sheshield.git
cd sheshield

# Backend
pip install -r requirements.txt
uvicorn main:app --reload

# Dashboard
cd sheshield-guard
npm install
npm run dev

Create a .env file for your alert settings (Twilio account details, email settings). Never commit this file.

Status and limitations

Be clear about what this project is and is not:

This is a research and engineering prototype. It has not been tested in a real deployment.
Performance numbers are not published yet. Frame rate, detection accuracy and hardware cost are still being measured on a fixed test setup. Results will be added here once they are verified.
A human must confirm every alert. The system should never be used to take action against a person without human review.
Camera footage involves privacy. Anyone deploying this must follow local law and get proper consent.
Author

Noor ul Huda BS Information Technology, GCUF | Interests: computer vision and efficient AI nulhuda000@gmail.com | LinkedIn | GitHub
