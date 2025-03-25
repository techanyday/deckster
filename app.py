from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import openai
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_AUTO_SIZE
from pptx.dml.color import RGBColor
import os
from dotenv import load_dotenv
import tempfile
from werkzeug.utils import secure_filename
import PyPDF2
import json
import re
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')

if not openai.api_key:
    logger.error("No OpenAI API key found")
    raise ValueError("No OpenAI API key found. Please set the OPENAI_API_KEY environment variable.")

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Use system temp directory for files
TEMP_DIR = tempfile.gettempdir()
UPLOAD_FOLDER = os.path.join(TEMP_DIR, "uploads")
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx'}

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Predefined color schemes
COLOR_SCHEMES = {
    'professional': {
        'background': {
            'type': 'solid',
            'color': 'FFFFFF',
            'pattern': None
        },
        'title': '1F497D',
        'text': '000000',
        'accent': '4F81BD'
    },
    'modern': {
        'background': {
            'type': 'gradient',
            'color1': 'F5F5F5',
            'color2': 'E0E0E0',
            'pattern': 'linear'
        },
        'title': '2C3E50',
        'text': '34495E',
        'accent': '3498DB'
    },
    'creative': {
        'background': {
            'type': 'pattern',
            'color1': 'FFFFFF',
            'color2': 'F1C40F',
            'pattern': 'dots'
        },
        'title': 'E74C3C',
        'text': '2C3E50',
        'accent': 'F1C40F'
    },
    'dark': {
        'background': {
            'type': 'solid',
            'color': '2C3E50',
            'pattern': None
        },
        'title': 'FFFFFF',
        'text': 'ECF0F1',
        'accent': '3498DB'
    },
    'nature': {
        'background': {
            'type': 'gradient',
            'color1': 'E8F5E9',
            'color2': 'C8E6C9',
            'pattern': 'radial'
        },
        'title': '2E7D32',
        'text': '1B5E20',
        'accent': '81C784'
    }
}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_file(file):
    """Extract text content from uploaded file."""
    if not file or not hasattr(file, 'filename'):
        return None
        
    if not allowed_file(file.filename):
        raise ValueError(f"Invalid file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}")
        
    filename = secure_filename(file.filename)
    temp_path = os.path.join(UPLOAD_FOLDER, filename)
    
    try:
        file.save(temp_path)
        
        # Extract text based on file type
        ext = filename.rsplit('.', 1)[1].lower()
        content = ""
        
        if ext == 'txt':
            with open(temp_path, 'r', encoding='utf-8') as f:
                content = f.read()
        elif ext == 'pdf':
            with open(temp_path, 'rb') as f:
                pdf = PyPDF2.PdfReader(f)
                for page in pdf.pages:
                    content += page.extract_text() + "\n"
        elif ext == 'docx':
            # Add docx handling if needed
            pass
            
        return content
    except Exception as e:
        logger.error(f"Error extracting text from file: {str(e)}")
        raise
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)

