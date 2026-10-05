import os

migration_dir = r"C:\Users\abhis\.gemini\antigravity-ide\scratch\temporal-intelligence\database\migrations\versions"
for filename in os.listdir(migration_dir):
    if filename.endswith(".py"):
        filepath = os.path.join(migration_dir, filename)
        with open(filepath, "r") as f:
            content = f.read()
        
        content = content.replace("astext_type=Text()", "astext_type=sa.Text()")
        
        with open(filepath, "w") as f:
            f.write(content)
