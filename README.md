# PowerPoint Generator Web App

A simple web application that generates PowerPoint presentations using GPT-3.5 Turbo.

## Setup

1. Create a `.env` file in the project root and add your OpenAI API key:
```
OPENAI_API_KEY=your_api_key_here
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

4. Open your browser and navigate to `http://localhost:5000`

## Usage

1. Enter your desired presentation topic in the input field
2. Click "Generate Presentation"
3. Wait for the content to be generated
4. Download the PowerPoint file when ready

## Features

- Modern, responsive UI using Tailwind CSS
- Generates 5 slides with titles and bullet points
- Uses GPT-3.5 Turbo for content generation
- Creates downloadable PowerPoint files
