# Nova workspace (Flask)
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key   # optional; Windows: set ANTHROPIC_API_KEY=your_key
python app.py   # open http://127.0.0.1:5000
