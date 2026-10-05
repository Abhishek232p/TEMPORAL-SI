with open(r"C:\Users\abhis\.gemini\antigravity-ide\scratch\temporal-intelligence\packages\core\db\models.py", "r") as f:
    text = f.read()

text = text.replace("Column(JSONB)", "Column(JSON_VARIANT)")

with open(r"C:\Users\abhis\.gemini\antigravity-ide\scratch\temporal-intelligence\packages\core\db\models.py", "w") as f:
    f.write(text)
