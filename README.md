# How to run
## 1. Set up Python virtual environment
cd backend
python3 -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate

## 2. Install deps
cd backend
pip install -r requirements.txt
playwright install chromium

## 3. Start backend
uvicorn main:app --reload --port 8000

## 4. Test backend
http://localhost:8000/carrier/2033842
http://localhost:8000/inspections/2033842

## 5. Open frontend
### Open frontend/index.html in your browser (or use VS Code Live Server extension)