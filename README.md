cd BubblePanel-Web/backend
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
# Set these envs or edit start.bat:
set BP_PYTHON=python
set BP_SCRIPT=smoke_test.py
set BP_REPO_ROOT=C:\\Users\\adity\\Downloads\\BubblePanel-main
uvicorn main:app --host 127.0.0.1 --port 8080 --reload