def generate_presentation_content(topic, source_content=None):
    system_prompt = """You are a presentation expert. Create a detailed presentation with 5 slides. 
For each slide, provide:
1. A clear, engaging title (without slide numbers)
2. 3-4 detailed bullet points with actual content (not just topics)
3. Each bullet point should be a complete thought/sentence
4. Include relevant examples, statistics, or real-world applications where appropriate
5. Make the content engaging and presentation-friendly

Format each slide as:
First Slide:
Presentation Title
• Subtitle or tagline

Subsequent Slides:
Title
• Detailed point 1
• Detailed point 2
• Detailed point 3
• Optional point 4

Make sure the content flows naturally from one slide to the next. Do not include slide numbers in the titles or put titles in square brackets."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Create a detailed, engaging presentation about: {topic}"}
    ]
    
    if source_content:
        messages.append({"role": "user", "content": f"Use this additional content as reference: {source_content}"})

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages,
        temperature=0.7
    )
    return response.choices[0].message['content']

def apply_background(slide, background_style):
    fill = slide.background.fill
    if background_style['type'] == 'solid':
        fill.solid()
        fill.fore_color.rgb = RGBColor.from_string(background_style['color'])
    elif background_style['type'] == 'gradient':
        fill.gradient()
        gradient_stops = fill.gradient_stops
        gradient_stops[0].color.rgb = RGBColor.from_string(background_style['color1'])
        gradient_stops[1].color.rgb = RGBColor.from_string(background_style['color2'])
    elif background_style['type'] == 'pattern':
        fill.patterned()
        fill.fore_color.rgb = RGBColor.from_string(background_style['color1'])
        fill.back_color.rgb = RGBColor.from_string(background_style['color2'])
        # Pattern types: https://python-pptx.readthedocs.io/en/latest/api/enum/MsoPatternType.html
        fill.pattern = 2  # Small grid dots

def create_ppt(content, template='modern', custom_styles=None):
    prs = Presentation()
    
    # Set slide width and height (standard 16:9 aspect ratio)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    
    color_scheme = COLOR_SCHEMES[template].copy()
    if custom_styles:
        for key, value in custom_styles.items():
            if key != 'background':
                color_scheme[key] = value
            else:
                color_scheme['background'].update(value)
    
    slides = content.split('\n\n')
    for i, slide_content in enumerate(slides):
        if not slide_content.strip():
            continue
            
        if i == 0:  # Title slide
            slide = prs.slides.add_slide(prs.slide_layouts[0])
            apply_background(slide, color_scheme['background'])
            
            # Create a custom title shape that spans the full width
            left = Inches(0.5)
            top = Inches(1)
            width = prs.slide_width - Inches(1)  # Full width minus margins
            height = Inches(2)  # Reduced height for title
            
            title_box = slide.shapes.add_textbox(left, top, width, height)
            title_frame = title_box.text_frame
            title_frame.word_wrap = False  # Prevent word wrap for title
            
            # Add subtitle shape
            subtitle_top = top + Inches(2.5)  # More space between title and subtitle
            subtitle_height = Inches(1.5)
            subtitle_box = slide.shapes.add_textbox(left, subtitle_top, width, subtitle_height)
            subtitle_frame = subtitle_box.text_frame
            subtitle_frame.word_wrap = True
            
            lines = slide_content.strip().split('\n')
            if lines:
                # Add title text
                title_para = title_frame.paragraphs[0]
                title_para.text = lines[0].replace('First Slide:', '').replace('Slide 1:', '').strip()
                title_para.alignment = PP_ALIGN.CENTER
                title_para.font.size = Pt(44)
                title_para.font.color.rgb = RGBColor.from_string(color_scheme['title'])
                
                # Add subtitle if present
                if len(lines) > 1:
                    subtitle_para = subtitle_frame.paragraphs[0]
                    subtitle_para.text = lines[1].strip('• ').strip()
                    subtitle_para.alignment = PP_ALIGN.CENTER
                    subtitle_para.font.size = Pt(32)
                    subtitle_para.font.color.rgb = RGBColor.from_string(color_scheme['text'])
        else:
            slide = prs.slides.add_slide(prs.slide_layouts[1])
            apply_background(slide, color_scheme['background'])
            
            # Create custom title shape
            left = Inches(0.5)
            top = Inches(0.5)
            width = prs.slide_width - Inches(1)
            height = Inches(1.2)  # Reduced height for content slide titles
            
            title_box = slide.shapes.add_textbox(left, top, width, height)
            title_frame = title_box.text_frame
            title_frame.word_wrap = False  # Prevent word wrap for title
            
            # Create content shape with more precise dimensions
            content_top = top + height + Inches(0.2)  # Small gap after title
            content_height = prs.slide_height - content_top - Inches(0.5)  # Leave margin at bottom
            content_box = slide.shapes.add_textbox(
                left + Inches(0.5),  # Indent content
                content_top,
                width - Inches(1),   # Narrower than title
                content_height
            )
            content_frame = content_box.text_frame
            content_frame.word_wrap = True
            
            lines = slide_content.strip().split('\n')
            if lines:
                # Add title
                title_text = lines[0]
                title_text = re.sub(r'^Slide \d+:', '', title_text)
                title_text = re.sub(r'^\d+[\.:]\s*', '', title_text)
                
                title_para = title_frame.paragraphs[0]
                title_para.text = title_text.strip()
                title_para.alignment = PP_ALIGN.LEFT
                title_para.font.size = Pt(40)  # Slightly smaller for content slides
                title_para.font.color.rgb = RGBColor.from_string(color_scheme['title'])
                
                # Add content with proper spacing
                first_para = True
                for line in lines[1:]:
                    if not line.strip():
                        continue
                    
                    p = content_frame.add_paragraph()
                    p.text = line.strip('• ').strip()
                    p.font.size = Pt(24)  # Start with slightly smaller font
                    p.font.color.rgb = RGBColor.from_string(color_scheme['text'])
                    p.level = 0
                    
                    # Add space after paragraphs, except the last one
                    if not first_para:
                        p.space_before = Pt(12)
                    first_para = False
                
                # Ensure content fits by reducing font size if needed
                min_font_size = Pt(18)
                current_font_size = Pt(24)
                
                while current_font_size > min_font_size:
                    overflow = False
                    for shape in slide.shapes:
                        if shape.top + shape.height > prs.slide_height - Inches(0.2):
                            overflow = True
                            break
                    
                    if not overflow:
                        break
                        
                    current_font_size = Pt(current_font_size.pt - 1)
                    for para in content_frame.paragraphs:
                        para.font.size = current_font_size

    # Save to temporary file with unique name
    temp_file = os.path.join(TEMP_DIR, f"presentation_{hash(str(content))}.pptx")
    try:
        prs.save(temp_file)
        return os.path.basename(temp_file)
    except Exception as e:
        logger.error(f"Error saving presentation: {str(e)}")
        raise

@app.route('/health')
def health_check():
    """Health check endpoint for Render."""
    try:
        # Verify OpenAI API key is set
        if not openai.api_key:
            raise ValueError("OpenAI API key not configured")
            
        # Verify temp directories exist and are writable
        if not os.path.exists(TEMP_DIR) or not os.access(TEMP_DIR, os.W_OK):
            raise ValueError("Temp directory not accessible")
            
        if not os.path.exists(UPLOAD_FOLDER) or not os.access(UPLOAD_FOLDER, os.W_OK):
            raise ValueError("Upload folder not accessible")
            
        return jsonify({
            'status': 'healthy',
            'temp_dir': os.path.exists(TEMP_DIR),
            'upload_dir': os.path.exists(UPLOAD_FOLDER)
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@app.route('/')
def index():
    try:
        return render_template('index.html', color_schemes=COLOR_SCHEMES)
    except Exception as e:
        logger.error(f"Error rendering index: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/generate', methods=['POST'])
def generate():
    try:
        topic = request.form.get('topic', '')
        template = request.form.get('template', 'modern')
        custom_styles = None
        
        # Handle file upload
        source_content = None
        if 'file' in request.files:
            uploaded_file = request.files['file']
            if uploaded_file and uploaded_file.filename:
                try:
                    source_content = extract_text_from_file(uploaded_file)
                except ValueError as e:
                    return jsonify({'error': str(e)}), 400
                except Exception as e:
                    logger.error(f"File upload error: {str(e)}")
                    return jsonify({'error': 'Error processing uploaded file'}), 500
        
        # Handle custom styles
        custom_styles_json = request.form.get('customStyles')
        if custom_styles_json:
            try:
                custom_styles = json.loads(custom_styles_json)
            except json.JSONDecodeError:
                return jsonify({'error': 'Invalid custom styles format'}), 400
        
        if not topic:
            return jsonify({'error': 'Please provide a topic'}), 400
            
        # Generate presentation content
        content = generate_presentation_content(topic, source_content)
        if not content:
            return jsonify({'error': 'Failed to generate presentation content'}), 500
            
        # Create PowerPoint file
        filename = create_ppt(content, template, custom_styles)
        
        return jsonify({
            'message': 'Presentation generated successfully',
            'content': content,
            'filename': filename
        })
        
    except Exception as e:
        logger.error(f"Error generating presentation: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>')
def download(filename):
    try:
        file_path = os.path.join(TEMP_DIR, filename)
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
            
        return send_file(
            file_path,
            as_attachment=True,
            download_name='presentation.pptx',
            mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation'
        )
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        return jsonify({'error': 'File not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
