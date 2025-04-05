from flask import Flask, send_from_directory
import os

app = Flask(__name__)

# Create templates directory if it doesn't exist
os.makedirs('templates', exist_ok=True)

# Create a simple HTML file
with open('templates/index.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>Flask Test</title>
</head>
<body>
    <h1>Hello from Flask!</h1>
    <p>If you can see this, the server is working correctly.</p>
</body>
</html>
''')

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
